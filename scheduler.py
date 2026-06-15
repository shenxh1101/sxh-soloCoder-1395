from datetime import datetime, timedelta, date
from models import Store, Employee, Schedule, EmployeeAvailability, ScheduleChangeLog
import random
from collections import defaultdict

class Scheduler:
    def __init__(self, db_session):
        self.db = db_session
        self.MAX_DAILY_HOURS = 10
        self.MIN_SHIFT_HOURS = 4
        self.MAX_SHIFT_HOURS = 9
        self.TARGET_WEEKLY_HOURS = 40
        self.STANDARD_WORKDAYS = 5

    def _parse_date(self, date_str):
        if isinstance(date_str, date):
            return date_str
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            return date_str

    def _parse_time(self, time_str):
        return datetime.strptime(time_str, '%H:%M')

    def _time_diff_hours(self, t1, t2):
        return round((t2 - t1).total_seconds() / 3600, 2)

    def validate_basic(self, employee_id, store_id, start_time, end_time):
        errors = []
        try:
            s = self._parse_time(start_time)
            e = self._parse_time(end_time)
            if s >= e:
                errors.append({
                    'type': 'invalid_time_range',
                    'message': f'开始时间 ({start_time}) 必须早于结束时间 ({end_time})'
                })
            duration = self._time_diff_hours(s, e)
            if duration < self.MIN_SHIFT_HOURS:
                errors.append({
                    'type': 'shift_too_short',
                    'message': f'班次时长不足 {duration} 小时，最少需要 {self.MIN_SHIFT_HOURS} 小时'
                })
            if duration > self.MAX_SHIFT_HOURS:
                errors.append({
                    'type': 'shift_too_long',
                    'message': f'班次时长 {duration} 小时过长，最多 {self.MAX_SHIFT_HOURS} 小时'
                })
        except Exception as ex:
            errors.append({
                'type': 'invalid_time_format',
                'message': f'时间格式错误: {str(ex)}'
            })
        return errors

    def check_store_availability(self, employee_id, store_id):
        errors = []
        employee = Employee.query.get(employee_id)
        store = Store.query.get(store_id)
        if not employee or not store:
            errors.append({'type': 'invalid_data', 'message': '员工或门店不存在'})
            return errors
        preferred_stores = [int(s) for s in employee.preferred_stores.split(',')] if employee.preferred_stores else []
        if store.id not in preferred_stores:
            errors.append({
                'type': 'store_not_allowed',
                'message': f'{employee.name} 不能在 {store.name} 上班（可工作门店：{", ".join([Store.query.get(s).name for s in preferred_stores if Store.query.get(s)])}）'
            })
        return errors

    def check_conflict(self, employee_id, store_id, date_str, start_time, end_time, exclude_schedule_id=None, check_staff_sufficiency=False, original_store_id=None):
        conflicts = []

        basic_errors = self.validate_basic(employee_id, store_id, start_time, end_time)
        conflicts.extend(basic_errors)

        store_errors = self.check_store_availability(employee_id, store_id)
        conflicts.extend(store_errors)

        date_obj = self._parse_date(date_str)
        employee = Employee.query.get(employee_id)
        store = Store.query.get(store_id)

        if not employee or not store:
            return {'has_conflict': True, 'conflicts': conflicts}

        day_of_week = date_obj.weekday()
        avail = employee.get_availability(day_of_week)

        if not avail or not avail.is_available:
            conflicts.append({
                'type': 'employee_unavailable',
                'message': f'{employee.name} 在 {["周一","周二","周三","周四","周五","周六","周日"][day_of_week]} 不上班'
            })
        else:
            shift_start = self._parse_time(start_time)
            shift_end = self._parse_time(end_time)
            avail_start = self._parse_time(avail.start_time)
            avail_end = self._parse_time(avail.end_time)

            if shift_start < avail_start or shift_end > avail_end:
                conflicts.append({
                    'type': 'time_out_of_range',
                    'message': f'排班时间超出员工可用时段（可用：{avail.start_time}-{avail.end_time}）'
                })

        if check_staff_sufficiency:
            store_scheds = Schedule.query.filter_by(store_id=store_id, date=date_obj)
            if exclude_schedule_id:
                store_scheds = store_scheds.filter(Schedule.id != exclude_schedule_id)
            store_scheds_list = store_scheds.all()
            
            new_sched_obj = Schedule(
                employee_id=employee_id,
                store_id=store_id,
                date=date_obj,
                start_time=start_time,
                end_time=end_time
            )
            new_scheds = store_scheds_list + [new_sched_obj]
            
            new_slots = self._get_time_slots(store, new_scheds)
            new_insufficient = [s for s in new_slots if not s['meets_minimum']]
            
            old_slots = self._get_time_slots(store, store_scheds_list)
            old_insufficient = set(s['time'] for s in old_slots if not s['meets_minimum'])
            
            new_bad = [s for s in new_insufficient if s['time'] not in old_insufficient]
            
            if exclude_schedule_id and new_bad:
                conflicts.append({
                    'type': 'store_will_be_short',
                    'message': f'调整后，{store.name} 在 {", ".join([s["time"] for s in new_bad])} 将低于最低 {store.min_staff} 人要求'
                })
            
            daily_scheds = Schedule.query.filter_by(employee_id=employee_id, date=date_obj)
            if exclude_schedule_id:
                daily_scheds = daily_scheds.filter(Schedule.id != exclude_schedule_id)
            daily_hours = sum(self._time_diff_hours(self._parse_time(s.start_time), self._parse_time(s.end_time)) for s in daily_scheds.all())
            new_duration = self._time_diff_hours(shift_start, shift_end)
            if daily_hours + new_duration > self.MAX_DAILY_HOURS:
                conflicts.append({
                    'type': 'daily_hours_exceeded',
                    'message': f'{employee.name} 当日总工时将达到 {round(daily_hours + new_duration, 1)} 小时，超过单日上限 {self.MAX_DAILY_HOURS} 小时'
                })

        existing_query = Schedule.query.filter_by(employee_id=employee_id, date=date_obj)
        if exclude_schedule_id:
            existing_query = existing_query.filter(Schedule.id != exclude_schedule_id)

        new_start = self._parse_time(start_time)
        new_end = self._parse_time(end_time)

        for existing in existing_query.all():
            exist_start = self._parse_time(existing.start_time)
            exist_end = self._parse_time(existing.end_time)
            if new_start < exist_end and new_end > exist_start:
                conflicts.append({
                    'type': 'time_overlap',
                    'message': f'与 {existing.store.name} {existing.start_time}-{existing.end_time} 重叠'
                })

        store_open = self._parse_time(store.open_time)
        store_close = self._parse_time(store.close_time)
        if new_start < store_open or new_end > store_close:
            conflicts.append({
                'type': 'outside_business_hours',
                'message': f'超出门店营业时间（{store.open_time}-{store.close_time}）'
            })

        if check_staff_sufficiency and original_store_id and original_store_id != store_id:
            orig_store = Store.query.get(original_store_id)
            if orig_store:
                orig_scheds = Schedule.query.filter_by(store_id=original_store_id, date=date_obj).filter(Schedule.id != exclude_schedule_id).all()
                orig_slots = self._get_time_slots(orig_store, orig_scheds)
                insufficient = [s for s in orig_slots if not s['meets_minimum']]
                if insufficient:
                    conflicts.append({
                        'type': 'orig_store_will_be_short',
                        'message': f'移出后，{orig_store.name} 在 {", ".join([s["time"] for s in insufficient])} 将低于最低人数要求'
                    })

        return {
            'has_conflict': len([c for c in conflicts if not c.get('warning')]) > 0,
            'conflicts': conflicts
        }

    def check_delete_impact(self, schedule_id):
        schedule = Schedule.query.get(schedule_id)
        if not schedule:
            return {'has_conflict': True, 'conflicts': [{'type': 'not_found', 'message': '排班不存在'}]}

        remaining = Schedule.query.filter_by(store_id=schedule.store_id, date=schedule.date).filter(Schedule.id != schedule_id).all()
        store = schedule.store
        slots = self._get_time_slots(store, remaining)
        insufficient = [s for s in slots if not s['meets_minimum']]

        if insufficient:
            return {
                'has_conflict': True,
                'conflicts': [{
                    'type': 'store_will_be_short',
                    'message': f'删除后，{store.name} 在 {", ".join([s["time"] for s in insufficient])} 将低于最低 {store.min_staff} 人要求'
                }]
            }
        return {'has_conflict': False, 'conflicts': []}

    def generate_schedule(self, start_date, end_date, store_id=None):
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

        delete_query = Schedule.query.filter(Schedule.date >= start_date, Schedule.date <= end_date)
        if store_id:
            delete_query = delete_query.filter_by(store_id=store_id)
        delete_query.delete()
        self.db.session.commit()

        stores = Store.query.all()
        if store_id:
            stores = [s for s in stores if s.id == store_id]
        employees = Employee.query.all()

        emp_weekly_stats = defaultdict(lambda: {'hours': 0, 'days': 0, 'shifts_per_store': defaultdict(int)})

        date_range = []
        d = start_date
        while d <= end_date:
            date_range.append((d, d.weekday()))
            d += timedelta(days=1)

        all_conflicts = []
        generated = 0

        for current_date, day_of_week in date_range:
            daily_assigned = set()

            for store in stores:
                result = self._generate_store_day_schedule(
                    store, employees, current_date, day_of_week,
                    daily_assigned, emp_weekly_stats, start_date, end_date
                )
                for sched in result['schedules']:
                    self.db.session.add(sched)
                    generated += 1
                    daily_assigned.add(sched.employee_id)
                    duration = self._time_diff_hours(self._parse_time(sched.start_time), self._parse_time(sched.end_time))
                    emp_weekly_stats[sched.employee_id]['hours'] += duration
                    emp_weekly_stats[sched.employee_id]['days'] += 1
                    emp_weekly_stats[sched.employee_id]['shifts_per_store'][sched.store_id] += 1

                all_conflicts.extend(result['conflicts'])

        self.db.session.commit()

        summary_conflicts = self._summarize_conflicts(all_conflicts)
        
        emp_stats_list = []
        for emp_id, stats in emp_weekly_stats.items():
            emp = Employee.query.get(emp_id)
            emp_stats_list.append({
                'employee_id': emp_id,
                'employee_name': emp.name if emp else f'员工{emp_id}',
                'total_hours': round(stats['hours'], 1),
                'shift_count': stats['days'],
                'per_store': dict(stats['shifts_per_store'])
            })
        emp_stats_list.sort(key=lambda x: x['total_hours'], reverse=True)
        
        return {
            'generated': generated,
            'conflicts': all_conflicts,
            'summary': summary_conflicts,
            'emp_stats': emp_stats_list
        }

    def _generate_store_day_schedule(self, store, employees, date_obj, day_of_week, daily_assigned, emp_weekly_stats, week_start, week_end):
        schedules = []
        conflicts = []

        open_t = self._parse_time(store.open_time)
        close_t = self._parse_time(store.close_time)
        business_hours = self._time_diff_hours(open_t, close_t)

        shift_defs = self._build_shifts(open_t, close_t)

        for shift_start, shift_end in shift_defs:
            shift_start_str = shift_start.strftime('%H:%M')
            shift_end_str = shift_end.strftime('%H:%M')
            duration = self._time_diff_hours(shift_start, shift_end)

            candidates = []
            for emp in employees:
                if emp.id in daily_assigned:
                    continue

                avail = emp.get_availability(day_of_week)
                if not avail or not avail.is_available:
                    continue

                avail_start = self._parse_time(avail.start_time)
                avail_end = self._parse_time(avail.end_time)
                if shift_start < avail_start or shift_end > avail_end:
                    continue

                preferred_stores = [int(s) for s in emp.preferred_stores.split(',')] if emp.preferred_stores else []
                if store.id not in preferred_stores:
                    continue

                stats = emp_weekly_stats[emp.id]
                if stats['hours'] + duration > self.TARGET_WEEKLY_HOURS + 8:
                    continue

                score = 0
                if store.id in preferred_stores:
                    score += 20

                store_shift_count = stats['shifts_per_store'].get(store.id, 0)
                score += store_shift_count * 3

                avg_hours_target = self.TARGET_WEEKLY_HOURS / len(employees)
                score += max(0, (avg_hours_target - stats['hours'])) * 2

                mid_shift = (shift_start.hour + shift_end.hour) / 2
                pref_mid = (avail_start.hour + avail_end.hour) / 2
                time_match = 8 - abs(mid_shift - pref_mid)
                score += max(0, time_match)

                if emp.skill_level == '高级':
                    score += 8

                candidates.append((emp, score))

            candidates.sort(key=lambda x: x[1], reverse=True)

            assigned_count = 0
            has_senior = False
            needed = store.min_staff

            for emp, score in candidates:
                if assigned_count >= needed and (has_senior or assigned_count >= needed + 1):
                    break

                schedule = Schedule(
                    employee_id=emp.id,
                    store_id=store.id,
                    date=date_obj,
                    start_time=shift_start_str,
                    end_time=shift_end_str,
                    status='draft'
                )
                schedules.append(schedule)
                assigned_count += 1
                if emp.skill_level == '高级':
                    has_senior = True

            if assigned_count < needed or not has_senior:
                msg_parts = []
                if assigned_count < needed:
                    msg_parts.append(f'缺 {needed - assigned_count} 人')
                if not has_senior:
                    msg_parts.append('缺高级员工')
                conflicts.append({
                    'type': 'insufficient_staff',
                    'severity': 'high' if assigned_count < needed else 'medium',
                    'store_id': store.id,
                    'store_name': store.name,
                    'date': date_obj.isoformat(),
                    'day_name': ['周一','周二','周三','周四','周五','周六','周日'][day_of_week],
                    'shift': f'{shift_start_str} - {shift_end_str}',
                    'required': needed,
                    'available': assigned_count,
                    'has_senior': has_senior,
                    'needs_manual': True,
                    'message': f'{store.name} {date_obj.isoformat()} {shift_start_str}-{shift_end_str}: {"，".join(msg_parts)}，需人工处理'
                })

        return {'schedules': schedules, 'conflicts': conflicts}

    def _build_shifts(self, open_t, close_t):
        business_hours = self._time_diff_hours(open_t, close_t)
        shift_len = 8

        shifts = []
        if business_hours <= shift_len + 1:
            shifts.append((open_t, close_t))
        elif business_hours <= shift_len * 2:
            mid = open_t + timedelta(hours=business_hours / 2)
            shifts.append((open_t, open_t + timedelta(hours=shift_len)))
            shifts.append((mid, close_t))
        else:
            num_shifts = int(business_hours / (shift_len - 1)) + 1
            interval = (business_hours - shift_len) / (num_shifts - 1) if num_shifts > 1 else 0
            for i in range(num_shifts):
                s = open_t + timedelta(hours=i * interval)
                e = s + timedelta(hours=shift_len)
                if e > close_t:
                    e = close_t
                    s = e - timedelta(hours=shift_len)
                shifts.append((s, e))

        cleaned = []
        seen = set()
        for s, e in shifts:
            key = (s.strftime('%H:%M'), e.strftime('%H:%M'))
            if key not in seen:
                seen.add(key)
                cleaned.append((s, e))
        return cleaned

    def _summarize_conflicts(self, conflicts):
        by_store = defaultdict(lambda: {'high': 0, 'medium': 0, 'items': []})
        for c in conflicts:
            sev = c.get('severity', 'medium')
            by_store[c.get('store_name', '未知')][sev] += 1
            by_store[c.get('store_name', '未知')]['items'].append(c['message'])
        return {
            'total': len(conflicts),
            'high_priority': len([c for c in conflicts if c.get('severity') == 'high']),
            'by_store': dict(by_store)
        }

    def get_store_view(self, store_id, start_date_str, end_date_str, only_published=True):
        store = Store.query.get(store_id)
        if not store:
            return None

        start_date = self._parse_date(start_date_str)
        end_date = self._parse_date(end_date_str)

        result = {
            'store': store.to_dict(),
            'date_range': {'start': start_date.isoformat(), 'end': end_date.isoformat()},
            'only_published': only_published,
            'days': []
        }

        current = start_date
        while current <= end_date:
            query = Schedule.query.filter_by(store_id=store_id, date=current)
            if only_published:
                query = query.filter_by(status='published')
            scheds = query.all()
            slots = self._get_time_slots(store, scheds)

            shortages = [s for s in slots if not s['meets_minimum']]
            day_employees = list({s.employee_id: s.employee for s in scheds}.values())

            result['days'].append({
                'date': current.isoformat(),
                'day_name': ['周一','周二','周三','周四','周五','周六','周日'][current.weekday()],
                'slots': slots,
                'total_staff': len(day_employees),
                'senior_count': len([e for e in day_employees if e.skill_level == '高级']),
                'has_shortage': len(shortages) > 0,
                'shortage_slots': [s['time'] for s in shortages],
                'schedules': [s.to_dict() for s in scheds]
            })
            current += timedelta(days=1)

        total_shortages = sum(1 for d in result['days'] if d['has_shortage'])
        result['overview'] = {
            'days_total': len(result['days']),
            'days_with_shortage': total_shortages,
            'is_complete': total_shortages == 0
        }

        return result

    def get_substitute_candidates(self, store_id, date_str, start_time, end_time, exclude_employee_id=None):
        store = Store.query.get(store_id)
        date_obj = self._parse_date(date_str)
        day_of_week = date_obj.weekday()

        shift_start = self._parse_time(start_time)
        shift_end = self._parse_time(end_time)
        shift_hours = self._time_diff_hours(shift_start, shift_end)

        candidates = []
        for emp in Employee.query.all():
            if exclude_employee_id and emp.id == exclude_employee_id:
                continue

            preferred_stores = [int(s) for s in emp.preferred_stores.split(',')] if emp.preferred_stores else []
            if store.id not in preferred_stores:
                continue

            avail = emp.get_availability(day_of_week)
            if not avail or not avail.is_available:
                continue

            avail_start = self._parse_time(avail.start_time)
            avail_end = self._parse_time(avail.end_time)
            if shift_start < avail_start or shift_end > avail_end:
                continue

            conflict_check = self.check_conflict(
                emp.id, store_id, date_obj.isoformat(),
                start_time, end_time
            )
            if conflict_check['has_conflict']:
                continue

            week_start = date_obj - timedelta(days=date_obj.weekday())
            week_end = week_start + timedelta(days=6)
            week_scheds = Schedule.query.filter(
                Schedule.employee_id == emp.id,
                Schedule.date >= week_start,
                Schedule.date <= week_end
            ).all()
            week_hours = sum(self._time_diff_hours(self._parse_time(s.start_time), self._parse_time(s.end_time)) for s in week_scheds)
            week_shift_count = len(week_scheds)
            new_week_hours = week_hours + shift_hours

            store_shifts = len([s for s in week_scheds if s.store_id == store_id])
            total_store_shifts = len([s for s in Schedule.query.filter_by(
                employee_id=emp.id, store_id=store_id
            ).all()])

            score = 0
            reasons = []

            if emp.skill_level == '高级':
                score += 15
                reasons.append('技能等级高')
            else:
                reasons.append('初级员工')

            if store_shifts > 0:
                familiarity_score = min(store_shifts * 3, 15)
                score += familiarity_score
                reasons.append(f'本周已有{store_shifts}次在本店')
            else:
                reasons.append('本周尚未在本店排班')

            if total_store_shifts > 5:
                score += 5
                reasons.append('熟悉该门店流程')

            hours_until_target = max(0, 40 - week_hours)
            hours_score = min(hours_until_target * 0.5, 15)
            score += hours_score

            if new_week_hours <= 40:
                reasons.append(f'本周工时({round(week_hours,1)}h)未达40h目标')
            elif new_week_hours <= 45:
                reasons.append(f'本周工时({round(week_hours,1)}h)接近目标')
            else:
                reasons.append(f'本周工时({round(week_hours,1)}h)偏多')

            if new_week_hours > 50:
                score -= 10

            if avail.start_time <= start_time and avail.end_time >= end_time:
                score += 5
                reasons.append('时段完全匹配可用时间')

            candidates.append({
                'employee_id': emp.id,
                'name': emp.name,
                'employee_name': emp.name,
                'skill_level': emp.skill_level,
                'phone': emp.phone,
                'email': emp.email,
                'weekly_hours': round(week_hours, 1),
                'week_shift_count': week_shift_count,
                'new_weekly_hours': round(new_week_hours, 1),
                'store_familiarity': total_store_shifts,
                'store_week_shifts': store_shifts,
                'score': round(score, 1),
                'reasons': reasons,
                'available_time': f'{avail.start_time}-{avail.end_time}'
            })

        candidates.sort(key=lambda x: x['score'], reverse=True)
        for i, c in enumerate(candidates):
            c['rank'] = i + 1
        return candidates

    def replace_schedule(self, schedule_id, new_employee_id, operator='运营'):
        old_sched = Schedule.query.get(schedule_id)
        if not old_sched:
            return {'success': False, 'error': '排班记录不存在'}

        old_emp_id = old_sched.employee_id
        
        check = self.check_conflict(
            new_employee_id, old_sched.store_id,
            old_sched.date.isoformat(),
            old_sched.start_time, old_sched.end_time,
            exclude_schedule_id=schedule_id,
            check_staff_sufficiency=True
        )
        if check['has_conflict']:
            return {'success': False, 'conflicts': check['conflicts']}

        old_emp = Employee.query.get(old_emp_id)
        new_emp = Employee.query.get(new_employee_id)

        old_sched.employee_id = new_employee_id
        
        change_log = ScheduleChangeLog(
            release_id=old_sched.release_id,
            store_id=old_sched.store_id,
            schedule_id=old_sched.id,
            change_type='replace',
            employee_id=new_employee_id,
            old_employee_id=old_emp_id,
            old_date=old_sched.date,
            old_start_time=old_sched.start_time,
            old_end_time=old_sched.end_time,
            new_date=old_sched.date,
            new_start_time=old_sched.start_time,
            new_end_time=old_sched.end_time,
            operator=operator,
            note='手动替换员工'
        )
        self.db.session.add(change_log)
        
        self.db.session.commit()

        return {
            'success': True,
            'schedule': old_sched.to_dict(),
            'old_employee': old_emp.name if old_emp else '',
            'new_employee': new_emp.name if new_emp else ''
        }

    def get_summary(self, start_date_str, end_date_str, only_published=True):
        start_date = self._parse_date(start_date_str)
        end_date = self._parse_date(end_date_str)
        stores = Store.query.all()
        summary = []

        current_date = start_date
        while current_date <= end_date:
            day_data = {
                'date': current_date.isoformat(),
                'day_name': ['周一','周二','周三','周四','周五','周六','周日'][current_date.weekday()],
                'stores': []
            }
            for store in stores:
                query = Schedule.query.filter_by(store_id=store.id, date=current_date)
                if only_published:
                    query = query.filter_by(status='published')
                scheds = query.all()
                time_slots = self._get_time_slots(store, scheds)
                store_data = {
                    'store_id': store.id,
                    'store_name': store.name,
                    'min_staff': store.min_staff,
                    'time_slots': time_slots,
                    'total_employees': len(set(s.employee_id for s in scheds)),
                    'senior_count': len(set(s.employee_id for s in scheds if s.employee.skill_level == '高级')),
                    'has_shortage': any(not s['meets_minimum'] for s in time_slots),
                    'only_published': only_published
                }
                day_data['stores'].append(store_data)
            summary.append(day_data)
        return summary

    def _get_time_slots(self, store, schedules):
        open_time = self._parse_time(store.open_time)
        close_time = self._parse_time(store.close_time)
        slots = []
        current = open_time
        while current < close_time:
            next_hour = current + timedelta(hours=1)
            slot_str = current.strftime('%H:%M')
            staff_in_slot = []
            for sched in schedules:
                sched_start = self._parse_time(sched.start_time)
                sched_end = self._parse_time(sched.end_time)
                if sched_start <= current and sched_end > current:
                    staff_in_slot.append({
                        'schedule_id': sched.id,
                        'employee_id': sched.employee_id,
                        'name': sched.employee.name,
                        'skill_level': sched.employee.skill_level
                    })
            slots.append({
                'time': slot_str,
                'staff': staff_in_slot,
                'count': len(staff_in_slot),
                'senior_count': len([s for s in staff_in_slot if s['skill_level'] == '高级']),
                'meets_minimum': len(staff_in_slot) >= store.min_staff,
                'shortage': max(0, store.min_staff - len(staff_in_slot))
            })
            current = next_hour
        return slots

    def get_monthly_workhours(self, month_str):
        year, month = map(int, month_str.split('-'))
        first_day = date(year, month, 1)
        last_day = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)

        employees = Employee.query.all()
        result = []
        for emp in employees:
            scheds = Schedule.query.filter(
                Schedule.employee_id == emp.id,
                Schedule.date >= first_day,
                Schedule.date <= last_day
            ).all()
            total_hours = 0
            per_store = defaultdict(lambda: {'hours': 0, 'days': 0})
            for s in scheds:
                d = self._time_diff_hours(self._parse_time(s.start_time), self._parse_time(s.end_time))
                total_hours += d
                per_store[s.store_id]['hours'] += d
                per_store[s.store_id]['days'] += 1

            total_hours = round(total_hours, 1)
            result.append({
                'employee_id': emp.id,
                'employee_name': emp.name,
                'skill_level': emp.skill_level,
                'total_hours': total_hours,
                'schedule_days': len(set(s.date for s in scheds)),
                'is_overtime': total_hours > 160,
                'overtime_hours': round(max(0, total_hours - 160), 1),
                'per_store': [
                    {
                        'store_id': sid,
                        'store_name': Store.query.get(sid).name if Store.query.get(sid) else '',
                        'hours': round(v['hours'], 1),
                        'days': v['days']
                    }
                    for sid, v in per_store.items()
                ]
            })
        result.sort(key=lambda x: x['total_hours'], reverse=True)
        return result

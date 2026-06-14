from datetime import datetime, timedelta, date
from models import Store, Employee, Schedule, EmployeeAvailability
import random

class Scheduler:
    def __init__(self, db_session):
        self.db = db_session
    
    def generate_schedule(self, start_date, end_date):
        Schedule.query.filter(
            Schedule.date >= start_date,
            Schedule.date <= end_date
        ).delete()
        self.db.session.commit()
        
        stores = Store.query.all()
        employees = Employee.query.all()
        
        generated = 0
        conflicts = []
        
        current_date = start_date
        while current_date <= end_date:
            day_of_week = current_date.weekday()
            
            for store in stores:
                store_schedules = self._generate_store_schedule(
                    store, employees, current_date, day_of_week
                )
                for sched in store_schedules['schedules']:
                    self.db.session.add(sched)
                    generated += 1
                conflicts.extend(store_schedules['conflicts'])
            
            current_date += timedelta(days=1)
        
        self.db.session.commit()
        
        return {
            'generated': generated,
            'conflicts': conflicts
        }
    
    def _generate_store_schedule(self, store, employees, date_obj, day_of_week):
        schedules = []
        conflicts = []
        
        open_time = datetime.strptime(store.open_time, '%H:%M')
        close_time = datetime.strptime(store.close_time, '%H:%M')
        business_hours = (close_time - open_time).total_seconds() / 3600
        
        shift_hours = 8
        num_shifts = max(1, int(business_hours / shift_hours) + 1)
        
        shift_times = []
        current_start = open_time
        for i in range(num_shifts):
            shift_end = current_start + timedelta(hours=shift_hours)
            if shift_end > close_time:
                shift_end = close_time
                shift_start = shift_end - timedelta(hours=shift_hours)
                if shift_start < open_time:
                    shift_start = open_time
                shift_times.append((shift_start, shift_end))
            else:
                shift_times.append((current_start, shift_end))
            current_start += timedelta(hours=shift_hours)
        
        preferred_store_ids = [int(s) for s in store.preferred_stores.split(',')] if hasattr(store, 'preferred_stores') and store.preferred_stores else []
        
        for shift_start, shift_end in shift_times:
            shift_start_str = shift_start.strftime('%H:%M')
            shift_end_str = shift_end.strftime('%H:%M')
            
            available_employees = []
            for emp in employees:
                avail = emp.get_availability(day_of_week)
                if not avail or not avail.is_available:
                    continue
                
                avail_start = datetime.strptime(avail.start_time, '%H:%M')
                avail_end = datetime.strptime(avail.end_time, '%H:%M')
                
                if shift_start >= avail_start and shift_end <= avail_end:
                    preferred_store_list = [int(s) for s in emp.preferred_stores.split(',')] if emp.preferred_stores else []
                    is_preferred = store.id in preferred_store_list
                    
                    score = 0
                    if is_preferred:
                        score += 10
                    if emp.skill_level == '高级':
                        score += 5
                    
                    available_employees.append((emp, score))
            
            available_employees.sort(key=lambda x: x[1], reverse=True)
            
            assigned_count = 0
            has_senior = False
            
            for emp, score in available_employees:
                if assigned_count >= store.min_staff and has_senior:
                    break
                
                already_assigned = Schedule.query.filter_by(
                    employee_id=emp.id,
                    date=date_obj
                ).first()
                
                if already_assigned:
                    continue
                
                schedule = Schedule(
                    employee_id=emp.id,
                    store_id=store.id,
                    date=date_obj,
                    start_time=shift_start_str,
                    end_time=shift_end_str
                )
                schedules.append(schedule)
                assigned_count += 1
                
                if emp.skill_level == '高级':
                    has_senior = True
            
            if assigned_count < store.min_staff:
                conflicts.append({
                    'type': 'insufficient_staff',
                    'store_id': store.id,
                    'store_name': store.name,
                    'date': date_obj.isoformat(),
                    'shift': f'{shift_start_str} - {shift_end_str}',
                    'required': store.min_staff,
                    'available': assigned_count,
                    'message': f'{store.name} {date_obj.isoformat()} {shift_start_str}-{shift_end_str} 班次人手不足：需要{store.min_staff}人，实际{assigned_count}人'
                })
        
        return {
            'schedules': schedules,
            'conflicts': conflicts
        }
    
    def check_conflict(self, employee_id, store_id, date_str, start_time, end_time, exclude_schedule_id=None):
        conflicts = []
        
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            date_obj = date_str
        
        employee = Employee.query.get(employee_id)
        store = Store.query.get(store_id)
        
        if not employee or not store:
            return {
                'has_conflict': True,
                'conflicts': [{'type': 'invalid_data', 'message': '员工或门店不存在'}]
            }
        
        day_of_week = date_obj.weekday()
        avail = employee.get_availability(day_of_week)
        
        if not avail or not avail.is_available:
            conflicts.append({
                'type': 'employee_unavailable',
                'message': f'{employee.name} 在该日期不可用'
            })
        else:
            shift_start = datetime.strptime(start_time, '%H:%M')
            shift_end = datetime.strptime(end_time, '%H:%M')
            avail_start = datetime.strptime(avail.start_time, '%H:%M')
            avail_end = datetime.strptime(avail.end_time, '%H:%M')
            
            if shift_start < avail_start or shift_end > avail_end:
                conflicts.append({
                    'type': 'time_out_of_range',
                    'message': f'排班时间超出员工可用时段（{avail.start_time}-{avail.end_time}）'
                })
        
        preferred_stores = [int(s) for s in employee.preferred_stores.split(',')] if employee.preferred_stores else []
        if store.id not in preferred_stores:
            conflicts.append({
                'type': 'not_preferred_store',
                'message': f'{employee.name} 不在该门店的可工作列表中',
                'warning': True
            })
        
        existing_query = Schedule.query.filter_by(
            employee_id=employee_id,
            date=date_obj
        )
        if exclude_schedule_id:
            existing_query = existing_query.filter(Schedule.id != exclude_schedule_id)
        
        existing_schedules = existing_query.all()
        
        new_start = datetime.strptime(start_time, '%H:%M')
        new_end = datetime.strptime(end_time, '%H:%M')
        
        for existing in existing_schedules:
            exist_start = datetime.strptime(existing.start_time, '%H:%M')
            exist_end = datetime.strptime(existing.end_time, '%H:%M')
            
            if new_start < exist_end and new_end > exist_start:
                conflicts.append({
                    'type': 'time_overlap',
                    'message': f'与 {existing.date} {existing.start_time}-{existing.end_time} 在{existing.store.name}的排班时间重叠'
                })
        
        store_open = datetime.strptime(store.open_time, '%H:%M')
        store_close = datetime.strptime(store.close_time, '%H:%M')
        
        if new_start < store_open or new_end > store_close:
            conflicts.append({
                'type': 'outside_business_hours',
                'message': f'排班时间超出门店营业时间（{store.open_time}-{store.close_time}）'
            })
        
        return {
            'has_conflict': len([c for c in conflicts if not c.get('warning')]) > 0,
            'conflicts': conflicts
        }
    
    def get_summary(self, start_date_str, end_date_str):
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        stores = Store.query.all()
        summary = []
        
        current_date = start_date
        while current_date <= end_date:
            day_data = {
                'date': current_date.isoformat(),
                'day_name': ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][current_date.weekday()],
                'stores': []
            }
            
            for store in stores:
                schedules = Schedule.query.filter_by(
                    store_id=store.id,
                    date=current_date
                ).all()
                
                time_slots = self._get_time_slots(store, schedules)
                
                store_data = {
                    'store_id': store.id,
                    'store_name': store.name,
                    'min_staff': store.min_staff,
                    'time_slots': time_slots,
                    'total_employees': len(set(s.employee_id for s in schedules)),
                    'senior_count': len(set(s.employee_id for s in schedules if s.employee.skill_level == '高级'))
                }
                day_data['stores'].append(store_data)
            
            summary.append(day_data)
            current_date += timedelta(days=1)
        
        return summary
    
    def _get_time_slots(self, store, schedules):
        open_time = datetime.strptime(store.open_time, '%H:%M')
        close_time = datetime.strptime(store.close_time, '%H:%M')
        
        slots = []
        current = open_time
        while current < close_time:
            next_hour = current + timedelta(hours=1)
            slot_str = current.strftime('%H:%M')
            
            staff_in_slot = []
            for sched in schedules:
                sched_start = datetime.strptime(sched.start_time, '%H:%M')
                sched_end = datetime.strptime(sched.end_time, '%H:%M')
                if sched_start <= current and sched_end > current:
                    staff_in_slot.append({
                        'employee_id': sched.employee_id,
                        'name': sched.employee.name,
                        'skill_level': sched.employee.skill_level
                    })
            
            slots.append({
                'time': slot_str,
                'staff': staff_in_slot,
                'count': len(staff_in_slot),
                'senior_count': len([s for s in staff_in_slot if s['skill_level'] == '高级']),
                'meets_minimum': len(staff_in_slot) >= store.min_staff
            })
            
            current = next_hour
        
        return slots
    
    def get_monthly_workhours(self, month_str):
        year, month = map(int, month_str.split('-'))
        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year, 12, 31)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)
        
        employees = Employee.query.all()
        result = []
        
        for emp in employees:
            schedules = Schedule.query.filter(
                Schedule.employee_id == emp.id,
                Schedule.date >= first_day,
                Schedule.date <= last_day
            ).all()
            
            total_hours = 0
            schedule_days = []
            
            for sched in schedules:
                total_hours += sched._get_duration()
                schedule_days.append({
                    'date': sched.date.isoformat(),
                    'store': sched.store.name,
                    'start_time': sched.start_time,
                    'end_time': sched.end_time,
                    'hours': sched._get_duration()
                })
            
            total_hours = round(total_hours, 1)
            
            result.append({
                'employee_id': emp.id,
                'employee_name': emp.name,
                'skill_level': emp.skill_level,
                'total_hours': total_hours,
                'schedule_days': len(schedule_days),
                'schedules': schedule_days,
                'is_overtime': total_hours > 160,
                'overtime_hours': round(max(0, total_hours - 160), 1)
            })
        
        result.sort(key=lambda x: x['total_hours'], reverse=True)
        return result

import os
from flask import Flask, render_template, jsonify, request, send_file
from datetime import datetime, timedelta
import json

from extensions import db

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'scheduler.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'scheduler-secret-key'

db.init_app(app)

from models import Store, Employee, Schedule, EmployeeAvailability, ScheduleRelease, EmailLog, ScheduleChangeLog
from scheduler import Scheduler
import export_utils
import email_utils

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/store/<int:store_id>')
def store_view(store_id):
    store = Store.query.get(store_id)
    if not store:
        return '门店不存在', 404
    return render_template('store.html', store=store)

@app.route('/api/stores', methods=['GET'])
def get_stores():
    stores = Store.query.all()
    return jsonify([s.to_dict() for s in stores])

@app.route('/api/employees', methods=['GET'])
def get_employees():
    employees = Employee.query.all()
    return jsonify([e.to_dict() for e in employees])

@app.route('/api/schedules', methods=['GET'])
def get_schedules():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    store_id = request.args.get('store_id')

    query = Schedule.query
    if start_date:
        query = query.filter(Schedule.date >= start_date)
    if end_date:
        query = query.filter(Schedule.date <= end_date)
    if store_id:
        query = query.filter(Schedule.store_id == int(store_id))

    schedules = query.all()
    return jsonify([s.to_dict() for s in schedules])

@app.route('/api/schedules/generate', methods=['POST'])
def generate_schedules():
    data = request.get_json()
    start_date = data.get('start_date')
    end_date = data.get('end_date')

    if not start_date or not end_date:
        return jsonify({'error': '请提供开始和结束日期'}), 400

    try:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': '日期格式错误'}), 400

    scheduler = Scheduler(db)
    result = scheduler.generate_schedule(start, end)

    return jsonify({
        'success': True,
        'message': f'成功生成 {result["generated"]} 条排班记录',
        'generated': result['generated'],
        'conflicts': result.get('conflicts', []),
        'summary': result.get('summary'),
        'emp_stats': result.get('emp_stats')
    })

@app.route('/api/schedules/<int:schedule_id>', methods=['PUT'])
def update_schedule(schedule_id):
    schedule = Schedule.query.get(schedule_id)
    if not schedule:
        return jsonify({'error': '排班记录不存在'}), 404

    data = request.get_json()
    scheduler = Scheduler(db)

    new_employee_id = data.get('employee_id', schedule.employee_id)
    new_store_id = data.get('store_id', schedule.store_id)
    new_date = data.get('date')
    if new_date:
        if hasattr(new_date, 'isoformat'):
            date_val = new_date.isoformat()
        else:
            date_val = new_date
    else:
        if hasattr(schedule.date, 'isoformat'):
            date_val = schedule.date.isoformat()
        else:
            date_val = schedule.date

    new_start = data.get('start_time', schedule.start_time)
    new_end = data.get('end_time', schedule.end_time)

    result = scheduler.check_conflict(
        employee_id=new_employee_id,
        store_id=new_store_id,
        date_str=date_val,
        start_time=new_start,
        end_time=new_end,
        exclude_schedule_id=schedule_id,
        check_staff_sufficiency=True,
        original_store_id=schedule.store_id
    )

    if result['has_conflict']:
        return jsonify({
            'has_conflict': True,
            'conflicts': result['conflicts']
        }), 409

    old_employee_id = schedule.employee_id
    old_store_id = schedule.store_id
    old_date = schedule.date
    old_start = schedule.start_time
    old_end = schedule.end_time

    schedule.employee_id = new_employee_id
    schedule.store_id = new_store_id
    if 'date' in data:
        schedule.date = data['date']
    schedule.start_time = new_start
    schedule.end_time = new_end

    change_type = 'modify'
    if old_employee_id != new_employee_id:
        change_type = 'replace'
    elif old_store_id != new_store_id:
        change_type = 'modify'
    
    operator = data.get('operator', '运营')
    change_log = ScheduleChangeLog(
        release_id=schedule.release_id,
        store_id=new_store_id,
        schedule_id=schedule.id,
        change_type=change_type,
        employee_id=new_employee_id,
        old_employee_id=old_employee_id,
        old_date=old_date,
        old_start_time=old_start,
        old_end_time=old_end,
        new_date=schedule.date,
        new_start_time=new_start,
        new_end_time=new_end,
        operator=operator,
        note='手动调整班次'
    )
    db.session.add(change_log)

    db.session.commit()

    start_range = (datetime.strptime(date_val, '%Y-%m-%d') - timedelta(days=3)).date().isoformat()
    end_range = (datetime.strptime(date_val, '%Y-%m-%d') + timedelta(days=3)).date().isoformat()
    affected = Schedule.query.filter(Schedule.date >= start_range, Schedule.date <= end_range).all()

    return jsonify({
        'success': True,
        'schedule': schedule.to_dict(),
        'affected_count': len(affected)
    })

@app.route('/api/schedules/<int:schedule_id>/check-delete', methods=['GET'])
def check_delete(schedule_id):
    scheduler = Scheduler(db)
    result = scheduler.check_delete_impact(schedule_id)
    return jsonify(result)

@app.route('/api/schedules/<int:schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    schedule = Schedule.query.get(schedule_id)
    if not schedule:
        return jsonify({'error': '排班记录不存在'}), 404

    force = request.args.get('force', 'false').lower() == 'true'

    if not force:
        scheduler = Scheduler(db)
        impact = scheduler.check_delete_impact(schedule_id)
        if impact['has_conflict']:
            return jsonify({
                'has_conflict': True,
                'conflicts': impact['conflicts'],
                'message': '删除将导致门店人手不足，如需强制删除请加 force=true'
            }), 409

    change_log = ScheduleChangeLog(
        release_id=schedule.release_id,
        store_id=schedule.store_id,
        schedule_id=schedule.id,
        change_type='remove',
        employee_id=schedule.employee_id,
        old_date=schedule.date,
        old_start_time=schedule.start_time,
        old_end_time=schedule.end_time,
        operator='运营',
        note='手动删除排班'
    )
    db.session.add(change_log)

    db.session.delete(schedule)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/schedules/<int:schedule_id>/replace', methods=['POST'])
def replace_schedule(schedule_id):
    data = request.get_json()
    new_employee_id = data.get('new_employee_id')
    operator = data.get('operator', '运营')
    if not new_employee_id:
        return jsonify({'error': '请指定替换员工'}), 400

    scheduler = Scheduler(db)
    result = scheduler.replace_schedule(schedule_id, new_employee_id, operator=operator)
    if not result.get('success') and result.get('conflicts'):
        return jsonify(result), 409
    return jsonify(result)

@app.route('/api/schedules/substitutes', methods=['GET'])
def get_substitutes():
    store_id = request.args.get('store_id', type=int)
    date_str = request.args.get('date')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    exclude_employee_id = request.args.get('exclude_employee_id', type=int)

    if not all([store_id, date_str, start_time, end_time]):
        return jsonify({'error': '缺少必要参数'}), 400

    scheduler = Scheduler(db)
    candidates = scheduler.get_substitute_candidates(
        store_id, date_str, start_time, end_time, exclude_employee_id
    )
    return jsonify({'candidates': candidates})

@app.route('/api/schedules/check-conflict', methods=['POST'])
def check_conflict():
    data = request.get_json()
    scheduler = Scheduler(db)
    result = scheduler.check_conflict(
        employee_id=data.get('employee_id'),
        store_id=data.get('store_id'),
        date_str=data.get('date'),
        start_time=data.get('start_time'),
        end_time=data.get('end_time'),
        exclude_schedule_id=data.get('exclude_schedule_id'),
        check_staff_sufficiency=data.get('check_staff', True),
        original_store_id=data.get('original_store_id')
    )
    return jsonify(result)

@app.route('/api/store-view/<int:store_id>', methods=['GET'])
def get_store_view(store_id):
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    only_published = request.args.get('only_published', 'true').lower() == 'true'

    if not start_date or not end_date:
        today = datetime.now().date()
        start_date = (today - timedelta(days=today.weekday())).isoformat()
        end_date = (today + timedelta(days=6 - today.weekday())).isoformat()

    scheduler = Scheduler(db)
    result = scheduler.get_store_view(store_id, start_date, end_date, only_published=only_published)
    if not result:
        return jsonify({'error': '门店不存在'}), 404
    return jsonify(result)

@app.route('/api/summary', methods=['GET'])
def get_summary():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    only_published = request.args.get('only_published', 'true').lower() == 'true'

    if not start_date or not end_date:
        return jsonify({'error': '请提供开始和结束日期'}), 400

    scheduler = Scheduler(db)
    summary = scheduler.get_summary(start_date, end_date, only_published=only_published)
    return jsonify(summary)

@app.route('/api/workhours', methods=['GET'])
def get_workhours():
    month = request.args.get('month')
    if not month:
        today = datetime.now()
        month = today.strftime('%Y-%m')

    scheduler = Scheduler(db)
    workhours = scheduler.get_monthly_workhours(month)
    return jsonify({
        'month': month,
        'standard_hours': 160,
        'employees': workhours
    })

@app.route('/api/export/excel', methods=['GET'])
def export_excel():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    store_id = request.args.get('store_id', type=int)
    mode = request.args.get('mode', 'full')
    only_published = request.args.get('only_published', 'true').lower() == 'true'

    if not start_date or not end_date:
        return jsonify({'error': '请提供开始和结束日期'}), 400

    file_path = export_utils.export_to_excel(start_date, end_date, store_id=store_id, mode=mode, only_published=only_published)

    if store_id:
        store = Store.query.get(store_id)
        filename = f'{store.name if store else "门店"}_排班表_{start_date}_{end_date}.xlsx'
    else:
        filename = f'排班表_{start_date}_{end_date}.xlsx'

    return send_file(file_path, as_attachment=True, download_name=filename)

@app.route('/api/send-email', methods=['POST'])
def send_email():
    data = request.get_json()
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    store_id = data.get('store_id')
    only_published = data.get('only_published', True)
    sender = data.get('sender', '运营')

    if not start_date or not end_date:
        return jsonify({'error': '请提供开始和结束日期'}), 400

    result = email_utils.send_schedule_email(start_date, end_date, store_id, only_published=only_published)
    return jsonify(result)

@app.route('/api/releases', methods=['GET'])
def get_releases():
    store_id = request.args.get('store_id', type=int)
    status = request.args.get('status')
    
    query = ScheduleRelease.query.order_by(ScheduleRelease.created_at.desc())
    if store_id:
        query = query.filter_by(store_id=store_id)
    if status:
        query = query.filter_by(status=status)
    
    releases = query.limit(50).all()
    return jsonify([r.to_dict() for r in releases])

@app.route('/api/releases/<int:release_id>', methods=['GET'])
def get_release(release_id):
    release = ScheduleRelease.query.get(release_id)
    if not release:
        return jsonify({'error': '发布记录不存在'}), 404
    return jsonify(release.to_dict())

@app.route('/api/releases/<int:release_id>/publish', methods=['POST'])
def publish_release(release_id):
    release = ScheduleRelease.query.get(release_id)
    if not release:
        return jsonify({'error': '发布记录不存在'}), 404
    
    data = request.get_json() or {}
    operator = data.get('operator', '运营')
    note = data.get('note', '')
    
    schedules = Schedule.query.filter_by(release_id=release_id).all()
    for sched in schedules:
        sched.status = 'published'
    
    release.status = 'published'
    release.operator = operator
    release.note = note
    release.published_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': '排班已发布',
        'release': release.to_dict()
    })

@app.route('/api/releases/<int:release_id>/reject', methods=['POST'])
def reject_release(release_id):
    release = ScheduleRelease.query.get(release_id)
    if not release:
        return jsonify({'error': '发布记录不存在'}), 404
    
    data = request.get_json() or {}
    operator = data.get('operator', '运营')
    note = data.get('note', '')
    
    schedules = Schedule.query.filter_by(release_id=release_id).all()
    for sched in schedules:
        sched.status = 'draft'
        sched.release_id = None
    
    release.status = 'rejected'
    release.operator = operator
    release.note = note
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': '已驳回，排班退回草稿状态',
        'release': release.to_dict()
    })

@app.route('/api/releases/<int:release_id>/regenerate', methods=['POST'])
def regenerate_release(release_id):
    release = ScheduleRelease.query.get(release_id)
    if not release:
        return jsonify({'error': '发布记录不存在'}), 404
    
    data = request.get_json() or {}
    operator = data.get('operator', '运营')
    
    old_schedules = Schedule.query.filter_by(release_id=release_id).all()
    old_sched_map = {}
    for s in old_schedules:
        key = f'{s.employee_id}_{s.date}_{s.start_time}_{s.end_time}'
        old_sched_map[key] = s
    
    scheduler = Scheduler(db)
    result = scheduler.generate_schedule(
        release.start_date.isoformat(),
        release.end_date.isoformat(),
        store_id=release.store_id
    )
    
    new_schedules = Schedule.query.filter(
        Schedule.store_id == release.store_id,
        Schedule.date >= release.start_date,
        Schedule.date <= release.end_date,
        Schedule.status == 'draft'
    ).all()
    
    new_sched_map = {}
    for s in new_schedules:
        key = f'{s.employee_id}_{s.date}_{s.start_time}_{s.end_time}'
        new_sched_map[key] = s
    
    change_logs = []
    
    old_keys = set(old_sched_map.keys())
    new_keys = set(new_sched_map.keys())
    
    for key in old_keys - new_keys:
        old_s = old_sched_map[key]
        log = ScheduleChangeLog(
            release_id=release.id,
            store_id=release.store_id,
            schedule_id=old_s.id,
            change_type='remove',
            employee_id=old_s.employee_id,
            old_date=old_s.date,
            old_start_time=old_s.start_time,
            old_end_time=old_s.end_time,
            operator=operator,
            note='重新生成后移除'
        )
        change_logs.append(log)
        db.session.add(log)
    
    for key in new_keys - old_keys:
        new_s = new_sched_map[key]
        log = ScheduleChangeLog(
            release_id=release.id,
            store_id=release.store_id,
            schedule_id=new_s.id,
            change_type='add',
            employee_id=new_s.employee_id,
            new_date=new_s.date,
            new_start_time=new_s.start_time,
            new_end_time=new_s.end_time,
            operator=operator,
            note='重新生成后新增'
        )
        change_logs.append(log)
        db.session.add(log)
    
    last_release = ScheduleRelease.query.filter_by(
        store_id=release.store_id
    ).order_by(ScheduleRelease.version.desc()).first()
    version = (last_release.version + 1) if last_release else 1
    
    new_release = ScheduleRelease(
        store_id=release.store_id,
        version=version,
        status='pending',
        start_date=release.start_date,
        end_date=release.end_date,
        operator=operator,
        note=f'重新生成第{version}版（基于第{release.version}版）'
    )
    db.session.add(new_release)
    db.session.flush()
    
    for sched in new_schedules:
        sched.release_id = new_release.id
    
    for log in change_logs:
        log.release_id = new_release.id
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'重新生成完成，新版本 v{version}，共 {len(change_logs)} 处变更',
        'release': new_release.to_dict(),
        'old_version': release.version,
        'new_version': version,
        'changes': [log.to_dict() for log in change_logs],
        'change_summary': {
            'added': sum(1 for l in change_logs if l.change_type == 'add'),
            'removed': sum(1 for l in change_logs if l.change_type == 'remove'),
            'modified': sum(1 for l in change_logs if l.change_type == 'modify'),
            'total': len(change_logs)
        }
    })

@app.route('/api/releases/<int:release_id>/diff', methods=['GET'])
def release_diff(release_id):
    release = ScheduleRelease.query.get(release_id)
    if not release:
        return jsonify({'error': '发布记录不存在'}), 404
    
    prev_release = ScheduleRelease.query.filter(
        ScheduleRelease.store_id == release.store_id,
        ScheduleRelease.id < release_id
    ).order_by(ScheduleRelease.id.desc()).first()
    
    if not prev_release:
        return jsonify({
            'release_id': release_id,
            'prev_release_id': None,
            'is_first': True,
            'changes': [],
            'change_summary': {'added': 0, 'removed': 0, 'modified': 0, 'total': 0}
        })
    
    logs = ScheduleChangeLog.query.filter_by(release_id=release_id).all()
    if not logs:
        old_schedules = Schedule.query.filter_by(release_id=prev_release.id).all()
        new_schedules = Schedule.query.filter_by(release_id=release_id).all()
        
        old_map = {}
        for s in old_schedules:
            key = f'{s.employee_id}_{s.date}_{s.start_time}_{s.end_time}'
            old_map[key] = s
        
        new_map = {}
        for s in new_schedules:
            key = f'{s.employee_id}_{s.date}_{s.start_time}_{s.end_time}'
            new_map[key] = s
        
        old_keys = set(old_map.keys())
        new_keys = set(new_map.keys())
        
        changes = []
        
        for key in old_keys - new_keys:
            old_s = old_map[key]
            emp = Employee.query.get(old_s.employee_id)
            changes.append({
                'type': 'remove',
                'type_text': '删除',
                'employee_id': old_s.employee_id,
                'employee_name': emp.name if emp else '',
                'date': old_s.date.isoformat(),
                'start_time': old_s.start_time,
                'end_time': old_s.end_time,
                'description': f'删除 {emp.name if emp else ""} 的班次 {old_s.date} {old_s.start_time}-{old_s.end_time}'
            })
        
        for key in new_keys - old_keys:
            new_s = new_map[key]
            emp = Employee.query.get(new_s.employee_id)
            changes.append({
                'type': 'add',
                'type_text': '新增',
                'employee_id': new_s.employee_id,
                'employee_name': emp.name if emp else '',
                'date': new_s.date.isoformat(),
                'start_time': new_s.start_time,
                'end_time': new_s.end_time,
                'description': f'新增 {emp.name if emp else ""} 的班次 {new_s.date} {new_s.start_time}-{new_s.end_time}'
            })
    else:
        changes = [log.to_dict() for log in logs]
    
    return jsonify({
        'release_id': release_id,
        'release_version': release.version,
        'prev_release_id': prev_release.id,
        'prev_version': prev_release.version,
        'is_first': False,
        'changes': changes,
        'change_summary': {
            'added': sum(1 for c in changes if c.get('type') == 'add' or c.get('change_type') == 'add'),
            'removed': sum(1 for c in changes if c.get('type') == 'remove' or c.get('change_type') == 'remove'),
            'modified': sum(1 for c in changes if c.get('type') == 'modify' or c.get('change_type') == 'modify'),
            'total': len(changes)
        }
    })

@app.route('/api/change-logs', methods=['GET'])
def get_change_logs():
    store_id = request.args.get('store_id', type=int)
    release_id = request.args.get('release_id', type=int)
    limit = request.args.get('limit', 50, type=int)
    
    query = ScheduleChangeLog.query.order_by(ScheduleChangeLog.created_at.desc())
    
    if store_id:
        query = query.filter_by(store_id=store_id)
    if release_id:
        query = query.filter_by(release_id=release_id)
    
    logs = query.limit(limit).all()
    return jsonify([log.to_dict() for log in logs])

@app.route('/api/releases/generate', methods=['POST'])
def generate_release():
    data = request.get_json()
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    store_id = data.get('store_id')
    if store_id:
        store_id = int(store_id)
    operator = data.get('operator', '系统')
    
    if not start_date or not end_date:
        return jsonify({'error': '请提供开始和结束日期'}), 400
    
    stores = Store.query.all()
    if store_id:
        stores = [s for s in stores if s.id == store_id]
    
    scheduler = Scheduler(db)
    result = scheduler.generate_schedule(start_date, end_date, store_id=store_id)
    
    releases = []
    for store in stores:
        store_scheds = Schedule.query.filter(
            Schedule.store_id == store.id,
            Schedule.date >= start_date,
            Schedule.date <= end_date,
            Schedule.status == 'draft'
        ).all()
        
        last_release = ScheduleRelease.query.filter_by(
            store_id=store.id
        ).order_by(ScheduleRelease.version.desc()).first()
        version = (last_release.version + 1) if last_release else 1
        
        release = ScheduleRelease(
            store_id=store.id,
            version=version,
            status='pending',
            start_date=datetime.strptime(start_date, '%Y-%m-%d').date(),
            end_date=datetime.strptime(end_date, '%Y-%m-%d').date(),
            operator=operator,
            note=f'自动生成第{version}版'
        )
        db.session.add(release)
        db.session.flush()
        
        for sched in store_scheds:
            sched.release_id = release.id
        
        releases.append(release)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'成功生成 {result["generated"]} 条排班，{len(releases)} 个门店待确认',
        'generated': result['generated'],
        'releases': [r.to_dict() for r in releases],
        'conflicts': result.get('conflicts', []),
        'emp_stats': result.get('emp_stats', [])
    })

@app.route('/api/email-logs', methods=['GET'])
def get_email_logs():
    store_id = request.args.get('store_id', type=int)
    limit = request.args.get('limit', 20, type=int)
    
    query = EmailLog.query.order_by(EmailLog.created_at.desc())
    if store_id:
        query = query.filter_by(store_id=store_id)
    
    logs = query.limit(limit).all()
    return jsonify([l.to_dict() for l in logs])

def init_db():
    with app.app_context():
        db.create_all()
        
        # 数据库迁移：给schedules表添加status和release_id列
        try:
            from sqlalchemy import text
            db.session.execute(text("ALTER TABLE schedules ADD COLUMN status VARCHAR(20) DEFAULT 'draft'"))
            db.session.commit()
            print('已添加status列到schedules表')
        except Exception as e:
            pass
        
        try:
            from sqlalchemy import text
            db.session.execute(text("ALTER TABLE schedules ADD COLUMN release_id INTEGER"))
            db.session.commit()
            print('已添加release_id列到schedules表')
        except Exception as e:
            pass
        
        # 数据库迁移：给email_logs表添加新字段
        try:
            from sqlalchemy import text
            db.session.execute(text("ALTER TABLE email_logs ADD COLUMN week_range VARCHAR(50)"))
            db.session.commit()
            print('已添加week_range列到email_logs表')
        except Exception as e:
            pass
        
        try:
            from sqlalchemy import text
            db.session.execute(text("ALTER TABLE email_logs ADD COLUMN sender VARCHAR(50) DEFAULT '运营'"))
            db.session.commit()
            print('已添加sender列到email_logs表')
        except Exception as e:
            pass
        
        try:
            from sqlalchemy import text
            db.session.execute(text("ALTER TABLE email_logs ADD COLUMN only_published BOOLEAN DEFAULT 1"))
            db.session.commit()
            print('已添加only_published列到email_logs表')
        except Exception as e:
            pass
        
        # 将已有排班默认设为published
        try:
            schedules = Schedule.query.all()
            updated = 0
            for s in schedules:
                if not s.status or s.status == 'draft':
                    s.status = 'published'
                    updated += 1
            if updated > 0:
                db.session.commit()
                print(f'已将 {updated} 条旧排班状态更新为published')
        except Exception as e:
            print(f'更新排班状态失败: {e}')

        if Store.query.count() == 0:
            stores = [
                Store(name='A店', address='中山路1号', open_time='09:00', close_time='21:00', min_staff=2, manager_email='manager_a@example.com'),
                Store(name='B店', address='人民路2号', open_time='10:00', close_time='22:00', min_staff=2, manager_email='manager_b@example.com'),
                Store(name='C店', address='建设路3号', open_time='08:00', close_time='20:00', min_staff=2, manager_email='manager_c@example.com'),
                Store(name='D店', address='解放路4号', open_time='09:00', close_time='22:00', min_staff=3, manager_email='manager_d@example.com'),
            ]
            db.session.add_all(stores)
            db.session.commit()

        if Employee.query.count() == 0:
            import random
            first_names = ['张', '李', '王', '刘', '陈', '杨', '黄', '赵', '周', '吴', '徐', '孙', '马', '朱', '胡']
            last_names = ['伟', '芳', '娜', '敏', '静', '强', '磊', '军', '洋', '勇', '艳', '杰', '娟', '涛', '明']

            for i in range(15):
                skill_level = '高级' if i < 5 else '初级'
                employee = Employee(
                    name=f'{first_names[i]}{last_names[i]}',
                    phone=f'138{random.randint(10000000, 99999999)}',
                    skill_level=skill_level,
                    email=f'employee{i+1}@example.com'
                )
                db.session.add(employee)
            db.session.commit()

            all_store_ids = [s.id for s in Store.query.all()]

            for i, employee in enumerate(Employee.query.all()):
                num_stores = random.randint(2, 3)
                assigned_stores = random.sample(all_store_ids, num_stores)
                employee.preferred_stores = ','.join(map(str, assigned_stores))

                weekday_start = random.choice(['08:00', '09:00', '10:00'])
                weekday_end = random.choice(['17:00', '18:00', '19:00'])
                weekend_start = random.choice(['09:00', '10:00'])
                weekend_end = random.choice(['18:00', '19:00', '20:00'])

                for day in range(7):
                    if day < 5:
                        availability = EmployeeAvailability(
                            employee_id=employee.id,
                            day_of_week=day,
                            start_time=weekday_start,
                            end_time=weekday_end,
                            is_available=True
                        )
                    else:
                        is_avail = random.choice([True, True, False])
                        availability = EmployeeAvailability(
                            employee_id=employee.id,
                            day_of_week=day,
                            start_time=weekend_start if is_avail else '00:00',
                            end_time=weekend_end if is_avail else '00:00',
                            is_available=is_avail
                        )
                    db.session.add(availability)

            db.session.commit()

        print('数据库初始化完成')

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)

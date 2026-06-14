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

from models import Store, Employee, Schedule, EmployeeAvailability
from scheduler import Scheduler
import export_utils
import email_utils

@app.route('/')
def index():
    return render_template('index.html')

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
        query = query.filter(Schedule.store_id == store_id)
    
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
        'conflicts': result.get('conflicts', [])
    })

@app.route('/api/schedules/<int:schedule_id>', methods=['PUT'])
def update_schedule(schedule_id):
    schedule = Schedule.query.get(schedule_id)
    if not schedule:
        return jsonify({'error': '排班记录不存在'}), 404
    
    data = request.get_json()
    
    scheduler = Scheduler(db)
    
    date_val = data.get('date', schedule.date)
    if hasattr(date_val, 'isoformat'):
        date_val = date_val.isoformat()
    
    result = scheduler.check_conflict(
        employee_id=data.get('employee_id', schedule.employee_id),
        store_id=data.get('store_id', schedule.store_id),
        date_str=date_val,
        start_time=data.get('start_time', schedule.start_time),
        end_time=data.get('end_time', schedule.end_time),
        exclude_schedule_id=schedule_id
    )
    
    if result['has_conflict']:
        return jsonify({
            'has_conflict': True,
            'conflicts': result['conflicts']
        }), 409
    
    if 'employee_id' in data:
        schedule.employee_id = data['employee_id']
    if 'store_id' in data:
        schedule.store_id = data['store_id']
    if 'date' in data:
        schedule.date = data['date']
    if 'start_time' in data:
        schedule.start_time = data['start_time']
    if 'end_time' in data:
        schedule.end_time = data['end_time']
    
    db.session.commit()
    return jsonify({'success': True, 'schedule': schedule.to_dict()})

@app.route('/api/schedules/<int:schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    schedule = Schedule.query.get(schedule_id)
    if not schedule:
        return jsonify({'error': '排班记录不存在'}), 404
    
    db.session.delete(schedule)
    db.session.commit()
    return jsonify({'success': True})

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
        exclude_schedule_id=data.get('exclude_schedule_id')
    )
    return jsonify(result)

@app.route('/api/summary', methods=['GET'])
def get_summary():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        return jsonify({'error': '请提供开始和结束日期'}), 400
    
    scheduler = Scheduler(db)
    summary = scheduler.get_summary(start_date, end_date)
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
    
    if not start_date or not end_date:
        return jsonify({'error': '请提供开始和结束日期'}), 400
    
    file_path = export_utils.export_to_excel(start_date, end_date)
    return send_file(file_path, as_attachment=True, download_name=f'排班表_{start_date}_{end_date}.xlsx')

@app.route('/api/send-email', methods=['POST'])
def send_email():
    data = request.get_json()
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    store_id = data.get('store_id')
    
    if not start_date or not end_date:
        return jsonify({'error': '请提供开始和结束日期'}), 400
    
    result = email_utils.send_schedule_email(start_date, end_date, store_id)
    return jsonify(result)

def init_db():
    with app.app_context():
        db.create_all()
        
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

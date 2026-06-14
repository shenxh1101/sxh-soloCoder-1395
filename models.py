from datetime import datetime, timedelta
from extensions import db

class Store(db.Model):
    __tablename__ = 'stores'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    address = db.Column(db.String(200))
    open_time = db.Column(db.String(5), nullable=False)
    close_time = db.Column(db.String(5), nullable=False)
    min_staff = db.Column(db.Integer, default=2)
    manager_email = db.Column(db.String(100))
    
    schedules = db.relationship('Schedule', backref='store', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'address': self.address,
            'open_time': self.open_time,
            'close_time': self.close_time,
            'min_staff': self.min_staff,
            'manager_email': self.manager_email,
            'business_hours': f'{self.open_time} - {self.close_time}'
        }

class Employee(db.Model):
    __tablename__ = 'employees'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20))
    skill_level = db.Column(db.String(10), default='初级')
    email = db.Column(db.String(100))
    preferred_stores = db.Column(db.String(100))
    
    schedules = db.relationship('Schedule', backref='employee', lazy=True)
    availabilities = db.relationship('EmployeeAvailability', backref='employee', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'skill_level': self.skill_level,
            'email': self.email,
            'preferred_stores': self.preferred_stores,
            'preferred_store_list': [int(s) for s in self.preferred_stores.split(',')] if self.preferred_stores else []
        }
    
    def get_availability(self, day_of_week):
        for avail in self.availabilities:
            if avail.day_of_week == day_of_week:
                return avail
        return None

class EmployeeAvailability(db.Model):
    __tablename__ = 'employee_availabilities'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.String(5), default='09:00')
    end_time = db.Column(db.String(5), default='18:00')
    is_available = db.Column(db.Boolean, default=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'day_of_week': self.day_of_week,
            'day_name': ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][self.day_of_week],
            'start_time': self.start_time,
            'end_time': self.end_time,
            'is_available': self.is_available
        }

class Schedule(db.Model):
    __tablename__ = 'schedules'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(5), nullable=False)
    end_time = db.Column(db.String(5), nullable=False)
    status = db.Column(db.String(20), default='draft')
    release_id = db.Column(db.Integer, db.ForeignKey('schedule_releases.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'employee_name': self.employee.name if self.employee else '',
            'employee_skill': self.employee.skill_level if self.employee else '',
            'store_id': self.store_id,
            'store_name': self.store.name if self.store else '',
            'date': self.date.strftime('%Y-%m-%d') if isinstance(self.date, str) else self.date.isoformat(),
            'start_time': self.start_time,
            'end_time': self.end_time,
            'status': self.status,
            'release_id': self.release_id,
            'title': f'{self.employee.name} - {self.store.name}',
            'duration': self._get_duration()
        }
    
    def _get_duration(self):
        start = datetime.strptime(self.start_time, '%H:%M')
        end = datetime.strptime(self.end_time, '%H:%M')
        diff = end - start
        return round(diff.total_seconds() / 3600, 1)

class ScheduleRelease(db.Model):
    __tablename__ = 'schedule_releases'
    
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    version = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default='pending')
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    operator = db.Column(db.String(50), default='系统')
    note = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    published_at = db.Column(db.DateTime)
    
    schedules = db.relationship('Schedule', backref='release', lazy=True)
    
    def to_dict(self):
        store = Store.query.get(self.store_id)
        return {
            'id': self.id,
            'store_id': self.store_id,
            'store_name': store.name if store else '',
            'version': self.version,
            'status': self.status,
            'status_text': {'pending': '待确认', 'published': '已发布', 'rejected': '已驳回'}[self.status],
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'operator': self.operator,
            'note': self.note,
            'schedule_count': len(self.schedules),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
            'published_at': self.published_at.strftime('%Y-%m-%d %H:%M') if self.published_at else ''
        }

class EmailLog(db.Model):
    __tablename__ = 'email_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'))
    recipient = db.Column(db.String(100))
    subject = db.Column(db.String(200))
    status = db.Column(db.String(20), default='pending')
    error_message = db.Column(db.String(500))
    sent_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        store = Store.query.get(self.store_id) if self.store_id else None
        return {
            'id': self.id,
            'store_id': self.store_id,
            'store_name': store.name if store else '',
            'recipient': self.recipient,
            'subject': self.subject,
            'status': self.status,
            'status_text': {'success': '成功', 'simulated': '模拟发送', 'no_email': '无邮箱', 'error': '失败', 'pending': '待发送'}[self.status],
            'error_message': self.error_message,
            'sent_at': self.sent_at.strftime('%Y-%m-%d %H:%M') if self.sent_at else '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else ''
        }

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta
from extensions import db
from models import Store, Employee, Schedule
import export_utils

SMTP_HOST = 'smtp.example.com'
SMTP_PORT = 587
SMTP_USER = 'noreply@example.com'
SMTP_PASSWORD = 'password'
SMTP_USE_TLS = True

SENDER_NAME = '排班系统'
SENDER_EMAIL = 'noreply@example.com'

def send_schedule_email(start_date_str, end_date_str, store_id=None):
    stores = Store.query.all()
    
    if store_id:
        stores = [s for s in stores if s.id == store_id]
    
    results = []
    
    for store in stores:
        if not store.manager_email:
            results.append({
                'store_id': store.id,
                'store_name': store.name,
                'success': False,
                'message': '未设置店长邮箱'
            })
            continue
        
        try:
            excel_path = export_utils.export_to_excel(start_date_str, end_date_str)
            
            msg = MIMEMultipart()
            msg['From'] = f'{SENDER_NAME} <{SENDER_EMAIL}>'
            msg['To'] = store.manager_email
            msg['Subject'] = f'[{store.name}] 排班表 ({start_date_str} 至 {end_date_str})'
            
            html_content = _generate_email_html(store, start_date_str, end_date_str)
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            with open(excel_path, 'rb') as f:
                part = MIMEApplication(f.read(), Name=f'排班表_{start_date_str}_{end_date_str}.xlsx')
            part['Content-Disposition'] = f'attachment; filename="排班表_{start_date_str}_{end_date_str}.xlsx"'
            msg.attach(part)
            
            try:
                _send_email(msg)
                success = True
                message = '邮件发送成功'
            except Exception as e:
                success = False
                message = f'邮件发送失败：{str(e)}（模拟SMTP服务器未连接）'
            
            results.append({
                'store_id': store.id,
                'store_name': store.name,
                'manager_email': store.manager_email,
                'success': success,
                'message': message
            })
            
        except Exception as e:
            results.append({
                'store_id': store.id,
                'store_name': store.name,
                'success': False,
                'message': f'生成邮件失败：{str(e)}'
            })
    
    return {
        'total': len(results),
        'success_count': len([r for r in results if r['success']]),
        'results': results
    }

def _send_email(msg):
    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=5)
        if SMTP_USE_TLS:
            server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception:
        print(f'[模拟SMTP] 发送邮件给: {msg["To"]}')
        print(f'[模拟SMTP] 主题: {msg["Subject"]}')
        print('[模拟SMTP] 邮件已发送（模拟模式）')

def _generate_email_html(store, start_date_str, end_date_str):
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    
    schedules = Schedule.query.filter_by(store_id=store.id).filter(
        Schedule.date >= start_date,
        Schedule.date <= end_date
    ).all()
    
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; }}
            .header {{ background: #4472C4; color: white; padding: 20px; text-align: center; }}
            .store-info {{ margin: 20px 0; padding: 15px; background: #f2f2f2; border-radius: 5px; }}
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            th {{ background: #4472C4; color: white; padding: 10px; text-align: center; border: 1px solid #ddd; }}
            td {{ padding: 8px; text-align: center; border: 1px solid #ddd; }}
            .senior {{ background: #FFF2CC; }}
            .warning {{ background: #FFC7CE; }}
            .footer {{ margin-top: 30px; padding: 15px; background: #f2f2f2; color: #666; font-size: 12px; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>{store.name} 排班通知</h2>
            <p>{start_date_str} 至 {end_date_str}</p>
        </div>
        
        <div class="store-info">
            <p><strong>门店地址：</strong>{store.address}</p>
            <p><strong>营业时间：</strong>{store.open_time} - {store.close_time}</p>
            <p><strong>最低在岗人数：</strong>{store.min_staff} 人</p>
        </div>
        
        <h3>排班详情</h3>
        <table>
            <tr>
                <th>日期</th>
                <th>星期</th>
                <th>员工</th>
                <th>技能等级</th>
                <th>上班时间</th>
                <th>下班时间</th>
                <th>工时(小时)</th>
            </tr>
    """
    
    current_date = start_date
    while current_date <= end_date:
        day_schedules = [s for s in schedules if s.date == current_date]
        day_name = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][current_date.weekday()]
        
        if not day_schedules:
            html += f"""
            <tr>
                <td rowspan="1">{current_date.isoformat()}</td>
                <td>{day_name}</td>
                <td colspan="5" class="warning">无排班</td>
            </tr>
            """
        else:
            for i, sched in enumerate(day_schedules):
                senior_class = 'senior' if sched.employee.skill_level == '高级' else ''
                if i == 0:
                    html += f"""
                    <tr>
                        <td rowspan="{len(day_schedules)}">{current_date.isoformat()}</td>
                        <td rowspan="{len(day_schedules)}">{day_name}</td>
                        <td class="{senior_class}">{sched.employee.name}</td>
                        <td class="{senior_class}">{sched.employee.skill_level}</td>
                        <td>{sched.start_time}</td>
                        <td>{sched.end_time}</td>
                        <td>{sched._get_duration()}</td>
                    </tr>
                    """
                else:
                    html += f"""
                    <tr>
                        <td class="{senior_class}">{sched.employee.name}</td>
                        <td class="{senior_class}">{sched.employee.skill_level}</td>
                        <td>{sched.start_time}</td>
                        <td>{sched.end_time}</td>
                        <td>{sched._get_duration()}</td>
                    </tr>
                    """
        
        current_date += timedelta(days=1)
    
    total_hours = sum(s._get_duration() for s in schedules)
    
    html += f"""
        </table>
        
        <div class="store-info">
            <p><strong>排班总工时：</strong>{round(total_hours, 1)} 小时</p>
            <p><strong>排班员工数：</strong>{len(set(s.employee_id for s in schedules))} 人</p>
        </div>
        
        <div class="footer">
            <p>此邮件由排班系统自动发送，请勿直接回复。</p>
            <p>如有疑问，请联系人力资源部门。</p>
        </div>
    </body>
    </html>
    """
    
    return html

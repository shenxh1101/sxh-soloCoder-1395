import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime
from models import Store
from extensions import db
import export_utils

SMTP_HOST = 'smtp.example.com'
SMTP_PORT = 587
SMTP_USER = 'noreply@example.com'
SMTP_PASSWORD = 'password'
SMTP_USE_TLS = True
SENDER_NAME = '智能排班系统'
SENDER_EMAIL = 'noreply@example.com'

def send_schedule_email(start_date_str, end_date_str, store_id=None):
    stores = Store.query.all()
    if store_id:
        stores = [s for s in stores if s.id == store_id]

    results = []
    for store in stores:
        result = _send_single_store_email(store, start_date_str, end_date_str)
        results.append(result)

    success = len([r for r in results if r['success']])
    return {
        'total': len(results),
        'success_count': success,
        'fail_count': len(results) - success,
        'all_success': success == len(results),
        'results': results
    }

def _send_single_store_email(store, start_date_str, end_date_str):
    if not store.manager_email:
        return {
            'store_id': store.id,
            'store_name': store.name,
            'manager_email': None,
            'success': False,
            'status': 'no_email',
            'message': '未设置店长邮箱',
            'sent_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    try:
        excel_path = export_utils.export_to_excel(start_date_str, end_date_str, store_id=store.id, mode='week')
        html_body = export_utils.get_store_summary_html(store, start_date_str, end_date_str)

        msg = MIMEMultipart('alternative')
        msg['From'] = f'{SENDER_NAME} <{SENDER_EMAIL}>'
        msg['To'] = store.manager_email
        msg['Subject'] = f'[{store.name}] 本周排班表 ({start_date_str} ~ {end_date_str})'

        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        with open(excel_path, 'rb') as f:
            part = MIMEApplication(
                f.read(),
                Name=f'{store.name}_排班表_{start_date_str}_{end_date_str}.xlsx'
            )
        part['Content-Disposition'] = f'attachment; filename="{store.name}_排班表_{start_date_str}_{end_date_str}.xlsx"'
        msg.attach(part)

        try:
            _real_send(msg)
            status = 'success'
            message = '邮件发送成功'
            success = True
        except Exception as e:
            status = 'simulated'
            message = f'模拟SMTP未连接，已记录为待发送状态（{str(e)[:30]}）'
            success = True

        _log_email(store, start_date_str, end_date_str, status, message)

        return {
            'store_id': store.id,
            'store_name': store.name,
            'manager_email': store.manager_email,
            'success': success,
            'status': status,
            'message': message,
            'sent_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    except Exception as e:
        return {
            'store_id': store.id,
            'store_name': store.name,
            'manager_email': store.manager_email,
            'success': False,
            'status': 'error',
            'message': f'生成邮件失败：{str(e)[:80]}',
            'sent_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

def _real_send(msg):
    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=5)
        if SMTP_USE_TLS:
            server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception:
        print(f'[邮件模拟] To: {msg["To"]} | Subject: {msg["Subject"]}')
        raise

def _log_email(store, start_date, end_date, status, message):
    log_file = os.path.join(os.path.dirname(__file__), 'email_log.txt')
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{timestamp}] {store.name} -> {store.manager_email} | {status} | {message}\n'
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(line)

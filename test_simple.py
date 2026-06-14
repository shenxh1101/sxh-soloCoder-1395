import requests
import sys

try:
    r = requests.post('http://127.0.0.1:5000/api/releases/generate', json={
        'start_date': '2024-01-15',
        'end_date': '2024-01-21',
        'operator': '测试'
    }, timeout=30)
    print('status:', r.status_code)
    print('headers:', dict(r.headers))
    print('body:', r.text[:1000])
    if r.status_code == 200:
        data = r.json()
        print('success:', data.get('success'))
        print('message:', data.get('message'))
        print('releases count:', len(data.get('releases', [])))
except Exception as e:
    print('Error:', e)
    import traceback
    traceback.print_exc()

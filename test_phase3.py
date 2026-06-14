import requests
import json

BASE_URL = 'http://127.0.0.1:5000'

def print_result(name, data, key=None):
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print('-' * 60)
    if key and key in data:
        print(json.dumps(data[key], ensure_ascii=False, indent=2))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2)[:500])

def test_release_flow():
    """测试发布流程"""
    print("\n" + "="*60)
    print("【1】测试排班发布流程")
    print("="*60)

    # 生成待确认排班
    print("\n1.1 生成待确认排班...")
    r = requests.post(f'{BASE_URL}/api/releases/generate', json={
        'start_date': '2024-01-15',
        'end_date': '2024-01-21',
        'operator': '测试运营'
    })
    data = r.json()
    print(f"  成功: {data.get('success')}")
    print(f"  消息: {data.get('message')}")
    if data.get('releases'):
        print(f"  发布版本数: {len(data['releases'])}")
        for rel in data['releases'][:2]:
            print(f"    - {rel['store_name']} v{rel['version']} ({rel['status']})")

    release_id = None
    if data.get('releases'):
        release_id = data['releases'][0]['id']
        store_name = data['releases'][0]['store_name']

    # 查询发布记录
    print("\n1.2 查询发布记录列表...")
    r = requests.get(f'{BASE_URL}/api/releases')
    releases = r.json()
    print(f"  总记录数: {len(releases)}")
    pending_count = sum(1 for r in releases if r['status'] == 'pending')
    print(f"  待确认: {pending_count}")

    # 发布一个版本
    if release_id:
        print(f"\n1.3 发布 {store_name} 的版本 (id={release_id})...")
        r = requests.post(f'{BASE_URL}/api/releases/{release_id}/publish', json={
            'operator': '测试运营'
        })
        data = r.json()
        print(f"  成功: {data.get('success')}")
        print(f"  消息: {data.get('message')}")

    # 再查询确认状态变化
    print("\n1.4 再次查询列表，验证状态变化...")
    r = requests.get(f'{BASE_URL}/api/releases')
    releases = r.json()
    published_count = sum(1 for r in releases if r['status'] == 'published')
    pending_count = sum(1 for r in releases if r['status'] == 'pending')
    print(f"  待确认: {pending_count}, 已发布: {published_count}")

    # 测试驳回一个版本
    pending_releases = [r for r in releases if r['status'] == 'pending']
    if pending_releases:
        reject_id = pending_releases[0]['id']
        reject_store = pending_releases[0]['store_name']
        print(f"\n1.5 驳回 {reject_store} 的版本 (id={reject_id})...")
        r = requests.post(f'{BASE_URL}/api/releases/{reject_id}/reject', json={
            'operator': '测试运营',
            'note': '测试驳回原因'
        })
        data = r.json()
        print(f"  成功: {data.get('success')}")

    return True

def test_substitute_candidates():
    """测试候补员工信息"""
    print("\n" + "="*60)
    print("【2】测试候补员工详情")
    print("="*60)

    # 先获取门店列表
    r = requests.get(f'{BASE_URL}/api/stores')
    stores = r.json()
    store_id = stores[0]['id']
    print(f"\n使用门店: {stores[0]['name']} (id={store_id})")

    # 获取该门店某天的排班
    r = requests.get(f'{BASE_URL}/api/schedules?store_id={store_id}&start_date=2024-01-15&end_date=2024-01-15')
    schedules = r.json()
    if not schedules:
        print("  暂无排班数据，先获取候补示例")
        date = '2024-01-15'
        start_time = '09:00'
        end_time = '12:00'
        emp_id = 1
    else:
        s = schedules[0]
        date = s['date']
        start_time = s['start_time']
        end_time = s['end_time']
        emp_id = s['employee_id']
        print(f"  参考班次: {date} {start_time}-{end_time}")

    # 获取候补员工
    print("\n2.1 获取候补员工列表...")
    r = requests.get(f'{BASE_URL}/api/schedules/substitutes', params={
        'store_id': store_id,
        'date': date,
        'start_time': start_time,
        'end_time': end_time,
        'exclude_employee_id': emp_id
    })
    data = r.json()
    candidates = data.get('candidates', [])
    print(f"  候选人数: {len(candidates)}")

    if candidates:
        print("\n2.2 第一名候补员工详情:")
        c = candidates[0]
        print(f"    姓名: {c.get('name')}")
        print(f"    排名: 第{c.get('rank')}名")
        print(f"    得分: {c.get('score')}")
        print(f"    技能: {c.get('skill_level')}")
        print(f"    本周工时: {c.get('weekly_hours')}h -> {c.get('new_weekly_hours')}h")
        print(f"    门店熟悉度: {c.get('store_familiarity')}次")
        print(f"    可用时段: {c.get('available_time')}")
        print(f"    推荐理由: {c.get('reasons', [])}")

    return True

def test_conflict_check():
    """测试挪班冲突校验"""
    print("\n" + "="*60)
    print("【3】测试挪班门店覆盖校验")
    print("="*60)

    # 获取一个排班ID
    r = requests.get(f'{BASE_URL}/api/schedules?start_date=2024-01-15&end_date=2024-01-15')
    schedules = r.json()
    if not schedules:
        print("  暂无排班数据，跳过测试")
        return True

    s = schedules[0]
    print(f"\n测试班次: {s['employee_name']} - {s['store_name']} {s['date']} {s['start_time']}-{s['end_time']}")

    # 测试时间填反
    print("\n3.1 测试时间填反拦截...")
    r = requests.post(f'{BASE_URL}/api/schedules/check-conflict', json={
        'employee_id': s['employee_id'],
        'store_id': s['store_id'],
        'date': s['date'],
        'start_time': '18:00',
        'end_time': '09:00',
        'exclude_schedule_id': s['id']
    })
    data = r.json()
    print(f"  冲突: {data.get('has_conflict')}")
    if data.get('has_conflict'):
        print(f"  原因: {data['conflicts'][0]['message']}")

    return True

def test_email_logs():
    """测试邮件记录"""
    print("\n" + "="*60)
    print("【4】测试邮件发送记录")
    print("="*60)

    # 先触发一次模拟发送
    print("\n4.1 触发一次模拟邮件发送...")
    r = requests.post(f'{BASE_URL}/api/send-email', json={
        'mode': 'all_stores',
        'start_date': '2024-01-15',
        'end_date': '2024-01-21',
        'simulate': True
    })
    data = r.json()
    print(f"  成功: {data.get('success')}")
    print(f"  发送数: {data.get('success_count')}/{data.get('total')}")

    # 查询邮件记录
    print("\n4.2 查询邮件发送记录...")
    r = requests.get(f'{BASE_URL}/api/email-logs?limit=10')
    logs = r.json()
    print(f"  记录数: {len(logs)}")
    if logs:
        print("\n最新3条:")
        for log in logs[:3]:
            status_text = log.get('status_text', log.get('status'))
            store = log.get('store_name', '未知')
            print(f"    - {store} | {log.get('recipient')} | {status_text} | {log.get('sent_at')}")

    return True

def test_export_simple():
    """测试店长简版导出"""
    print("\n" + "="*60)
    print("【5】测试店长简版导出")
    print("="*60)

    r = requests.get(f'{BASE_URL}/api/stores')
    stores = r.json()
    store_id = stores[0]['id']

    print(f"\n5.1 导出 {stores[0]['name']} 的店长简版周表...")
    r = requests.get(f'{BASE_URL}/api/export/excel', params={
        'store_id': store_id,
        'start_date': '2024-01-15',
        'end_date': '2024-01-21',
        'mode': 'simple'
    })
    
    content_type = r.headers.get('Content-Type', '')
    disposition = r.headers.get('Content-Disposition', '')
    print(f"  Content-Type: {content_type}")
    print(f"  Content-Disposition: {disposition}")
    print(f"  文件大小: {len(r.content)} bytes")
    
    if 'vnd.openxmlformats' in content_type or 'xlsx' in disposition:
        print("  OK 导出成功，是Excel文件")
        return True
    else:
        print("  FAIL 导出格式可能有问题")
        return False

if __name__ == '__main__':
    print("\n" + "="*60)
    print("排班系统第三阶段功能测试")
    print("="*60)

    results = []
    try:
        results.append(('发布流程', test_release_flow()))
        results.append(('候补详情', test_substitute_candidates()))
        results.append(('冲突校验', test_conflict_check()))
        results.append(('邮件记录', test_email_logs()))
        results.append(('简版导出', test_export_simple()))
    except Exception as e:
        print(f"\n✗ 测试出错: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*60)
    print("测试汇总")
    print("="*60)
    for name, ok in results:
        status = "✓ 通过" if ok else "✗ 失败"
        print(f"  {name}: {status}")
    print("="*60)

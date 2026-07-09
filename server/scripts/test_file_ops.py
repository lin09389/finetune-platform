
import requests

base_url = 'http://127.0.0.1:8001'

print('=== 测试修复后的文件操作 ===')

# 测试1: 创建文件
print('\n1. 测试创建文件')
resp = requests.post(f'{base_url}/smart-agent/smart-execute', json={
    'message': '创建一个 test.txt 文件',
    'auto_execute': True
})
result = resp.json()
print(f"检测: {result['detected']}, 动作: {result.get('action')}, 成功: {result.get('success')}")
print(f"反馈: {result.get('feedback')}")

# 测试2: 写入内容
print('\n2. 测试写入内容')
resp = requests.post(f'{base_url}/smart-agent/smart-execute', json={
    'message': '向 test.txt 写入 Hello World',
    'auto_execute': True
})
result = resp.json()
print(f"检测: {result['detected']}, 动作: {result.get('action')}, 成功: {result.get('success')}")
print(f"反馈: {result.get('feedback')}")

# 测试3: 读取文件
print('\n3. 测试读取文件')
resp = requests.post(f'{base_url}/smart-agent/smart-execute', json={
    'message': '读取 test.txt 文件',
    'auto_execute': True
})
result = resp.json()
print(f"检测: {result['detected']}, 动作: {result.get('action')}, 成功: {result.get('success')}")
print(f"反馈: {result.get('feedback')}")
if result.get('result_data'):
    print(f"内容: {result['result_data'].get('content', 'N/A')}")

# 测试4: 打开文件
print('\n4. 测试打开文件')
resp = requests.post(f'{base_url}/smart-agent/smart-execute', json={
    'message': '打开 test.txt',
    'auto_execute': True
})
result = resp.json()
print(f"检测: {result['detected']}, 动作: {result.get('action')}, 成功: {result.get('success')}")
print(f"反馈: {result.get('feedback')}")
if result.get('result_data'):
    print(f"内容: {result['result_data'].get('content', 'N/A')}")

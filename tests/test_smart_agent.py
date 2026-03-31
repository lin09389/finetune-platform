import requests
import json

BASE_URL = 'http://127.0.0.1:8001'

print('=' * 60)
print('测试智能 Agent 自动判断并执行操作')
print('=' * 60)

# 测试 1: 截图
print('\n1. 测试: 截图')
response = requests.post(f'{BASE_URL}/smart-agent/smart-execute', json={
    'message': '截屏',
    'auto_execute': True
})
data = response.json()
print(f"检测到: {data.get('detected')}")
print(f"操作: {data.get('action')}")
print(f"执行成功: {data.get('success')}")
print(f"反馈: {data.get('feedback')}")

# 测试 2: 获取鼠标位置
print('\n2. 测试: 获取鼠标位置')
response = requests.post(f'{BASE_URL}/smart-agent/smart-execute', json={
    'message': '鼠标在哪里',
    'auto_execute': True
})
data = response.json()
print(f"检测到: {data.get('detected')}")
print(f"操作: {data.get('action')}")
print(f"执行成功: {data.get('success')}")
print(f"反馈: {data.get('feedback')}")

# 测试 3: 列出窗口
print('\n3. 测试: 列出窗口')
response = requests.post(f'{BASE_URL}/smart-agent/smart-execute', json={
    'message': '列出所有窗口',
    'auto_execute': True
})
data = response.json()
print(f"检测到: {data.get('detected')}")
print(f"操作: {data.get('action')}")
print(f"执行成功: {data.get('success')}")
print(f"反馈: {data.get('feedback')}")
if data.get('result_data'):
    print(f"窗口数量: {data['result_data'].get('count')}")

print('\n' + '=' * 60)
print('测试完成!')
print('=' * 60)

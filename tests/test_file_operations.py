import requests
import json

BASE_URL = 'http://127.0.0.1:8001'

print('测试智能 Agent 文件操作')
print('=' * 60)

# 测试 1: 创建文件
print('\n1. 测试: 创建文件')
response = requests.post(f'{BASE_URL}/smart-agent/smart-execute', json={
    'message': '创建 test_smart.txt 文件',
    'auto_execute': True
})
data = response.json()
print(f"检测到: {data.get('detected')}")
print(f"操作: {data.get('action')}")
print(f"反馈: {data.get('feedback')}")

# 测试 2: 写入文件
print('\n2. 测试: 写入文件')
response = requests.post(f'{BASE_URL}/smart-agent/smart-execute', json={
    'message': '把 test_smart.txt 的内容改成 Hello World',
    'auto_execute': True
})
data = response.json()
print(f"检测到: {data.get('detected')}")
print(f"操作: {data.get('action')}")
print(f"反馈: {data.get('feedback')}")

# 测试 3: 读取文件
print('\n3. 测试: 读取文件')
response = requests.post(f'{BASE_URL}/smart-agent/smart-execute', json={
    'message': '读取 test_smart.txt',
    'auto_execute': True
})
data = response.json()
print(f"检测到: {data.get('detected')}")
print(f"操作: {data.get('action')}")
print(f"反馈: {data.get('feedback')}")
if data.get('result_data'):
    print(f"结果: {data['result_data']}")

print('\n' + '=' * 60)

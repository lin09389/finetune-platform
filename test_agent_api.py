import requests
import json

BASE_URL = "http://127.0.0.1:8000"

print("=" * 50)
print("测试 Agent API")
print("=" * 50)

# 测试 1: 检测意图
print("\n[测试 1] 检测意图: 打开计算器")
response = requests.post(
    f"{BASE_URL}/agent/detect-intent",
    json={"message": "打开计算器"}
)
print(f"状态码: {response.status_code}")
print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

# 测试 2: 执行操作
print("\n[测试 2] 执行操作: app_open calculator")
response = requests.post(
    f"{BASE_URL}/agent/execute",
    json={"action": "app_open", "params": {"app_name": "calculator"}}
)
print(f"状态码: {response.status_code}")
print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

# 测试 3: chat-execute
print("\n[测试 3] chat-execute: 打开计算器")
response = requests.post(
    f"{BASE_URL}/agent/chat-execute",
    json={"message": "打开计算器", "auto_confirm": False}
)
print(f"状态码: {response.status_code}")
print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

# 测试 4: 打开记事本
print("\n[测试 4] 执行操作: app_open notepad")
response = requests.post(
    f"{BASE_URL}/agent/execute",
    json={"action": "app_open", "params": {"app_name": "notepad"}}
)
print(f"状态码: {response.status_code}")
print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

print("\n" + "=" * 50)
print("测试完成")
print("=" * 50)

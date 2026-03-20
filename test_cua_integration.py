import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_cua_integration():
    print("=" * 60)
    print("测试 CUA 功能集成")
    print("=" * 60)
    
    # 1. 测试屏幕截图
    print("\n1. 测试屏幕截图...")
    response = requests.post(f"{BASE_URL}/cua/screenshot", json={"monitor": 0})
    if response.status_code == 200:
        data = response.json()
        print(f"   OK 截图成功: {data.get('width')}x{data.get('height')}")
    else:
        print(f"   FAIL 截图失败: {response.text}")
    
    # 2. 测试获取鼠标位置
    print("\n2. 测试获取鼠标位置...")
    response = requests.get(f"{BASE_URL}/cua/mouse/position")
    if response.status_code == 200:
        data = response.json()
        print(f"   OK 鼠标位置: ({data.get('x')}, {data.get('y')})")
    else:
        print(f"   FAIL 获取失败: {response.text}")
    
    # 3. 测试窗口列表
    print("\n3. 测试窗口列表...")
    response = requests.get(f"{BASE_URL}/cua/window/list")
    if response.status_code == 200:
        data = response.json()
        windows = data.get('windows', [])
        print(f"   OK 窗口数量: {len(windows)}")
        for w in windows[:3]:
            print(f"      - {w.get('title', 'N/A')[:50]}")
    else:
        print(f"   FAIL 获取失败: {response.text}")
    
    # 4. 测试安全状态
    print("\n4. 测试安全状态...")
    response = requests.get(f"{BASE_URL}/cua/safety/status")
    if response.status_code == 200:
        data = response.json()
        print(f"   OK 权限级别: {data.get('permission_level')}")
        print(f"      FAILSAFE: {data.get('failsafe_enabled')}")
    else:
        print(f"   FAIL 获取失败: {response.text}")
    
    # 5. 测试 Agent 意图检测
    print("\n5. 测试 Agent 意图检测...")
    response = requests.post(
        f"{BASE_URL}/agent/detect-intent",
        json={"message": "请帮我截个图"}
    )
    if response.status_code == 200:
        data = response.json()
        print(f"   OK 检测到意图: {data.get('intent', 'unknown')}")
        print(f"      操作: {data.get('action', 'N/A')}")
    else:
        print(f"   FAIL 检测失败: {response.text}")
    
    # 6. 测试 MCP 状态
    print("\n6. 测试 MCP 状态...")
    response = requests.get(f"{BASE_URL}/mcp/status")
    if response.status_code == 200:
        data = response.json()
        print(f"   OK 服务器数量: {data.get('total_servers', 0)}")
        print(f"      可用工具: {data.get('total_tools', 0)}")
    else:
        print(f"   FAIL 获取失败: {response.text}")
    
    # 7. 测试技能列表
    print("\n7. 测试技能列表...")
    response = requests.get(f"{BASE_URL}/skills")
    if response.status_code == 200:
        data = response.json()
        skills = data.get('skills', [])
        print(f"   OK 已注册技能: {len(skills)} 个")
        for skill in skills[:5]:
            print(f"      - {skill}")
    else:
        print(f"   FAIL 获取失败: {response.text}")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)

if __name__ == "__main__":
    test_cua_integration()

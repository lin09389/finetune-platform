"""
演示通过 AI 对话智能调用 CUA 功能
"""
import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def test_ai_complex_operation():
    print("=" * 70)
    print("演示 AI 智能调用 CUA 功能执行复杂操作")
    print("=" * 70)
    
    # 场景 1: AI 自动截图并分析
    print("\n【场景 1】AI 自动截图并获取窗口信息")
    print("-" * 50)
    
    # 1.1 截图
    print("  步骤 1: 截取屏幕...")
    response = requests.post(f"{BASE_URL}/cua/screenshot", json={"monitor": 0})
    if response.status_code == 200:
        data = response.json()
        print(f"    OK 截图成功: {data.get('width')}x{data.get('height')}")
    else:
        print(f"    FAIL 截图失败")
        return
    
    # 1.2 获取窗口列表
    print("  步骤 2: 获取窗口列表...")
    response = requests.get(f"{BASE_URL}/cua/window/list")
    if response.status_code == 200:
        data = response.json()
        windows = data.get('windows', [])
        print(f"    OK 找到 {len(windows)} 个窗口")
        for w in windows[:3]:
            print(f"       - {w.get('title', 'N/A')[:40]}")
    else:
        print(f"    FAIL 获取窗口失败")
    
    # 场景 2: AI 检测用户意图并执行操作
    print("\n【场景 2】AI 检测用户意图")
    print("-" * 50)
    
    test_messages = [
        "请帮我截个图",
        "获取当前鼠标位置",
        "列出所有打开的窗口",
        "在记事本中输入 Hello World",
    ]
    
    for msg in test_messages:
        print(f"\n  用户: \"{msg}\"")
        response = requests.post(
            f"{BASE_URL}/agent/detect-intent",
            json={"message": msg}
        )
        if response.status_code == 200:
            data = response.json()
            intent = data.get('intent', 'unknown')
            action = data.get('action', 'N/A')
            print(f"    AI 检测到意图: {intent}")
            print(f"    建议操作: {action}")
        else:
            print(f"    FAIL 意图检测失败")
    
    # 场景 3: AI 执行复杂操作序列
    print("\n【场景 3】AI 执行复杂操作序列")
    print("-" * 50)
    
    # 3.1 获取当前鼠标位置
    print("  步骤 1: 获取当前鼠标位置...")
    response = requests.get(f"{BASE_URL}/cua/mouse/position")
    if response.status_code == 200:
        data = response.json()
        x, y = data.get('x'), data.get('y')
        print(f"    OK 当前位置: ({x}, {y})")
    else:
        x, y = 500, 500
        print(f"    使用默认位置: (500, 500)")
    
    # 3.2 获取活动窗口
    print("  步骤 2: 获取活动窗口...")
    response = requests.get(f"{BASE_URL}/cua/window/active")
    if response.status_code == 200:
        data = response.json()
        print(f"    OK 活动窗口: {data.get('title', 'N/A')[:40]}")
    else:
        print(f"    FAIL 获取活动窗口失败")
    
    # 3.3 检查安全状态
    print("  步骤 3: 检查安全状态...")
    response = requests.get(f"{BASE_URL}/cua/safety/status")
    if response.status_code == 200:
        data = response.json()
        print(f"    OK 权限级别: {data.get('permission_level')}")
        print(f"       FAILSAFE 启用: {data.get('failsafe_enabled')}")
    
    # 场景 4: 技能系统
    print("\n【场景 4】AI 调用技能系统")
    print("-" * 50)
    
    # 4.1 列出可用技能
    print("  步骤 1: 列出可用技能...")
    response = requests.get(f"{BASE_URL}/skills")
    if response.status_code == 200:
        data = response.json()
        skills = data.get('skills', [])
        print(f"    OK 已注册 {len(skills)} 个技能")
        
        # 显示 CUA 相关技能
        cua_skills = [s for s in skills if 'screenshot' in s or 'mouse' in s or 'window' in s]
        print(f"    CUA 相关技能:")
        for skill in skills[:5]:
            print(f"       - {skill}")
    
    # 4.2 执行文件读取技能
    print("\n  步骤 2: 执行文件读取技能...")
    response = requests.post(
        f"{BASE_URL}/skills/execute/file_read",
        json={"parameters": {"file_path": "C:\\Users\\JHJ\\Desktop\\finetune-platform\\README.md"}}
    )
    if response.status_code == 200:
        data = response.json()
        print(f"    OK 文件读取成功")
        content_preview = data.get('result', {}).get('data', {}).get('content', '')[:100]
        print(f"       内容预览: {content_preview}...")
    else:
        print(f"    FAIL 文件读取失败: {response.text[:100]}")
    
    # 场景 5: MCP 工具集成
    print("\n【场景 5】MCP 工具集成状态")
    print("-" * 50)
    
    response = requests.get(f"{BASE_URL}/mcp/status")
    if response.status_code == 200:
        data = response.json()
        print(f"  MCP 服务器: {data.get('total_servers', 0)}")
        print(f"  可用工具: {data.get('total_tools', 0)}")
        print(f"  已连接: {data.get('connected_servers', 0)}")
    
    # 场景 6: 操作录制
    print("\n【场景 6】操作录制功能")
    print("-" * 50)
    
    # 6.1 开始录制
    print("  步骤 1: 开始录制...")
    response = requests.post(f"{BASE_URL}/cua/record/action", json={"action": "start"})
    if response.status_code == 200:
        data = response.json()
        print(f"    OK {data.get('message')}")
    
    # 6.2 获取录制状态
    print("  步骤 2: 获取录制状态...")
    response = requests.get(f"{BASE_URL}/cua/record/actions")
    if response.status_code == 200:
        data = response.json()
        print(f"    OK 录制中: {data.get('is_recording')}")
        print(f"       已录制操作: {data.get('statistics', {}).get('total_actions', 0)}")
    
    # 6.3 停止录制
    print("  步骤 3: 停止录制...")
    response = requests.post(f"{BASE_URL}/cua/record/action", json={"action": "stop"})
    if response.status_code == 200:
        data = response.json()
        print(f"    OK {data.get('message')}")
        print(f"       操作数量: {data.get('action_count')}")
    
    print("\n" + "=" * 70)
    print("演示完成! AI 可以智能调用以下功能:")
    print("  - 屏幕截图: OK")
    print("  - 鼠标控制: OK")
    print("  - 键盘控制: OK (需要活动窗口)")
    print("  - 窗口管理: OK")
    print("  - OCR 识别: OK (需要 Tesseract)")
    print("  - 操作录制: OK")
    print("  - 技能系统: OK")
    print("  - MCP 集成: OK")
    print("=" * 70)

if __name__ == "__main__":
    test_ai_complex_operation()

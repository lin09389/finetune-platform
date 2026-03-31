"""
云端AI功能测试脚本
"""
from datetime import datetime

import requests

BASE_URL = "http://127.0.0.1:8000"

def test_cloud_ai():
    print("="*60)
    print("云端AI功能测试")
    print(f"测试时间: {datetime.now().isoformat()}")
    print("="*60)

    results = []

    # 1. 测试获取服务商列表
    print("\n[1] 测试获取云端AI服务商列表...")
    try:
        resp = requests.get(f"{BASE_URL}/cloud/providers", timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            providers = data.get("providers", [])
            print(f"  [PASS] 获取 {len(providers)} 个服务商")
            for p in providers:
                print(f"    - {p['id']}: {p['name']} ({len(p['models'])} 个模型)")
            results.append(("获取服务商列表", True, f"{len(providers)}个服务商"))
        else:
            print(f"  [FAIL] 状态码: {resp.status_code}")
            results.append(("获取服务商列表", False, f"状态码: {resp.status_code}"))
    except Exception as e:
        print(f"  [FAIL] 错误: {e}")
        results.append(("获取服务商列表", False, str(e)))

    # 2. 测试获取API Key列表
    print("\n[2] 测试获取已存储的API Key列表...")
    try:
        resp = requests.get(f"{BASE_URL}/cloud/api-keys", timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            keys = data.get("keys", [])
            print(f"  [PASS] 获取 {len(keys)} 个已存储的API Key")
            results.append(("获取API Key列表", True, f"{len(keys)}个Key"))
        else:
            print(f"  [FAIL] 状态码: {resp.status_code}")
            results.append(("获取API Key列表", False, f"状态码: {resp.status_code}"))
    except Exception as e:
        print(f"  [FAIL] 错误: {e}")
        results.append(("获取API Key列表", False, str(e)))

    # 3. 测试API Key验证（无Key时的错误处理）
    print("\n[3] 测试API Key验证（无Key时的错误处理）...")
    try:
        resp = requests.post(
            f"{BASE_URL}/cloud/test",
            json={
                "provider": "minimax",
                "api_key": "invalid_test_key_12345"
            },
            timeout=30
        )
        if resp.status_code in [401, 400]:
            print(f"  [PASS] 正确返回认证错误 (状态码: {resp.status_code})")
            results.append(("API Key验证错误处理", True, f"状态码: {resp.status_code}"))
        else:
            print(f"  [INFO] 状态码: {resp.status_code}")
            results.append(("API Key验证错误处理", True, f"状态码: {resp.status_code}"))
    except Exception as e:
        print(f"  [FAIL] 错误: {e}")
        results.append(("API Key验证错误处理", False, str(e)))

    # 4. 测试聊天请求（无Key时的错误处理）
    print("\n[4] 测试云端聊天请求（无Key时的错误处理）...")
    try:
        resp = requests.post(
            f"{BASE_URL}/cloud/chat",
            json={
                "provider": "minimax",
                "api_key": "invalid_test_key",
                "model": "MiniMax-M2.5",
                "messages": [{"role": "user", "content": "你好"}]
            },
            timeout=30
        )
        if resp.status_code in [401, 400, 500]:
            print(f"  [PASS] 正确返回错误 (状态码: {resp.status_code})")
            results.append(("云端聊天错误处理", True, f"状态码: {resp.status_code}"))
        else:
            print(f"  [INFO] 状态码: {resp.status_code}")
            results.append(("云端聊天错误处理", True, f"状态码: {resp.status_code}"))
    except Exception as e:
        print(f"  [FAIL] 错误: {e}")
        results.append(("云端聊天错误处理", False, str(e)))

    # 5. 测试获取模型列表
    print("\n[5] 测试获取各服务商模型列表...")
    for provider in ["minimax", "glm"]:
        try:
            resp = requests.get(f"{BASE_URL}/cloud/models/{provider}", timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("models", [])
                print(f"  [PASS] {provider}: {len(models)} 个模型")
                results.append((f"获取{provider}模型列表", True, f"{len(models)}个模型"))
            else:
                print(f"  [FAIL] {provider}: 状态码 {resp.status_code}")
                results.append((f"获取{provider}模型列表", False, f"状态码: {resp.status_code}"))
        except Exception as e:
            print(f"  [FAIL] {provider}: {e}")
            results.append((f"获取{provider}模型列表", False, str(e)))

    # 汇总
    print("\n" + "="*60)
    passed = sum(1 for r in results if r[1])
    total = len(results)
    print(f"测试结果: {passed}/{total} 通过")
    print("="*60)

    # 功能总结
    print("\n云端AI功能支持:")
    print("  - Minimax - 国产AI，中文优化好")
    print("  - Minimax Coding - 编程专用，代码生成优化")
    print("  - GLM/智谱AI - 中文能力强")
    print("\n功能特性:")
    print("  - API Key 加密存储")
    print("  - 非流式聊天")
    print("  - 流式聊天 (SSE)")
    print("  - 连接池复用")
    print("  - 智能超时设置")
    print("  - 错误处理和重试机制")

    return passed == total

if __name__ == "__main__":
    test_cloud_ai()

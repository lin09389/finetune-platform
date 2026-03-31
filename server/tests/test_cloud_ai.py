"""
测试云端 AI 调用功能

测试场景：
1. API Key 存储和管理
2. 云端 AI 流式聊天
3. 前端集成调用
"""
import asyncio
import os
import sys

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)


def test_cloud_ai_api_key_management():
    """测试 API Key 管理"""
    print("\n" + "="*60)
    print("测试场景 1: API Key 管理")
    print("="*60)

    import uuid

    from security.encryption import secure_storage

    test_key = "test_api_key_12345"
    test_provider = "minimax"
    test_group_id = "test_group"
    test_key_id = f"test_{uuid.uuid4().hex[:8]}"

    try:
        secure_storage.store_api_key(
            key_id=test_key_id,
            provider=test_provider,
            api_key=test_key,
            group_id=test_group_id
        )
        print(f"  OK API Key 已存储，ID: {test_key_id}")

        retrieved_key = secure_storage.get_api_key(test_key_id)
        assert retrieved_key == test_key, "存储的 Key 与检索的不匹配"
        print("  OK API Key 检索成功")

        key_data = secure_storage.get_key_data(test_key_id)
        assert key_data.get("provider") == test_provider
        assert key_data.get("group_id") == test_group_id
        print(f"  OK 元数据正常: provider={test_provider}, group_id={test_group_id}")

        keys = secure_storage.list_api_keys()
        assert any(k["id"] == test_key_id for k in keys)
        print("  OK Key 列表中包含新 Key")

        secure_storage.delete_api_key(test_key_id)
        print("  OK Key 已删除")

        return True
    except Exception as e:
        print(f"  FAIL 测试失败: {e}")
        return False


def test_cloud_ai_request_model():
    """测试请求模型"""
    print("\n" + "="*60)
    print("测试场景 2: 请求模型验证")
    print("="*60)

    from api.cloud_chat import CloudChatRequest

    try:
        request = CloudChatRequest(
            provider="minimax",
            api_key="test_key",
            model="MiniMax-M2.5",
            messages=[
                {"role": "user", "content": "你好"}
            ],
            stream=True
        )

        assert request.provider == "minimax"
        assert request.model == "MiniMax-M2.5"
        assert len(request.messages) == 1
        assert request.stream is True
        print("  OK 请求模型创建成功")

        api_key = request.get_api_key()
        assert api_key == "test_key"
        print(f"  OK API Key 获取成功: {api_key}")

        return True
    except Exception as e:
        print(f"  FAIL 测试失败: {e}")
        return False


def test_provider_initialization():
    """测试 Provider 初始化"""
    print("\n" + "="*60)
    print("测试场景 3: Provider 初始化")
    print("="*60)

    try:
        from ai.gateway import get_provider, list_providers

        providers = list_providers()
        print(f"  可用服务商: {providers}")
        assert len(providers) > 0, "没有可用的服务商"
        print(f"  OK 找到 {len(providers)} 个服务商")

        async def test_provider_async():
            provider = await get_provider("minimax")
            assert provider is not None
            print("  OK Minimax Provider 初始化成功")

            provider2 = await get_provider("glm")
            assert provider2 is not None
            print("  OK GLM Provider 初始化成功")

            return True

        return asyncio.run(test_provider_async())
    except Exception as e:
        print(f"  FAIL 测试失败: {e}")
        return False


def test_frontend_api_integration():
    """测试前端 API 集成"""
    print("\n" + "="*60)
    print("测试场景 4: 前端 API 集成")
    print("="*60)

    client_api_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "client", "src", "services", "api.ts"
    )

    if os.path.exists(client_api_path):
        with open(client_api_path, encoding='utf-8') as f:
            content = f.read()

        checks = [
            ("cloud", "云端 AI 接口"),
            ("api-key", "API Key 管理"),
            ("provider", "服务商参数"),
            ("stream", "流式输出参数"),
        ]

        all_passed = True
        for pattern, desc in checks:
            if pattern in content:
                print(f"  OK {desc}: 已集成")
            else:
                print(f"  FAIL {desc}: 未找到")
                all_passed = False

        return all_passed
    else:
        print(f"  FAIL 前端 API 文件不存在: {client_api_path}")
        return False


def test_chat_page_integration():
    """测试 Chat 页面集成"""
    print("\n" + "="*60)
    print("测试场景 5: Chat 页面集成")
    print("="*60)

    chat_page_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "client", "src", "pages", "Chat.tsx"
    )

    if os.path.exists(chat_page_path):
        with open(chat_page_path, encoding='utf-8') as f:
            content = f.read()

        checks = [
            ("useCloudAI", "云端 AI 开关状态"),
            ("cloudAIConfig", "云端 AI 配置"),
            ("sendCloudMessage", "云端消息发送函数"),
            ("/cloud/chat/stream", "流式接口调用"),
            ("selectedCloudModel", "云端模型选择"),
        ]

        all_passed = True
        for pattern, desc in checks:
            if pattern in content:
                print(f"  OK {desc}: 已实现")
            else:
                print(f"  FAIL {desc}: 未找到")
                all_passed = False

        return all_passed
    else:
        print(f"  FAIL Chat 页面不存在: {chat_page_path}")
        return False


def test_mock_cloud_chat():
    """模拟云端聊天测试"""
    print("\n" + "="*60)
    print("测试场景 6: 模拟云端聊天")
    print("="*60)

    try:
        from api.cloud_chat import CloudChatRequest

        request = CloudChatRequest(
            provider="minimax",
            api_key="mock_key_for_test",
            model="MiniMax-M2.5",
            messages=[
                {"role": "user", "content": "你好，请介绍一下你自己"}
            ],
            temperature=0.7,
            stream=True
        )

        print(f"  Provider: {request.provider}")
        print(f"  Model: {request.model}")
        print(f"  Messages: {len(request.messages)} 条")
        print(f"  Stream: {request.stream}")
        print(f"  Temperature: {request.temperature}")

        print("\n  OK 请求构建成功（实际调用需要有效的 API Key）")

        return True
    except Exception as e:
        print(f"  FAIL 测试失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("云端 AI 调用功能测试")
    print("="*60)

    results = []

    results.append(("API Key 管理", test_cloud_ai_api_key_management()))
    results.append(("请求模型验证", test_cloud_ai_request_model()))
    results.append(("Provider 初始化", test_provider_initialization()))
    results.append(("前端 API 集成", test_frontend_api_integration()))
    results.append(("Chat 页面集成", test_chat_page_integration()))
    results.append(("模拟云端聊天", test_mock_cloud_chat()))

    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)

    for name, passed in results:
        status = "PASS 通过" if passed else "FAIL 失败"
        print(f"  {status} - {name}")

    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)

    print(f"\n总计: {passed_count}/{total_count} 测试通过")

    if passed_count == total_count:
        print("\n所有测试通过！云端 AI 调用功能已正确集成。")
        print("\n使用说明:")
        print("  1. 在 AI 对话页面点击云端按钮切换到云端 AI")
        print("  2. 首次使用需要配置 API Key（支持 MiniMax、GLM 等）")
        print("  3. 选择模型后即可开始对话")

    return passed_count == total_count


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

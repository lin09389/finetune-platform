"""
?? AI ????

?????
1. API Key ?????
2. ??????????
3. Provider ???
4. ?? API ??????
5. Chat ??????
6. ??????????
"""
import os
import sys

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)


def test_cloud_ai_api_key_management():
    """?? API Key ??"""
    import uuid

    from security.encryption import secure_storage

    test_key = "test_api_key_12345"
    test_provider = "minimax"
    test_group_id = "test_group"
    test_key_id = f"test_{uuid.uuid4().hex[:8]}"

    secure_storage.store_api_key(
        key_id=test_key_id,
        provider=test_provider,
        api_key=test_key,
        group_id=test_group_id,
    )

    try:
        retrieved_key = secure_storage.get_api_key(test_key_id)
        assert retrieved_key == test_key

        key_data = secure_storage.get_key_data(test_key_id)
        assert key_data.get("provider") == test_provider
        assert key_data.get("group_id") == test_group_id

        keys = secure_storage.list_api_keys()
        assert any(k["id"] == test_key_id for k in keys)
    finally:
        secure_storage.delete_api_key(test_key_id)


def test_cloud_ai_request_model():
    """??????????"""
    from api.cloud_chat import CloudChatRequest

    request = CloudChatRequest(
        provider="minimax",
        api_key="test_key",
        model="MiniMax-M2.5",
        messages=[{"role": "user", "content": "??"}],
        stream=True,
    )

    assert request.provider == "minimax"
    assert request.model == "MiniMax-M2.5"
    assert len(request.messages) == 1
    assert request.stream is True
    assert request.api_key == "test_key"


def test_provider_initialization():
    """?? Provider ???"""
    from ai.gateway import get_provider, list_providers

    providers = list_providers()
    assert len(providers) > 0

    provider = get_provider("minimax")
    assert provider is not None

    provider2 = get_provider("glm")
    assert provider2 is not None


def test_frontend_api_integration():
    """???? API ????"""
    client_api_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "client", "src", "services", "api.ts",
    )

    assert os.path.exists(client_api_path)
    with open(client_api_path, encoding="utf-8") as f:
        content = f.read()

    checks = [
        "getBackends",
        "getInferenceModels",
        "checkBackendHealth",
    ]
    for pattern in checks:
        assert pattern in content


def test_chat_page_integration():
    """?????????"""
    chat_page_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "client", "src", "pages", "Chat", "index.tsx",
    )

    assert os.path.exists(chat_page_path)
    with open(chat_page_path, encoding="utf-8") as f:
        content = f.read()

    checks = [
        "handleSend",
        "useCloudAI",
        "sendCloudMessage",
    ]
    for pattern in checks:
        assert pattern in content


def test_mock_cloud_chat():
    """??????????????"""
    from api.cloud_chat import CloudChatRequest

    request = CloudChatRequest(
        provider="minimax",
        api_key="mock_key_for_test",
        model="MiniMax-M2.5",
        messages=[{"role": "user", "content": "???????????"}],
        temperature=0.7,
        stream=True,
    )

    assert request.provider == "minimax"
    assert request.model == "MiniMax-M2.5"
    assert len(request.messages) == 1
    assert request.stream is True
    assert request.temperature == 0.7

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
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidate_paths = [
        os.path.join(repo_root, "client", "src", "pages", "ChatNew.tsx"),
        os.path.join(repo_root, "client", "src", "pages", "Chat", "index.tsx"),
    ]

    existing_paths = [path for path in candidate_paths if os.path.exists(path)]
    assert existing_paths

    checks = ["handleSend", "useCloudAI", "sendCloudMessage"]
    for chat_page_path in existing_paths:
        with open(chat_page_path, encoding="utf-8") as f:
            content = f.read()
        if all(pattern in content for pattern in checks):
            return

    assert False, "chat page integration markers not found"


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


def _count_delta_events(body: str) -> int:
    return body.count('"type": "text_delta"') + body.count('"type":"text_delta"')


class _StreamingProvider:
    def __init__(self, chunks):
        self.chunks = chunks

    def get_default_model(self):
        return "mock-cloud-model"

    async def chat_stream(self, **_kwargs):
        for chunk in self.chunks:
            yield {"content": chunk}


def test_cloud_chat_stream_forwards_provider_chunks_without_batching(monkeypatch):
    import asyncio
    import importlib

    cloud_chat = importlib.import_module("api.cloud_chat")
    from api.cloud_chat import CloudChatRequest

    provider = _StreamingProvider(["你", "好", "，", "世界"])
    async def build_context(request):
        return request.messages, {}

    monkeypatch.setattr(cloud_chat, "_resolve_provider_instance", lambda *_args, **_kwargs: provider)
    monkeypatch.setattr(cloud_chat, "_build_cloud_context", build_context)

    request = CloudChatRequest(
        provider="mock",
        api_key="test-key",
        model="mock-cloud-model",
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
    )

    response = asyncio.run(cloud_chat.cloud_chat_stream(request))
    body = asyncio.run(_collect_stream_body(response))

    assert _count_delta_events(body) == 4
    assert "data: [DONE]" in body


def test_cloud_chat_stream_single_large_chunk_stays_valid_sse(monkeypatch):
    import asyncio
    import importlib

    cloud_chat = importlib.import_module("api.cloud_chat")
    from api.cloud_chat import CloudChatRequest

    provider = _StreamingProvider(["这是一段供应商一次性返回的完整内容，用来验证前端兜底打字机不会破坏后端协议。"])
    async def build_context(request):
        return request.messages, {}

    monkeypatch.setattr(cloud_chat, "_resolve_provider_instance", lambda *_args, **_kwargs: provider)
    monkeypatch.setattr(cloud_chat, "_build_cloud_context", build_context)

    request = CloudChatRequest(
        provider="mock",
        api_key="test-key",
        model="mock-cloud-model",
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
    )

    response = asyncio.run(cloud_chat.cloud_chat_stream(request))
    body = asyncio.run(_collect_stream_body(response))

    assert _count_delta_events(body) == 1
    assert '"type": "done"' in body or '"type":"done"' in body
    assert "data: [DONE]" in body


def test_provider_stream_probe_persists_success_metadata(monkeypatch):
    import asyncio
    import importlib
    import uuid

    from security.encryption import secure_storage

    cloud_chat = importlib.import_module("api.cloud_chat")
    provider_id = f"mock-stream-{uuid.uuid4().hex[:8]}"
    secure_storage.store(f"cloud_{provider_id}_key", {"api_key": "test-key", "default_model": "mock-cloud-model"})
    monkeypatch.setattr(cloud_chat, "_resolve_provider_instance", lambda *_args, **_kwargs: _StreamingProvider(["a", "b", "c"]))

    try:
        result = asyncio.run(cloud_chat.test_provider_stream(provider_id))
        key_data = secure_storage.get(f"cloud_{provider_id}_key") or {}
        assert result["streaming_supported"] is True
        assert result["streaming_chunks"] == 3
        assert key_data["streaming_status"] == "supported"
        assert key_data["streaming_supported"] is True
        assert key_data["streaming_chunks"] == 3
    finally:
        secure_storage.delete(f"cloud_{provider_id}_key")


def test_set_api_key_preserves_streaming_metadata():
    import asyncio
    import uuid

    from api.cloud_chat import APIKeyRequest, set_api_key
    from security.encryption import secure_storage

    provider_id = f"mock-preserve-{uuid.uuid4().hex[:8]}"
    secure_storage.store(
        f"cloud_{provider_id}_key",
        {
            "api_key": "old-key",
            "streaming_status": "supported",
            "streaming_supported": True,
            "streaming_chunks": 5,
        },
    )

    try:
        asyncio.run(set_api_key(APIKeyRequest(provider=provider_id, api_key="", name="Mock", models=["mock-model"])))
        key_data = secure_storage.get(f"cloud_{provider_id}_key") or {}
        assert key_data["streaming_status"] == "supported"
        assert key_data["streaming_supported"] is True
        assert key_data["streaming_chunks"] == 5
    finally:
        secure_storage.delete(f"cloud_{provider_id}_key")
        cloud_chat = __import__("api.cloud_chat", fromlist=["_delete_custom_provider_id"])
        cloud_chat._delete_custom_provider_id(provider_id)


async def _collect_stream_body(response) -> str:
    chunks = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8"))
        else:
            chunks.append(str(chunk))
    return "".join(chunks)

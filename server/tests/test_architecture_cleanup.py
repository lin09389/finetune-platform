from __future__ import annotations

import importlib
import json
import sys

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

workspace_api = importlib.import_module("api.workspace")
chat_session = importlib.import_module("api.chat.session")
chat_branch_api = importlib.import_module("api.chat_branch")
cua_api = importlib.import_module("api.cua")
heartbeat_api = importlib.import_module("api.heartbeat")
gateway_routes = importlib.import_module("api.gateway_api.routes")
main_module = importlib.import_module("main")
ocr_api = importlib.import_module("api.ocr")
knowledge_routes = importlib.import_module("api.knowledge.routes")
inference_routes = importlib.import_module("api.inference.routes")

from gateway.cross_agent import CrossAgentCommunicator  # noqa: E402
from gateway.device_auth import DeviceAuthManager  # noqa: E402
from heartbeat import HeartbeatScheduler  # noqa: E402

from api.chat.routes import SendMessageRequest, send_message  # noqa: E402
from api.chat_branch import (  # noqa: E402
    CURRENT_BRANCH_METADATA_KEY,
    MESSAGE_BRANCH_ID_METADATA_KEY,
    MESSAGE_MERGED_FROM_BRANCH_METADATA_KEY,
    MESSAGE_PARENT_ID_METADATA_KEY,
    CreateBranchRequest,
    create_branch,
    get_message_tree,
    list_branches,
    merge_branch,
    switch_branch,
)  # noqa: E402
from api.cua import (  # noqa: E402
    RecordLoadRequest,
    RecordSaveRequest,
    clear_recorded_actions,
    get_action_recorder,
    load_recorded_actions,
    save_recorded_actions,
)  # noqa: E402
from cua.recorder import RecordedAction  # noqa: E402
from security.jwt_auth import Role, TokenPayload  # noqa: E402


class _VectorStoreStub:
    def __init__(self) -> None:
        self.collections: dict[str, list[dict]] = {}

    def get_or_create_collection(self, name: str):
        self.collections.setdefault(name, [])
        return name

    def get_collection_stats(self, name: str):
        return {"count": len(self.collections.get(name, []))}

    def list_documents(self, name: str):
        return list(self.collections.get(name, []))

    def delete_collection(self, name: str):
        self.collections.pop(name, None)


@pytest.mark.asyncio
async def test_workspace_metadata_persists(tmp_path, monkeypatch):
    metadata_file = tmp_path / "metadata.json"
    monkeypatch.setattr(workspace_api, "WORKSPACE_METADATA_FILE", metadata_file)
    monkeypatch.setattr(workspace_api, "workspaces", {})
    monkeypatch.setattr(workspace_api, "get_vector_store", lambda: _VectorStoreStub())

    # Call the route function directly (no FastAPI DI), so pass an explicit user.
    created = await workspace_api.create_workspace(
        workspace_api.WorkspaceCreate(name="Persistent", description="test", local_path=str(tmp_path)),
        current_user=TokenPayload(
            user_id="test-user",
            username="tester",
            role=Role.USER,
            permissions=["workspace:local"],
        ),
    )

    assert metadata_file.exists()
    payload = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert created.id in payload
    assert payload[created.id]["name"] == "Persistent"
    assert payload[created.id]["local_path"] == str(tmp_path.resolve())


@pytest.mark.asyncio
async def test_cua_record_save_load_and_clear(tmp_path, monkeypatch):
    recorder = get_action_recorder()
    recorder.clear_actions()
    recorder._actions = [
        RecordedAction(action_type="mouse_move", timestamp=0.1, data={"x": 10, "y": 20})
    ]

    monkeypatch.setattr(cua_api, "get_recordings_dir", lambda: tmp_path)

    saved = await save_recorded_actions(RecordSaveRequest(filename="session-one"))
    assert saved["success"] is True
    assert (tmp_path / "session-one.json").exists()

    recorder.clear_actions()
    loaded = await load_recorded_actions(RecordLoadRequest(filepath="session-one.json"))
    assert loaded["success"] is True
    assert recorder.get_action_count() == 1

    cleared = await clear_recorded_actions()
    assert cleared["success"] is True
    assert recorder.get_action_count() == 0


@pytest.mark.asyncio
async def test_chat_branch_merge_reparents_messages_into_main_tree(tmp_path):
    chat_session._session_manager = chat_session.SessionManager(storage_path=str(tmp_path / "sessions"))
    manager = chat_session.get_session_manager()
    session = manager.create_session(title="Branch Test")
    await send_message(session.id, SendMessageRequest(content="root", role="user"))
    session = manager.get_session(session.id)
    root_message = session.messages[0]

    await send_message(session.id, SendMessageRequest(content="trunk reply", role="assistant"))
    session = manager.get_session(session.id)
    trunk_message = session.messages[-1]

    response = await create_branch(
        CreateBranchRequest(session_id=session.id, from_message_id=root_message.id, branch_name="alt")
    )
    assert response.success is True

    switched = await switch_branch(session.id, response.branch.id)
    assert switched["success"] is True

    await send_message(session.id, SendMessageRequest(content="branch reply", role="assistant"))
    await send_message(session.id, SendMessageRequest(content="branch follow-up", role="user"))

    session = manager.get_session(session.id)
    branch_first_message = session.messages[-2]
    branch_second_message = session.messages[-1]
    assert branch_first_message.metadata[MESSAGE_PARENT_ID_METADATA_KEY] == root_message.id
    assert branch_first_message.metadata[MESSAGE_BRANCH_ID_METADATA_KEY] == response.branch.id
    assert branch_second_message.metadata[MESSAGE_PARENT_ID_METADATA_KEY] == branch_first_message.id
    assert branch_second_message.metadata[MESSAGE_BRANCH_ID_METADATA_KEY] == response.branch.id

    manager.update_session_metadata(session.id, {CURRENT_BRANCH_METADATA_KEY: None})

    merged = await merge_branch(session.id, response.branch.id)
    assert merged["success"] is True
    assert merged["merged_count"] == 2
    assert merged["target_branch_id"] is None

    session = manager.get_session(session.id)
    branch_first_message = session.messages[-2]
    branch_second_message = session.messages[-1]

    branches = await list_branches(session.id)
    assert branches.branches == []
    assert branch_first_message.metadata[MESSAGE_PARENT_ID_METADATA_KEY] == trunk_message.id
    assert MESSAGE_BRANCH_ID_METADATA_KEY not in branch_first_message.metadata
    assert branch_first_message.metadata[MESSAGE_MERGED_FROM_BRANCH_METADATA_KEY] == response.branch.id
    assert branch_second_message.metadata[MESSAGE_PARENT_ID_METADATA_KEY] == branch_first_message.id
    assert MESSAGE_BRANCH_ID_METADATA_KEY not in branch_second_message.metadata
    assert branch_second_message.metadata[MESSAGE_MERGED_FROM_BRANCH_METADATA_KEY] == response.branch.id

    tree = await get_message_tree(session.id)
    assert tree.root_id == root_message.id
    assert tree.nodes[root_message.id].children_ids == [trunk_message.id]
    assert tree.nodes[trunk_message.id].children_ids == [branch_first_message.id]
    assert tree.nodes[branch_first_message.id].children_ids == [branch_second_message.id]


@pytest.mark.asyncio
async def test_training_root_alias_is_removed():
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/training")

    assert response.status_code in {404, 405}


@pytest.mark.asyncio
async def test_chat_compat_routes_are_removed():
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_response = await client.post("/chat", json={"title": "compat route"})
        get_response = await client.get("/chat/test-session")
        delete_response = await client.delete("/chat/test-session")
        message_response = await client.post(
            "/chat/test-session/messages",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

    assert create_response.status_code in {404, 405}
    assert get_response.status_code in {404, 405}
    assert delete_response.status_code in {404, 405}
    assert message_response.status_code in {404, 405}


@pytest.mark.asyncio
async def test_heartbeat_missing_task_operations_raise_404(monkeypatch):
    scheduler = HeartbeatScheduler()
    monkeypatch.setattr(heartbeat_api, "get_heartbeat_scheduler", lambda: scheduler)

    with pytest.raises(HTTPException) as exc:
        await heartbeat_api.delete_task("missing-task")
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await heartbeat_api.enable_task("missing-task")
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await heartbeat_api.disable_task("missing-task")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_heartbeat_create_task_returns_task_payload(monkeypatch):
    scheduler = HeartbeatScheduler()
    monkeypatch.setattr(heartbeat_api, "get_heartbeat_scheduler", lambda: scheduler)

    response = await heartbeat_api.create_task(
        heartbeat_api.TaskCreateRequest(
            name="demo",
            description="desc",
            schedule="60",
            task_type="check",
            enabled=True,
            config={"scope": "test"},
        )
    )

    assert response["success"] is True
    assert response["task"]["name"] == "demo"
    assert response["task"]["task_type"] == "check"
    assert response["task"]["config"] == {"scope": "test"}


@pytest.mark.asyncio
async def test_heartbeat_list_and_get_task_return_canonical_fields(monkeypatch):
    scheduler = HeartbeatScheduler()
    task = heartbeat_api.HeartbeatTask(
        id="task-1",
        name="demo",
        description="desc",
        schedule="60",
        enabled=True,
        metadata={"type": "report", "scope": "test"},
    )
    scheduler.add_task(task)
    monkeypatch.setattr(heartbeat_api, "get_heartbeat_scheduler", lambda: scheduler)

    tasks = await heartbeat_api.list_tasks()
    fetched = await heartbeat_api.get_task("task-1")

    assert tasks["tasks"][0]["task_type"] == "report"
    assert tasks["tasks"][0]["config"] == {"scope": "test"}
    assert fetched["task_type"] == "report"
    assert fetched["config"] == {"scope": "test"}


@pytest.mark.asyncio
async def test_gateway_missing_entities_raise_http_errors(monkeypatch):
    auth_manager = DeviceAuthManager(secret_key="test")
    communicator = CrossAgentCommunicator()
    monkeypatch.setattr(gateway_routes, "get_device_auth_manager", lambda: auth_manager)
    monkeypatch.setattr(gateway_routes, "get_cross_agent_communicator", lambda: communicator)

    with pytest.raises(HTTPException) as exc:
        await gateway_routes.unregister_device("missing-device")
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await gateway_routes.set_device_permissions("missing-device", level="user")
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await gateway_routes.send_and_wait(
            gateway_routes.MessageSendRequest(target_agent="missing-agent", payload={"hello": "world"})
        )
    assert exc.value.status_code == 504

    with pytest.raises(HTTPException) as exc:
        await gateway_routes.broadcast_message(payload={"hello": "world"})
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_gateway_devices_include_canonical_fields_and_permissions(monkeypatch):
    auth_manager = DeviceAuthManager(secret_key="test")
    monkeypatch.setattr(gateway_routes, "get_device_auth_manager", lambda: auth_manager)

    registered = await gateway_routes.register_device(
        gateway_routes.DeviceRegisterRequest(
            device_id="device-1",
            device_type="web",
            device_name="Demo Device",
            metadata={"source": "test"},
        )
    )
    assert registered["success"] is True

    devices = await gateway_routes.list_devices()
    device = devices["devices"][0]

    assert device["id"] == "device-1"
    assert device["device_id"] == "device-1"
    assert device["name"] == "Demo Device"
    assert device["device_name"] == "Demo Device"
    assert device["type"] == "web"
    assert device["device_type"] == "web"
    assert "chat" in device["permissions"]


@pytest.mark.asyncio
async def test_cua_screen_info_returns_canonical_and_legacy_fields(monkeypatch):
    class _ScreenSize:
        def __init__(self, x: int, y: int) -> None:
            self.x = x
            self.y = y

    class _ScreenCaptureStub:
        def get_monitor_count(self) -> int:
            return 2

        def get_screen_size(self, index: int) -> _ScreenSize:
            return _ScreenSize(1920 if index == 0 else 1280, 1080 if index == 0 else 720)

    monkeypatch.setattr(cua_api, "get_screen_capture", lambda: _ScreenCaptureStub())

    payload = await cua_api.get_screen_info()

    assert payload["width"] == 1920
    assert payload["height"] == 1080
    assert payload["monitorCount"] == 2
    assert payload["monitor_count"] == 2
    assert len(payload["monitors"]) == 2


@pytest.mark.asyncio
async def test_cua_screenshot_returns_image_aliases(monkeypatch):
    class _ScreenCaptureStub:
        async def capture_screen_async(self, monitor: int):
            class _Result:
                width = 1920
                height = 1080
                format = "png"
                base64 = "ZmFrZS1pbWFnZQ=="
                monitor_index = monitor

            return _Result()

    monkeypatch.setattr(cua_api, "get_screen_capture", lambda: _ScreenCaptureStub())

    payload = await cua_api.take_screenshot(cua_api.ScreenshotRequest(monitor=0))

    assert payload["image"] == "ZmFrZS1pbWFnZQ=="
    assert payload["image_base64"] == "ZmFrZS1pbWFnZQ=="


@pytest.mark.asyncio
async def test_ocr_unavailable_returns_explicit_dependency_error(monkeypatch):
    monkeypatch.setattr(ocr_api, "TESSERACT_AVAILABLE", False)
    monkeypatch.setattr(ocr_api, "RAPIDOCR_AVAILABLE", False)
    monkeypatch.setattr(ocr_api, "pytesseract", None)
    monkeypatch.setattr(ocr_api, "Image", None)

    with pytest.raises(HTTPException) as exc:
        await ocr_api.ocr_image(ocr_api.OCRRequest(image_base64="ZmFrZQ==", language="ch"))

    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "dependency_missing"
    assert exc.value.detail["status"] == "unavailable"


@pytest.mark.asyncio
async def test_knowledge_embedder_status_returns_explicit_unavailable_payload(monkeypatch):
    def _raise_embedder_error():
        raise RuntimeError("embedder backend unavailable")

    monkeypatch.setitem(sys.modules, "rag.embedder", type("EmbedderModule", (), {"get_embedder": staticmethod(_raise_embedder_error)}))

    payload = await knowledge_routes.get_embedder_status()

    assert payload["loaded"] is False
    assert "embedder backend unavailable" in payload["error"]


@pytest.mark.asyncio
async def test_knowledge_embedder_preload_raises_explicit_failure(monkeypatch):
    def _raise_embedder_error():
        raise RuntimeError("embedder preload unavailable")

    monkeypatch.setitem(sys.modules, "rag.embedder", type("EmbedderModule", (), {"get_embedder": staticmethod(_raise_embedder_error)}))

    with pytest.raises(HTTPException) as exc:
        await knowledge_routes.preload_embedder()

    assert exc.value.status_code == 500
    assert "预加载失败" in exc.value.detail


@pytest.mark.asyncio
async def test_inference_ollama_status_returns_explicit_runtime_flags_when_unavailable(monkeypatch):
    class _SchedulerStub:
        async def is_backend_available(self, backend: str) -> bool:
            assert backend == "ollama"
            return False

        async def list_models(self, backend: str):
            raise AssertionError("list_models should not be called when backend is unavailable")

    monkeypatch.setattr(inference_routes, "get_scheduler", lambda: _SchedulerStub())
    monkeypatch.setattr(inference_routes.settings, "ollama_base_url", "http://ollama.local:11434")

    payload = await inference_routes.get_ollama_status()

    assert payload["running"] is False
    assert payload["base_url"] == "http://ollama.local:11434"
    assert payload["models"] == []


@pytest.mark.asyncio
async def test_inference_backends_reports_ollama_unavailable_without_hiding_backend(monkeypatch):
    class _SchedulerStub:
        _default_backend = "huggingface"

        async def is_backend_available(self, backend: str) -> bool:
            return backend == "huggingface"

    monkeypatch.setattr(inference_routes, "get_scheduler", lambda: _SchedulerStub())

    payload = await inference_routes.list_backends()
    backends = {backend.id: backend for backend in payload.backends}

    assert payload.current == "huggingface"
    assert backends["huggingface"].available is True
    assert backends["ollama"].available is False

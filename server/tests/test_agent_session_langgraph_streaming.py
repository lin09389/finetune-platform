from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from core.config import settings


class _MockCloudProvider:
    def get_default_model(self):
        return "mock-model"

    async def chat(self, messages, model, api_key):
        return "mock response"


def _mock_resolve_cloud_provider_config(session):
    return _MockCloudProvider(), "mock-key", session.get("model") or "mock-model"


def _service(tmp_path: Path) -> AgentSessionService:
    return AgentSessionService(AgentSessionRepository(str(tmp_path / f"agent_session_langgraph_streaming_{uuid.uuid4().hex}.db")))


def _patch_provider(monkeypatch, service):
    monkeypatch.setattr(service, "_resolve_cloud_provider_config", _mock_resolve_cloud_provider_config)


def test_agent_session_langgraph_streaming_runs_through_graph(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "agent_session_langgraph_enabled", True)
    monkeypatch.setattr("agent_session.service.secure_storage.get", lambda _key: {"api_key": "mock-key"})
    service = _service(tmp_path)
    _patch_provider(monkeypatch, service)
    session = service.create_session(
        AgentSessionCreate(title="langgraph stream", project_path=str(Path.cwd()), provider="mock", model="mock-model")
    )

    async def model_call(_messages):
        raise AssertionError("non-stream fallback should not be used in this scenario")

    async def stream_model_call(_messages):
        for token in ["最终", "结果", "：", "流式", "LangGraph"]:
            yield {"content": token}

    monkeypatch.setattr(service, "_cloud_model_call", lambda _session: model_call)
    monkeypatch.setattr(service, "_cloud_stream_model_call", lambda _session: stream_model_call)

    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="使用流式 LangGraph")))
    events = service.list_events(session.id)

    assert result.status == "completed"
    assert result.metadata["runtime"] == "langgraph"
    assert result.metadata["execution_trace"]["runtime"] == "langgraph"
    assert result.metadata["execution_trace"]["model_entry"] == "chat_stream"
    assert result.metadata["execution_trace"]["fallback_used"] is False
    assert any(event["event_type"] == "model_stream_started" for event in events)
    assert any(event["event_type"] == "part_delta" for event in events)
    assert any(event["event_type"] == "model_stream_completed" for event in events)
    assert result.parts[-1].type == "summary"
    assert result.parts[-1].content == "最终结果：流式LangGraph"


def test_agent_session_cloud_provider_missing_key_fails_fast(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "agent_session_langgraph_enabled", True)
    monkeypatch.setattr("agent_session.service.secure_storage.get", lambda _key: {})
    service = _service(tmp_path)
    session = service.create_session(
        AgentSessionCreate(title="missing key", project_path=str(Path.cwd()), provider="mock", model="mock-model")
    )

    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="调用云端模型")))
    events = service.list_events(session.id)

    assert result.status == "needs_manual_review"
    assert result.parts[-1].type == "summary"
    assert "未配置 mock 的 API Key" in result.parts[-1].content
    assert result.metadata["execution_trace"]["failure_code"] == "missing_api_key"
    assert result.metadata["execution_trace"]["fallback_used"] is False
    assert any(event["event_type"] == "agent_chain_failed" for event in events)


def test_agent_session_langgraph_streaming_supports_multi_turn_tool_loop(tmp_path: Path, monkeypatch):
    workspace = Path.cwd()
    run_dir = workspace / "tmp" / f"agent-langgraph-stream-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "hello.txt"
    target.write_text("hello from streaming langgraph", encoding="utf-8")
    rel = target.relative_to(workspace).as_posix()

    monkeypatch.setattr(settings, "agent_session_langgraph_enabled", True)
    monkeypatch.setattr("agent_session.service.secure_storage.get", lambda _key: {"api_key": "mock-key"})
    service = _service(tmp_path)
    _patch_provider(monkeypatch, service)
    session = service.create_session(
        AgentSessionCreate(title="streaming tool loop", project_path=str(workspace), provider="mock", model="mock-model")
    )

    async def model_call(_messages):
        raise AssertionError("streaming flow should finish without non-stream fallback")

    async def stream_model_call(messages):
        saw_tool_result = any("工具结果" in str(message.get("content") or "") for message in messages)
        response = (
            json.dumps({"tool": "finalize", "arguments": {"summary": "流式工具链路完成。"}}, ensure_ascii=False)
            if saw_tool_result
            else "我先读取目标文件。\n"
            + json.dumps({"tool": "read", "arguments": {"path": rel}}, ensure_ascii=False)
        )
        for index in range(0, len(response), 5):
            yield {"content": response[index:index + 5]}

    monkeypatch.setattr(service, "_cloud_model_call", lambda _session: model_call)
    monkeypatch.setattr(service, "_cloud_stream_model_call", lambda _session: stream_model_call)

    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="读取 hello.txt 并总结")))
        events = service.list_events(session.id)

        assert result.status == "completed"
        assert [part.type for part in result.parts] == ["text", "text", "tool_call", "tool_result", "summary"]
        assert result.parts[-1].content == "流式工具链路完成。"
        assert sum(1 for event in events if event["event_type"] == "model_stream_started") >= 2
        assert any(event["event_type"] == "tool_call_started" for event in events)
        assert any(event["event_type"] == "summary_completed" for event in events)
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_agent_session_langgraph_streaming_marks_protocol_only_text(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "agent_session_langgraph_enabled", True)
    monkeypatch.setattr("agent_session.service.secure_storage.get", lambda _key: {"api_key": "mock-key"})
    service = _service(tmp_path)
    _patch_provider(monkeypatch, service)
    session = service.create_session(
        AgentSessionCreate(title="protocol only", project_path=str(Path.cwd()), provider="mock", model="mock-model")
    )

    async def model_call(_messages):
        raise AssertionError("streaming flow should not fall back here")

    async def stream_model_call(messages):
        saw_tool_result = any("工具结果" in str(message.get("content") or "") for message in messages)
        response = (
            json.dumps({"tool": "finalize", "arguments": {"summary": "完成。"}}, ensure_ascii=False)
            if saw_tool_result
            else json.dumps({"tool": "collect_context", "arguments": {}}, ensure_ascii=False)
        )
        for index in range(0, len(response), 8):
            yield {"content": response[index:index + 8]}

    monkeypatch.setattr(service, "_cloud_model_call", lambda _session: model_call)
    monkeypatch.setattr(service, "_cloud_stream_model_call", lambda _session: stream_model_call)

    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="只输出工具请求")))

    protocol_parts = [
        part
        for part in result.parts
        if part.type == "text" and bool((part.payload or {}).get("protocol_only"))
    ]
    assert protocol_parts
    assert protocol_parts[0].content == ""
    assert result.parts[-1].type == "summary"


def test_agent_session_langgraph_streaming_falls_back_to_non_stream_within_graph(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "agent_session_langgraph_enabled", True)
    monkeypatch.setattr("agent_session.service.secure_storage.get", lambda _key: {"api_key": "mock-key"})
    service = _service(tmp_path)
    _patch_provider(monkeypatch, service)
    session = service.create_session(
        AgentSessionCreate(title="stream failure", project_path=str(Path.cwd()), provider="mock", model="mock-model")
    )

    async def model_call(_messages):
        return json.dumps({"tool": "finalize", "arguments": {"summary": "同一 graph run 内已回退。"}}, ensure_ascii=False)

    async def stream_model_call(_messages):
        raise RuntimeError("stream failed in graph")
        yield

    monkeypatch.setattr(service, "_cloud_model_call", lambda _session: model_call)
    monkeypatch.setattr(service, "_cloud_stream_model_call", lambda _session: stream_model_call)

    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="测试流式失败回退")))
    events = service.list_events(session.id)

    assert result.status == "completed"
    assert result.metadata["runtime"] == "langgraph"
    assert any(event["event_type"] == "model_stream_failed" for event in events)
    assert result.metadata["streaming_diagnostics"]["status"] == "failed_then_fallback"
    assert result.parts[-1].type == "summary"
    assert result.parts[-1].content == "同一 graph run 内已回退。"

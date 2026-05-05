from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService


def _service(tmp_path: Path) -> AgentSessionService:
    return AgentSessionService(AgentSessionRepository(str(tmp_path / f"agent-token-stream-{uuid.uuid4().hex}.db")))


async def _stream_tokens(tokens: list[str]):
    async def stream_fn(messages):
        for token in tokens:
            yield {"content": token, "delta": True}

    return stream_fn


def test_stream_creates_running_text_part_and_completes(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="token-stream", project_path=str(Path.cwd())))

    tokens = ["你好", "，", "我", "是", "Agent"]
    full_text = "".join(tokens)

    async def model_call(messages):
        return full_text

    async def stream_model_call(messages):
        for token in tokens:
            yield {"content": token, "delta": True}

    result = asyncio.run(service.processor.prompt(
        session.id, "测试流式",
        model_call=model_call,
        stream_model_call=stream_model_call,
    ))

    parts = result.get("parts", [])
    text_parts = [p for p in parts if p.get("type") == "text" and p.get("title") != "请求"]
    assert len(text_parts) >= 1, f"Expected at least 1 non-request text part, got {[p.get('title') for p in parts if p.get('type') == 'text']}"
    assert text_parts[0].get("content") == full_text, f"Expected '{full_text}', got '{text_parts[0].get('content')}'"
    assert text_parts[0].get("status") == "completed"

    events = service.repository.list_events(session.id)
    stream_started = [e for e in events if e.get("event_type") == "model_stream_started"]
    stream_completed = [e for e in events if e.get("event_type") == "model_stream_completed"]
    delta_events = [e for e in events if e.get("event_type") == "part_delta"]

    assert len(stream_started) >= 1, "Expected model_stream_started event"
    assert len(stream_completed) >= 1, "Expected model_stream_completed event"
    assert len(delta_events) >= 1, "Expected part_delta events"


def test_stream_with_tool_call_parses_correctly(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = workspace / "tmp" / f"agent-token-stream-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "test_file.txt"
    target.write_text("hello world", encoding="utf-8")
    rel = target.relative_to(workspace).as_posix()

    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="stream-tool", project_path=str(workspace)))

    first_response = "我来读取这个文件。\n" + json.dumps({"tool": "read", "arguments": {"path": rel}}, ensure_ascii=False)
    second_response = json.dumps({"tool": "finalize", "arguments": {"summary": "读取完成。"}}, ensure_ascii=False)
    responses = [first_response, second_response]
    call_index = {"count": 0}

    async def model_call(messages):
        idx = call_index["count"]
        call_index["count"] += 1
        return responses[idx]

    async def stream_model_call(messages):
        idx = call_index["count"]
        call_index["count"] += 1
        full_text = responses[idx]
        tokens = [full_text[i:i+4] for i in range(0, len(full_text), 4)]
        for token in tokens:
            yield {"content": token, "delta": True}

    try:
        result = asyncio.run(service.processor.prompt(
            session.id, "读取文件",
            model_call=model_call,
            stream_model_call=stream_model_call,
        ))

        parts = result.get("parts", [])
        part_types = [p.get("type") for p in parts]
        assert "tool_call" in part_types, f"Expected tool_call in part types: {part_types}"
        assert "summary" in part_types, f"Expected summary in part types: {part_types}"

        events = service.repository.list_events(session.id)
        tool_events = [e for e in events if e.get("event_type") == "tool_call_started"]
        assert len(tool_events) >= 1, "Expected tool_call_started event"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_stream_failure_falls_back_to_non_streaming(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="stream-fallback", project_path=str(Path.cwd())))

    called_fallback = {"count": 0}

    async def model_call(messages):
        called_fallback["count"] += 1
        return json.dumps({"tool": "finalize", "arguments": {"summary": "回退成功。"}}, ensure_ascii=False)

    async def stream_model_call(messages):
        raise RuntimeError("stream failed")
        yield

    result = asyncio.run(service.processor.prompt(
        session.id, "测试回退",
        model_call=model_call,
        stream_model_call=stream_model_call,
    ))

    assert called_fallback["count"] >= 1, f"Expected fallback model_call to be used, got {called_fallback['count']} calls"
    parts = result.get("parts", [])
    text_parts = [p for p in parts if p.get("type") == "text" and p.get("title") != "请求" and p.get("title") != "生成中"]
    summary_parts = [p for p in parts if p.get("type") == "summary"]
    has_fallback_content = (len(text_parts) >= 1 and "回退成功" in (text_parts[0].get("content") or "")) or (len(summary_parts) >= 1 and "回退成功" in (summary_parts[0].get("content") or ""))
    assert has_fallback_content, f"Fallback content not found. Parts: {[(p.get('type'), p.get('content', '')[:50]) for p in parts]}"


def test_stream_delta_events_have_correct_payload(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="delta-payload", project_path=str(Path.cwd())))

    tokens = ["Hello", " ", "World"]

    async def model_call(messages):
        return "Hello World"

    async def stream_model_call(messages):
        for token in tokens:
            yield {"content": token, "delta": True}

    result = asyncio.run(service.processor.prompt(
        session.id, "测试delta payload",
        model_call=model_call,
        stream_model_call=stream_model_call,
    ))

    events = service.repository.list_events(session.id)
    delta_events = [e for e in events if e.get("event_type") == "part_delta"]
    assert len(delta_events) >= 1, f"Expected at least 1 part_delta event, got {len(delta_events)}"

    for event in delta_events:
        payload = event.get("payload", {})
        assert "part_id" in payload, f"Expected part_id in delta payload: {payload}"
        assert "streaming" in payload, f"Expected streaming in delta payload: {payload}"
        assert payload.get("part_type") == "text", f"Expected part_type text: {payload}"


def test_stream_chunk_delta_has_typed_payload_and_part_snapshot(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="chunk-delta", project_path=str(Path.cwd())))

    tokens = ["Hello", " ", "Chunk"]

    async def model_call(messages):
        return "Hello Chunk"

    async def stream_model_call(messages):
        for token in tokens:
            yield {"content": token, "delta": True}

    asyncio.run(service.processor.prompt(
        session.id, "测试 chunk delta",
        model_call=model_call,
        stream_model_call=stream_model_call,
    ))

    events = service.repository.list_events(session.id)
    delta_event = next(event for event in events if event.get("event_type") == "part_delta")
    chunk = service.build_stream_chunk(delta_event)

    assert chunk["chunk_type"] == "part_delta"
    assert chunk["session_id"] == session.id
    assert chunk["part"]["id"] == delta_event["payload"]["part_id"]
    assert chunk["part"]["type"] == "text"
    assert chunk["part"]["status"] == "running"
    assert chunk["part"]["content"] == delta_event["payload"]["content"]
    assert chunk["content"] == delta_event["payload"]["content"]


def test_non_streaming_still_works(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="no-stream", project_path=str(Path.cwd())))

    async def model_call(messages):
        return json.dumps({"tool": "finalize", "arguments": {"summary": "正常完成。"}}, ensure_ascii=False)

    result = asyncio.run(service.processor.prompt(
        session.id, "正常测试",
        model_call=model_call,
        stream_model_call=None,
    ))

    parts = result.get("parts", [])
    summary_parts = [p for p in parts if p.get("type") == "summary"]
    assert len(summary_parts) >= 1
    assert "正常完成" in (summary_parts[0].get("content") or "")

    events = service.repository.list_events(session.id)
    stream_events = [e for e in events if e.get("event_type") in ("model_stream_started", "model_stream_completed", "part_delta")]
    assert len(stream_events) == 0, "Expected no stream events for non-streaming call"


def test_get_session_recovers_full_content_after_streaming(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="recovery", project_path=str(Path.cwd())))

    full_text = "这是完整的流式输出内容，包含很多文字。"

    async def model_call(messages):
        return full_text

    async def stream_model_call(messages):
        for i in range(0, len(full_text), 6):
            yield {"content": full_text[i:i+6], "delta": True}

    asyncio.run(service.processor.prompt(
        session.id, "恢复测试",
        model_call=model_call,
        stream_model_call=stream_model_call,
    ))

    recovered = service.get_session(session.id)
    text_parts = [p for p in recovered.parts if p.type == "text" and p.title != "请求"]
    assert len(text_parts) >= 1, f"Expected at least 1 non-request text part, got: {[p.title for p in recovered.parts if p.type == 'text']}"
    assert text_parts[0].content == full_text, f"Expected full content, got: {text_parts[0].content}"

    all_events = service.list_events(session.id)
    recovered_event_ids = {e['id'] for e in all_events}
    assert len(recovered_event_ids) == len(all_events), "Event IDs should be unique"


def test_streaming_finalize_no_duplicate_text_part(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="no-dup-text", project_path=str(Path.cwd())))

    first_response = "我来帮助你。\n" + json.dumps({"tool": "read", "arguments": {"path": "README.md"}}, ensure_ascii=False)
    second_response = json.dumps({"tool": "finalize", "arguments": {"summary": "任务完成。"}}, ensure_ascii=False)
    responses = [first_response, second_response]
    call_index = {"count": 0}

    async def model_call(messages):
        idx = call_index["count"]
        call_index["count"] += 1
        return responses[idx]

    async def stream_model_call(messages):
        idx = call_index["count"]
        call_index["count"] += 1
        full = responses[idx]
        for i in range(0, len(full), 8):
            yield {"content": full[i:i+8], "delta": True}

    workspace = Path.cwd()
    result = asyncio.run(service.processor.prompt(
        session.id, "去重测试",
        model_call=model_call,
        stream_model_call=stream_model_call,
    ))

    parts = result.get("parts", [])
    text_parts = [p for p in parts if p.get("type") == "text" and p.get("title") != "请求"]
    summary_parts = [p for p in parts if p.get("type") == "summary"]
    text_contents = [p.get("content", "")[:30] for p in text_parts]
    assert len(text_parts) <= 1, f"Expected at most 1 streaming text part, got {len(text_parts)}: {text_contents}"
    assert len(summary_parts) == 1, f"Expected exactly 1 summary part, got {len(summary_parts)}"
    assert "任务完成" in summary_parts[0].get("content", "")


def test_streaming_finalize_converted_to_summary(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="finalize-summary", project_path=str(Path.cwd())))

    summary_text = "流式finalize转为summary"
    response = json.dumps({"tool": "finalize", "arguments": {"summary": summary_text}}, ensure_ascii=False)

    async def model_call(messages):
        return response

    async def stream_model_call(messages):
        for i in range(0, len(response), 8):
            yield {"content": response[i:i+8], "delta": True}

    result = asyncio.run(service.processor.prompt(
        session.id, "finalize转summary",
        model_call=model_call,
        stream_model_call=stream_model_call,
    ))

    parts = result.get("parts", [])
    summary_parts = [p for p in parts if p.get("type") == "summary"]
    text_parts = [p for p in parts if p.get("type") == "text" and p.get("title") != "请求"]
    assert len(summary_parts) == 1, f"Expected exactly 1 summary, got {len(summary_parts)}"
    assert summary_parts[0].get("content") == summary_text
    assert len(text_parts) == 0, f"Expected no stray text parts, got {[p.get('content')[:30] for p in text_parts]}"


def test_streaming_summary_does_not_create_duplicate_summary(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="no-dup-summary", project_path=str(Path.cwd())))

    summary_text = "流式摘要测试完成"
    response = json.dumps({"tool": "finalize", "arguments": {"summary": summary_text}}, ensure_ascii=False)

    async def model_call(messages):
        return response

    async def stream_model_call(messages):
        for i in range(0, len(response), 8):
            yield {"content": response[i:i+8], "delta": True}

    result = asyncio.run(service.processor.prompt(
        session.id, "摘要去重",
        model_call=model_call,
        stream_model_call=stream_model_call,
    ))

    parts = result.get("parts", [])
    summary_parts = [p for p in parts if p.get("type") == "summary"]
    assert len(summary_parts) == 1, f"Expected exactly 1 summary part, got {len(summary_parts)}: {[p.get('content')[:30] for p in summary_parts]}"
    assert summary_parts[0].get("content") == summary_text


def test_stream_chunk_summary_uses_completed_part_snapshot(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="chunk-summary", project_path=str(Path.cwd())))

    response = json.dumps({"tool": "finalize", "arguments": {"summary": "完成摘要"}}, ensure_ascii=False)

    async def model_call(messages):
        return response

    async def stream_model_call(messages):
        for i in range(0, len(response), 8):
            yield {"content": response[i:i+8], "delta": True}

    asyncio.run(service.processor.prompt(
        session.id, "测试 chunk summary",
        model_call=model_call,
        stream_model_call=stream_model_call,
    ))

    events = service.repository.list_events(session.id)
    summary_event = next(event for event in events if event.get("event_type") == "summary_completed")
    chunk = service.build_stream_chunk(summary_event)

    assert chunk["chunk_type"] == "summary"
    assert chunk["session_status"] == "completed"
    assert chunk["part"] is not None
    assert chunk["part"]["type"] == "summary"
    assert chunk["part"]["status"] == "completed"
    assert chunk["part"]["content"] == "完成摘要"


def test_event_payload_contains_chunk_type_for_all_events(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="chunk-types", project_path=str(Path.cwd())))

    async def model_call(messages):
        return json.dumps({"tool": "finalize", "arguments": {"summary": "完成"}}, ensure_ascii=False)

    asyncio.run(service.processor.prompt(
        session.id, "测试chunk_type字段",
        model_call=model_call,
        stream_model_call=None,
    ))

    events = service.repository.list_events(session.id)
    assert len(events) > 0, "Expected at least 1 event"

    chunk_type_map = {
        "session_started": "status",
        "phase_change": "phase",
        "tool_call_started": "tool_call",
        "tool_call_completed": "tool_result",
        "summary_completed": "summary",
    }
    for event in events:
        payload = event.get("payload", {})
        assert "chunk_type" in payload, f"Event {event['event_type']} missing chunk_type in payload: {payload}"
        expected = chunk_type_map.get(event["event_type"])
        if expected:
            assert payload["chunk_type"] == expected, (
                f"Event {event['event_type']}: expected chunk_type={expected}, got {payload['chunk_type']}"
            )


def test_event_payload_contains_part_for_part_events(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="part-snapshots", project_path=str(Path.cwd())))

    async def model_call(messages):
        return json.dumps({"tool": "finalize", "arguments": {"summary": "快照完成"}}, ensure_ascii=False)

    asyncio.run(service.processor.prompt(
        session.id, "测试part快照",
        model_call=model_call,
        stream_model_call=None,
    ))

    events = service.repository.list_events(session.id)
    part_events = [
        e for e in events
        if e.get("payload", {}).get("part_id", "").startswith("agp_")
        and e["event_type"] not in ("session_started", "phase_change")
    ]
    assert len(part_events) > 0, "Expected at least 1 event with a part_id"

    for event in part_events:
        payload = event.get("payload", {})
        assert "part" in payload, f"Event {event['event_type']}/{event['id']} missing 'part' in payload (has part_id={payload.get('part_id')})"
        assert payload["part"] is not None, f"Event {event['event_type']} has part=None"
        assert payload["part"].get("id") == payload.get("part_id"), (
            f"Part snapshot id mismatch: part.id={payload['part'].get('id')} vs part_id={payload.get('part_id')}"
        )


def test_build_stream_chunk_uses_payload_chunk_type(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="chunk-type-override", project_path=str(Path.cwd())))

    async def model_call(messages):
        return json.dumps({"tool": "finalize", "arguments": {"summary": "类型覆盖测试"}}, ensure_ascii=False)

    asyncio.run(service.processor.prompt(
        session.id, "测试chunk_type优先级",
        model_call=model_call,
        stream_model_call=None,
    ))

    events = service.repository.list_events(session.id)
    summary_event = next(e for e in events if e["event_type"] == "summary_completed")
    chunk = service.build_stream_chunk(summary_event)

    assert chunk["chunk_type"] == "summary"
    assert chunk["chunk_type"] == summary_event["payload"]["chunk_type"]


def test_build_stream_chunk_uses_payload_part(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="part-from-payload", project_path=str(Path.cwd())))

    async def model_call(messages):
        return json.dumps({"tool": "finalize", "arguments": {"summary": "part优先测试"}}, ensure_ascii=False)

    asyncio.run(service.processor.prompt(
        session.id, "测试part优先",
        model_call=model_call,
        stream_model_call=None,
    ))

    events = service.repository.list_events(session.id)
    summary_event = next(e for e in events if e["event_type"] == "summary_completed")
    chunk = service.build_stream_chunk(summary_event)

    assert chunk["part"] is not None
    assert chunk["part"]["type"] == "summary"
    assert chunk["part"]["content"] == "part优先测试"


def test_build_session_snapshot_chunk(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="snapshot", project_path=str(Path.cwd())))

    async def model_call(messages):
        return json.dumps({"tool": "finalize", "arguments": {"summary": "snap完成"}}, ensure_ascii=False)

    asyncio.run(service.processor.prompt(
        session.id, "快照测试",
        model_call=model_call,
        stream_model_call=None,
    ))

    snapshot = service.build_session_snapshot_chunk(session.id)
    assert snapshot["chunk_type"] == "session_snapshot"
    assert snapshot["session_id"] == session.id
    assert snapshot["event_type"] == "session_snapshot"
    assert snapshot["session_status"] == "completed"
    assert snapshot["session_snapshot"] is not None
    parts = snapshot["session_snapshot"]["parts"]
    summary_parts = [p for p in parts if (p.type if hasattr(p, 'type') else p.get("type")) == "summary"]
    assert len(summary_parts) >= 1
    assert (summary_parts[0].content if hasattr(summary_parts[0], 'content') else summary_parts[0].get("content")) == "snap完成"

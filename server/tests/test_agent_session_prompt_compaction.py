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
    return AgentSessionService(AgentSessionRepository(str(tmp_path / f"agent-compact-{uuid.uuid4().hex}.db")))


def _workspace_tmp(name: str) -> Path:
    path = Path.cwd() / "tmp" / f"{name}-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_initial_prompt_is_strict_json_protocol(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="prompt", project_path=str(Path.cwd())))
    messages = service.processor._initial_messages(session.model_dump(), "分析当前执行链路，不要写文件")
    system = messages[0]["content"]

    assert "只输出 JSON 工具请求" in system
    assert '{"tool":"工具名","arguments":{...}}' in system
    assert "不要解释" in system
    assert "只读分析" in system


def test_collect_context_observation_omits_full_file_content(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("compact-context")
    target = run_dir / "feature.ts"
    target.write_text("export const VALUE = 1;\n" * 300, encoding="utf-8")
    rel = target.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="context", project_path=str(workspace)))
    captured: list[list[dict[str, str]]] = []
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {"read": [rel]}},
            {"tool": "finalize", "arguments": {"summary": "分析完成。"}},
        ]
    )

    async def model_call(messages):
        captured.append(list(messages))
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="分析 feature.ts，不要写文件")))
        observation = json.loads(captured[1][-1]["content"].split("工具结果：\n", 1)[1])

        assert result.status == "completed"
        assert rel in observation["payload"]["files"]
        assert "content" not in json.dumps(observation["payload"], ensure_ascii=False)
        assert len(captured[1][-1]["content"]) < 5000
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_read_observation_truncates_large_content(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("compact-read")
    target = run_dir / "large.txt"
    target.write_text("A" * 5000, encoding="utf-8")
    rel = target.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="read", project_path=str(workspace)))
    captured: list[list[dict[str, str]]] = []
    responses = iter(
        [
            {"tool": "read", "arguments": {"path": rel}},
            {"tool": "finalize", "arguments": {"summary": "读取完成。"}},
        ]
    )

    async def model_call(messages):
        captured.append(list(messages))
        return json.dumps(next(responses), ensure_ascii=False)

    service.model_call = model_call
    try:
        asyncio.run(service.prompt(session.id, AgentPromptRequest(content="读取大文件")))
        observation = json.loads(captured[1][-1]["content"].split("工具结果：\n", 1)[1])

        assert len(observation["payload"]["content"]) < 2200
        assert observation["payload"]["truncated"] is True
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_search_observation_limits_matches(tmp_path: Path):
    service = _service(tmp_path)
    payload = {
        "query": "VALUE",
        "matches": [{"path": f"f{i}.py", "line": i, "preview": "VALUE"} for i in range(20)],
        "touched_paths": [f"f{i}.py" for i in range(20)],
    }
    observation = service.processor._compact_observation("search", "completed", "找到 20 条匹配", payload)

    assert len(observation["payload"]["matches"]) == 8
    assert len(observation["payload"]["touched_paths"]) == 12


def test_command_observation_keeps_failure_summary_and_truncates_output(tmp_path: Path):
    service = _service(tmp_path)
    payload = {
        "command": ["python", "-m", "pytest"],
        "stdout": "O" * 5000,
        "stderr": "E" * 5000,
        "exit_code": 1,
        "failure_summary": "一个失败摘要",
    }
    observation = service.processor._compact_observation("bash_command", "failed", "命令执行失败", payload, "一个失败摘要")

    assert observation["payload"]["failure_summary"] == "一个失败摘要"
    assert len(observation["payload"]["stdout"]) < 2200
    assert len(observation["payload"]["stderr"]) < 2200


def test_plain_text_after_execution_auto_finalizes(tmp_path: Path):
    workspace = Path.cwd()
    run_dir = _workspace_tmp("compact-finalize")
    target = run_dir / "smoke.py"
    rel = target.relative_to(workspace).as_posix()
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="finalize", project_path=str(workspace)))
    responses = iter(
        [
            {"tool": "collect_context", "arguments": {"read": []}},
            {"tool": "patch", "arguments": {"payload": {"files": [{"path": rel, "content": "VALUE = 1\n"}]}}},
            "已完成 smoke 文件创建。",
        ]
    )

    async def model_call(_messages):
        value = next(responses)
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    service.model_call = model_call
    service.processor.max_iterations = 5
    try:
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="新增 smoke 文件")))

        assert result.status == "completed"
        assert result.parts[-1].type == "summary"
        assert "smoke" in result.parts[-1].content
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_plain_text_without_execution_gets_protocol_guidance_then_continues(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="protocol", project_path=str(Path.cwd())))
    responses = iter(
        [
            "我先解释一下，不输出工具。",
            {"tool": "finalize", "arguments": {"summary": "已按协议完成。"}},
        ]
    )

    async def model_call(_messages):
        value = next(responses)
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    service.model_call = model_call
    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="看看项目结构")))
    guidance = next(part for part in result.parts if part.type == "tool_result" and part.title == "协议纠偏")

    assert result.status == "completed"
    assert guidance.status == "completed"
    assert result.metadata["protocol_repair_count"] == 1


def test_repeated_protocol_failure_enters_manual_review(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="protocol fail", project_path=str(Path.cwd())))

    async def model_call(_messages):
        return "nonsense"

    service.model_call = model_call
    service.processor.max_iterations = 5
    result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="看看项目")))

    assert result.status == "needs_manual_review"
    assert result.parts[-1].type == "summary"
    assert "JSON 工具协议" in result.parts[-1].content

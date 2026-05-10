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


def test_initial_prompt_allows_natural_text_with_json_tool_protocol(tmp_path: Path):
    service = _service(tmp_path)
    session = service.create_session(AgentSessionCreate(title="prompt", project_path=str(Path.cwd())))
    messages = service.processor._initial_messages(session.model_dump(), "分析当前执行链路，不要写文件")
    system = messages[0]["content"]

    assert "自然语言说明" in system
    assert "JSON 工具请求" in system
    assert '{"tool":"工具名","arguments":{...}}' in system
    assert "JSON 数组" in system
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


def test_collect_context_observation_keeps_symbol_summary_compact(tmp_path: Path):
    service = _service(tmp_path)
    payload = {
        "goal": "修复 alpha",
        "markers": {"client_dir": True},
        "files": [{"path": "tmp/demo.ts", "content": "export function alpha() {}\n", "truncated": False}],
        "matches": [{"path": "tmp/demo.ts", "line": 1, "preview": "export function alpha() {}"}],
        "symbols": [
            {
                "symbol": "alpha",
                "engine": "ast-grep",
                "definitions": [{"path": "tmp/demo.ts", "line": 1, "kind": "function", "preview": "export function alpha() {}"}],
                "references": [{"path": "tmp/demo.ts", "line": 3, "is_definition": False, "preview": "const x = alpha()"}],
            }
        ],
        "commands": [],
        "touched_paths": ["tmp/demo.ts"],
    }

    observation = service.processor._compact_observation("collect_context", "completed", "done", payload)

    assert observation["payload"]["symbols"][0]["symbol"] == "alpha"
    assert observation["payload"]["symbols"][0]["definitions"][0]["kind"] == "function"
    assert "preview" not in json.dumps(observation["payload"]["symbols"], ensure_ascii=False)


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


def test_page_validation_observations_are_compact(tmp_path: Path):
    service = _service(tmp_path)
    probe = service.processor._compact_observation(
        "http_probe",
        "completed",
        "页面探测成功：200",
        {
            "url": "http://127.0.0.1:5173",
            "final_url": "http://127.0.0.1:5173/",
            "status_code": 200,
            "ok": True,
            "content_type": "text/html",
            "title": "Agent Probe",
            "body_excerpt": "A" * 4000,
        },
    )
    page = service.processor._compact_observation(
        "read_local_page",
        "completed",
        "页面摘要读取完成",
        {
            "url": "http://127.0.0.1:5173",
            "final_url": "http://127.0.0.1:5173/",
            "status_code": 200,
            "ok": True,
            "content_type": "text/html",
            "title": "Agent Probe",
            "headings": [{"tag": "h1", "text": "Frontend Ready"} for _ in range(10)],
            "links": [f"/item/{i}" for i in range(12)],
            "text_excerpt": "B" * 5000,
        },
    )

    assert len(probe["payload"]["body_excerpt"]) <= 800
    assert len(page["payload"]["headings"]) == 6
    assert len(page["payload"]["links"]) == 8
    assert len(page["payload"]["text_excerpt"]) <= 1200


def test_api_probe_and_network_capture_observations_are_compact(tmp_path: Path):
    service = _service(tmp_path)
    api = service.processor._compact_observation(
        "probe_json_endpoint",
        "completed",
        "JSON 接口探测成功",
        {
            "url": "http://127.0.0.1:8010/api/status",
            "final_url": "http://127.0.0.1:8010/api/status",
            "status_code": 200,
            "ok": True,
            "content_type": "application/json",
            "json_type": "dict",
            "json_preview": {"ok": True, "items": [1, 2, 3]},
            "parse_error": None,
        },
    )
    network = service.processor._compact_observation(
        "capture_network_errors",
        "failed",
        "检测到网络错误",
        {
            "url": "http://127.0.0.1:5173",
            "final_url": "http://127.0.0.1:5173/",
            "status_code": 200,
            "ok": False,
            "request_failures": [{"url": f"http://127.0.0.1:8010/api/{i}", "method": "GET", "failure": "boom"} for i in range(12)],
            "error_responses": [{"url": f"http://127.0.0.1:8010/api/{i}", "method": "GET", "status": 500} for i in range(12)],
            "console_errors": [f"err-{i}" for i in range(10)],
            "page_errors": [f"page-{i}" for i in range(10)],
            "engine": "playwright",
        },
    )

    assert api["payload"]["json_type"] == "dict"
    assert len(network["payload"]["request_failures"]) == 8
    assert len(network["payload"]["error_responses"]) == 8
    assert len(network["payload"]["console_errors"]) == 6


def test_browser_validation_observation_is_compact(tmp_path: Path):
    service = _service(tmp_path)
    observation = service.processor._compact_observation(
        "browser_validate_page",
        "failed",
        "浏览器验证失败",
        {
            "url": "http://127.0.0.1:5173",
            "final_url": "http://127.0.0.1:5173/",
            "status_code": 200,
            "ok": False,
            "title": "Agent Probe",
            "headings": [{"tag": "h1", "text": "Frontend Ready"} for _ in range(10)],
            "console_errors": [f"err-{i}" for i in range(10)],
            "page_errors": [f"page-{i}" for i in range(10)],
            "selector_results": [{"selector": f"#item-{i}", "found": i == 0, "count": i} for i in range(10)],
            "text_results": [{"text": f"text-{i}", "found": i == 0} for i in range(10)],
            "body_excerpt": "C" * 5000,
            "engine": "playwright",
        },
        "browser validation failed",
    )

    assert len(observation["payload"]["console_errors"]) == 6
    assert len(observation["payload"]["page_errors"]) == 6
    assert len(observation["payload"]["selector_results"]) == 6
    assert len(observation["payload"]["text_results"]) == 6
    assert len(observation["payload"]["body_excerpt"]) <= 1200


def test_browser_interaction_and_test_failure_observations_are_compact(tmp_path: Path):
    service = _service(tmp_path)
    browser = service.processor._compact_observation(
        "browser_click",
        "completed",
        "浏览器点击完成",
        {
            "url": "http://127.0.0.1:5173",
            "final_url": "http://127.0.0.1:5173/after",
            "status_code": 200,
            "ok": True,
            "title": "After Action",
            "action": "click",
            "headings": [{"tag": "h1", "text": "Done"} for _ in range(10)],
            "console_errors": [f"err-{i}" for i in range(10)],
            "page_errors": [f"page-{i}" for i in range(10)],
            "selector_results": [{"selector": f"#item-{i}", "found": True, "count": i} for i in range(10)],
            "text_results": [{"text": f"text-{i}", "found": True} for i in range(10)],
            "body_excerpt": "D" * 5000,
            "engine": "playwright",
        },
    )
    failures = service.processor._compact_observation(
        "collect_test_failures",
        "completed",
        "提取到 2 条测试失败信息",
        {
            "failure_summary": "2 failures",
            "failures": [{"headline": f"FAILED test_{i}", "details": ["AssertionError"]} for i in range(12)],
            "stdout_excerpt": "X" * 5000,
            "stderr_excerpt": "Y" * 5000,
        },
    )

    assert len(browser["payload"]["headings"]) == 6
    assert len(browser["payload"]["selector_results"]) == 6
    assert len(browser["payload"]["body_excerpt"]) <= 1200
    assert len(failures["payload"]["failures"]) == 8
    assert len(failures["payload"]["stdout_excerpt"]) <= 1200
    assert len(failures["payload"]["stderr_excerpt"]) <= 1200


def test_targeted_test_and_summary_observations_are_compact(tmp_path: Path):
    service = _service(tmp_path)
    summary = service.processor._compact_observation(
        "summarize_test_results",
        "completed",
        "测试结果已汇总",
        {
            "framework": "pytest",
            "exit_code": 1,
            "headline": "2 passed, 1 failed in 0.45s",
            "passed": 2,
            "failed": 1,
            "skipped": 0,
            "collected": 3,
            "duration": "0.45s",
        },
    )

    assert summary["payload"]["framework"] == "pytest"
    assert summary["payload"]["failed"] == 1
    assert summary["payload"]["duration"] == "0.45s"


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

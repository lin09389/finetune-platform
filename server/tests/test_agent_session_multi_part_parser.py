from __future__ import annotations

import json

from agent_session.parser import parse_agent_response, parse_tool_request


def test_parse_legacy_single_json_tool_request():
    parts = parse_agent_response('{"tool":"read","arguments":{"path":"README.md"}}')

    assert len(parts) == 1
    assert parts[0].type == "tool_call"
    assert parts[0].tool == "read"
    assert parts[0].arguments == {"path": "README.md"}
    assert parse_tool_request('{"tool":"read","arguments":{"path":"README.md"}}') == {
        "tool": "read",
        "arguments": {"path": "README.md"},
    }


def test_parse_json_array_multiple_tool_requests():
    raw = json.dumps(
        [
            {"tool": "collect_context", "arguments": {}},
            {"tool": "read", "arguments": {"path": "server/main.py"}},
        ],
        ensure_ascii=False,
    )

    parts = parse_agent_response(raw)

    assert [part.type for part in parts] == ["tool_call", "tool_call"]
    assert [part.tool for part in parts] == ["collect_context", "read"]


def test_parse_markdown_json_tool_block():
    parts = parse_agent_response(
        """
我先看一下上下文。

```json
{"tool":"collect_context","arguments":{}}
```
""".strip()
    )

    assert [part.type for part in parts] == ["text", "tool_call"]
    assert "上下文" in parts[0].content
    assert parts[1].tool == "collect_context"


def test_parse_text_with_multiple_inline_json_blocks():
    parts = parse_agent_response(
        '我会先读文件 {"tool":"read","arguments":{"path":"a.py"}} 然后搜索 {"tool":"search","arguments":{"query":"VALUE"}}'
    )

    assert [part.type for part in parts] == ["text", "tool_call", "text", "tool_call"]
    assert [part.tool for part in parts if part.type == "tool_call"] == ["read", "search"]


def test_parse_plain_final_text_as_summary():
    parts = parse_agent_response("已完成：读取项目结构并给出建议。验证结果：不需要运行命令。")

    assert len(parts) == 1
    assert parts[0].type == "summary"
    assert "已完成" in parts[0].content


def test_invalid_json_is_kept_as_text_for_protocol_repair():
    parts = parse_agent_response('{"tool":"read","arguments":')

    assert len(parts) == 1
    assert parts[0].type == "text"
    assert parts[0].content.startswith('{"tool"')


def test_parse_content_blocks_with_tool_use_shape():
    raw = json.dumps(
        {
            "content": [
                {"type": "text", "text": "我先读取相关文件。"},
                {"type": "tool_use", "name": "read", "input": {"path": "client/src/App.tsx"}},
                {"type": "tool_use", "name": "search", "input": {"query": "AgentPartMessage"}},
            ]
        },
        ensure_ascii=False,
    )

    parts = parse_agent_response(raw)

    assert [part.type for part in parts] == ["text", "tool_call", "tool_call"]
    assert parts[0].content == "我先读取相关文件。"
    assert [part.tool for part in parts if part.type == "tool_call"] == ["read", "search"]


def test_parse_tool_calls_wrapper_and_json_string_arguments():
    raw = json.dumps(
        {
            "tool_calls": [
                {
                    "type": "function_call",
                    "name": "read",
                    "arguments": "{\"path\":\"server/main.py\"}",
                }
            ]
        },
        ensure_ascii=False,
    )

    parts = parse_agent_response(raw)

    assert len(parts) == 1
    assert parts[0].tool == "read"
    assert parts[0].arguments == {"path": "server/main.py"}

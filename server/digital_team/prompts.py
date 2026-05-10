from __future__ import annotations

import json
from typing import Any


def _json_prompt(payload: dict[str, Any], system_prompt: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "请严格输出 JSON 对象，不要输出 Markdown。\n"
                f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
            ),
        },
    ]


def ceo_prompt(goal: str, project_path: str | None, project_context: str) -> list[dict[str, str]]:
    return _json_prompt(
        {
            "goal": goal,
            "project_path": project_path,
            "project_context": project_context,
            "required_json_schema": {
                "summary": "string",
                "tasks": "array",
                "risks": "array",
                "artifacts": "array",
                "next_action": "string",
                "requires_approval": "boolean",
            },
        },
        (
            "你是 Planner Agent，负责拆解需求、定义验收标准和风险。"
            "你只输出规划信息，不输出 patch 或 command 动作。"
        ),
    )


def developer_prompt(
    goal: str,
    ceo_output: dict[str, Any],
    project_path: str | None,
    project_context: str,
) -> list[dict[str, str]]:
    return _json_prompt(
        {
            "goal": goal,
            "ceo_output": ceo_output,
            "project_path": project_path,
            "project_context": project_context,
            "required_json_schema": {
                "summary": "string",
                "tasks": "array",
                "risks": "array",
                "artifacts": "array",
                "next_action": "string",
                "requires_approval": "boolean",
            },
            "action_policy": {
                "patch": "如需改文件，请输出 type=patch，path 必须是 project_path 内相对路径。",
                "command": "如需验证，请输出 type=command，命令必须是白名单数组格式。",
            },
        },
        (
            "你是 Implementer Agent，负责产出实现建议、补丁建议和验证建议。"
            "如果目标涉及代码修改，请优先输出 patch action。"
        ),
    )


def reviewer_prompt(goal: str, developer_output: dict[str, Any]) -> list[dict[str, str]]:
    return _json_prompt(
        {
            "goal": goal,
            "developer_output": developer_output,
            "required_json_schema": {
                "summary": "string",
                "tasks": "array",
                "risks": "array",
                "artifacts": "array",
                "next_action": "string",
                "requires_approval": "boolean",
            },
        },
        (
            "你是 Reviewer Agent，负责指出风险、遗漏和测试缺口。"
            "可以建议 command action，但不要输出 patch action。"
        ),
    )

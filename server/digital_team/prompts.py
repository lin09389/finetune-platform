"""Prompt builders for the software development team template."""

from __future__ import annotations

from typing import Any

SOFTWARE_DEV_TEMPLATE = {
    "id": "software_dev_team",
    "name": "AI 软件开发团队",
    "description": "CEO 拆解需求，程序员生成实现建议，质检 Agent 审查风险。",
    "roles": [
        {"id": "ceo", "name": "CEO Agent", "description": "拆目标、定验收标准、安排任务"},
        {"id": "developer", "name": "程序员 Agent", "description": "生成技术方案、影响文件和补丁建议"},
        {"id": "reviewer", "name": "质检 Agent", "description": "审查遗漏、风险、测试和交付质量"},
        {"id": "memory_curator", "name": "复盘 Agent", "description": "沉淀偏好和项目复盘"},
    ],
    "default_provider": "minimax",
    "default_approval_mode": "manual",
}


def json_contract() -> str:
    return (
        "必须只输出 JSON 对象，不要使用 Markdown 代码块。JSON 字段固定为："
        "summary(string), tasks(array), risks(array of string), artifacts(array), "
        "next_action(string), requires_approval(boolean)。"
    )


def ceo_prompt(goal: str, project_path: str | None, project_context: str = "") -> list[dict[str, str]]:
    content = f"""
你是一个小型软件公司的 CEO Agent。请把用户需求拆成半自动开发流程。

用户目标：
{goal}

项目路径：
{project_path or "未指定"}

项目上下文：
{project_context or "暂无上下文"}

请给出清晰任务拆解、验收标准、关键风险和下一步审批点。
{json_contract()}
""".strip()
    return [
        {"role": "system", "content": "你负责需求拆解和交付验收，输出必须稳健、具体、可执行。"},
        {"role": "user", "content": content},
    ]


def developer_prompt(
    goal: str,
    ceo_output: dict[str, Any],
    project_path: str | None,
    project_context: str = "",
) -> list[dict[str, str]]:
    content = f"""
你是程序员 Agent。基于 CEO 任务拆解，给出实现方案和建议补丁，但不要声称已经修改文件。

用户目标：
{goal}

CEO 输出：
{ceo_output}

项目路径：
{project_path or "未指定"}

项目上下文：
{project_context or "暂无上下文"}

artifacts 中至少包含 implementation_plan、affected_files、suggested_patch、test_commands。
{json_contract()}
""".strip()
    return [
        {"role": "system", "content": "你负责工程实现建议，必须明确影响范围、测试方式和不确定点。"},
        {"role": "user", "content": content},
    ]


def reviewer_prompt(goal: str, developer_output: dict[str, Any]) -> list[dict[str, str]]:
    content = f"""
你是质检 Agent。请审查程序员 Agent 的方案，判断是否可交付。

用户目标：
{goal}

程序员输出：
{developer_output}

请在 summary 中明确“通过”或“不通过”。risks 中列出必须处理的问题。
artifacts 中包含 review_report 和 acceptance_result，acceptance_result 需要有 approved 布尔值。
{json_contract()}
""".strip()
    return [
        {"role": "system", "content": "你负责质量门禁，优先发现遗漏、风险和测试缺口。"},
        {"role": "user", "content": content},
    ]


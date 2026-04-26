"""Workflow templates for the internal multi-agent runtime."""

from __future__ import annotations

from .definitions import AgentDefinition, StepDefinition, WorkflowDefinition

SOFTWARE_DELIVERY_TEMPLATE = WorkflowDefinition(
    id="software_delivery",
    name="AI 软件交付流程",
    description="Planner 拆解需求，Implementer 生成实现建议，Reviewer 做质量门禁。",
    legacy_template_id="software_dev_team",
    is_builtin=True,
    agents=[
        AgentDefinition(
            id="planner",
            name="Planner",
            description="拆解需求、定义验收标准",
            system_prompt="你是 Planner Agent，负责拆解用户目标、给出任务列表、验收标准和下一步审批建议。",
        ),
        AgentDefinition(
            id="implementer",
            name="Implementer",
            description="给出实现方案和补丁建议",
            system_prompt="你是 Implementer Agent，负责基于计划生成实现方案、影响文件、补丁建议和测试建议。",
        ),
        AgentDefinition(
            id="reviewer",
            name="Reviewer",
            description="审查风险、遗漏和测试缺口",
            system_prompt="你是 Reviewer Agent，负责审查实现建议，指出风险、遗漏、测试缺口和是否可交付。",
        ),
        AgentDefinition(
            id="memory_curator",
            name="Memory Curator",
            description="后续阶段用于复盘沉淀",
            system_prompt="你负责沉淀项目复盘和偏好记忆。",
        ),
    ],
    steps=[
        StepDefinition(
            key="plan",
            agent_id="planner",
            legacy_role="ceo",
            title="需求拆解与验收标准",
            description="CEO Agent 将用户目标拆成可审批的软件开发任务。",
            artifact_type="ceo_plan",
            artifact_title="CEO 任务拆解",
            requires_approval=True,
            sort_order=0,
        ),
        StepDefinition(
            key="implement",
            agent_id="implementer",
            legacy_role="developer",
            title="实现方案与补丁建议",
            description="程序员 Agent 生成实现计划、影响文件和建议补丁。",
            artifact_type="implementation_suggestion",
            artifact_title="程序员实现建议",
            requires_approval=False,
            sort_order=1,
        ),
        StepDefinition(
            key="review",
            agent_id="reviewer",
            legacy_role="reviewer",
            title="质量审查与交付门禁",
            description="质检 Agent 审查实现建议的风险、测试和可交付性。",
            artifact_type="review_report",
            artifact_title="质检审查报告",
            requires_approval=True,
            sort_order=2,
        ),
    ],
)


def get_workflow_definition(template_id: str) -> WorkflowDefinition | None:
    if template_id in {SOFTWARE_DELIVERY_TEMPLATE.id, SOFTWARE_DELIVERY_TEMPLATE.legacy_template_id}:
        return SOFTWARE_DELIVERY_TEMPLATE
    return None

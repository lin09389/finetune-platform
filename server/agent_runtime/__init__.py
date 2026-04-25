"""Internal multi-agent runtime used by Digital Team phase 1."""

from .adapters import step_from_task, workflow_from_project
from .definitions import AgentDefinition, RuntimeExecutionContext, StepDefinition, WorkflowDefinition
from .engine import AgentRuntimeEngine
from .runner import AgentRuntimeRunner
from .templates import SOFTWARE_DELIVERY_TEMPLATE, get_workflow_definition

__all__ = [
    "AgentDefinition",
    "AgentRuntimeEngine",
    "AgentRuntimeRunner",
    "RuntimeExecutionContext",
    "SOFTWARE_DELIVERY_TEMPLATE",
    "StepDefinition",
    "WorkflowDefinition",
    "get_workflow_definition",
    "step_from_task",
    "workflow_from_project",
]

from __future__ import annotations

from typing import Any

from agent_runtime_legacy.read_service import LegacyWorkflowReadService
from core.agent_run_state import workflow_state_snapshot

from .models import LegacyAgentHistoryResponse


class LegacyAgentHistoryService:
    """Project retired workflow data into the agent-session history shape."""

    def __init__(self, reader: LegacyWorkflowReadService):
        self.reader = reader

    def get_workflow_history(self, workflow_id: str) -> LegacyAgentHistoryResponse:
        workflow = self.reader.get_workflow(workflow_id)
        workflow_data = workflow.model_dump()
        observability = self.reader.get_observability(workflow_id)
        timeline = self.reader.list_timeline(workflow_id)
        artifacts = self.reader.list_artifacts(workflow_id)
        metadata = dict(workflow_data.get("metadata") or {})
        return LegacyAgentHistoryResponse(
            id=workflow_id,
            source_runtime="workflow_langgraph" if metadata.get("runtime") == "langgraph" else "workflow_legacy",
            title=workflow_data.get("title") or "Legacy Workflow",
            goal=workflow_data.get("goal") or "",
            summary=self._latest_summary(workflow_data),
            state=workflow_state_snapshot(
                workflow_data,
                runtime_kind="workflow_langgraph" if metadata.get("runtime") == "langgraph" else "workflow_legacy",
            ),
            timeline=timeline,
            artifacts=artifacts,
            observability=observability.model_dump(),
            metadata=metadata,
            created_at=workflow_data.get("created_at"),
            updated_at=workflow_data.get("updated_at"),
        )

    def _latest_summary(self, workflow: dict[str, Any]) -> str:
        steps = workflow.get("steps") or workflow.get("tasks") or []
        for step in reversed(steps):
            if not isinstance(step, dict):
                continue
            output = step.get("output") or step.get("output_data") or {}
            if not isinstance(output, dict):
                continue
            summary = str(output.get("summary") or "").strip()
            if summary:
                return summary
        return ""

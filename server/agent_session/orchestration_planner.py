from __future__ import annotations

from typing import Any

from .models import (
    AgentSessionResponse,
    AgentWorkspaceArtifact,
    AgentWorkspaceChangedFile,
    AgentWorkspaceNextAction,
)

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
ACTIVE_REVIEW_STATUSES = {"pending", "running", "completed"}
RISK_TYPES = {"risk", "risks"}
FINDING_TYPES = {"finding", "findings"}


class AgentOrchestrationPlanner:
    def plan(
        self,
        *,
        session: AgentSessionResponse,
        artifacts: list[AgentWorkspaceArtifact],
        changed_files: list[AgentWorkspaceChangedFile],
        tasks: list[dict[str, Any]],
        pending_permission: dict[str, Any] | None,
    ) -> list[AgentWorkspaceNextAction]:
        actions: list[AgentWorkspaceNextAction] = []

        if pending_permission:
            actions.append(
                AgentWorkspaceNextAction(
                    id=f"resolve_permission:{pending_permission.get('part_id') or 'current'}",
                    action_type="resolve_permission",
                    title="处理待确认动作",
                    summary="Agent 正在等待你确认权限或工具调用。",
                    priority="high",
                    payload={"permission_part_id": pending_permission.get("part_id")},
                )
            )
        for task in tasks:
            if not task.get("has_pending_permission"):
                continue
            permission_part_id = task.get("pending_permission_part_id")
            task_id = str(task.get("task_id") or "")
            actions.append(
                AgentWorkspaceNextAction(
                    id=f"resolve_permission:{permission_part_id or task_id or 'child'}",
                    action_type="resolve_permission",
                    title="处理子任务确认",
                    summary="异步子任务正在等待权限确认。",
                    priority="high",
                    source_task_id=task_id or None,
                    payload={
                        "permission_part_id": permission_part_id,
                        "task_id": task_id,
                        "child_session_id": task.get("child_session_id"),
                    },
                )
            )

        actions.extend(self._risk_actions(artifacts))
        actions.extend(self._validation_actions(artifacts))
        actions.extend(self._subtask_actions(session, artifacts, tasks))
        actions.extend(self._file_actions(changed_files))

        deduped = self._dedupe(actions)
        return sorted(deduped, key=lambda action: (PRIORITY_ORDER.get(action.priority, 3), action.id))[:8]

    def _risk_actions(self, artifacts: list[AgentWorkspaceArtifact]) -> list[AgentWorkspaceNextAction]:
        actions: list[AgentWorkspaceNextAction] = []
        for artifact in artifacts:
            if artifact.artifact_type not in RISK_TYPES:
                continue
            verdict = str(artifact.payload.get("verdict") or "").lower()
            if verdict not in {"fail", "conditional"}:
                continue
            priority = "high" if verdict == "fail" else "medium"
            actions.append(
                AgentWorkspaceNextAction(
                    id=f"review_risks:{artifact.id}",
                    action_type="review_risks",
                    title="查看审查风险",
                    summary=artifact.summary or "Review 子代理发现需要处理的风险。",
                    priority=priority,
                    source_artifact_id=artifact.id,
                    source_task_id=artifact.source_task_id,
                    payload={"artifact_id": artifact.id, "verdict": verdict},
                )
            )
        return actions

    def _validation_actions(self, artifacts: list[AgentWorkspaceArtifact]) -> list[AgentWorkspaceNextAction]:
        has_file_change = any(artifact.artifact_type == "file_change" for artifact in artifacts)
        has_test_result = any(artifact.artifact_type == "test_result" for artifact in artifacts)
        if not has_file_change or has_test_result:
            return []
        return [
            AgentWorkspaceNextAction(
                id="run_tests:file_changes",
                action_type="run_tests",
                title="补充验证",
                summary="检测到文件变更，但当前 workspace 还没有测试或类型检查结果。",
                priority="medium",
                payload={"reason": "file_changes_without_test_result"},
            )
        ]

    def _subtask_actions(
        self,
        session: AgentSessionResponse,
        artifacts: list[AgentWorkspaceArtifact],
        tasks: list[dict[str, Any]],
    ) -> list[AgentWorkspaceNextAction]:
        actions: list[AgentWorkspaceNextAction] = []
        task_agents = {str(task.get("agent_name") or "") for task in tasks}
        has_review_task = any(
            str(task.get("agent_name") or "") == "review"
            and str(task.get("status") or "") in ACTIVE_REVIEW_STATUSES
            for task in tasks
        )
        findings = [artifact for artifact in artifacts if artifact.artifact_type in FINDING_TYPES]

        if findings and not has_review_task:
            artifact = findings[-1]
            actions.append(
                AgentWorkspaceNextAction(
                    id=f"start_review:{artifact.id}",
                    action_type="start_review",
                    title="启动审查子任务",
                    summary="探索结果已经形成，建议让 review 子代理检查风险。",
                    priority="medium",
                    source_artifact_id=artifact.id,
                    source_task_id=artifact.source_task_id,
                    payload={
                        "subagent_type": "review",
                        "description": f"基于探索结果审查风险：{artifact.summary}".strip(),
                    },
                )
            )

        if "explore" not in task_agents and str(session.status) != "completed":
            actions.append(
                AgentWorkspaceNextAction(
                    id="start_explore:session",
                    action_type="start_explore",
                    title="启动探索子任务",
                    summary="让 explore 子代理先只读梳理当前问题和相关文件。",
                    priority="low",
                    payload={
                        "subagent_type": "explore",
                        "description": "只读探索当前 Agent 工作区，梳理关键文件、当前状态和下一步建议。",
                    },
                )
            )

        for task in tasks:
            if str(task.get("status") or "") != "failed":
                continue
            task_id = str(task.get("task_id") or "")
            if not task_id:
                continue
            actions.append(
                AgentWorkspaceNextAction(
                    id=f"restart_failed_task:{task_id}",
                    action_type="restart_failed_task",
                    title="查看失败子任务",
                    summary=str(task.get("error") or "子任务失败，可检查详情后决定是否重启。"),
                    priority="medium",
                    source_task_id=task_id,
                    payload={"task_id": task_id, "child_session_id": task.get("child_session_id")},
                )
            )

        return actions

    def _file_actions(self, changed_files: list[AgentWorkspaceChangedFile]) -> list[AgentWorkspaceNextAction]:
        actions: list[AgentWorkspaceNextAction] = []
        for changed_file in changed_files[-3:]:
            actions.append(
                AgentWorkspaceNextAction(
                    id=f"inspect_file:{changed_file.path}",
                    action_type="inspect_file",
                    title=f"查看文件 {changed_file.path}",
                    summary=changed_file.summary or "检查 Agent 产生的文件变更。",
                    priority="low",
                    source_artifact_id=None,
                    payload={"path": changed_file.path},
                )
            )
        return actions

    @staticmethod
    def _dedupe(actions: list[AgentWorkspaceNextAction]) -> list[AgentWorkspaceNextAction]:
        seen: set[str] = set()
        deduped: list[AgentWorkspaceNextAction] = []
        for action in actions:
            if action.id in seen:
                continue
            seen.add(action.id)
            deduped.append(action)
        return deduped

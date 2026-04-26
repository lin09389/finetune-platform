"""Step-level context assembly for workflow execution."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .definitions import RuntimeExecutionContext, StepDefinition, WorkflowDefinition

logger = logging.getLogger(__name__)


@dataclass
class ContextPack:
    project_context: str = ""
    chat_context: str = ""
    memory_context: str = ""
    artifact_context: str = ""
    combined_context: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)


class WorkflowContextBuilder:
    """Builds the exact context that is injected into each runtime step."""

    def __init__(self, repository: Any):
        self.repository = repository

    def build_for_step(
        self,
        project: dict[str, Any],
        workflow: WorkflowDefinition,
        step: StepDefinition,
        task: dict[str, Any],
        previous_outputs: list[dict[str, Any]],
        fallback_project_context: str = "",
    ) -> RuntimeExecutionContext:
        profile = self._profile(project)
        max_chars = int(profile.get("max_context_chars") or 6000)
        parts: list[tuple[str, str]] = []
        sources: list[dict[str, Any]] = []

        project_context = ""
        if profile.get("include_project_context", True):
            project_context = self._project_context(
                profile.get("project_path") or project.get("project_path"),
                project["goal"],
                max_chars=max(800, max_chars // 2),
                fallback=fallback_project_context,
                workflow_id=project["id"],
            )
            if project_context:
                parts.append(("项目上下文", project_context))
                sources.append({"type": "project", "project_path": profile.get("project_path") or project.get("project_path")})

        chat_context = ""
        if profile.get("include_chat_context") and profile.get("chat_session_id"):
            chat_context = self._chat_context(profile["chat_session_id"], max_chars=max(800, max_chars // 4), workflow_id=project["id"])
            if chat_context:
                parts.append(("聊天上下文", chat_context))
                sources.append({"type": "chat", "chat_session_id": profile["chat_session_id"]})

        memory_context = ""
        if profile.get("include_memory", True):
            memory_context = self._memory_context(max_chars=max(600, max_chars // 5), workflow_id=project["id"])
            if memory_context:
                parts.append(("历史偏好", memory_context))
                sources.append({"type": "memory", "user_id": "default"})

        artifact_context = self._artifact_context(project["id"], previous_outputs, max_chars=max(600, max_chars // 5))
        if artifact_context:
            parts.append(("已有产物与前序输出", artifact_context))
            sources.append({"type": "artifacts", "workflow_id": project["id"]})

        combined = self._trim("\n\n".join(f"## {title}\n{content}" for title, content in parts), max_chars)
        if hasattr(self.repository, "add_context_snapshot"):
            self.repository.add_context_snapshot(
                project["id"],
                task.get("id"),
                step.key,
                combined,
                sources=sources,
                context_type="step",
            )

        return RuntimeExecutionContext(
            workflow_id=project["id"],
            goal=project["goal"],
            project_path=profile.get("project_path") or project.get("project_path"),
            project_context=project_context,
            chat_context=chat_context,
            memory_context=memory_context,
            artifact_context=artifact_context,
            context_pack={
                "project": project_context,
                "chat": chat_context,
                "memory": memory_context,
                "artifacts": artifact_context,
                "combined": combined,
                "profile": profile,
            },
            context_sources=sources,
            provider=project["provider"],
            model=project.get("model"),
            metadata={"template_id": workflow.id, "step_key": step.key},
        )

    def _profile(self, project: dict[str, Any]) -> dict[str, Any]:
        if hasattr(self.repository, "get_context_profile"):
            return self.repository.get_context_profile(project["id"])
        return {
            "project_path": project.get("project_path"),
            "include_project_context": True,
            "include_chat_context": False,
            "include_memory": False,
            "max_context_chars": 6000,
            "metadata": {},
        }

    def _project_context(
        self,
        project_path: str | None,
        goal: str,
        max_chars: int,
        fallback: str,
        workflow_id: str,
    ) -> str:
        if not project_path:
            return ""
        try:
            from context.service import get_context_service

            service = get_context_service()
            return self._trim(service.get_context_for_chat(query=goal, project_path=project_path, max_length=max_chars), max_chars)
        except Exception as exc:
            self._warn(workflow_id, "project_context_warning", f"项目上下文不可用：{exc}")
            logger.info("Workflow project context unavailable: %s", exc)
            return self._trim(fallback, max_chars)

    def _chat_context(self, chat_session_id: str, max_chars: int, workflow_id: str) -> str:
        try:
            from api.chat.session import get_session_manager

            session = get_session_manager().get_session(chat_session_id)
            if not session:
                return ""
            lines = []
            for message in session.get_messages(limit=12):
                content = self._trim(message.content.replace("\n", " "), 700)
                lines.append(f"{message.role}: {content}")
            return self._trim("\n".join(lines), max_chars)
        except Exception as exc:
            self._warn(workflow_id, "chat_context_warning", f"聊天上下文不可用：{exc}")
            logger.info("Workflow chat context unavailable: %s", exc)
            return ""

    def _memory_context(self, max_chars: int, workflow_id: str) -> str:
        try:
            from memory.preference_learner import get_preference_learner

            preferences = get_preference_learner().get_all_preferences("default")
            if not preferences:
                return ""
            lines = [f"{key}: {value}" for key, value in preferences.items()]
            return self._trim("\n".join(lines), max_chars)
        except Exception as exc:
            self._warn(workflow_id, "memory_context_warning", f"历史偏好不可用：{exc}")
            logger.info("Workflow memory context unavailable: %s", exc)
            return ""

    def _artifact_context(self, workflow_id: str, previous_outputs: list[dict[str, Any]], max_chars: int) -> str:
        summaries: list[str] = []
        for output in previous_outputs[-4:]:
            summary = output.get("summary") if isinstance(output, dict) else None
            if summary:
                summaries.append(str(summary))
        return self._trim("\n".join(summaries), max_chars)

    def _warn(self, workflow_id: str, event_type: str, message: str) -> None:
        if hasattr(self.repository, "add_event"):
            self.repository.add_event(workflow_id, None, event_type, "system", message)

    def _trim(self, text: str | None, max_chars: int) -> str:
        if not text:
            return ""
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 20] + "\n...[已截断]"

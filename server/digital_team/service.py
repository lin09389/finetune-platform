"""Digital Team orchestration service."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from agent_runtime.engine import AgentRuntimeEngine
from agent_runtime.templates import get_workflow_definition
from core.config import settings

from .agents import DigitalTeamAgentRunner
from .models import AgentOutput, ProjectCreate, ProjectStatus, TaskStatus, TeamTemplate
from .prompts import SOFTWARE_DEV_TEMPLATE
from .repository import DigitalTeamRepository

logger = logging.getLogger(__name__)


class DigitalTeamService:
    def __init__(
        self,
        repository: DigitalTeamRepository | None = None,
        agent_runner: DigitalTeamAgentRunner | None = None,
    ):
        self.repository = repository or DigitalTeamRepository()
        self.agent_runner = agent_runner or DigitalTeamAgentRunner()
        self.runtime_engine = AgentRuntimeEngine(self.repository, self.agent_runner)

    def list_templates(self) -> list[TeamTemplate]:
        return [TeamTemplate(**SOFTWARE_DEV_TEMPLATE)]

    def create_project(self, request: ProjectCreate) -> dict[str, Any]:
        template = self._get_template(request.template_id)
        project_path = self._validate_project_path(request.project_path)
        team = self.repository.create_team(template.id, template.name, template.description)
        data = request.model_dump()
        data["project_path"] = project_path
        return self.repository.create_project(data, team)

    def list_projects(self) -> list[dict[str, Any]]:
        return self.repository.list_projects()

    def get_project(self, project_id: str) -> dict[str, Any]:
        project = self.repository.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Digital team project not found")
        return project

    async def run_project(self, project_id: str) -> dict[str, Any]:
        project = self.get_project(project_id)
        if get_workflow_definition(project["template_id"]) is None:
            raise HTTPException(status_code=400, detail="Unsupported team template")
        context = self._project_context(project["project_path"], project["goal"])
        return await self.runtime_engine.start(project, context)

    async def approve_task(
        self,
        task_id: str,
        approved: bool = True,
        comment: str | None = None,
    ) -> dict[str, Any]:
        task = self.repository.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Digital team task not found")
        project = self.get_project(task["project_id"])
        if not approved:
            return await self.runtime_engine.reject(project, task, comment)

        context = self._project_context(project["project_path"], project["goal"])
        return await self.runtime_engine.approve(project, task, context, comment)

    async def retry_task(self, task_id: str) -> dict[str, Any]:
        task = self.repository.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Digital team task not found")
        project = self.get_project(task["project_id"])
        context = self._project_context(project["project_path"], project["goal"])
        return await self.runtime_engine.retry(project, task, context)

    def list_timeline(self, project_id: str) -> list[dict[str, Any]]:
        self.get_project(project_id)
        return self.repository.list_events(project_id)

    def list_artifacts(self, project_id: str) -> list[dict[str, Any]]:
        self.get_project(project_id)
        return self.repository.list_artifacts(project_id)

    def _get_template(self, template_id: str) -> TeamTemplate:
        for template in self.list_templates():
            if template.id == template_id:
                return template
        raise HTTPException(status_code=400, detail="Unknown digital team template")

    def _validate_project_path(self, project_path: str | None) -> str | None:
        if not project_path or not project_path.strip():
            return None
        resolved = Path(project_path).resolve()
        cwd = Path.cwd().resolve()
        roots = {cwd, settings.base_dir.resolve()}
        for root in list(roots):
            if root.name == "server":
                roots.add(root.parent)

        workspace_env = os.getenv("WORKSPACE_ROOT") or os.getenv("PROJECT_ROOT")
        if workspace_env:
            roots.add(Path(workspace_env).resolve())

        if not any(resolved == root or resolved.is_relative_to(root) for root in roots):
            allowed = ", ".join(str(root) for root in sorted(roots, key=lambda item: str(item)))
            raise HTTPException(
                status_code=400,
                detail=f"project_path must be inside the workspace. Allowed roots: {allowed}",
            )
        return str(resolved)

    def _project_context(self, project_path: str | None, goal: str) -> str:
        if not project_path:
            return ""
        try:
            from context.service import get_context_service

            service = get_context_service()
            return service.get_context_for_chat(query=goal, project_path=project_path, max_length=1800)
        except Exception as exc:
            logger.info("Digital team project context unavailable: %s", exc)
            return ""

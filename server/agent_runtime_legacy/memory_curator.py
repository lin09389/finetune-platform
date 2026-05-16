"""Automatic workflow memory curation."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class WorkflowMemoryCurator:
    """Persists workflow retrospectives and learned preferences with audit records."""

    def __init__(self, repository: Any):
        self.repository = repository

    async def curate_completed_workflow(self, workflow_id: str) -> list[dict[str, Any]]:
        if not hasattr(self.repository, "add_memory_entry"):
            return []
        project = self.repository.get_project(workflow_id)
        if not project:
            return []
        existing = [
            item
            for item in self.repository.list_memory_entries(workflow_id)
            if item.get("status") == "active"
        ]
        if existing:
            return existing

        text = self._workflow_text(project)
        stored: list[dict[str, Any]] = []
        preference_entries = await self._learn_preferences(workflow_id, text)
        stored.extend(preference_entries)

        summary = self._retro_summary(project)
        if summary:
            stored.append(
                self.repository.add_memory_entry(
                    workflow_id=workflow_id,
                    memory_type="workflow_retro",
                    memory_key=f"workflow_retro_{workflow_id}",
                    memory_value={"summary": summary, "template_id": project.get("template_id")},
                    content=summary,
                    confidence=0.65,
                )
            )

        if stored:
            self.repository.add_event(
                workflow_id,
                None,
                "memory_curated",
                "system",
                f"已自动沉淀 {len(stored)} 条工作流记忆",
                {"memory_ids": [item.get("id") for item in stored]},
            )
        return stored

    async def _learn_preferences(self, workflow_id: str, text: str) -> list[dict[str, Any]]:
        try:
            from memory.preference_learner import PreferenceExtractor, get_preference_learner

            extracted = PreferenceExtractor.extract_from_text(text)
            if not extracted:
                return []
            learned = await get_preference_learner().learn_from_text(text, user_id="default")
            entries: list[dict[str, Any]] = []
            for pref in learned:
                entries.append(
                    self.repository.add_memory_entry(
                        workflow_id=workflow_id,
                        memory_type="preference",
                        memory_key=pref.key,
                        memory_value={"value": pref.value},
                        content=f"{pref.key}: {pref.value}",
                        confidence=pref.confidence,
                        external_memory_id=pref.key,
                    )
                )
            return entries
        except Exception as exc:
            logger.info("Workflow preference curation unavailable: %s", exc)
            if hasattr(self.repository, "add_event"):
                self.repository.add_event(workflow_id, None, "memory_warning", "system", f"偏好记忆写入失败：{exc}")
            return []

    def _workflow_text(self, project: dict[str, Any]) -> str:
        chunks = [project.get("goal", "")]
        for task in project.get("tasks", []):
            output = task.get("output") or {}
            if isinstance(output, dict):
                chunks.append(output.get("summary", ""))
                chunks.extend(str(item) for item in output.get("risks", [])[:4])
                chunks.append(json.dumps(output.get("artifacts", [])[:3], ensure_ascii=False))
        return "\n".join(chunk for chunk in chunks if chunk)

    def _retro_summary(self, project: dict[str, Any]) -> str:
        task_summaries = []
        for task in project.get("tasks", []):
            output = task.get("output") or {}
            if isinstance(output, dict) and output.get("summary"):
                task_summaries.append(f"{task.get('title')}: {output['summary']}")
        if not task_summaries:
            return ""
        return f"工作流《{project.get('title')}》已完成。关键产出：\n" + "\n".join(task_summaries[:6])

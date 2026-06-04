from __future__ import annotations

import re
from typing import Any

from .models import AgentWorkspaceArtifact, AgentWorkspaceChangedFile

MAX_PAYLOAD_TEXT = 1200
TEST_COMMAND_HINTS = ("test", "pytest", "vitest", "typecheck", "tsc", "lint", "coverage")


class AgentArtifactExtractor:
    def extract(
        self,
        parts: list[Any],
        tasks: list[dict[str, Any]],
        diff_artifacts: list[Any],
    ) -> tuple[list[AgentWorkspaceArtifact], list[AgentWorkspaceChangedFile]]:
        artifacts: list[AgentWorkspaceArtifact] = []
        changed_files: list[AgentWorkspaceChangedFile] = []
        seen_files: set[str] = set()

        file_artifacts, changed_files = self._extract_file_changes(diff_artifacts, seen_files)
        artifacts.extend(file_artifacts)

        for part in parts:
            part_artifacts = self._extract_part_artifacts(part)
            artifacts.extend(part_artifacts)

        for task in tasks:
            artifacts.extend(self._extract_task_artifacts(task))

        return artifacts[-80:], changed_files[-80:]

    def _extract_file_changes(
        self,
        diff_artifacts: list[Any],
        seen_files: set[str],
    ) -> tuple[list[AgentWorkspaceArtifact], list[AgentWorkspaceChangedFile]]:
        artifacts: list[AgentWorkspaceArtifact] = []
        changed_files: list[AgentWorkspaceChangedFile] = []
        for item in diff_artifacts:
            path = str(getattr(item, "path", "") or "").strip()
            source_part_id = str(getattr(item, "source_part_id", "") or "")
            summary = str(getattr(item, "summary", "") or "")
            status = str(getattr(item, "status", "modified") or "modified")
            if path and path not in seen_files:
                seen_files.add(path)
                changed_files.append(
                    AgentWorkspaceChangedFile(
                        path=path,
                        status=status,
                        summary=summary,
                        source_part_id=source_part_id or None,
                    )
                )
            artifacts.append(
                AgentWorkspaceArtifact(
                    id=f"file_change:{source_part_id}:{path}",
                    artifact_type="file_change",
                    title=path or "文件变更",
                    summary=summary,
                    payload={
                        "path": path,
                        "status": status,
                        "preview": getattr(item, "preview", "") or "",
                    },
                    source_part_id=source_part_id or None,
                )
            )
        return artifacts, changed_files

    def _extract_part_artifacts(self, part: Any) -> list[AgentWorkspaceArtifact]:
        payload = dict(getattr(part, "payload", None) or {})
        part_type = str(getattr(part, "type", "") or "")
        part_id = str(getattr(part, "id", "") or "")
        content = str(getattr(part, "content", "") or "")
        title = str(getattr(part, "title", "") or "")
        created_at = str(getattr(part, "created_at", "") or "") or None
        agent_name = str(payload.get("agent_name") or "") or None

        if part_type == "command":
            return self._extract_command_artifacts(part_id, title, content, payload, agent_name, created_at)
        if part_type == "summary":
            return [
                AgentWorkspaceArtifact(
                    id=f"run_summary:{part_id}",
                    artifact_type="run_summary",
                    title=title or "运行摘要",
                    summary=content[:240],
                    payload=payload,
                    source_part_id=part_id,
                    producer_agent=agent_name,
                    created_at=created_at,
                )
            ]
        return []

    def _extract_command_artifacts(
        self,
        part_id: str,
        title: str,
        content: str,
        payload: dict[str, Any],
        agent_name: str | None,
        created_at: str | None,
    ) -> list[AgentWorkspaceArtifact]:
        command = payload.get("command")
        command_text = self._command_text(command, title)
        exit_code = payload.get("exit_code")
        stdout = self._truncate(payload.get("stdout"))
        stderr = self._truncate(payload.get("stderr"))
        passed = self._passed(exit_code)
        base_payload = {
            "command": command_text,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
        }
        artifacts = [
            AgentWorkspaceArtifact(
                id=f"command_result:{part_id}",
                artifact_type="command_result",
                title=command_text,
                summary=content[:240],
                payload=base_payload,
                source_part_id=part_id,
                producer_agent=agent_name,
                created_at=created_at,
            )
        ]
        if self._looks_like_test_command(command_text):
            artifacts.append(
                AgentWorkspaceArtifact(
                    id=f"test_result:{part_id}",
                    artifact_type="test_result",
                    title=command_text,
                    summary=content[:240] or ("验证通过" if passed else "验证失败"),
                    payload={**base_payload, "passed": passed},
                    source_part_id=part_id,
                    producer_agent=agent_name,
                    created_at=created_at,
                )
            )
        return artifacts

    def _extract_task_artifacts(self, task: dict[str, Any]) -> list[AgentWorkspaceArtifact]:
        agent_name = str(task.get("agent_name") or "")
        result = dict(task.get("result") or {})
        summary = str(result.get("summary") or task.get("error") or "")
        task_id = str(task.get("task_id") or "")
        base = AgentWorkspaceArtifact(
            id=f"subtask_result:{task_id}",
            artifact_type="subtask_result",
            title=f"{agent_name or 'subagent'} 子任务",
            summary=summary[:240],
            payload={
                "status": task.get("status"),
                "child_status": task.get("child_status"),
                "result": result,
            },
            source_task_id=task_id,
            producer_agent=agent_name or None,
            created_at=str(task.get("updated_at") or task.get("created_at") or "") or None,
        )
        if agent_name == "explore":
            return [base, self._findings_artifact(task, summary)]
        if agent_name == "review":
            return [base, self._risks_artifact(task, summary)]
        return [base]

    def _findings_artifact(self, task: dict[str, Any], summary: str) -> AgentWorkspaceArtifact:
        result = dict(task.get("result") or {})
        items = self._items_from_result(result, fallback_title="探索发现", fallback_summary=summary)
        files = self._files_from_text(summary)
        return AgentWorkspaceArtifact(
            id=f"findings:{task.get('task_id')}",
            artifact_type="findings",
            title="探索发现",
            summary=summary[:240],
            payload={"items": items, "files_examined": files},
            source_task_id=str(task.get("task_id") or ""),
            producer_agent="explore",
            created_at=str(task.get("updated_at") or task.get("created_at") or "") or None,
        )

    def _risks_artifact(self, task: dict[str, Any], summary: str) -> AgentWorkspaceArtifact:
        result = dict(task.get("result") or {})
        items = self._items_from_result(result, fallback_title="审查风险", fallback_summary=summary, risk=True)
        return AgentWorkspaceArtifact(
            id=f"risks:{task.get('task_id')}",
            artifact_type="risks",
            title="审查风险",
            summary=summary[:240],
            payload={"verdict": self._verdict(summary), "items": items},
            source_task_id=str(task.get("task_id") or ""),
            producer_agent="review",
            created_at=str(task.get("updated_at") or task.get("created_at") or "") or None,
        )

    @staticmethod
    def _items_from_result(
        result: dict[str, Any],
        *,
        fallback_title: str,
        fallback_summary: str,
        risk: bool = False,
    ) -> list[dict[str, Any]]:
        raw_items = result.get("items") or result.get("findings") or result.get("risks")
        if isinstance(raw_items, list):
            items = [item for item in raw_items if isinstance(item, dict)]
            if items:
                return items
        if not fallback_summary:
            return []
        item: dict[str, Any] = {
            "title": fallback_title,
            "summary": fallback_summary,
        }
        if risk:
            item["severity"] = "medium" if "不通过" in fallback_summary or "失败" in fallback_summary else "low"
        else:
            item["confidence"] = "medium"
        files = AgentArtifactExtractor._files_from_text(fallback_summary)
        if files:
            item["files"] = files
        return [item]

    @staticmethod
    def _files_from_text(text: str) -> list[str]:
        matches = re.findall(r"(?:/workspace/)?[\w./\\-]+\.(?:py|tsx?|jsx?|md|json|yml|yaml|css|scss|html)", text)
        seen: list[str] = []
        for match in matches:
            normalized = match.replace("\\", "/")
            if normalized not in seen:
                seen.append(normalized)
        return seen[:12]

    @staticmethod
    def _verdict(summary: str) -> str:
        if "不通过" in summary or "阻塞" in summary:
            return "fail"
        if "有条件通过" in summary or "需修复" in summary:
            return "conditional"
        if "通过" in summary or "放行" in summary:
            return "pass"
        return "conditional" if summary else "pass"

    @staticmethod
    def _command_text(command: Any, title: str) -> str:
        if isinstance(command, list):
            return " ".join(str(part) for part in command)
        return str(command or title or "命令")

    @staticmethod
    def _looks_like_test_command(command_text: str) -> bool:
        lowered = command_text.lower()
        return any(hint in lowered for hint in TEST_COMMAND_HINTS)

    @staticmethod
    def _passed(exit_code: Any) -> bool:
        try:
            return int(exit_code) == 0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _truncate(value: Any, limit: int = MAX_PAYLOAD_TEXT) -> str:
        text = "" if value is None else str(value)
        return text if len(text) <= limit else f"{text[:limit]}..."

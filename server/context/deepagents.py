"""DeepAgents-oriented context packaging.

This module is the boundary between the platform Context Engine and the
DeepAgents harness. It keeps large task context out of the main prompt and
offloads it into DeepAgents' virtual filesystem under /context/.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from context.budget import ContextBuildOptions, estimate_tokens
from context.builder import get_context_builder
from context.pack import ContextPack

logger = logging.getLogger(__name__)

CONTEXT_ROOT = "/context"
MAX_INLINE_PROMPT_CHARS = 1600
MAX_CONTEXT_FILE_CHARS = 24_000
MAX_CONTEXT_FILES = 12


@dataclass(frozen=True)
class DeepAgentsContextPack:
    """Per-run context package consumed by DeepAgents."""

    prompt: str
    files: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_files(self) -> bool:
        return bool(self.files)


async def build_deepagents_context_pack(
    *,
    goal: str,
    active_context: dict[str, Any] | None,
    explicit_context: list[dict[str, Any]] | None,
    project_path: str | None,
    session_id: str | None = None,
    user_id: str = "default",
) -> DeepAgentsContextPack:
    """Build a bounded prompt plus /context files for a DeepAgents run."""

    files: dict[str, str] = {}
    metadata: dict[str, Any] = {"strategy": "deepagents_context_files_v2"}

    task_index = _task_index(goal, active_context, explicit_context)
    files[f"{CONTEXT_ROOT}/task.md"] = task_index
    files["/task.md"] = task_index

    if active_context:
        active_text = _active_context_text(active_context)
        if active_text:
            active_file_text = _limit(active_text, MAX_CONTEXT_FILE_CHARS)
            files[f"{CONTEXT_ROOT}/editor/active-file.md"] = active_file_text
            files["/editor/active-file.md"] = active_file_text
            files["/active-file.md"] = active_file_text

    for index, item in enumerate((explicit_context or [])[:MAX_CONTEXT_FILES], start=1):
        text = _explicit_context_text(item)
        if text:
            files[f"{CONTEXT_ROOT}/mentions/{index:02d}-{_safe_slug(item)}.md"] = _limit(text, MAX_CONTEXT_FILE_CHARS)

    related = _expand_related_context(active_context, explicit_context, project_path)
    if related:
        files[f"{CONTEXT_ROOT}/retrieval/related.md"] = _limit(_related_context_text(related), MAX_CONTEXT_FILE_CHARS)

    retrieved_pack = await _build_retrieval_pack(goal, project_path, session_id=session_id, user_id=user_id)
    if retrieved_pack and retrieved_pack.context_text:
        files.update(_context_pack_files(retrieved_pack))
        metadata["retrieval"] = retrieved_pack.to_dict()

    file_lines = [f"- `{path}` ({estimate_tokens(content)} tokens est.)" for path, content in files.items()]
    prompt_context = (
        "\n\n上下文已按 DeepAgents 官方 context engineering 方式放入虚拟文件系统。"
        "\n需要细节时请使用 read_file/grep/glob 读取这些文件，不要依赖主消息中的长文本。"
        "\n如果你想读取任务索引，优先读取 `/context/task.md`；`/task.md` 只是兼容别名。"
        "\n如果你想读取当前编辑器文件，优先读取 `/context/editor/active-file.md`；"
        "`/editor/active-file.md` 和 `/active-file.md` 是兼容别名。"
        "\n可用上下文文件：\n"
        + "\n".join(file_lines)
    )
    prompt = _limit(goal.strip(), MAX_INLINE_PROMPT_CHARS) + prompt_context
    metadata.update(
        {
            "file_count": len(files),
            "files": [{"path": path, "tokens": estimate_tokens(content), "chars": len(content)} for path, content in files.items()],
            "prompt_tokens": estimate_tokens(prompt),
            "source_hash": hashlib.sha256(json.dumps(_metadata_seed(active_context, explicit_context), ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        }
    )
    return DeepAgentsContextPack(prompt=prompt, files=files, metadata=metadata)


async def _build_retrieval_pack(
    goal: str,
    project_path: str | None,
    *,
    session_id: str | None,
    user_id: str,
) -> ContextPack | None:
    if not project_path:
        return None
    try:
        return await get_context_builder().build(
            query=goal,
            user_id=user_id,
            session_id=session_id,
            options=ContextBuildOptions(
                use_memory=True,
                use_knowledge=False,
                use_project_context=True,
                project_path=project_path,
                max_context_tokens=3200,
                reserved_output_tokens=1024,
                max_total_sources=8,
                project_max_tokens=2200,
            ),
        )
    except Exception as exc:
        logger.debug("DeepAgents retrieval context build failed: %s", exc, exc_info=True)
        return None


def _context_pack_files(pack: ContextPack) -> dict[str, str]:
    files: dict[str, str] = {
        f"{CONTEXT_ROOT}/retrieval/index.md": _limit(_context_pack_index_text(pack), MAX_CONTEXT_FILE_CHARS),
    }
    for kind in ("memory", "knowledge", "project"):
        text = _context_sources_text(pack, kind)
        if text:
            files[f"{CONTEXT_ROOT}/retrieval/{kind}.md"] = _limit(text, MAX_CONTEXT_FILE_CHARS)
    return files


def _context_pack_index_text(pack: ContextPack) -> str:
    lines = [
        "# Retrieved Context Index",
        "",
        f"- query: {pack.query}",
        f"- total_sources: {pack.total_sources}",
        f"- used_tokens: {pack.budget.used_tokens}",
        "",
        "## Files",
        "- `/context/retrieval/memory.md`: file-memory index/snippets only; read full files from `/memories/`, `/agent-memory/`, or `/policies/` when needed",
        "- `/context/retrieval/knowledge.md`: retrieved RAG/reference material when present",
        "- `/context/retrieval/project.md`: project/codebase context when present",
        "",
    ]
    if pack.warnings:
        lines.extend(["", "## Warnings", *[f"- {warning}" for warning in pack.warnings]])
    return "\n".join(line for line in lines if line is not None).strip() + "\n"


def _context_sources_text(pack: ContextPack, kind: str) -> str:
    sources = [source for source in pack.sources if source.kind == kind]
    if not sources:
        return ""
    title = {"memory": "Memory Context", "knowledge": "Knowledge Context", "project": "Project Context"}.get(kind, kind.title())
    if kind == "memory":
        return _memory_sources_index_text(sources)
    parts = [f"# {title}"]
    for index, source in enumerate(sources, 1):
        source_path = f"\npath: `{source.path}`" if source.path else ""
        parts.extend(
            [
                "",
                f"## Source {index}: {source.source}",
                f"score: {source.score}",
                f"tokens: {source.tokens}{source_path}",
                "",
                "```text",
                source.content.strip(),
                "```",
            ]
        )
    return "\n".join(parts).strip() + "\n"


def _memory_sources_index_text(sources: list[Any]) -> str:
    parts = [
        "# Memory Context Index",
        "",
        "These are file-memory snippets. For full durable memory, read the referenced files from `/memories/`, `/agent-memory/`, or `/policies/`.",
    ]
    for index, source in enumerate(sources, 1):
        path = source.metadata.get("memory_path") or source.path or ""
        scope = source.metadata.get("scope") or "user"
        namespace = source.metadata.get("namespace") or ""
        version = source.metadata.get("version")
        updated_at = source.metadata.get("updated_at") or ""
        parts.extend(
            [
                "",
                f"## Memory File {index}: `{path}`",
                f"- scope: `{scope}`",
                f"- namespace: `{namespace}`",
                f"- score: {source.score}",
                f"- version: {version if version is not None else 'unknown'}",
                f"- updated_at: {updated_at}",
                "",
                "```text",
                source.content.strip(),
                "```",
            ]
        )
    return "\n".join(parts).strip() + "\n"


def _task_index(goal: str, active_context: dict[str, Any] | None, explicit_context: list[dict[str, Any]] | None) -> str:
    lines = ["# Task Context", "", "## User Goal", goal.strip() or "继续执行当前任务。"]
    if active_context:
        cursor = active_context.get("cursor") or {}
        selection = active_context.get("selection") or {}
        lines.extend(
            [
                "",
                "## Active Editor",
                f"- file: `{active_context.get('file_path') or 'unknown'}`",
                f"- cursor: line {cursor.get('line', 1)}, column {cursor.get('column', 1)}",
            ]
        )
        if isinstance(selection, dict) and selection.get("text"):
            lines.append("- selected_text: see `/context/editor/active-file.md`")
    if explicit_context:
        lines.extend(["", "## Explicit Mentions"])
        for item in explicit_context[:MAX_CONTEXT_FILES]:
            label = item.get("label") or item.get("path") or "context"
            path = item.get("path") or ""
            line = item.get("line")
            location = f"{path}{':' + str(line) if line else ''}"
            lines.append(f"- @{label}: {location}".strip())
    return "\n".join(lines).strip() + "\n"


def _active_context_text(active_context: dict[str, Any]) -> str:
    selection = active_context.get("selection") or {}
    selected_text = str(selection.get("text") or "").strip() if isinstance(selection, dict) else ""
    preview = str(active_context.get("content_preview") or "").strip()
    content = selected_text or preview
    if not content:
        return ""
    return "\n".join(
        [
            "# Active File Context",
            "",
            f"file: `{active_context.get('file_path') or 'unknown'}`",
            "",
            "```text",
            content,
            "```",
        ]
    )


def _explicit_context_text(item: dict[str, Any]) -> str:
    content = str(item.get("content") or "").strip()
    if not content:
        return ""
    title = item.get("label") or item.get("path") or "context"
    return "\n".join(
        [
            f"# @{title}",
            "",
            f"type: `{item.get('type') or 'context'}`",
            f"path: `{item.get('path') or ''}`",
            "",
            "```text",
            content,
            "```",
        ]
    )


def _expand_related_context(
    active_context: dict[str, Any] | None,
    explicit_context: list[dict[str, Any]] | None,
    project_path: str | None,
) -> list[dict[str, Any]]:
    try:
        from context.service import get_context_service

        return get_context_service().expand_deep_context(active_context, explicit_context, project_path)
    except Exception:
        logger.debug("DeepAgents related topology expansion failed", exc_info=True)
        return []


def _related_context_text(related: list[dict[str, Any]]) -> str:
    parts = ["# Related Dependency Context"]
    for item in related:
        relation = item.get("relation") or "related"
        path = item.get("path") or ""
        line = f":{item.get('line')}" if item.get("line") else ""
        content = str(item.get("content") or "").strip()
        parts.extend(["", f"## {relation}: `{path}{line}`", "", "```text", content, "```"])
    return "\n".join(parts)


def _safe_slug(item: dict[str, Any]) -> str:
    raw = str(item.get("label") or item.get("path") or item.get("type") or "context")
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in raw).strip("-")
    return (slug or "context")[:48]


def _limit(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[truncated]\n"


def _metadata_seed(active_context: dict[str, Any] | None, explicit_context: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {"active_context": active_context or {}, "explicit_context": explicit_context or []}

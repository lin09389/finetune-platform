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
MAX_KICKOFF_BRIEF_CHARS = 4_200
MAX_CONTEXT_FILE_CHARS = 24_000
MAX_CONTEXT_FILES = 12
MAX_RETRIEVAL_BRIEF_SOURCES = 8
MAX_RETRIEVAL_BRIEF_SOURCES_PER_KIND = 3


@dataclass(frozen=True)
class DeepAgentsContextPack:
    """Per-run context package consumed by DeepAgents.

    ``files`` values are DeepAgents FileData mappings (``content`` + ``encoding``)
    after build; callers must not pass bare strings into StateBackend.
    """

    prompt: str
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
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
    metadata: dict[str, Any] = {"strategy": "deepagents_kickoff_brief_v1"}

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

    kickoff_brief = _kickoff_brief(
        goal=goal,
        active_context=active_context,
        explicit_context=explicit_context,
        related=related,
        retrieved_pack=retrieved_pack,
    )
    file_lines = [f"- `{path}` ({estimate_tokens(content)} tokens est.)" for path, content in files.items()]
    virtual_file_list = "\n".join(file_lines) if file_lines else "- 无"

    prompt = "\n\n".join(
        [
            "【用户目标】\n" + _limit(goal.strip() or "继续执行当前任务。", MAX_INLINE_PROMPT_CHARS),
            "【启动速览】\n" + kickoff_brief,
            (
                "【虚拟文件系统补充材料】\n"
                "速览已包含启动所需信息；只有需要完整原文、长上下文或更细代码片段时，再按需读取 `/context/...` 下的虚拟文件。\n"
                "长文本上下文仍保留在虚拟文件系统中，可用 read_file/grep/glob 深挖，但这些文件不是启动必读步骤。\n"
                "读取或修改真实项目文件时优先使用 `/workspace/...` 路径。\n"
                "可用虚拟上下文文件：\n"
                f"{virtual_file_list}"
            ),
        ]
    )
    virtual_file_tokens = sum(estimate_tokens(content) for content in files.values())
    metadata.update(
        {
            "file_count": len(files),
            "virtual_file_count": len(files),
            "virtual_file_tokens": virtual_file_tokens,
            "kickoff_brief_chars": len(kickoff_brief),
            "kickoff_brief_tokens": estimate_tokens(kickoff_brief),
            "files": [{"path": path, "tokens": estimate_tokens(content), "chars": len(content)} for path, content in files.items()],
            "prompt_tokens": estimate_tokens(prompt),
            "source_hash": hashlib.sha256(json.dumps(_metadata_seed(active_context, explicit_context), ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        }
    )
    # Emit FileData at the context-pack boundary so graph injection cannot pass bare strings.
    from agent_session.runtime import normalize_deepagents_files

    return DeepAgentsContextPack(prompt=prompt, files=normalize_deepagents_files(files), metadata=metadata)


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


def _kickoff_brief(
    *,
    goal: str,
    active_context: dict[str, Any] | None,
    explicit_context: list[dict[str, Any]] | None,
    related: list[dict[str, Any]],
    retrieved_pack: ContextPack | None,
) -> str:
    lines = [
        "## Task",
        f"- goal: {_text_preview(goal.strip() or '继续执行当前任务。', 700)}",
    ]
    if active_context:
        lines.extend(_active_context_brief(active_context))
    if explicit_context:
        lines.extend(_explicit_context_brief(explicit_context))
    if related:
        lines.extend(_related_context_brief(related))
    if retrieved_pack and retrieved_pack.sources:
        lines.extend(_retrieval_sources_brief(retrieved_pack))
    lines.extend(_recommended_first_actions(active_context, explicit_context, related, retrieved_pack))
    return _limit("\n".join(lines).strip(), MAX_KICKOFF_BRIEF_CHARS)


def _active_context_brief(active_context: dict[str, Any]) -> list[str]:
    cursor = active_context.get("cursor") or {}
    selection = active_context.get("selection") or {}
    selected_text = str(selection.get("text") or "").strip() if isinstance(selection, dict) else ""
    preview = _text_preview(str(active_context.get("content_preview") or ""), 240)
    lines = [
        "",
        "## Active editor",
        f"- file: `{active_context.get('file_path') or 'unknown'}`",
        f"- cursor: line {cursor.get('line', 1)}, column {cursor.get('column', 1)}",
    ]
    if selected_text:
        lines.append(f"- selected_text: {len(selected_text)} chars stored at `/context/editor/active-file.md`")
    if preview:
        lines.append(f"- preview: {preview}")
    return lines


def _explicit_context_brief(explicit_context: list[dict[str, Any]]) -> list[str]:
    lines = ["", "## Explicit mentions"]
    for index, item in enumerate(explicit_context[:MAX_CONTEXT_FILES], start=1):
        label = item.get("label") or item.get("path") or "context"
        path = item.get("path") or ""
        line = f":{item.get('line')}" if item.get("line") else ""
        content = str(item.get("content") or "").strip()
        suffix = f" - {_text_preview(content, 180)}" if content else ""
        lines.append(f"- {index}. @{label}: `{path}{line}`{suffix}")
    return lines


def _related_context_brief(related: list[dict[str, Any]]) -> list[str]:
    lines = ["", "## Related files"]
    for index, item in enumerate(related[:MAX_RETRIEVAL_BRIEF_SOURCES], start=1):
        relation = item.get("relation") or "related"
        path = item.get("path") or ""
        line = f":{item.get('line')}" if item.get("line") else ""
        content = _text_preview(str(item.get("content") or ""), 160)
        suffix = f" - {content}" if content else ""
        lines.append(f"- {index}. {relation}: `{path}{line}`{suffix}")
    return lines


def _retrieval_sources_brief(pack: ContextPack) -> list[str]:
    lines = ["", "## Retrieved context summary"]
    total = 0
    for kind in ("memory", "project", "knowledge"):
        sources = [source for source in pack.sources if source.kind == kind][:MAX_RETRIEVAL_BRIEF_SOURCES_PER_KIND]
        if not sources:
            continue
        lines.append(f"- {kind}:")
        for source in sources:
            if total >= MAX_RETRIEVAL_BRIEF_SOURCES:
                break
            lines.append(f"  - {_source_brief(source)}")
            total += 1
        if total >= MAX_RETRIEVAL_BRIEF_SOURCES:
            break
    if pack.warnings:
        lines.append(f"- warnings: {_text_preview('; '.join(pack.warnings), 240)}")
    return lines if total else []


def _source_brief(source: Any) -> str:
    path = source.metadata.get("memory_path") or source.path or source.source
    preview = _text_preview(str(source.content or ""), 220)
    return f"`{path}` | kind={source.kind} | score={source.score:.3g} | tokens={source.tokens} | {preview}"


def _recommended_first_actions(
    active_context: dict[str, Any] | None,
    explicit_context: list[dict[str, Any]] | None,
    related: list[dict[str, Any]],
    retrieved_pack: ContextPack | None,
) -> list[str]:
    candidate_paths: list[str] = []
    if active_context and active_context.get("file_path"):
        candidate_paths.append(str(active_context.get("file_path")))
    for item in explicit_context or []:
        if item.get("path"):
            candidate_paths.append(str(item.get("path")))
    for item in related[:3]:
        if item.get("path"):
            candidate_paths.append(str(item.get("path")))
    if retrieved_pack:
        for source in retrieved_pack.sources:
            if source.kind == "project" and source.path and _looks_like_file_path(str(source.path)):
                candidate_paths.append(str(source.path))
    unique_paths = list(dict.fromkeys(candidate_paths))[:5]
    lines = ["", "## Recommended first actions"]
    if unique_paths:
        workspace_paths = ", ".join(f"`/workspace/{path.lstrip('/')}`" for path in unique_paths)
        lines.append(f"- Start from the real project file(s): {workspace_paths}.")
    else:
        lines.append("- Start from the user goal and search real project files under `/workspace/` as needed.")
    lines.append("- Use virtual `/context/...` files only when the brief is insufficient or full offloaded text is required.")
    lines.append("- After reading the necessary real files, edit and verify according to the task.")
    return lines


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


def _text_preview(text: str, max_chars: int) -> str:
    cleaned = " ".join(
        line.strip()
        for line in text.replace("```", "").splitlines()
        if line.strip()
    )
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip() + "..."


def _looks_like_file_path(path: str) -> bool:
    name = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return "." in name


def _limit(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[truncated]\n"


def _metadata_seed(active_context: dict[str, Any] | None, explicit_context: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {"active_context": active_context or {}, "explicit_context": explicit_context or []}

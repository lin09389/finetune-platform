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
# Phase 3: total token budget across all /context virtual files. When exceeded,
# lowest-priority retrieval files are dropped (task/editor always kept).
MAX_TOTAL_CONTEXT_FILE_TOKENS = 60_000

# Alias paths historically injected alongside canonical /context/ files.
# Phase 3 drops them so the file listing is canonical-only (less prompt bloat).
_ALIAS_PATHS = frozenset({"/task.md", "/active-file.md", "/editor/active-file.md"})

# Drop priority for total-token-budget enforcement (lowest first).
_BUDGET_DROP_PRIORITY = (
    f"{CONTEXT_ROOT}/retrieval/",
    f"{CONTEXT_ROOT}/mentions/",
    f"{CONTEXT_ROOT}/editor/",
)


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
    task_scope: dict[str, Any] | None = None,
    verify_recipe: dict[str, Any] | None = None,
    knowledge_collection_id: str | None = None,
    session_metadata: dict[str, Any] | None = None,
) -> DeepAgentsContextPack:
    """Build a bounded prompt plus /context files for a DeepAgents run."""

    files: dict[str, str] = {}
    metadata: dict[str, Any] = {"strategy": "deepagents_kickoff_brief_v1"}

    task_index = _task_index(goal, active_context, explicit_context)
    files[f"{CONTEXT_ROOT}/task.md"] = task_index
    files["/task.md"] = task_index

    # Phase B0: verify recipe + scope as virtual context (optional).
    if verify_recipe and isinstance(verify_recipe, dict):
        recipe_md = str(verify_recipe.get("markdown") or "").strip()
        if recipe_md:
            files[f"{CONTEXT_ROOT}/verify-recipe.md"] = _limit(recipe_md, MAX_CONTEXT_FILE_CHARS)
            metadata["verify_recipe_sources"] = list(verify_recipe.get("sources") or [])[:12]
    if task_scope and isinstance(task_scope, dict):
        scope_paths = [str(p) for p in (task_scope.get("paths") or []) if str(p).strip()]
        if scope_paths or task_scope.get("notes"):
            scope_lines = [
                "# Task Scope",
                "",
                "Platform-enforced work scope for this session.",
                "Prefer exploration and edits under these project-relative paths.",
                "",
            ]
            for path in scope_paths:
                scope_lines.append(f"- `{path}`")
            if task_scope.get("notes"):
                scope_lines.extend(["", f"Notes: {task_scope.get('notes')}"])
            files[f"{CONTEXT_ROOT}/task-scope.md"] = _limit("\n".join(scope_lines) + "\n", 4000)
            metadata["task_scope_paths"] = scope_paths

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

    # Phase B1: shallow workspace inventory (works without embeddings/index).
    inventory = _build_workspace_inventory(goal, project_path, task_scope=task_scope)
    metadata["workspace_inventory"] = _inventory_public_meta(inventory)
    if inventory.get("status") == "ok" and inventory.get("markdown"):
        files[f"{CONTEXT_ROOT}/retrieval/workspace-inventory.md"] = _limit(
            str(inventory.get("markdown") or ""),
            MAX_CONTEXT_FILE_CHARS,
        )

    from context.knowledge_binding import resolve_agent_knowledge_collection

    collection_id = knowledge_collection_id
    knowledge_obs: dict[str, Any]
    if collection_id is not None and str(collection_id).strip():
        knowledge_obs = {
            "status": "configured",
            "source": "explicit",
            "collection_id": str(collection_id).strip(),
            "use_knowledge": True,
        }
        collection_id = str(collection_id).strip()
    else:
        collection_id, knowledge_obs = resolve_agent_knowledge_collection(session_metadata)

    retrieved_pack, project_retrieval = await _build_retrieval_pack(
        goal,
        project_path,
        session_id=session_id,
        user_id=user_id,
        knowledge_collection_id=collection_id,
    )
    metadata["project_retrieval"] = project_retrieval
    metadata["knowledge_binding"] = knowledge_obs
    if retrieved_pack and retrieved_pack.context_text:
        files.update(_context_pack_files(retrieved_pack))
        metadata["retrieval"] = retrieved_pack.to_dict()
        if retrieved_pack.warnings:
            metadata.setdefault("warnings", [])
            if isinstance(metadata["warnings"], list):
                metadata["warnings"].extend(list(retrieved_pack.warnings)[:8])
    elif knowledge_obs.get("status") == "not_configured":
        metadata.setdefault("warnings", [])
        if isinstance(metadata["warnings"], list):
            metadata["warnings"].append("knowledge_not_configured")
    elif knowledge_obs.get("status") == "disabled":
        metadata.setdefault("warnings", [])
        if isinstance(metadata["warnings"], list):
            metadata["warnings"].append("knowledge_disabled")

    # Phase 3: secret redaction across all virtual file contents + goal.
    from context.redaction import REDACTED, count_redactions, redact_secrets

    redaction_count = 0
    redacted_files: dict[str, str] = {}
    for path, content in files.items():
        cleaned = redact_secrets(content)
        redaction_count += count_redactions(content, cleaned)
        redacted_files[path] = cleaned
    files = redacted_files
    goal = redact_secrets(goal)
    metadata["secret_redaction"] = {"applied": True, "count": redaction_count}

    # Phase 3: enforce a total token budget across virtual files.
    files, budget_dropped = _apply_total_token_budget(files)
    metadata["max_total_context_file_tokens"] = MAX_TOTAL_CONTEXT_FILE_TOKENS
    if budget_dropped:
        metadata.setdefault("warnings", [])
        if isinstance(metadata["warnings"], list):
            metadata["warnings"].append(
                f"context_budget_dropped:{len(budget_dropped)}"
            )

    # Phase 3: inject "Recently modified" from session context_refresh signal.
    refresh_lines = _context_refresh_brief(session_metadata)
    if refresh_lines:
        metadata["context_refresh_injected"] = True

    kickoff_brief = _kickoff_brief(
        goal=goal,
        active_context=active_context,
        explicit_context=explicit_context,
        related=related,
        retrieved_pack=retrieved_pack,
        inventory=inventory,
        project_retrieval=project_retrieval,
    )
    file_lines = [f"- `{path}` ({estimate_tokens(content)} tokens est.)" for path, content in files.items()]
    virtual_file_list = "\n".join(file_lines) if file_lines else "- 无"

    from agent_session.task_scope import (
        format_scope_prompt_section,
        format_verify_recipe_prompt_section,
    )

    prompt_sections = [
        "【用户目标】\n" + _limit(goal.strip() or "继续执行当前任务。", MAX_INLINE_PROMPT_CHARS),
        "【启动速览】\n" + kickoff_brief,
    ]
    if refresh_lines:
        prompt_sections.append("【Recently modified】\n" + "\n".join(refresh_lines))
    scope_section = format_scope_prompt_section(task_scope if isinstance(task_scope, dict) else None)
    if scope_section:
        prompt_sections.append(scope_section)
    recipe_section = format_verify_recipe_prompt_section(
        verify_recipe if isinstance(verify_recipe, dict) else None
    )
    if recipe_section:
        prompt_sections.append(recipe_section)
    prompt_sections.append(
        (
            "【虚拟文件系统补充材料】\n"
            "速览已包含启动所需信息；只有需要完整原文、长上下文或更细代码片段时，再按需读取 `/context/...` 下的虚拟文件。\n"
            "长文本上下文仍保留在虚拟文件系统中，可用 read_file/grep/glob 深挖，但这些文件不是启动必读步骤。\n"
            "读取或修改真实项目文件时优先使用 `/workspace/...` 路径。\n"
            "可用虚拟上下文文件：\n"
            f"{virtual_file_list}"
        )
    )
    prompt = "\n\n".join(prompt_sections)
    virtual_file_tokens = sum(estimate_tokens(content) for content in files.values())
    # Canonical file listing excludes alias paths (kept in pack.files for
    # DeepAgents compatibility but not advertised to the model/UI).
    file_listing = [
        {"path": path, "tokens": estimate_tokens(content), "chars": len(content)}
        for path, content in files.items()
        if path not in _ALIAS_PATHS
    ]
    metadata.update(
        {
            "file_count": len(files),
            "virtual_file_count": len(file_listing),
            "virtual_file_tokens": virtual_file_tokens,
            "injected_file_count": len(files),
            "kickoff_brief_chars": len(kickoff_brief),
            "kickoff_brief_tokens": estimate_tokens(kickoff_brief),
            "files": file_listing,
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
    knowledge_collection_id: str | None = None,
) -> tuple[ContextPack | None, dict[str, Any]]:
    """Return (pack, project_retrieval observability).

    Knowledge is enabled only when ``knowledge_collection_id`` is non-empty
    (session/workspace binding). Failures stay non-blocking via pack warnings.
    """
    if not project_path and not knowledge_collection_id:
        return None, {"status": "skipped", "reason": "no_project_path", "project_source_count": 0}
    use_knowledge = bool(knowledge_collection_id and str(knowledge_collection_id).strip())
    try:
        pack = await get_context_builder().build(
            query=goal,
            user_id=user_id,
            session_id=session_id,
            options=ContextBuildOptions(
                use_memory=True,
                use_knowledge=use_knowledge,
                use_project_context=bool(project_path),
                knowledge_collection_id=str(knowledge_collection_id).strip() if use_knowledge else None,
                project_path=project_path,
                max_context_tokens=3200,
                reserved_output_tokens=1024,
                max_total_sources=8,
                project_max_tokens=2200,
            ),
        )
        project_count = sum(1 for source in pack.sources if source.kind == "project")
        knowledge_count = sum(1 for source in pack.sources if source.kind == "knowledge")
        status = "ok" if project_count > 0 or knowledge_count > 0 or pack.memory_count else "empty"
        return pack, {
            "status": status,
            "reason": None if (project_count or knowledge_count or pack.memory_count) else "no_project_sources",
            "project_source_count": project_count,
            "knowledge_source_count": knowledge_count,
            "use_knowledge": use_knowledge,
            "knowledge_collection_id": str(knowledge_collection_id).strip() if use_knowledge else None,
            "total_sources": len(pack.sources),
            "warnings": list(pack.warnings or [])[:6],
        }
    except Exception as exc:
        logger.debug("DeepAgents retrieval context build failed: %s", exc, exc_info=True)
        return None, {
            "status": "error",
            "reason": str(exc)[:200],
            "project_source_count": 0,
            "use_knowledge": use_knowledge,
        }


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
    inventory: dict[str, Any] | None = None,
    project_retrieval: dict[str, Any] | None = None,
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
    lines.extend(_inventory_brief(inventory, project_retrieval))
    lines.extend(
        _recommended_first_actions(
            active_context,
            explicit_context,
            related,
            retrieved_pack,
            inventory=inventory,
        )
    )
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
    *,
    inventory: dict[str, Any] | None = None,
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
            path = source.path or (source.metadata or {}).get("path")
            if source.kind == "project" and path and _looks_like_file_path(str(path)):
                candidate_paths.append(str(path))
    for path in (inventory or {}).get("recommended_reads") or []:
        if path:
            candidate_paths.append(str(path))
    unique_paths = list(dict.fromkeys(_normalize_workspace_rel(p) for p in candidate_paths if p))[:5]
    unique_paths = [p for p in unique_paths if p]
    lines = ["", "## Recommended first actions"]
    if unique_paths:
        workspace_paths = ", ".join(f"`/workspace/{path}`" for path in unique_paths)
        lines.append(f"- Start from the real project file(s): {workspace_paths}.")
    else:
        lines.append("- Start from the user goal and search real project files under `/workspace/` as needed.")
    if inventory and inventory.get("status") == "ok":
        lines.append(
            "- Workspace inventory is at `/context/retrieval/workspace-inventory.md` "
            "(prefer it over broad ls/glob when project retrieval is empty)."
        )
    lines.append("- Use virtual `/context/...` files only when the brief is insufficient or full offloaded text is required.")
    lines.append("- After reading the necessary real files, edit and verify according to the task.")
    return lines


def _inventory_brief(
    inventory: dict[str, Any] | None,
    project_retrieval: dict[str, Any] | None,
) -> list[str]:
    if not inventory and not project_retrieval:
        return []
    lines = ["", "## Workspace context (B1)"]
    pr = project_retrieval or {}
    if pr:
        status = pr.get("status") or "unknown"
        lines.append(
            f"- project_retrieval: `{status}`"
            + (f" ({pr.get('reason')})" if pr.get("reason") else "")
            + f"; project_sources={int(pr.get('project_source_count') or 0)}"
        )
    inv = inventory or {}
    if inv:
        lines.append(
            f"- workspace_inventory: `{inv.get('status') or 'unknown'}`"
            + (f" ({inv.get('reason')})" if inv.get("reason") else "")
            + f"; recommended={len(inv.get('recommended_reads') or [])}"
            + ("; scope_filtered" if inv.get("scoped") else "")
        )
        reads = [str(p) for p in (inv.get("recommended_reads") or []) if str(p).strip()][:5]
        if reads:
            lines.append("- inventory recommended reads: " + ", ".join(f"`/workspace/{p}`" for p in reads))
            lines.append("- full inventory: `/context/retrieval/workspace-inventory.md`")
    return lines


def _build_workspace_inventory(
    goal: str,
    project_path: str | None,
    *,
    task_scope: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        from context.workspace_inventory import build_workspace_inventory

        return build_workspace_inventory(project_path, goal, task_scope=task_scope)
    except Exception as exc:
        logger.debug("Workspace inventory build failed: %s", exc, exc_info=True)
        return {
            "schema_version": 1,
            "status": "error",
            "reason": str(exc)[:200],
            "recommended_reads": [],
            "matched_files": [],
            "tree": [],
            "markdown": "",
        }


def _inventory_public_meta(inventory: dict[str, Any] | None) -> dict[str, Any]:
    inv = inventory or {}
    return {
        "status": inv.get("status"),
        "reason": inv.get("reason"),
        "scoped": bool(inv.get("scoped")),
        "recommended_reads": list(inv.get("recommended_reads") or [])[:12],
        "matched_files": list(inv.get("matched_files") or [])[:12],
        "tree_count": len(inv.get("tree") or []),
        "scanned_files": int(inv.get("scanned_files") or 0),
        "tokens": list(inv.get("tokens") or [])[:16],
    }


def _normalize_workspace_rel(path: str) -> str:
    text = str(path or "").replace("\\", "/").strip()
    if text.startswith("/workspace/"):
        text = text[len("/workspace/") :]
    text = text.lstrip("/")
    # Drop absolute Windows/Unix roots from retrieval metadata.
    if len(text) >= 2 and text[1] == ":":
        return ""
    if text.startswith(("C:/", "c:/", "D:/", "d:/")):
        return ""
    return text


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


def _context_refresh_brief(session_metadata: dict[str, Any] | None) -> list[str]:
    """Build a short "Recently modified" section from the context_refresh signal.

    Returns an empty list when there is no refresh signal. The section names
    recently changed files and recent tool failures so the agent starts from
    fresh evidence rather than stale assumptions.
    """
    if not session_metadata:
        return []
    refresh = session_metadata.get("context_refresh")
    if not isinstance(refresh, dict):
        return []
    lines: list[str] = []
    changed = [str(p) for p in (refresh.get("changed_files") or []) if str(p).strip()]
    if changed:
        lines.append("Changed files:")
        for path in changed[:12]:
            lines.append(f"- `{path}`")
    failures = [f for f in (refresh.get("recent_failures") or []) if isinstance(f, dict)]
    if failures:
        lines.append("Recent failures:")
        for failure in failures[:6]:
            tool = str(failure.get("tool") or "")
            path = str(failure.get("path") or "")
            reason = str(failure.get("reason") or "")[:120]
            lines.append(f"- {tool} `{path}`: {reason}".rstrip())
    return lines


def _apply_total_token_budget(
    files: dict[str, str],
    *,
    max_tokens: int = MAX_TOTAL_CONTEXT_FILE_TOKENS,
) -> tuple[dict[str, str], dict[str, str]]:
    """Drop lowest-priority files until the total token budget fits.

    Always keeps ``/context/task.md``. Retrieval/mentions/editor files are
    dropped first (in that order) until the kept set is within budget.
    Returns ``(kept, dropped)`` as path -> content mappings.
    """
    kept = dict(files)
    if not kept:
        return {}, {}

    def _total(mapping: dict[str, str]) -> int:
        return sum(estimate_tokens(content) for content in mapping.values())

    if _total(kept) <= max_tokens:
        return kept, {}

    dropped: dict[str, str] = {}
    # Drop by priority prefix; within a prefix, drop the largest first.
    for prefix in _BUDGET_DROP_PRIORITY:
        candidates = sorted(
            (path for path in list(kept.keys()) if path.startswith(prefix)),
            key=lambda p: estimate_tokens(kept[p]),
            reverse=True,
        )
        for path in candidates:
            if _total(kept) <= max_tokens:
                break
            dropped[path] = kept.pop(path)
    return kept, dropped


def _limit(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[truncated]\n"


def _metadata_seed(active_context: dict[str, Any] | None, explicit_context: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {"active_context": active_context or {}, "explicit_context": explicit_context or []}

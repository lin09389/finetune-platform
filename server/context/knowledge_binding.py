"""Resolve optional knowledge-collection binding for Agent context packs.

Policy (Phase 2):
- Session metadata ``knowledge_collection_id`` wins when the key is present.
  Empty / null means explicitly disabled for this session.
- Otherwise inherit workspace default: ``knowledge_collection_id`` then
  ``vector_collection_name``.
- Missing collection is non-blocking: callers leave ``use_knowledge=False`` and
  record observability for UI / metadata.
"""
from __future__ import annotations

from typing import Any


def get_workspace_knowledge_collection(workspace_id: str | None) -> str | None:
    """Read default knowledge collection id from workspace metadata store."""
    ws_id = str(workspace_id or "").strip()
    if not ws_id:
        return None
    try:
        from api.workspace import workspaces
    except Exception:
        return None
    workspace = workspaces.get(ws_id)
    if not isinstance(workspace, dict):
        return None
    for key in ("knowledge_collection_id", "vector_collection_name"):
        raw = workspace.get(key)
        if raw is None:
            continue
        value = str(raw).strip()
        if value:
            return value
    # Fallback: workspace id itself is often the vector collection name.
    return ws_id if ws_id else None


def resolve_agent_knowledge_collection(
    metadata: dict[str, Any] | None,
    *,
    workspace_id: str | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Return ``(collection_id|None, observability)``.

    Observability is safe to store on session ``context_engineering`` metadata.
    """
    meta = dict(metadata or {})
    obs: dict[str, Any] = {
        "status": "not_configured",
        "source": None,
        "collection_id": None,
        "use_knowledge": False,
    }

    if "knowledge_collection_id" in meta:
        raw = meta.get("knowledge_collection_id")
        if raw is None or str(raw).strip() == "":
            obs["status"] = "disabled"
            obs["source"] = "session"
            return None, obs
        collection_id = str(raw).strip()
        obs.update(
            status="configured",
            source="session",
            collection_id=collection_id,
            use_knowledge=True,
        )
        return collection_id, obs

    nested = meta.get("workspace") if isinstance(meta.get("workspace"), dict) else {}
    ws_id = str(workspace_id or nested.get("id") or "").strip() or None
    inherited = get_workspace_knowledge_collection(ws_id)
    if inherited:
        obs.update(
            status="configured",
            source="workspace",
            collection_id=inherited,
            use_knowledge=True,
        )
        return inherited, obs

    return None, obs

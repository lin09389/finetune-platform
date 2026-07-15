"""Shipped knowledge-collection binding for Agent context packs."""
from __future__ import annotations

from context.knowledge_binding import (
    get_workspace_knowledge_collection,
    resolve_agent_knowledge_collection,
)


def test_resolve_defaults_to_not_configured_without_metadata():
    collection_id, obs = resolve_agent_knowledge_collection(None)
    assert collection_id is None
    assert obs["status"] == "not_configured"
    assert obs["use_knowledge"] is False


def test_resolve_session_explicit_collection():
    collection_id, obs = resolve_agent_knowledge_collection(
        {"knowledge_collection_id": "kb-demo"}
    )
    assert collection_id == "kb-demo"
    assert obs["status"] == "configured"
    assert obs["source"] == "session"
    assert obs["use_knowledge"] is True


def test_resolve_session_empty_disables_knowledge():
    collection_id, obs = resolve_agent_knowledge_collection(
        {"knowledge_collection_id": ""}
    )
    assert collection_id is None
    assert obs["status"] == "disabled"
    assert obs["source"] == "session"
    assert obs["use_knowledge"] is False


def test_get_workspace_knowledge_collection_missing_workspace():
    assert get_workspace_knowledge_collection(None) is None
    assert get_workspace_knowledge_collection("") is None

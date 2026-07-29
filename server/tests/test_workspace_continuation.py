from __future__ import annotations

from agent_session.repository import AgentSessionRepository
from agent_session.services.session_lifecycle import SessionLifecycleService

from workspace.portability.providers import AgentSessionTaskContextProvider
from workspace.portability.repository import WorkspacePortabilityRepository


def test_workspace_task_projection_is_owner_scoped_and_excludes_authority(tmp_path):
    sessions = AgentSessionRepository(str(tmp_path / "agent.db"))
    sessions.create_session(
        {
            "id": "old-session",
            "agent_id": "build",
            "title": "Port this workspace",
            "project_path": str(tmp_path),
            "metadata": {
                "user_id": "owner-a",
                "workspace": {"id": "ws-a", "path": str(tmp_path)},
                "task_mode": "build",
                "execution_plan": {"schema_version": "agent.execution.plan.v1", "nodes": []},
                "changed_files": ["src/app.py", str(tmp_path / "secret.py")],
                "session_tool_trust": {"shell": True},
                "deepagents_checkpoint": {"thread": "old"},
                "approval": {"id": "old-approval"},
            },
        }
    )
    provider = AgentSessionTaskContextProvider(sessions)

    assert provider.list_task_contexts("ws-a", "owner-b") == []
    [context] = provider.list_task_contexts("ws-a", "owner-a")
    assert context.title == "Port this workspace"
    assert [item.model_dump() for item in context.changed_files] == [
        {"path": "src/app.py", "additions": 0, "deletions": 0}
    ]
    assert "session_tool_trust" not in str(context)
    assert "deepagents_checkpoint" not in str(context)
    assert "approval" not in str(context)
    assert str(tmp_path) not in str(context)


def test_import_commit_is_idempotent_and_continuations_are_owner_scoped(tmp_path):
    repository = WorkspacePortabilityRepository(str(tmp_path / "portability.db"))
    inspection = repository.create_inspection(
        owner_id="owner-a",
        package_digest="digest",
        manifest={"portable_workspace_id": "pws_test"},
        preview={"task_count": 1},
    )
    first = repository.commit_import(
        token=inspection["token"],
        owner_id="owner-a",
        workspace_id="ws-new",
        source_portable_id="pws_test",
        package_digest="digest",
        resource_bindings={},
        contexts=[{"source_task_fingerprint": "fingerprint", "title": "Continue", "task_mode": "build"}],
    )
    second = repository.commit_import(
        token=inspection["token"],
        owner_id="owner-a",
        workspace_id="ws-ignored",
        source_portable_id="pws_test",
        package_digest="digest",
        resource_bindings={},
        contexts=[],
    )

    assert second == first
    assert len(repository.list_continuations("ws-new", "owner-a")) == 1
    assert repository.list_continuations("ws-new", "owner-b") == []


def test_continuation_metadata_is_an_explicit_safe_allowlist():
    metadata = SessionLifecycleService._safe_continuation_metadata(
        {
            "title": "Continue safely",
            "mode": "hybrid",
            "execution_plan": {"nodes": []},
            "session_tool_trust": {"execute": True},
            "approval": {"id": "old"},
            "deepagents_checkpoint": {"thread": "old"},
            "raw_prompt": "do not carry this",
        }
    )

    assert metadata == {"title": "Continue safely", "mode": "hybrid", "execution_plan": {"nodes": []}}

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_session.models import AgentSessionResponse  # noqa: E402
from agent_session.repository import AgentSessionRepository  # noqa: E402
from agent_session.services.session_lifecycle import SessionLifecycleService  # noqa: E402
from workspace.portability.archive import SafeWorkspaceArchiveCodec, UnsupportedWorkspaceManifestVersion  # noqa: E402
from workspace.portability.providers import LocalWorkspaceManifestProvider  # noqa: E402
from workspace.portability.repository import WorkspacePortabilityRepository  # noqa: E402
from workspace.portability.service import WorkspaceManifestService  # noqa: E402


def _session(repository: AgentSessionRepository, mode: str, index: int, root: Path) -> None:
    repository.create_session(
        {
            "id": f"source-{mode}",
            "agent_id": "build",
            "status": "completed",
            "title": f"{mode.title()} task",
            "project_path": str(root),
            "metadata": {
                "user_id": "owner-a",
                "workspace": {"id": "ws-source", "path": str(root)},
                "task_mode": mode,
                "summary": f"Safe {mode} summary",
                "changed_files": ["src/app.py", str(root / "private.py")],
                "verification": {"category": "test", "status": "passed", "summary": "Focused checks passed"},
                "portable_resource_references": [
                    {"kind": "artifact", "reference_id": f"artifact-{index}", "display_name": "Report"}
                ],
                "raw_prompt": "SOURCE_SNIPPET_DO_NOT_EXPORT",
                "terminal_output": "RAW_TERMINAL_DO_NOT_EXPORT",
                "diff": "FULL_DIFF_DO_NOT_EXPORT",
                "approval": {"id": "approval-do-not-export"},
                "session_tool_trust": ["execute"],
                "deepagents_checkpoint": {"thread_id": "old-thread"},
                "api_key": "sk-do-not-export-12345678901234567890",
            },
        }
    )


def test_golden_round_trip_preserves_safe_context_without_runtime_authority(tmp_path: Path) -> None:
    sessions = AgentSessionRepository(str(tmp_path / "sessions.db"))
    for index, mode in enumerate(("build", "train", "hybrid"), start=1):
        _session(sessions, mode, index, tmp_path)

    workspace = {
        "id": "ws-source",
        "name": "Portable demo",
        "description": "Reference-only project",
        "local_path": str(tmp_path),
    }
    service = WorkspaceManifestService(manifest_provider=LocalWorkspaceManifestProvider(workspace, sessions))
    package = service.export_package(workspace_id="ws-source", owner_id="owner-a")
    inspected = service.inspect_package(package)

    assert {context.mode for context in inspected.manifest.task_contexts} == {"build", "train", "hybrid"}
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        rendered = b"\n".join(archive.read(name) for name in archive.namelist()).decode("utf-8")
    for prohibited in (
        str(tmp_path),
        "SOURCE_SNIPPET_DO_NOT_EXPORT",
        "RAW_TERMINAL_DO_NOT_EXPORT",
        "FULL_DIFF_DO_NOT_EXPORT",
        "approval-do-not-export",
        "session_tool_trust",
        "old-thread",
        "sk-do-not-export",
    ):
        assert prohibited not in rendered

    imports = WorkspacePortabilityRepository(str(tmp_path / "imports.db"))
    inspection = imports.create_inspection(
        owner_id="owner-a",
        package_digest=inspected.package_digest,
        manifest=inspected.manifest.model_dump(mode="json"),
        preview={"task_count": 3},
    )
    committed = imports.commit_import(
        token=inspection["token"],
        owner_id="owner-a",
        workspace_id="ws-target",
        source_portable_id=inspected.manifest.portable_workspace_id,
        package_digest=inspected.package_digest,
        resource_bindings={},
        contexts=[context.model_dump(mode="json") for context in inspected.manifest.task_contexts],
    )
    replayed = imports.commit_import(
        token=inspection["token"],
        owner_id="owner-a",
        workspace_id="ignored",
        source_portable_id="ignored",
        package_digest=inspected.package_digest,
        resource_bindings={},
        contexts=[],
    )
    assert replayed == committed
    assert len(imports.list_continuations("ws-target", "owner-a")) == 3
    assert imports.list_continuations("ws-target", "owner-b") == []


def test_continuation_always_creates_a_fresh_policy_session() -> None:
    created_request = None
    base = AgentSessionResponse(
        id="new-session",
        agent_id="build",
        status="idle",
        title="Continue safely",
        workspace_id="ws-target",
        task_mode="hybrid",
        metadata={"autonomy_mode": "safe_auto", "deepagents_interrupt_on": False},
        created_at="2026-07-13T00:00:00+00:00",
        updated_at="2026-07-13T00:00:00+00:00",
        parts=[],
    )

    class Repository:
        def update_session(self, session_id: str, **updates):
            return {**base.model_dump(), "metadata": updates["metadata"]}

    owner = SimpleNamespace(
        repository=Repository(),
        event_service=SimpleNamespace(_attach_recovery_diagnostics=lambda value: value),
    )
    lifecycle = SessionLifecycleService(owner)

    def create_session(request, user_id=None):
        nonlocal created_request
        created_request = request
        assert user_id == "owner-a"
        return base

    lifecycle.create_session = create_session  # type: ignore[method-assign]
    continued = lifecycle.create_continuation_session(
        workspace_id="ws-target",
        continuation_context={
            "id": "old-context",
            "title": "Continue safely",
            "mode": "hybrid",
            "summary": "Only safe summary",
            "session_tool_trust": ["execute"],
            "approval": {"id": "old"},
            "deepagents_thread_id": "old-thread",
        },
        user_id="owner-a",
    )

    assert continued.id == "new-session"
    assert created_request.workspace_id == "ws-target"
    assert created_request.autonomy_mode is None
    assert created_request.task_mode == "hybrid"
    assert continued.metadata["continuation"] == {
        "title": "Continue safely",
        "mode": "hybrid",
        "summary": "Only safe summary",
    }
    assert "session_tool_trust" not in continued.metadata
    assert "approval" not in continued.metadata
    assert "deepagents_thread_id" not in continued.metadata


def test_explicitly_rejects_a_checksum_valid_future_manifest() -> None:
    from datetime import UTC, datetime

    from workspace.portability.schemas import PortableProjectReference, ProducerInfo, WorkspaceIdentity, WorkspaceManifestV1

    codec = SafeWorkspaceArchiveCodec()
    manifest = WorkspaceManifestV1(
        portable_workspace_id="pws_0123456789abcdef",
        exported_at=datetime(2026, 7, 13, tzinfo=UTC),
        producer=ProducerInfo(name="finetune-platform", version="2.1.0"),
        workspace=WorkspaceIdentity(name="demo"),
        project=PortableProjectReference(display_name="demo"),
    )
    package = codec.encode(manifest)
    with zipfile.ZipFile(io.BytesIO(package)) as source:
        entries = {name: source.read(name) for name in source.namelist()}
    payload = json.loads(entries["manifest.json"])
    payload["schema_version"] = 2
    entries["manifest.json"] = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    checksums = json.loads(entries["checksums.json"])
    checksums["entries"]["manifest.json"] = hashlib.sha256(entries["manifest.json"]).hexdigest()
    entries["checksums.json"] = json.dumps(checksums, sort_keys=True, separators=(",", ":")).encode()
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)

    with pytest.raises(UnsupportedWorkspaceManifestVersion):
        codec.inspect(target.getvalue())

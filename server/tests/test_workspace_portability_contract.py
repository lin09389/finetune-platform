"""Contract tests for the stable, reference-only Workspace manifest."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent))

from workspace.portability.schemas import (  # noqa: E402
    PortableChangedFile,
    PortableDatasetReference,
    PortablePlanStep,
    PortableProjectReference,
    PortableResourceReference,
    PortableTaskContext,
    PortableVerification,
    ProducerInfo,
    WorkspaceIdentity,
    WorkspaceManifestV1,
)


def _manifest(**overrides: object) -> WorkspaceManifestV1:
    values: dict[str, object] = {
        "portable_workspace_id": "pws_0123456789abcdef",
        "exported_at": datetime(2026, 7, 13, tzinfo=UTC),
        "producer": ProducerInfo(name="finetune-platform", version="2.1.0"),
        "workspace": WorkspaceIdentity(name="demo"),
        "project": PortableProjectReference(display_name="demo", git_head="a" * 40),
        "resources": [
            PortableDatasetReference(
                resource_id="dataset_123",
                display_name="alpaca-clean",
                format="jsonl",
                size_bytes=120,
                checksum="b" * 64,
            )
        ],
        "task_contexts": [
            PortableTaskContext(
                source_task_fingerprint="c" * 64,
                title="Fine tune a small model",
                mode="train",
                status="completed",
                execution_plan=[
                    PortablePlanStep(title="prepare dataset", status="completed"),
                    PortablePlanStep(title="train", status="completed"),
                ],
                summary="Training completed and metrics were verified.",
                changed_files=[PortableChangedFile(path="configs/train.yaml", additions=2, deletions=1)],
                verifications=[PortableVerification(category="train", status="passed")],
                updated_at=datetime(2026, 7, 13, tzinfo=UTC),
            )
        ],
    }
    values.update(overrides)
    return WorkspaceManifestV1(**values)


def test_manifest_v1_serializes_only_safe_typed_context() -> None:
    manifest = _manifest()

    assert manifest.schema == "finetune.workspace-manifest"
    assert manifest.schema_version == 1
    assert manifest.resources[0].kind == "dataset"
    payload = manifest.model_dump(mode="json")
    rendered = str(payload)
    for prohibited in ("session_tool_trust", "approval", "prompt", "terminal", "diff", "checkpoint"):
        assert prohibited not in rendered


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("schema_version", 2),
        ("portable_workspace_id", "workspace_123"),
        ("project.git_head", "not-a-git-sha"),
        ("task_contexts.0.changed_files.0.path", "C:\\absolute\\file.py"),
        ("task_contexts.0.changed_files.0.path", "../outside.py"),
    ],
)
def test_manifest_rejects_invalid_version_ids_and_paths(path: str, value: object) -> None:
    payload = _manifest().model_dump(mode="json")
    target: object = payload
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]  # type: ignore[index]
    if isinstance(target, list):
        target[int(parts[-1])] = value
    else:
        target[parts[-1]] = value  # type: ignore[index]

    with pytest.raises(ValidationError):
        WorkspaceManifestV1.model_validate(payload)


def test_manifest_rejects_unknown_fields_at_every_level() -> None:
    payload = _manifest().model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        WorkspaceManifestV1.model_validate(payload)

    payload = _manifest().model_dump(mode="json")
    payload["task_contexts"][0]["session_tool_trust"] = {"shell": "trusted"}
    with pytest.raises(ValidationError):
        WorkspaceManifestV1.model_validate(payload)


def test_typed_resource_reference_rejects_untyped_or_secret_locator() -> None:
    adapter = TypeAdapter(PortableResourceReference)
    resource = adapter.validate_python(_manifest().model_dump(mode="json")["resources"][0])
    assert resource.kind == "dataset"

    payload = _manifest().model_dump(mode="json")
    payload["resources"][0]["locator"] = "/private/dataset.jsonl"
    with pytest.raises(ValidationError):
        WorkspaceManifestV1.model_validate(payload)


def test_manifest_limits_contexts_and_resources() -> None:
    payload = _manifest().model_dump(mode="json")
    payload["task_contexts"] *= 101
    with pytest.raises(ValidationError):
        WorkspaceManifestV1.model_validate(payload)

    payload = _manifest().model_dump(mode="json")
    payload["resources"] *= 501
    with pytest.raises(ValidationError):
        WorkspaceManifestV1.model_validate(payload)

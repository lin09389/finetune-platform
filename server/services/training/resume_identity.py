"""Shared checkpoint resume identity checks for HTTP API and Agent tools."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ResumeIdentityError(ValueError):
    """Hard identity failure that must block resume."""

    def __init__(self, message: str, *, code: str = "checkpoint_identity_mismatch"):
        super().__init__(message)
        self.code = code


def config_hash(config: dict[str, Any] | None) -> str:
    payload = json.dumps(config or {}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_resume_identity(
    *,
    original_record: Any,
    config_dict: dict[str, Any],
    checkpoint_path: Path,
) -> list[str]:
    """Validate semantic identity for checkpoint resume when metadata is available.

    Returns soft warnings for legacy checkpoints without metadata.
    Raises :class:`ResumeIdentityError` when metadata exists and mismatches.
    """
    warnings: list[str] = []
    metadata_path = Path(checkpoint_path) / "checkpoint_metadata.json"
    if not metadata_path.exists():
        warnings.append(
            "checkpoint_metadata.json 不存在，已按旧检查点兼容路径恢复；无法强校验模型/数据集/配置版本"
        )
        return warnings

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ResumeIdentityError(
            f"Checkpoint metadata is unreadable: {exc}",
            code="checkpoint_metadata_unreadable",
        ) from exc

    expected_model = (
        getattr(original_record, "base_model_id", None)
        or config_dict.get("model_id")
        or config_dict.get("modelId")
        or getattr(original_record, "model_name", None)
    )
    expected_dataset = (
        getattr(original_record, "dataset_id", None)
        or config_dict.get("dataset_id")
        or config_dict.get("datasetId")
        or getattr(original_record, "dataset_name", None)
    )
    metadata_model = metadata.get("base_model_id") or metadata.get("model_id") or metadata.get("model")
    metadata_dataset = metadata.get("dataset_id") or metadata.get("dataset")
    metadata_config_hash = metadata.get("config_hash")

    mismatches: list[str] = []
    if metadata_model and expected_model and metadata_model != expected_model:
        mismatches.append(f"base model mismatch: checkpoint={metadata_model}, record={expected_model}")
    if metadata_dataset and expected_dataset and metadata_dataset != expected_dataset:
        mismatches.append(f"dataset mismatch: checkpoint={metadata_dataset}, record={expected_dataset}")

    record_config = getattr(original_record, "config", None) or {}
    record_config_hash = getattr(original_record, "config_hash", None) or config_hash(record_config)
    current_config_hash = config_hash(config_dict)
    if metadata_config_hash and metadata_config_hash not in {record_config_hash, current_config_hash}:
        mismatches.append("training config hash mismatch")

    if mismatches:
        raise ResumeIdentityError(
            "Checkpoint identity validation failed: " + "; ".join(mismatches),
            code="checkpoint_identity_mismatch",
        )
    return warnings


__all__ = ["ResumeIdentityError", "config_hash", "validate_resume_identity"]

"""
训练报告与辅助工具 - 失败分析、进度转换、记录增强
"""
import hashlib
import json
import platform
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from core.logging import get_logger
from core.training_state import TrainingRecord

logger = get_logger(__name__)


def hash_path(path_value: str | Path | None) -> str | None:
    """Return a deterministic SHA-256 digest for a file or directory tree."""
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return None

    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.name.encode("utf-8"))
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    files = sorted(item for item in path.rglob("*") if item.is_file())
    for item in files:
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        with open(item, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _package_version(name: str) -> str | None:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return None


def runtime_provenance() -> dict[str, Any]:
    """Capture the minimum runtime facts needed to reproduce a release."""
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "pytorch": _package_version("torch"),
        "transformers": _package_version("transformers"),
        "peft": _package_version("peft"),
        "datasets": _package_version("datasets"),
    }


def build_failure_feedback(error_message: str) -> dict[str, Any]:
    normalized = (error_message or "").lower()

    if any(token in normalized for token in ("out of memory", "cuda oom", "显存", "oom")):
        return {
            "error_code": "OOM",
            "error_category": "oom",
            "actionable_suggestions": [
                "将 batch size 调整为 1，并提高梯度累积步数。",
                "降低 max_seq_length 后重新执行训练。",
                "优先使用 QLoRA + 4bit 量化。",
            ],
        }

    if any(token in normalized for token in ("dataset not found", "数据集", "加载数据集", "jsondecodeerror", "json 解析", "invalid json", "unsupported dataset", "样本格式")):
        return {
            "error_code": "DATASET_INVALID",
            "error_category": "dataset",
            "actionable_suggestions": [
                "检查数据集 JSON/JSONL 格式和字段。",
                "确保样本包含支持的训练字段。",
                "修复后重新上传并执行预检。",
            ],
        }

    if any(token in normalized for token in ("checkpoint", "resume", "检查点")):
        return {
            "error_code": "CHECKPOINT_INVALID",
            "error_category": "checkpoint",
            "actionable_suggestions": [
                "切换到最近可用 checkpoint 后重试。",
                "确认 checkpoint 与当前模型、数据集一致。",
                "必要时重新启动完整训练任务。",
            ],
        }

    return {
        "error_code": "TRAINING_FAILED",
        "error_category": "runtime",
        "actionable_suggestions": [
            "查看 outputs 中训练日志定位首个错误栈。",
            "重启后端并确认 GPU 资源占用。",
            "使用保守参数重新预检后再训练。",
        ],
    }


def legacy_progress_from_v2_event(event: Any, fallback: Any) -> dict[str, Any]:
    payload = (event.payload if event else {}) or {}
    fb = fallback.model_dump() if hasattr(fallback, "model_dump") else dict(fallback or {})
    status = payload.get("status") or event.phase
    if status == "queued":
        status = "loading"
    elif status == "running":
        status = "training"
    return {
        "epoch": payload.get("epoch", fb.get("epoch", 0)),
        "step": payload.get("step", fb.get("step", 0)),
        "total_steps": payload.get("total_steps", payload.get("totalSteps", fb.get("total_steps", 0))),
        "loss": payload.get("loss", payload.get("final_loss", fb.get("loss", 0.0))),
        "lr": payload.get("lr", payload.get("final_lr", fb.get("lr", 0.0))),
        "vram_used": payload.get("vram_used", payload.get("vramUsed", fb.get("vram_used", 0.0))),
        "elapsed_time": payload.get(
            "elapsed_time",
            payload.get("elapsedTime", payload.get("final_elapsed_time", fb.get("elapsed_time", 0.0))),
        ),
        "eta": payload.get("eta", fb.get("eta", 0.0)),
        "status": status,
        "message": payload.get("message", fb.get("message", "")),
        "queue_position": payload.get("queue_position", fb.get("queue_position", 0)),
        "estimated_wait_seconds": payload.get("estimated_wait_seconds", fb.get("estimated_wait_seconds", 0.0)),
        "error_code": payload.get("error_code"),
        "error_category": payload.get("error_category"),
        "actionable_suggestions": payload.get("actionable_suggestions"),
    }


def read_latest_metric_point(record: TrainingRecord) -> dict[str, Any] | None:
    """Read the latest metric sample for a training record from metrics.jsonl."""
    metrics_file = Path(record.output_path) / "metrics.jsonl"
    if not metrics_file.exists():
        return None

    try:
        with open(metrics_file, 'rb') as f:
            f.seek(0, 2)  # seek to end
            size = f.tell()
            if size == 0:
                return None
            # 从末尾往前读最多 4KB
            f.seek(max(0, size - 4096))
            lines = f.read().decode('utf-8').strip().split('\n')
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
    except Exception as exc:
        logger.debug(f"读取训练指标失败（task={record.id}）：{exc}")

    return None


def enrich_record_metrics(record: TrainingRecord) -> TrainingRecord:
    """Backfill final metrics for old history records when fields are missing."""
    if (
        record.final_loss is not None
        and record.final_lr is not None
        and record.elapsed_time is not None
        and record.total_steps is not None
    ):
        return record

    latest = read_latest_metric_point(record)
    if latest:
        if record.final_loss is None:
            record.final_loss = float(latest.get("loss", 0.0))
        if record.final_lr is None:
            record.final_lr = float(latest.get("lr", 0.0))
        if record.elapsed_time is None:
            record.elapsed_time = float(latest.get("elapsed_time", 0.0))
        if record.total_steps is None:
            record.total_steps = int(latest.get("step", 0))

    if record.elapsed_time is None and record.end_time:
        try:
            start_ts = datetime.fromisoformat(record.start_time).timestamp()
            end_ts = datetime.fromisoformat(record.end_time).timestamp()
            if end_ts >= start_ts:
                record.elapsed_time = float(end_ts - start_ts)
        except Exception:
            pass

    return record


def sync_training_record_metadata(record: TrainingRecord) -> TrainingRecord:
    """Fill stable evaluation metadata from record/config so history stays self-describing."""
    config = record.config or {}
    record.base_model_id = (
        record.base_model_id
        or config.get("model_id")
        or config.get("modelId")
        or record.model_name
    )
    record.dataset_id = (
        record.dataset_id
        or config.get("dataset_id")
        or config.get("datasetId")
        or config.get("test_dataset_id")
        or config.get("testDatasetId")
        or config.get("validation_dataset_id")
        or config.get("validationDatasetId")
        or record.dataset_name
    )
    record.task_goal = (
        record.task_goal
        or config.get("task_goal")
        or config.get("taskGoal")
        or "qa_assistant"
    )
    record.adapter_path = record.adapter_path or record.checkpoint_path
    record.release_id = record.release_id or f"release_{record.id}"
    if not record.config_hash:
        config_payload = json.dumps(config, ensure_ascii=False, sort_keys=True)
        record.config_hash = hashlib.sha256(config_payload.encode("utf-8")).hexdigest()
    if not record.dataset_fingerprint:
        try:
            from core.config import get_settings

            dataset_dir = get_settings().datasets_dir_resolved / str(record.dataset_id or "")
            record.dataset_fingerprint = hash_path(dataset_dir)
        except Exception:
            record.dataset_fingerprint = None
    if not record.dataset_fingerprint:
        dataset_payload = json.dumps(
            {
                "dataset_id": record.dataset_id,
                "dataset_name": record.dataset_name,
                "config_dataset_id": config.get("dataset_id") or config.get("datasetId"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        record.dataset_fingerprint = hashlib.sha256(dataset_payload.encode("utf-8")).hexdigest()
    if record.evaluation_snapshot_path and not record.evaluation_snapshot_hash:
        record.evaluation_snapshot_hash = hash_path(record.evaluation_snapshot_path)
    artifact_path = record.adapter_path or record.checkpoint_path
    if artifact_path and not record.artifact_digest:
        record.artifact_digest = hash_path(artifact_path)
    return record


def write_training_artifact_manifest(record: TrainingRecord) -> dict[str, Any]:
    """Write a stable release manifest next to the training output."""
    sync_training_record_metadata(record)
    output_dir = Path(record.output_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "artifact_manifest.json"

    artifact_path = record.adapter_path or record.checkpoint_path
    artifact_kind = "adapter" if record.adapter_path else "full_model" if record.method == "full" else "checkpoint"
    artifact_exists = bool(artifact_path and Path(artifact_path).exists())
    validation_status = "passed" if record.status == "completed" and artifact_exists else "unverified"
    if record.status in {"failed", "stopped"}:
        validation_status = record.status

    manifest: dict[str, Any] = {
        "schema_version": 2,
        "release_id": record.release_id,
        "training_task_id": record.id,
        "promotion_state": record.promotion_state,
        "status": record.status,
        "created_at": record.end_time or record.start_time,
        "base_model_id": record.base_model_id,
        "dataset_id": record.dataset_id,
        "task_goal": record.task_goal,
        "method": record.method,
        "config_hash": record.config_hash,
        "dataset_fingerprint": record.dataset_fingerprint,
        "evaluation_snapshot": {
            "path": record.evaluation_snapshot_path,
            "sha256": record.evaluation_snapshot_hash,
            "isolated_from_training": bool(record.evaluation_snapshot_path),
        },
        "artifacts": {
            "output_path": record.output_path,
            "adapter_path": record.adapter_path,
            "checkpoint_path": record.checkpoint_path,
            "final_artifact_path": artifact_path,
            "final_artifact_kind": artifact_kind,
            "final_artifact_exists": artifact_exists,
            "final_artifact_sha256": record.artifact_digest,
        },
        "runtime": runtime_provenance(),
        "quality_gate": {
            "validation_status": validation_status,
            "evaluation_run_id": record.evaluation_run_id,
            "deployment_package_id": record.deployment_package_id,
        },
        "rollback": {
            "checkpoint_path": record.checkpoint_path,
            "can_rollback": bool(record.checkpoint_path and Path(record.checkpoint_path).exists()),
        },
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    record.artifact_manifest_path = str(manifest_path)
    return manifest


def build_failure_analytics_payload(records: list[TrainingRecord]) -> dict[str, Any]:
    now = datetime.now()

    def within_days(record: TrainingRecord, days: int) -> bool:
        start_time = _safe_parse_time(record.start_time)
        return (now - start_time).days <= days

    failed = [record for record in records if record.status == "failed"]
    stopped = [record for record in records if record.status == "stopped"]
    completed = [record for record in records if record.status == "completed"]
    runs7d = [record for record in records if within_days(record, 7)]
    runs14d = [record for record in records if within_days(record, 14)]
    failed7d = [record for record in runs7d if record.status == "failed"]
    failed14d = [record for record in runs14d if record.status == "failed"]

    def top_names(values: list[str], top_n: int = 3) -> list[str]:
        return [name for name, _ in Counter(values).most_common(top_n)]

    def is_vram_pressure(record: TrainingRecord) -> bool:
        config = record.config or {}
        batch_size = int(config.get("batch_size", config.get("batchSize", 1)))
        max_seq_length = int(config.get("max_seq_length", config.get("maxSeqLength", 512)))
        quantization = int(config.get("quantization", 4))
        return batch_size >= 4 or max_seq_length > 2048 or quantization == 0

    def is_long_context(record: TrainingRecord) -> bool:
        config = record.config or {}
        return int(config.get("max_seq_length", config.get("maxSeqLength", 512))) > 1024

    def is_unquantized(record: TrainingRecord) -> bool:
        config = record.config or {}
        return int(config.get("quantization", 4)) == 0

    recent_failures = sorted(failed, key=lambda item: item.start_time, reverse=True)[:5]

    return {
        "totalRuns": len(records),
        "failedRuns": len(failed),
        "stoppedRuns": len(stopped),
        "completedRuns": len(completed),
        "failureRate": round((len(failed) / len(records) * 100), 1) if records else 0.0,
        "failureRate7d": round((len(failed7d) / len(runs7d) * 100), 1) if runs7d else 0.0,
        "failureRate14d": round((len(failed14d) / len(runs14d) * 100), 1) if runs14d else 0.0,
        "failedRuns7d": len(failed7d),
        "failedRuns14d": len(failed14d),
        "totalRuns7d": len(runs7d),
        "totalRuns14d": len(runs14d),
        "suspectedVramPressureCount": sum(1 for record in failed if is_vram_pressure(record)),
        "longContextFailureCount": sum(1 for record in failed if is_long_context(record)),
        "unquantizedFailureCount": sum(1 for record in failed if is_unquantized(record)),
        "topFailedModels": top_names([record.model_name for record in failed]),
        "topFailedDatasets": top_names([record.dataset_name for record in failed]),
        "topFailedMethods": top_names([record.method for record in failed]),
        "recentFailures": [
            {
                "id": record.id,
                "modelName": record.model_name,
                "datasetName": record.dataset_name,
                "method": record.method,
                "startTime": record.start_time,
            }
            for record in recent_failures
        ],
    }


def _safe_parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.min

"""
训练报告与辅助工具 - 失败分析、进度转换、记录增强
"""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from core.logging import get_logger
from core.training_state import TrainingRecord
from training_engine.schemas import TrainingConfigInput

logger = get_logger(__name__)


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

    if any(token in normalized for token in ("dataset", "json", "unsupported dataset", "样本")):
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

    latest: dict[str, Any] | None = None
    try:
        with open(metrics_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    latest = json.loads(line)
                except json.JSONDecodeError:
                    continue
    except Exception as exc:
        logger.debug(f"读取训练指标失败（task={record.id}）：{exc}")
        return None

    return latest


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
        or config.get("test_dataset_id")
        or config.get("testDatasetId")
        or config.get("validation_dataset_id")
        or config.get("validationDatasetId")
        or config.get("dataset_id")
        or config.get("datasetId")
        or record.dataset_name
    )
    record.task_goal = (
        record.task_goal
        or config.get("task_goal")
        or config.get("taskGoal")
        or "qa_assistant"
    )
    record.adapter_path = record.adapter_path or record.checkpoint_path
    return record


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

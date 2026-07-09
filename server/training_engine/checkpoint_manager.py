"""
检查点管理模块 - 扫描、保存、验证、恢复、紧急回退
"""
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import Settings
from core.logging import get_logger
from core.training_state import TrainingState

logger = get_logger(__name__)


def _get_training_record_by_id(state: TrainingState, task_id: str):
    """Look up a training record from history by task id."""
    for record in state.get_history():
        if record.id == task_id:
            return record
    return None


def _resolve_training_output_dir(state: TrainingState, settings: Settings, task_id: str) -> Path:
    """Resolve a task's output directory, preferring the persisted training record."""
    record = _get_training_record_by_id(state, task_id)
    if record and record.output_path:
        return Path(record.output_path)
    return settings.outputs_dir_resolved / f"train_{task_id[:8]}"


def get_checkpoint_dir(state: TrainingState, settings: Settings, task_id: str) -> Path:
    """获取任务检查点根目录"""
    output_dir = _resolve_training_output_dir(state, settings, task_id)
    return output_dir / "checkpoints"


def load_checkpoints_for_task(state: TrainingState, settings: Settings, task_id: str) -> list[dict[str, Any]]:
    """获取任务的检查点列表，按 step 排序"""
    checkpoint_dir = get_checkpoint_dir(state, settings, task_id)

    if not checkpoint_dir.exists():
        return []

    checkpoints: list[dict[str, Any]] = []
    for cp in checkpoint_dir.iterdir():
        if not (cp.is_dir() and cp.name.startswith("checkpoint-")):
            continue
        try:
            step = int(cp.name.split("-")[1])
        except Exception:
            step = 0
        meta_path = cp / "checkpoint_metadata.json"
        metadata = {}
        if meta_path.exists():
            try:
                with open(meta_path, encoding="utf-8") as f:
                    metadata = json.load(f)
            except Exception:
                pass
        checkpoints.append({
            "name": cp.name,
            "path": str(cp),
            "step": step,
            "created": datetime.fromtimestamp(cp.stat().st_mtime).isoformat(),
            "metadata": metadata,
            "valid": _quick_validate_checkpoint(cp),
        })

    return sorted(checkpoints, key=lambda x: x["step"])


def get_latest_checkpoint(state: TrainingState, settings: Settings, task_id: str) -> dict[str, Any] | None:
    """获取最新有效检查点（优先选择常规检查点，排除异常恢复检查点）"""
    checkpoints = load_checkpoints_for_task(state, settings, task_id)
    valid_checkpoints = [cp for cp in checkpoints if cp.get("valid")]
    if not valid_checkpoints:
        return None
    regular = [cp for cp in valid_checkpoints if "recovery" not in cp.get("name", "")]
    if regular:
        return regular[-1]
    return valid_checkpoints[-1]


def cleanup_invalid_checkpoints(
    state: TrainingState, settings: Settings, task_id: str
) -> dict[str, Any]:
    """清理任务的无效检查点，返回清理结果"""
    checkpoint_dir = get_checkpoint_dir(state, settings, task_id)
    if not checkpoint_dir.exists():
        return {"removed": 0, "freed_bytes": 0, "details": []}

    removed = 0
    freed_bytes = 0
    details: list[dict[str, Any]] = []

    for cp in checkpoint_dir.iterdir():
        if not (cp.is_dir() and cp.name.startswith("checkpoint-")):
            continue
        valid = _quick_validate_checkpoint(cp)
        if not valid:
            size = sum(
                f.stat().st_size for f in cp.rglob("*") if f.is_file()
            )
            try:
                shutil.rmtree(cp)
                removed += 1
                freed_bytes += size
                details.append({"name": cp.name, "size": size, "status": "removed"})
                logger.info(f"已清理无效检查点：{cp.name} ({size} bytes)")
            except Exception as e:
                details.append({"name": cp.name, "size": size, "status": "failed", "error": str(e)})
                logger.warning(f"清理检查点失败：{cp.name} - {e}")

    return {"removed": removed, "freed_bytes": freed_bytes, "details": details}


def compare_checkpoints(
    checkpoints: list[dict[str, Any]]
) -> dict[str, Any]:
    """对比多个检查点的元数据，返回结构化对比结果"""
    if len(checkpoints) < 2:
        return {"error": "至少需要两个检查点进行对比"}

    fields = ["step", "epoch", "loss", "lr"]
    comparison: dict[str, Any] = {
        "checkpoints": [],
        "differences": {},
        "trend": {},
    }

    values: dict[str, list[float | None]] = {f: [] for f in fields}

    for cp in checkpoints:
        meta = cp.get("metadata", {})
        entry = {
            "name": cp.get("name"),
            "step": cp.get("step"),
            "created": cp.get("created"),
            "valid": cp.get("valid"),
            "metadata": {
                "step": meta.get("step"),
                "epoch": meta.get("epoch"),
                "loss": meta.get("loss"),
                "lr": meta.get("lr"),
                "saved_at": meta.get("saved_at"),
                "tags": meta.get("tags", []),
            },
        }
        comparison["checkpoints"].append(entry)
        for f in fields:
            val = meta.get(f)
            values[f].append(val if val is not None else None)

    for f in fields:
        vals = [v for v in values[f] if v is not None]
        if len(vals) >= 2:
            diff = vals[-1] - vals[0]  # type: ignore[operator]
            comparison["differences"][f] = {
                "from": vals[0],
                "to": vals[-1],
                "delta": diff,
                "delta_percent": (
                    round((diff / vals[0]) * 100, 2) if vals[0] != 0 else None
                ),
            }
            comparison["trend"][f] = "improved" if diff < 0 else "worsened" if diff > 0 else "stable"

    return comparison


def _quick_validate_checkpoint(checkpoint_path: Path) -> bool:
    """快速验证检查点目录是否包含必要文件（模型权重或配置）"""
    required_files = ["pytorch_model.bin", "model.safetensors"]
    has_model_file = any((checkpoint_path / f).exists() for f in required_files)
    has_config = (checkpoint_path / "config.json").exists() or (checkpoint_path / "adapter_config.json").exists()
    return has_model_file or has_config


def validate_checkpoint(checkpoint_path: str | Path) -> dict[str, Any]:
    """详细验证检查点完整性，返回诊断信息"""
    cp = Path(checkpoint_path)
    result = {
        "path": str(cp),
        "exists": cp.exists(),
        "is_dir": cp.is_dir() if cp.exists() else False,
        "has_pytorch_model": (cp / "pytorch_model.bin").exists(),
        "has_safetensors": (cp / "model.safetensors").exists(),
        "has_config_json": (cp / "config.json").exists(),
        "has_adapter_config": (cp / "adapter_config.json").exists(),
        "has_optimizer_state": (cp / "optimizer.pt").exists(),
        "has_scheduler_state": (cp / "scheduler.pt").exists(),
        "has_trainer_state": (cp / "trainer_state.json").exists(),
        "has_metadata": (cp / "checkpoint_metadata.json").exists(),
        "valid": False,
        "missing": [],
    }

    if not result["exists"]:
        result["missing"].append("directory")
        return result

    if not (result["has_pytorch_model"] or result["has_safetensors"]):
        result["missing"].append("model weights")
    if not (result["has_config_json"] or result["has_adapter_config"]):
        result["missing"].append("config")

    result["valid"] = len(result["missing"]) == 0
    return result


def save_checkpoint_metadata(
    checkpoint_path: Path,
    task_id: str,
    step: int,
    epoch: float,
    loss: float | None = None,
    lr: float | None = None,
    config: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> None:
    """保存检查点元数据，便于后续恢复和诊断。

    Writes via temp file + ``os.replace`` so a mid-write crash cannot leave a
    truncated ``checkpoint_metadata.json`` as the only metadata artifact.
    """
    import os

    metadata = {
        "task_id": task_id,
        "step": step,
        "epoch": epoch,
        "loss": loss,
        "lr": lr,
        "saved_at": datetime.now().isoformat(),
        "config": config or {},
        "tags": tags or [],
    }
    checkpoint_path = Path(checkpoint_path)
    checkpoint_path.mkdir(parents=True, exist_ok=True)
    meta_path = checkpoint_path / "checkpoint_metadata.json"
    tmp_path = checkpoint_path / "checkpoint_metadata.json.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, meta_path)
        logger.info(f"检查点元数据已保存：{meta_path}")
    except Exception as e:
        logger.warning(f"保存检查点元数据失败：{e}")
        try:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def _write_minimal_trainer_state(recovery_path: Path, trainer) -> None:
    """当 trainer.save_state() 失败时，手动写入最小可用的 trainer_state.json"""
    import json as _json

    state_dict = {}
    if hasattr(trainer, "state"):
        for attr in ("global_step", "epoch", "total_flos", "log_history", "best_metric", "best_model_checkpoint"):
            val = getattr(trainer.state, attr, None)
            if val is not None:
                try:
                    _json.dumps(val)
                    state_dict[attr] = val
                except (TypeError, ValueError):
                    pass
    state_dict.setdefault("global_step", 0)
    state_dict["is_recovery"] = True

    trainer_state_path = recovery_path / "trainer_state.json"
    with open(trainer_state_path, "w", encoding="utf-8") as f:
        _json.dump(state_dict, f, ensure_ascii=False, indent=2)
    logger.info(f"已写入最小 trainer_state.json: {trainer_state_path}")


def create_recovery_checkpoint(
    trainer,
    output_dir: Path,
    reason: str = "emergency",
    metadata: dict[str, Any] | None = None,
) -> Path | None:
    """创建紧急恢复检查点（用于异常/停止时保存当前进度）"""
    if trainer is None:
        logger.warning("无法创建恢复检查点：trainer 为 None")
        return None

    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    current_step = getattr(trainer.state, "global_step", 0)
    recovery_name = f"checkpoint-{current_step}-recovery-{reason}"
    recovery_path = checkpoint_dir / recovery_name

    try:
        if hasattr(trainer, "save_model"):
            trainer.save_model(str(recovery_path))
        if hasattr(trainer, "save_state"):
            try:
                trainer.save_state(str(recovery_path))
            except Exception as state_err:
                logger.warning(f"trainer.save_state() 失败，尝试手动写入最小 trainer_state: {state_err}")
                _write_minimal_trainer_state(recovery_path, trainer)

        save_checkpoint_metadata(
            recovery_path,
            task_id=metadata.get("task_id", "unknown") if metadata else "unknown",
            step=current_step,
            epoch=getattr(trainer.state, "epoch", 0.0),
            loss=metadata.get("loss") if metadata else None,
            lr=metadata.get("lr") if metadata else None,
            tags=["recovery", reason],
        )

        logger.info(f"紧急恢复检查点已保存：{recovery_path} (reason={reason})")
        return recovery_path

    except Exception as e:
        logger.error(f"创建恢复检查点失败：{e}")
        return None


def create_rollback_checkpoint(
    model,
    tokenizer,
    output_dir: Path,
    task_id: str,
    step: int = 0,
    reason: str = "rollback",
) -> Path | None:
    """创建回退检查点（用于降级重试前保存当前状态）"""
    if model is None or tokenizer is None:
        logger.warning("无法创建回退检查点：model 或 tokenizer 为 None")
        return None

    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    rollback_name = f"checkpoint-{step}-rollback-{reason}"
    rollback_path = checkpoint_dir / rollback_name

    try:
        model.save_pretrained(str(rollback_path))
        tokenizer.save_pretrained(str(rollback_path))

        save_checkpoint_metadata(
            rollback_path,
            task_id=task_id,
            step=step,
            epoch=0.0,
            tags=["rollback", reason],
        )

        logger.info(f"回退检查点已保存：{rollback_path}")
        return rollback_path

    except Exception as e:
        logger.error(f"创建回退检查点失败：{e}")
        return None


def cleanup_old_checkpoints(
    state: TrainingState,
    settings: Settings,
    task_id: str,
    keep_count: int = 3,
    keep_recovery: bool = True,
) -> int:
    """清理旧检查点，保留最近 N 个有效检查点"""
    checkpoints = load_checkpoints_for_task(state, settings, task_id)
    if len(checkpoints) <= keep_count:
        return 0

    removed = 0
    for cp in checkpoints[:-keep_count]:
        if keep_recovery and "recovery" in cp["name"]:
            continue
        try:
            shutil.rmtree(cp["path"])
            logger.info(f"清理旧检查点：{cp['name']}")
            removed += 1
        except Exception as e:
            logger.warning(f"清理检查点失败 {cp['path']}：{e}")

    return removed

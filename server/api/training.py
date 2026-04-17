"""
训练管理 API - 线程安全版本 + 断点续训支持
"""
import asyncio
import gc
import inspect
import json
import logging
import os
import threading
import traceback as tb
import uuid
from collections import Counter
from collections.abc import Mapping
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Header, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.config import Settings, get_settings
from core.logging import get_logger
from core.training_events_v2 import (
    get_training_event_hub_v2,
    normalize_phase_v2,
)
from core.training_queue import TaskPriority
from core.training_state import TrainingRecord, TrainingState
from core.training_context import get_training_context
from core.utils import (
    cleanup_gpu_memory,
    get_vram_usage,
    pre_training_resource_check,
    safe_cleanup_model,
)

logger = get_logger(__name__)

router = APIRouter()


class TrainingWebSocketManager:
    """训练 WebSocket 管理器 - 实时推送训练进度（重构版）

    修复:
    - P0-3: WebSocket 连接泄漏，添加超时机制和心跳检测
    """

    CONNECTION_TIMEOUT = 300
    HEARTBEAT_INTERVAL = 30
    SEND_TIMEOUT = 10

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self._connection_times: dict[str, dict[WebSocket, float]] = {}
        self._lock = threading.Lock()
        self._async_lock = asyncio.Lock()

    async def connect(self, task_id: str, websocket: WebSocket):
        """连接到指定任务的 WebSocket"""
        await websocket.accept()
        async with self._async_lock:
            if task_id not in self._connections:
                self._connections[task_id] = []
                self._connection_times[task_id] = {}
            self._connections[task_id].append(websocket)
            self._connection_times[task_id][websocket] = asyncio.get_event_loop().time()
            logger.info(f"WebSocket 连接：task_id={task_id}, 连接数={len(self._connections[task_id])}")

    async def disconnect(self, task_id: str, websocket: WebSocket):
        """断开指定任务的 WebSocket 连接"""
        async with self._async_lock:
            if task_id in self._connections:
                with suppress(ValueError):
                    self._connections[task_id].remove(websocket)

                if task_id in self._connection_times and websocket in self._connection_times[task_id]:
                    del self._connection_times[task_id][websocket]

                if not self._connections[task_id]:
                    del self._connections[task_id]
                    if task_id in self._connection_times:
                        del self._connection_times[task_id]
                    logger.info(f"WebSocket 断开：task_id={task_id}")

    async def broadcast(self, task_id: str, data: dict[str, Any]):
        """向指定任务的所有连接广播数据"""
        async with self._async_lock:
            if task_id not in self._connections:
                return

            message = json.dumps(data)
            disconnected = []
            current_time = asyncio.get_event_loop().time()

            for websocket in list(self._connections[task_id]):
                try:
                    if task_id in self._connection_times:
                        conn_time = self._connection_times[task_id].get(websocket, 0)
                        if current_time - conn_time > self.CONNECTION_TIMEOUT:
                            logger.warning(f"WebSocket 连接超时：task_id={task_id}")
                            disconnected.append(websocket)
                            continue

                    try:
                        await asyncio.wait_for(
                            websocket.send_text(message),
                            timeout=self.SEND_TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"WebSocket 发送超时：task_id={task_id}")
                        disconnected.append(websocket)

                except Exception as e:
                    logger.warning(f"WebSocket 发送失败：{e}")
                    disconnected.append(websocket)

            for ws in disconnected:
                try:
                    if task_id in self._connections and ws in self._connections[task_id]:
                        self._connections[task_id].remove(ws)
                    if task_id in self._connection_times and ws in self._connection_times[task_id]:
                        del self._connection_times[task_id][ws]
                except Exception as e:
                    logger.debug(f"清理断开的 WebSocket 连接失败：{e}")

            if task_id in self._connections and not self._connections[task_id]:
                del self._connections[task_id]
                if task_id in self._connection_times:
                    del self._connection_times[task_id]

    async def broadcast_progress(self, task_id: str, progress: dict[str, Any]):
        """广播训练进度"""
        await self.broadcast(task_id, {
            "type": "progress",
            "data": progress
        })

    async def broadcast_event(self, task_id: str, event_type: str, data: dict[str, Any]):
        """广播训练事件"""
        await self.broadcast(task_id, {
            "type": "event",
            "event": event_type,
            "data": data
        })

    async def cleanup_stale_connections(self):
        """清理超时的连接"""
        async with self._async_lock:
            current_time = asyncio.get_event_loop().time()
            tasks_to_cleanup = []

            for task_id, conn_times in list(self._connection_times.items()):
                stale_websockets = [
                    ws for ws, conn_time in conn_times.items()
                    if current_time - conn_time > self.CONNECTION_TIMEOUT
                ]

                for ws in stale_websockets:
                    try:
                        if task_id in self._connections and ws in self._connections[task_id]:
                            self._connections[task_id].remove(ws)
                        del conn_times[ws]
                    except Exception as e:
                        logger.debug(f"清理超时 WebSocket 连接失败：{e}")

                if task_id in self._connections and not self._connections[task_id]:
                    tasks_to_cleanup.append(task_id)

            for task_id in tasks_to_cleanup:
                self._connections.pop(task_id, None)
                self._connection_times.pop(task_id, None)


_ws_manager: TrainingWebSocketManager | None = None


def get_ws_manager() -> TrainingWebSocketManager:
    """获取 WebSocket 管理器实例"""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = TrainingWebSocketManager()
    return _ws_manager


class RecoverableError(Exception):
    """可恢复错误 - 训练失败后可自动重试"""
    pass


class UnrecoverableError(Exception):
    """不可恢复错误 - 需要用户干预"""
    pass


TrainingProgressStatus = Literal[
    "idle",
    "loading",
    "training",
    "running",
    "stopping",
    "stopped",
    "completed",
    "failed",
]

TRAINING_PROGRESS_STATUS_VALUES: tuple[TrainingProgressStatus, ...] = (
    "idle",
    "loading",
    "training",
    "running",
    "stopping",
    "stopped",
    "completed",
    "failed",
)


def _queue_training_progress(
    state: TrainingState,
    *,
    status: TrainingProgressStatus,
    message: str,
    **kwargs: Any,
) -> None:
    """统一训练进度状态写入，确保 status 枚举可控。"""
    if status not in TRAINING_PROGRESS_STATUS_VALUES:
        raise ValueError(f"Unsupported training progress status: {status}")
    state.queue_progress_update(status=status, message=message, **kwargs)

    get_record = getattr(state, "get_current_record", None)
    if not callable(get_record):
        return

    record = get_record()
    if record is None:
        return

    phase = normalize_phase_v2(status)
    if not phase:
        return

    payload = {
        "status": status,
        "message": message,
        **kwargs,
    }
    get_training_event_hub_v2().publish(
        task_id=record.id,
        phase=phase,
        kind="progress_updated",
        payload=payload,
    )


def _build_failure_feedback(error_message: str) -> dict[str, Any]:
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


def _legacy_progress_from_v2_event(event: Any, fallback: Any) -> dict[str, Any]:
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
        "queue_position": payload.get("queue_position"),
        "estimated_wait_seconds": payload.get("estimated_wait_seconds"),
        "error_code": payload.get("error_code"),
        "error_category": payload.get("error_category"),
        "actionable_suggestions": payload.get("actionable_suggestions"),
    }


class TrainingConfigInput(BaseModel):
    """训练配置输入 - 支持高精度微调"""
    model_id: str = Field(..., description="模型 ID")
    dataset_id: str = Field(..., description="数据集 ID")
    method: str = Field(default="qlora", description="微调方法：qlora/lora/full/dora")
    rank: int = Field(default=8, ge=1, le=256, description="LoRA rank")
    alpha: int = Field(default=16, ge=1, description="LoRA alpha")
    learning_rate: float = Field(default=5e-5, gt=0, description="学习率")
    epochs: int = Field(default=3, ge=1, le=100, description="训练轮数")
    batch_size: int = Field(default=1, ge=1, le=32, description="批次大小")
    gradient_accumulation: int = Field(default=16, ge=1, le=128, description="梯度累积步数")
    max_seq_length: int = Field(default=512, ge=64, le=4096, description="最大序列长度")
    warmup_steps: int = Field(default=100, ge=0, description="预热步数")
    save_steps: int = Field(default=500, ge=100, description="保存间隔")
    logging_steps: int = Field(default=10, ge=1, description="日志间隔")
    resume_from_checkpoint: str | None = Field(default=None, description="从检查点恢复")
    quantization: int = Field(default=4, description="量化位数：4/8/none")

    use_dora: bool = Field(default=False, description="是否使用 DoRA 微调")
    lr_scheduler: str = Field(default="cosine", description="学习率调度：cosine/linear/constant")
    warmup_ratio: float = Field(default=0.1, ge=0, le=1, description="预热比例")
    weight_decay: float = Field(default=0.01, ge=0, description="权重衰减")
    label_smoothing: float = Field(default=0.0, ge=0, le=0.5, description="标签平滑")
    gradient_checkpointing: bool = Field(default=True, description="梯度检查点")
    bf16: bool = Field(default=True, description="使用 BF16 混合精度")
    eval_steps: int = Field(default=100, ge=10, description="评估间隔")
    load_best_model: bool = Field(default=True, description="加载最佳模型")
    target_modules: str = Field(default="all", description="目标模块：all/mlp/attn")
    lora_dropout: float = Field(default=0.05, ge=0, le=0.5, description="LoRA Dropout")
    max_grad_norm: float = Field(default=1.0, ge=0, description="梯度裁剪范数")

    early_stopping_patience: int = Field(default=0, ge=0, le=20, description="早停耐心值（0=禁用）")
    early_stopping_threshold: float = Field(default=0.0, ge=0, description="早停阈值")
    metric_for_best_model: str = Field(default="eval_loss", description="最佳模型指标")
    greater_is_better: bool = Field(default=False, description="指标是否越大越好")

    additional_datasets: list[dict[str, Any]] | None = Field(
        default=None,
        description="额外数据集列表，格式：[{'dataset_id': 'xxx', 'weight': 0.3}]"
    )

    memory_preset: str = Field(default="auto", description="显存预设：auto/6gb/8gb/12gb")
    use_flash_attn: bool = Field(default=False, description="使用 Flash Attention")
    deepspeed_stage: int = Field(default=0, description="DeepSpeed ZeRO 阶段：0/1/2/3")
    offload_optimizer: bool = Field(default=False, description="CPU Offload 优化器")

    use_torch_compile: bool = Field(default=False, description="使用 PyTorch 2.0 compile 编译模型")
    torch_compile_mode: str = Field(default="default", description="compile 模式：default/reduce-overhead/max-autotune")
    dataloader_num_workers: int = Field(default=2, ge=0, le=8, description="DataLoader 工作进程数")
    dataloader_pin_memory: bool = Field(default=True, description="DataLoader 固定内存")
    dataloader_persistent_workers: bool = Field(default=True, description="DataLoader 持久化工作进程")
    use_tf32: bool = Field(default=True, description="使用 TF32 加速（Ampere GPU）")

    precision_preset: str = Field(default="balanced", description="精度预设：max/balanced/fast")

    use_lora_plus: bool = Field(default=False, description="使用 LoRA+ 技术（不同学习率）")
    lora_plus_lr_ratio: float = Field(default=16.0, ge=1.0, description="LoRA+ B/A 学习率比例")

    use_galore: bool = Field(default=False, description="使用 GaLore 梯度投影技术")
    galore_rank: int = Field(default=128, ge=16, le=1024, description="GaLore 投影秩")
    galore_update_proj_gap: int = Field(default=50, ge=10, description="GaLore 投影更新间隔")

    output_path: str | None = Field(default=None, description="输出路径（运行时设置）")


class TrainingProgressResponse(BaseModel):
    """训练进度响应"""
    epoch: int
    step: int
    total_steps: int
    loss: float
    lr: float
    vram_used: float
    elapsed_time: float
    eta: float
    status: TrainingProgressStatus
    message: str


class TrainingRecordResponse(BaseModel):
    """训练记录响应"""
    id: str
    model_name: str
    dataset_name: str
    method: str
    status: str
    start_time: str
    end_time: str | None
    config: dict
    output_path: str
    checkpoint_path: str | None


class ResourceCheckResponse(BaseModel):
    """资源检查响应"""
    passed: bool
    available_vram: float
    required_vram: float
    suggestions: list[str]
    warnings: list[str]
    recommended_config: dict[str, Any]
    device_name: str | None = None


SUPPORTED_DATASET_FORMATS = (
    "messages",
    "text",
    "content",
    "instruction+output",
    "instruction+input+output",
)

RELEASE_EXPERIMENTAL_FEATURE_MESSAGES = {
    "use_dora": "DoRA 目前未纳入发布版稳定能力，请使用 LoRA / QLoRA 训练路径",
    "use_lora_plus": "LoRA+ 目前仅保留实验接线，发布版暂不开放",
    "use_galore": "GaLore 当前依赖和兼容性尚未收敛，发布版暂不开放",
}


def detect_dataset_sample_format(example: Any) -> str:
    """Detect the supported dataset sample format for a single record."""
    if not isinstance(example, Mapping):
        raise ValueError("Dataset sample must be a JSON object")

    if "messages" in example:
        return "messages"

    if "instruction" in example:
        if "output" not in example:
            raise ValueError("Alpaca format requires an 'output' field when 'instruction' is present")
        if "input" in example:
            return "instruction+input+output"
        return "instruction+output"

    if "content" in example:
        return "content"

    if "text" in example:
        return "text"

    supported = ", ".join(SUPPORTED_DATASET_FORMATS)
    raise ValueError(f"Unsupported dataset sample format; expected one of: {supported}")


def _detect_and_format(example: dict[str, Any], tokenizer) -> dict[str, Any]:
    """Detect format, normalize text, and carry format metadata for label masking.

    Returns a dict with 'text' (normalized string) and 'sample_format' (one of:
    'messages', 'instruction', 'content', 'text').
    """
    sample_format = detect_dataset_sample_format(example)

    if sample_format == "messages":
        messages = example.get("messages", [])

        if hasattr(tokenizer, "apply_chat_template") and messages:
            try:
                text = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
                return {"text": text, "sample_format": "messages"}
            except Exception as e:
                logger.warning(f"apply_chat_template failed, using fallback formatting: {e}")

        text = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                text += f"User: {content}\n"
            elif role == "assistant":
                text += f"Assistant: {content}\n"
            elif role == "system":
                text += f"System: {content}\n"
        return {"text": text, "sample_format": "messages"}

    if sample_format in {"instruction+output", "instruction+input+output"}:
        instruction = example.get("instruction", "")
        input_text = example.get("input", "")
        output = example.get("output", "")
        if input_text:
            text = f"Instruction: {instruction}\nInput: {input_text}\nResponse: {output}"
        else:
            text = f"Instruction: {instruction}\nResponse: {output}"
        return {"text": text, "sample_format": "instruction"}

    if sample_format == "content":
        return {"text": example.get("content", ""), "sample_format": "content"}

    return {"text": example.get("text", ""), "sample_format": "text"}


def load_dataset(dataset_path: str, tokenizer, max_length: int = 512):
    """加载数据集 - 支持多种格式，智能标签掩码"""
    import json

    from datasets import Dataset
    try:
        from datasets.utils.logging import disable_progress_bar

        disable_progress_bar()
    except Exception:
        os.environ["HF_DATASETS_DISABLE_PROGRESS_BAR"] = "1"
        os.environ["TQDM_DISABLE"] = "1"

    logger.info(f"加载数据集：{dataset_path}")

    if dataset_path.endswith(".jsonl"):
        data = []
        with open(dataset_path, encoding="utf-8") as f:
            for line in f:
                data.append(json.loads(line))
    else:
        with open(dataset_path, encoding="utf-8") as f:
            data = json.load(f)

    dataset = Dataset.from_list(data)
    dataset = dataset.map(lambda ex: _detect_and_format(ex, tokenizer))

    def tokenize_with_labels(examples):
        """Tokenize text and set labels based on sample format."""
        input_ids = tokenizer(
            examples["text"],
            truncation=True,
            max_length=max_length,
            padding="max_length",
        )

        batch_size = len(examples["text"])
        labels = []

        for i in range(batch_size):
            label = list(input_ids["input_ids"][i])
            fmt = examples.get("sample_format", ["text"] * batch_size)[i]
            text = examples["text"][i]

            if fmt == "instruction":
                # Mask everything before "Response:" / "### Response" / "Answer:"
                _mask_before_response(label, text, tokenizer)
            elif fmt == "messages":
                # Mask before the assistant's first response turn
                _mask_before_assistant(label, text, tokenizer)
            # For "content" and "text" formats, keep all tokens as labels

            # Mask padding tokens
            pad_id = tokenizer.pad_token_id
            if pad_id is not None:
                for j in range(len(label)):
                    if label[j] == pad_id:
                        label[j] = -100

            labels.append(label)

        input_ids["labels"] = labels
        return input_ids

    original_columns = dataset.column_names
    dataset = dataset.map(tokenize_with_labels, batched=True, remove_columns=original_columns)
    dataset = split_train_test_dataset(dataset)

    logger.info(f"数据集大小：训练={len(dataset['train'])}, 测试={len(dataset.get('test', []))}")
    return dataset


def _mask_before_response(label: list[int], text: str, tokenizer):
    """Mask all tokens before the response section for instruction format."""
    # Common response start markers - try each
    markers = [
        tokenizer.encode("Response:", add_special_tokens=False),
        tokenizer.encode("### Response", add_special_tokens=False),
        tokenizer.encode("Answer:", add_special_tokens=False),
        tokenizer.encode("### Answer", add_special_tokens=False),
        tokenizer.encode("Output:", add_special_tokens=False),
    ]
    # Filter out markers that failed to encode
    markers = [m for m in markers if m]

    mask_until = -1
    for marker_ids in markers:
        if not marker_ids:
            continue
        marker_len = len(marker_ids)
        for start in range(1, len(label) - marker_len + 1):
            if label[start:start + marker_len] == marker_ids:
                # Found marker; mask from position 1 (after BOS) up to end of marker
                mask_until = start + marker_len
                break
        if mask_until > 0:
            break

    if mask_until <= 1:
        return

    for j in range(1, mask_until):
        label[j] = -100


def _mask_before_assistant(label: list[int], text: str, tokenizer):
    """Mask all tokens before the assistant's first response for messages format."""
    # Find the first " Assistant:" or "Assistant:" in the tokenized sequence
    # We try several patterns that represent the start of assistant output
    markers = [
        tokenizer.encode(" Assistant:", add_special_tokens=False),
        tokenizer.encode("Assistant:", add_special_tokens=False),
        tokenizer.encode("[/INST]", add_special_tokens=False),
        tokenizer.encode("[INST]", add_special_tokens=False),
        tokenizer.encode("> ", add_special_tokens=False),
        tokenizer.encode("### Response", add_special_tokens=False),
    ]
    markers = [m for m in markers if m]

    mask_until = -1
    for marker_ids in markers:
        if not marker_ids:
            continue
        marker_len = len(marker_ids)
        for start in range(1, len(label) - marker_len + 1):
            if label[start:start + marker_len] == marker_ids:
                # Mask up to and including the marker, but keep BOS
                mask_until = start + marker_len
                break
        if mask_until > 0:
            break

    if mask_until <= 1:
        return

    for j in range(1, mask_until):
        label[j] = -100


def _validate_release_supported_features(
    config: TrainingConfigInput,
    backend: str = "standard",
) -> None:
    """Reject experimental fine-tuning options from the public release path."""
    for field_name, detail in RELEASE_EXPERIMENTAL_FEATURE_MESSAGES.items():
        if getattr(config, field_name, False):
            raise HTTPException(status_code=400, detail=detail)

    if config.method == "dora":
        raise HTTPException(
            status_code=400,
            detail=RELEASE_EXPERIMENTAL_FEATURE_MESSAGES["use_dora"],
        )

    if backend == "swift" and config.method not in {"lora", "qlora"}:
        raise HTTPException(
            status_code=400,
            detail="SWIFT 发布路径当前仅开放 LoRA / QLoRA",
        )


def _get_training_record_by_id(state: TrainingState, task_id: str) -> TrainingRecord | None:
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


def _safe_parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def _load_checkpoints_for_task(state: TrainingState, settings: Settings, task_id: str) -> list[dict[str, Any]]:
    output_dir = _resolve_training_output_dir(state, settings, task_id)
    checkpoint_dir = output_dir / "checkpoints"

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
        checkpoints.append({
            "name": cp.name,
            "path": str(cp),
            "step": step,
            "created": datetime.fromtimestamp(cp.stat().st_mtime).isoformat(),
        })

    return sorted(checkpoints, key=lambda x: x["step"])


def _build_failure_analytics_payload(records: list[TrainingRecord]) -> dict[str, Any]:
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
        return batch_size >= 2 or max_seq_length > 1024 or quantization == 0

    def is_long_context(record: TrainingRecord) -> bool:
        config = record.config or {}
        return int(config.get("max_seq_length", config.get("maxSeqLength", 512))) > 1024

    def is_unquantized(record: TrainingRecord) -> bool:
        config = record.config or {}
        return int(config.get("quantization", 4)) == 0

    recent_failures = sorted(failed, key=lambda item: _safe_parse_time(item.start_time), reverse=True)[:5]

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


def _estimate_training_total_steps(train_size: int, batch_size: int, epochs: int) -> int:
    """估算训练总步数，避免小数据集出现 0 步。"""
    if train_size <= 0:
        raise ValueError("训练集为空，无法开始训练")
    if batch_size <= 0:
        raise ValueError("batch_size 必须大于 0")
    if epochs <= 0:
        raise ValueError("epochs 必须大于 0")

    steps_per_epoch = max(1, (train_size + batch_size - 1) // batch_size)
    return steps_per_epoch * epochs


def load_model_and_tokenizer(
    model_path: str,
    method: str,
    quantize: int = 4,
    resume_from: str | None = None,
    rank: int = 8,
    alpha: int = 16,
    lora_dropout: float = 0.05,
    target_modules: str = "all",
    use_dora: bool = False,
    use_flash_attn: bool = False,
    gradient_checkpointing: bool = True,
    deepspeed_config: dict[str, Any] | None = None,
    use_lora_plus: bool = False,
    lora_plus_lr_ratio: float = 16.0
):
    """加载模型和分词器

    Args:
        model_path: 模型路径
        method: 微调方法 (lora/qlora/full/dora)
        quantize: 量化位数 (4/8/0)
        resume_from: 从检查点恢复的路径
        rank: LoRA rank
        alpha: LoRA alpha
        lora_dropout: LoRA dropout
        target_modules: 目标模块 (all/attn/mlp/自定义)
        use_dora: 是否使用 DoRA
        use_flash_attn: 是否使用 Flash Attention
        deepspeed_config: DeepSpeed 配置字典
        use_lora_plus: 是否使用 LoRA+ (论文: LoRA+)
        lora_plus_lr_ratio: LoRA+ B/A 学习率比例
    """
    import torch
    from peft import LoraConfig, PeftModel, TaskType, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    logger.info(f"加载模型：{model_path}, 方法：{method}, 量化：{quantize}, rank={rank}, alpha={alpha}, flash_attn={use_flash_attn}")

    model = None
    tokenizer = None

    try:
        quantization_config = None
        if method == "qlora" and quantize in [4, 8]:
            try:
                from bitsandbytes import BitsAndBytesConfig
                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=(quantize == 4),
                    load_in_8bit=(quantize == 8),
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",
                )
            except Exception as e:
                logger.warning(f"bitsandbytes 不可用，将使用标准 LoRA: {e}")
                method = "lora"

        load_kwargs = {
            "pretrained_model_name_or_path": model_path,
            "quantization_config": quantization_config,
            "device_map": "auto",
            "torch_dtype": torch.float16,
            "trust_remote_code": True,
        }

        if use_flash_attn and quantize == 0:
            try:
                load_kwargs["attn_implementation"] = "flash_attention_2"
                model = AutoModelForCausalLM.from_pretrained(**load_kwargs)
                logger.info("已启用 Flash Attention 2")
            except Exception as e:
                logger.warning(f"Flash Attention 2 不可用，回退到标准 attention: {e}")
                load_kwargs["attn_implementation"] = "eager"
                model = AutoModelForCausalLM.from_pretrained(**load_kwargs)
        else:
            if use_flash_attn and quantize > 0:
                logger.warning("量化模式下无法使用 Flash Attention 2，回退到标准 attention")
            model = AutoModelForCausalLM.from_pretrained(**load_kwargs)

        if gradient_checkpointing and hasattr(model, "config"):
            model.config.use_cache = False

        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        if target_modules == "all":
            # Use explicit module list for broader PEFT compatibility.
            # Some environments may not fully support the "all-linear" shortcut.
            target_modules_list = [
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ]
        elif target_modules == "attn":
            target_modules_list = ["q_proj", "v_proj", "k_proj", "o_proj"]
        elif target_modules == "mlp":
            target_modules_list = ["gate_proj", "up_proj", "down_proj"]
        else:
            target_modules_list = [m.strip() for m in target_modules.split(",")]

        if method == "qlora" and quantization_config is not None:
            try:
                from peft import prepare_model_for_kbit_training
                model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
                logger.info("QLoRA: 已完成 k-bit 训练准备（启用输入梯度与梯度检查点兼容）")
            except Exception as prep_error:
                logger.warning(f"QLoRA: prepare_model_for_kbit_training 失败，继续尝试训练: {prep_error}")

        if use_dora:
            lora_config = LoraConfig(
                task_type=TaskType.CAUSAL_LM,
                r=rank,
                lora_alpha=alpha,
                lora_dropout=lora_dropout,
                target_modules=target_modules_list,
                bias="none",
                inference_mode=False,
            )
        elif method == "full":
            logger.info("全参数微调模式，不应用 LoRA")
            return model, tokenizer
        else:
            lora_config = LoraConfig(
                task_type=TaskType.CAUSAL_LM,
                r=rank,
                lora_alpha=alpha,
                lora_dropout=lora_dropout,
                target_modules=target_modules_list,
                bias="none",
                inference_mode=False,
            )

        if resume_from and os.path.exists(resume_from):
            logger.info(f"从检查点恢复：{resume_from}")
            model = PeftModel.from_pretrained(model, resume_from, is_trainable=True)
        else:
            model = get_peft_model(model, lora_config)

        if gradient_checkpointing:
            if hasattr(model, "enable_input_require_grads"):
                model.enable_input_require_grads()
            if hasattr(model, "gradient_checkpointing_enable"):
                model.gradient_checkpointing_enable()

        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        if trainable_params == 0:
            raise RuntimeError("LoRA 配置后可训练参数为 0，请检查 target_modules 与模型结构是否匹配")
        logger.info(f"可训练参数量：{trainable_params:,}")

        if use_lora_plus and method not in ["full"]:
            logger.info(f"应用 LoRA+ 配置: lr_ratio={lora_plus_lr_ratio}")
            for name, param in model.named_parameters():
                if "lora_B" in name or "lora_A" in name:
                    param.requires_grad = True

        return model, tokenizer

    except Exception as e:
        logger.error(f"模型加载失败：{e}")
        if model is not None:
            del model
        if tokenizer is not None:
            del tokenizer
        cleanup_gpu_memory()
        raise


def load_multiple_datasets(
    dataset_path: str,
    additional_datasets: list[dict[str, Any]],
    tokenizer,
    max_length: int = 512,
    settings = None
):
    """加载多个数据集并进行混合训练

    Args:
        dataset_path: 主数据集路径
        additional_datasets: 额外数据集列表[{"dataset_id": "xxx", "weight": 0.3}, ...]
        tokenizer: 分词器
        max_length: 最大序列长度
        settings: 配置对象

    Returns:
        混合后的数据集
    """

    from datasets import interleave_datasets

    logger.info(f"加载主数据集：{dataset_path}")

    main_dataset = load_dataset(dataset_path, tokenizer, max_length)
    main_train = main_dataset["train"]

    if not additional_datasets:
        return main_dataset

    weights = [1.0]
    dataset_list = [main_train]

    for ds_config in additional_datasets:
        ds_id = ds_config.get("dataset_id")
        weight = ds_config.get("weight", 1.0)

        ds_path = None
        if settings:
            ds_dir = settings.datasets_dir_resolved / ds_id
            for ext in [".json", ".jsonl"]:
                for f in ds_dir.glob(f"*{ext}"):
                    ds_path = str(f)
                    break
                if ds_path:
                    break

        if ds_path and os.path.exists(ds_path):
            logger.info(f"加载额外数据集：{ds_id}, weight={weight}")
            ds = load_dataset(ds_path, tokenizer, max_length)
            dataset_list.append(ds["train"])
            weights.append(weight)
        else:
            logger.warning(f"数据集不存在，跳过：{ds_id}")

    if len(dataset_list) == 1:
        return main_dataset

    total_weight = sum(weights)
    normalized_weights = [w / total_weight for w in weights]

    logger.info(f"混合数据集：{len(dataset_list)} 个，权重={normalized_weights}")

    interleaved = interleave_datasets(
        dataset_list,
        probabilities=normalized_weights,
        seed=42
    )

    interleaved = split_train_test_dataset(interleaved)
    logger.info(f"混合数据集大小：训练={len(interleaved['train'])}, 测试={len(interleaved.get('test', []))}")
    return interleaved


def split_train_test_dataset(dataset, test_size: float = 0.1):
    """Create a stable train/test split even for very small datasets."""
    from datasets import DatasetDict

    sample_count = len(dataset)
    if sample_count <= 1:
        return DatasetDict({
            "train": dataset,
            "test": dataset.select([]),
        })

    if sample_count < 10:
        test_items = 1
    else:
        test_items = max(1, int(round(sample_count * test_size)))

    test_items = min(test_items, sample_count - 1)
    return dataset.train_test_split(test_size=test_items, seed=42)


class ProgressCallback:
    """训练进度回调 - 线程安全版本 + 异步检查点保存"""

    def __init__(
        self,
        total_steps: int,
        start_time: datetime,
        state: TrainingState,
        record: TrainingRecord,
        config: TrainingConfigInput,
        model=None,
        tokenizer=None,
        trainer=None,
        train_logger=None,
        event_loop=None,
    ):
        self.total_steps = total_steps
        self.start_time = start_time
        self.state = state
        self.record = record
        self.config = config
        self.current_step = 0
        self.current_epoch = 0
        self.current_loss = 0.0
        self.model = model
        self.tokenizer = tokenizer
        self.trainer = trainer
        self.train_logger = train_logger
        self._event_loop = event_loop

        self.last_update_step = -1
        self.update_interval = max(1, config.logging_steps)

        self._eta_window_size = 10
        self._eta_history = []
        self._last_eta_time = datetime.now()
        self._steps_per_second = 0.0

        if self._event_loop is None:
            try:
                self._event_loop = asyncio.get_running_loop()
            except RuntimeError:
                self._event_loop = None

    def set_trainer(self, trainer):
        """设置 trainer 引用"""
        self.trainer = trainer

    def on_train_begin(self, args, state, control, **kwargs):
        """训练开始时的回调"""
        logger.info(f"训练开始：总步数={self.total_steps}")
        _queue_training_progress(
            self.state,
            epoch=0, step=0, total_steps=self.total_steps, loss=0.0, lr=0.0,
            vram_used=get_vram_usage(), elapsed_time=0.0, eta=0.0,
            status="training",
            message="Training started",
        )

    def on_init_end(self, args, state, control, **kwargs):
        """Trainer 初始化结束时的回调"""
        logger.debug("Trainer 初始化完成")

    def on_epoch_begin(self, args, state, control, **kwargs):
        """每个 epoch 开始时的回调"""
        pass

    def on_epoch_end(self, args, state, control, **kwargs):
        """每个 epoch 结束时的回调"""
        pass

    def on_log(self, args, state, control, **kwargs):
        """日志回调"""
        pass

    def on_step_begin(self, args, state, control, **kwargs):
        """每一步开始时的回调"""
        pass

    def on_prediction_step(self, args, state, control, **kwargs):
        """预测步骤回调"""
        pass

    def on_substep_end(self, args, state, control, **kwargs):
        """子步骤结束回调（梯度累积）"""
        pass

    def on_pre_optimizer_step(self, args, state, control, **kwargs):
        """优化器步骤前回调"""
        pass

    def on_optimizer_step(self, args, state, control, **kwargs):
        """优化器步骤回调"""
        pass

    def on_save(self, args, state, control, **kwargs):
        """保存回调"""
        pass

    def on_evaluate(self, args, state, control, **kwargs):
        """评估回调"""
        pass

    def on_predict(self, args, state, control, metrics, **kwargs):
        """预测回调"""
        pass

    def on_push_begin(self, args, state, control, **kwargs):
        """模型推送到 Hub 前的回调"""
        logger.info("准备推送模型到 Hub")

    def on_step_end(self, args, state, control, **kwargs):
        """每一步结束时的回调 - 优化版：降低更新频率 + FIX-2: 停止信号传递"""
        if self.state.should_stop():
            logger.info(f"检测到停止信号，在第 {state.global_step} 步中断训练")
            control.should_training_stop = True
            return control

        self.current_step = state.global_step
        self.current_epoch = state.epoch

        loss = kwargs.get("loss", 0.0)
        self.current_loss = float(loss) if loss > 0 else 0.0

        if (self.current_step - self.last_update_step) >= self.update_interval:
            self._update_progress(state, args, kwargs)
            self.last_update_step = self.current_step

        return control

    def _update_progress(self, state, args, kwargs):
        """实际更新进度的逻辑"""
        elapsed = (datetime.now() - self.start_time).total_seconds()

        now = datetime.now()
        time_delta = (now - self._last_eta_time).total_seconds()

        if time_delta > 0:
            steps_delta = self.current_step - (self._eta_history[-1]["step"] if self._eta_history else 0)
            if steps_delta > 0:
                self._steps_per_second = steps_delta / time_delta
                self._eta_history.append({
                    "step": self.current_step,
                    "time": now,
                    "steps_per_second": self._steps_per_second
                })

                if len(self._eta_history) > self._eta_window_size:
                    self._eta_history.pop(0)

        self._last_eta_time = now

        if self.current_step > 0 and self._steps_per_second > 0:
            avg_steps_per_second = sum(h["steps_per_second"] for h in self._eta_history) / len(self._eta_history) if self._eta_history else self._steps_per_second
            eta = (self.total_steps - self.current_step) / avg_steps_per_second
        else:
            eta = 0

        vram = get_vram_usage()
        lr = getattr(args, "learning_rate", self.config.learning_rate)

        _queue_training_progress(
            self.state,
            epoch=int(self.current_epoch) + 1,
            step=self.current_step,
            total_steps=self.total_steps,
            loss=self.current_loss,
            lr=float(lr),
            vram_used=vram,
            elapsed_time=elapsed,
            eta=eta if eta > 0 and eta < 86400 else 0.0,
            status="running",
            message=f"Training epoch {int(self.current_epoch) + 1}/{self.config.epochs}",
        )

        if self.train_logger:
            self.train_logger.log_metrics(
                epoch=int(self.current_epoch) + 1,
                step=self.current_step,
                metrics={
                    "loss": self.current_loss,
                    "lr": float(lr),
                    "vram_used": vram,
                    "elapsed_time": elapsed,
                    "eta": eta
                }
            )

        try:
            ws_manager = get_ws_manager()
            progress_data = {
                "epoch": int(self.current_epoch) + 1,
                "step": self.current_step,
                "total_steps": self.total_steps,
                "loss": self.current_loss,
                "lr": float(lr),
                "vram_used": vram,
                "elapsed_time": elapsed,
                "eta": eta,
                "status": "running",
                "message": f"Training epoch {int(self.current_epoch) + 1}/{self.config.epochs}"
            }
            if self._event_loop and not self._event_loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast_progress(self.record.id, progress_data),
                    self._event_loop
                )
        except Exception as e:
            logger.debug(f"WebSocket 推送进度失败：{e}")

    def on_train_end(self, args, state, control, **kwargs):
        """训练结束时的回调"""
        final_elapsed = (datetime.now() - self.start_time).total_seconds()
        final_lr = float(getattr(args, "learning_rate", self.config.learning_rate))
        if self.train_logger:
            self.train_logger.log_completion({
                "loss": self.current_loss,
                "lr": final_lr,
                "elapsed_time": final_elapsed,
                "total_steps": self.total_steps,
            })

        try:
            ws_manager = get_ws_manager()
            completion_data = {
                "loss": self.current_loss,
                "lr": final_lr,
                "elapsed_time": final_elapsed,
                "total_steps": self.total_steps
            }
            if self._event_loop and not self._event_loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast_event(self.record.id, "training_completed", completion_data),
                    self._event_loop
                )
        except Exception as e:
            logger.debug(f"WebSocket 推送完成事件失败：{e}")

        _queue_training_progress(
            self.state,
            epoch=self.config.epochs,
            step=self.total_steps,
            total_steps=self.total_steps,
            loss=self.current_loss,
            lr=final_lr,
            vram_used=get_vram_usage(),
            elapsed_time=final_elapsed,
            eta=0.0,
            status="completed",
            message="Training completed!",
            final_loss=self.current_loss,
            final_lr=final_lr,
            final_elapsed_time=final_elapsed,
            final_steps=self.total_steps,
        )

        # Break circular references to avoid memory leaks
        self.model = None
        self.trainer = None


def training_thread(
    config: TrainingConfigInput,
    model_path: str,
    dataset_path: str,
    state: TrainingState,
    record: TrainingRecord,
    event_loop=None,
    task_id=None,
):
    """
    训练线程 - 使用队列式状态更新 + 循环重试机制

    Args:
        event_loop: asyncio 事件循环（用于 WebSocket 推送）
        task_id: 任务ID（用于线程注销）
    """
    import gc
    import time
    import torch
    from transformers import Trainer, TrainingArguments

    MAX_RETRIES = 2
    retry_count = 0
    settings = get_settings()
    model = None
    tokenizer = None
    trainer = None

    start_time = datetime.now()

    train_logger = TrainingLogger(record.id, Path(record.output_path))
    train_logger.log_start(config)

    while True:
        if state.should_stop():
            _finalize_stop_requested(
                state=state,
                record=record,
                task_id=task_id,
                model=model,
                tokenizer=tokenizer,
                trainer=trainer,
                message="Training stopped before next retry",
            )
            return

        if retry_count > 0:
            logger.info(f"第 {retry_count} 次重试训练：{record.id}")
            # Clean up resources before retry
            cleanup_gpu_memory(aggressive=True)
            if model is not None:
                safe_cleanup_model(model)
            del model, tokenizer, trainer
            gc.collect()

            # Degrade config and retry
            config = _degrade_training_config(config)
            logger.info(f"应用降级配置：batch_size={config.batch_size}, "
                       f"gradient_accumulation={config.gradient_accumulation}")

            cooldown = 30 * retry_count
            logger.info(f"等待 {cooldown} 秒后重试...")
            for _ in range(cooldown):
                if state.should_stop():
                    _finalize_stop_requested(
                        state=state,
                        record=record,
                        task_id=task_id,
                        model=model,
                        tokenizer=tokenizer,
                        trainer=trainer,
                        message="Training stopped during retry cooldown",
                    )
                    return
                time.sleep(1)

        try:
            state.queue_training_state(True)
            _queue_training_progress(
                state,
                epoch=0, step=0, total_steps=0, loss=0.0, lr=0.0,
                vram_used=0.0, elapsed_time=0.0, eta=0.0,
                status="loading",
                message="Loading model...",
            )

            try:
                model, tokenizer = load_model_and_tokenizer(
                    model_path,
                    config.method,
                    config.quantization,
                    config.resume_from_checkpoint,
                    rank=config.rank,
                    alpha=config.alpha,
                    lora_dropout=config.lora_dropout,
                    target_modules=config.target_modules,
                    use_dora=config.use_dora,
                    use_flash_attn=config.use_flash_attn,
                    gradient_checkpointing=config.gradient_checkpointing,
                    use_lora_plus=config.use_lora_plus,
                    lora_plus_lr_ratio=config.lora_plus_lr_ratio
                )
            except torch.cuda.OutOfMemoryError as e:
                raise RecoverableError(f"加载模型时 OOM: {e}")
            except FileNotFoundError as e:
                raise UnrecoverableError(f"模型文件丢失：{e}")
            except Exception as e:
                if "CUDA" in str(e) or "memory" in str(e).lower():
                    raise RecoverableError(f"GPU 错误：{e}")
                raise

            if state.should_stop():
                _finalize_stop_requested(
                    state=state,
                    record=record,
                    task_id=task_id,
                    model=model,
                    tokenizer=tokenizer,
                    trainer=trainer,
                    message="Training stopped after model load",
                )
                return

            _queue_training_progress(
                state,
                epoch=0, step=0, total_steps=0, loss=0.0, lr=0.0,
                vram_used=0.0, elapsed_time=0.0, eta=0.0,
                status="loading",
                message="Loading dataset...",
            )
            try:
                if config.additional_datasets:
                    logger.info(f"使用多数据集混合训练：{len(config.additional_datasets) + 1} 个数据集")
                    dataset = load_multiple_datasets(
                        dataset_path,
                        config.additional_datasets,
                        tokenizer,
                        config.max_seq_length,
                        settings
                    )
                else:
                    dataset = load_dataset(dataset_path, tokenizer, config.max_seq_length)
            except FileNotFoundError as e:
                raise UnrecoverableError(f"数据集文件丢失：{e}")
            except json.JSONDecodeError as e:
                raise UnrecoverableError(f"数据集格式错误：{e}")

            if state.should_stop():
                _finalize_stop_requested(
                    state=state,
                    record=record,
                    task_id=task_id,
                    model=model,
                    tokenizer=tokenizer,
                    trainer=trainer,
                    message="Training stopped after dataset load",
                )
                return

            try:
                total_steps = _estimate_training_total_steps(
                    train_size=len(dataset["train"]),
                    batch_size=config.batch_size,
                    epochs=config.epochs,
                )
            except ValueError as e:
                raise UnrecoverableError(str(e))

            eval_steps = config.eval_steps if config.eval_steps > 0 else None
            eval_strategy = "steps" if eval_steps else "no"

            use_best_model = config.load_best_model and eval_strategy == "steps"
            if config.load_best_model and eval_strategy != "steps":
                logger.warning("load_best_model 需要 eval_steps > 0，已自动禁用")

            warmup_steps = config.warmup_steps
            warmup_ratio = None
            if warmup_steps == 0 and config.warmup_ratio > 0:
                warmup_ratio = config.warmup_ratio
            logger.info(f"学习率预热配置：warmup_steps={warmup_steps}, warmup_ratio={warmup_ratio}")

            deepspeed_config = None
            if config.deepspeed_stage > 0 and config.method != "qlora":
                deepspeed_config = {
                    "fp16": {"enabled": not config.bf16},
                    "bf16": {"enabled": config.bf16},
                    "zero_optimization": {
                        "stage": config.deepspeed_stage,
                        "offload_optimizer": {"device": "cpu"} if config.offload_optimizer else False,
                        "offload_param": {"device": "cpu"} if config.offload_optimizer and config.deepspeed_stage >= 2 else False,
                    },
                    "gradient_accumulation_steps": config.gradient_accumulation,
                    "gradient_clipping": config.max_grad_norm,
                    "steps_per_print": config.logging_steps,
                    "train_batch_size": config.batch_size,
                    "train_micro_batch_size_per_gpu": config.batch_size,
                }
                logger.info(f"已配置 DeepSpeed ZeRO-{config.deepspeed_stage}, offload={config.offload_optimizer}")
            elif config.deepspeed_stage > 0 and config.method == "qlora":
                logger.warning("QLoRA 模式下不支持 DeepSpeed，将使用标准训练")

            output_dir = config.output_path if hasattr(config, 'output_path') else record.output_path
            base_training_args_kwargs = {
                "output_dir": output_dir,
                "num_train_epochs": config.epochs,
                "per_device_train_batch_size": config.batch_size,
                "gradient_accumulation_steps": config.gradient_accumulation,
                "learning_rate": config.learning_rate,
                "max_steps": total_steps,
                "warmup_steps": warmup_steps,
                "warmup_ratio": warmup_ratio,
                "logging_steps": config.logging_steps,
                "save_steps": config.save_steps,
                "save_total_limit": 3,
                "load_best_model_at_end": use_best_model,
                "eval_steps": eval_steps,
                "report_to": "none",
                "fp16": not config.bf16,
                "bf16": config.bf16,
                "gradient_checkpointing": config.gradient_checkpointing,
                "dataloader_num_workers": config.dataloader_num_workers,
                "dataloader_pin_memory": config.dataloader_pin_memory,
                "dataloader_persistent_workers": config.dataloader_persistent_workers if config.dataloader_num_workers > 0 else False,
                "remove_unused_columns": False,
                "save_strategy": "steps",
                "lr_scheduler_type": config.lr_scheduler,
                "weight_decay": config.weight_decay,
                "max_grad_norm": config.max_grad_norm,
                "label_smoothing_factor": config.label_smoothing if config.label_smoothing > 0 else None,
                "optim": "adamw_torch",
                "ddp_find_unused_parameters": False,
                "deepspeed": deepspeed_config,
                "metric_for_best_model": config.metric_for_best_model,
                "greater_is_better": config.greater_is_better,
                # Windows/redirected stderr environments may raise OSError([Errno 22])
                # when tqdm tries to render terminal progress bars. We already expose
                # training progress via V2 events, so disable trainer tqdm safely.
                "disable_tqdm": True,
            }
            training_args_signature = inspect.signature(TrainingArguments.__init__)
            supported_args = set(training_args_signature.parameters.keys())

            training_args_kwargs = dict(base_training_args_kwargs)
            if "eval_strategy" in supported_args:
                training_args_kwargs["eval_strategy"] = eval_strategy
            elif "evaluation_strategy" in supported_args:
                training_args_kwargs["evaluation_strategy"] = eval_strategy
            else:
                training_args_kwargs["load_best_model_at_end"] = False
                training_args_kwargs.pop("metric_for_best_model", None)
                training_args_kwargs.pop("greater_is_better", None)
                logger.warning("当前 TrainingArguments 不支持 eval strategy 参数，已禁用 load_best_model_at_end")

            filtered_training_args_kwargs = {
                key: value
                for key, value in training_args_kwargs.items()
                if key in supported_args and value is not None
            }
            training_args = TrainingArguments(**filtered_training_args_kwargs)

            early_stopping_callback = None
            if config.early_stopping_patience > 0 and use_best_model:
                from transformers import EarlyStoppingCallback
                early_stopping_callback = EarlyStoppingCallback(
                    early_stopping_patience=config.early_stopping_patience,
                    early_stopping_threshold=config.early_stopping_threshold
                )
                logger.info(f"已启用早停：patience={config.early_stopping_patience}, threshold={config.early_stopping_threshold}")

            callbacks = []
            if early_stopping_callback:
                callbacks.append(early_stopping_callback)

            trainer = Trainer(
                model=model,
                args=training_args,
                train_dataset=dataset["train"],
                eval_dataset=dataset.get("test"),
                processing_class=tokenizer,
                callbacks=callbacks,
            )

            if config.use_lora_plus and config.method not in ["full"] and not config.use_galore:
                logger.info(f"应用 LoRA+ 不同学习率配置 ratio={config.lora_plus_lr_ratio}")
                base_lr = config.learning_rate

                lora_a_params = []
                lora_b_params = []
                other_params = []

                for name, param in model.named_parameters():
                    if param.requires_grad:
                        if "lora_A" in name:
                            lora_a_params.append(param)
                        elif "lora_B" in name:
                            lora_b_params.append(param)
                        else:
                            other_params.append(param)

                from torch.optim import AdamW
                param_groups = [
                    {"params": lora_a_params, "lr": base_lr},
                    {"params": lora_b_params, "lr": base_lr * config.lora_plus_lr_ratio},
                    {"params": other_params, "lr": base_lr},
                ]
                trainer.optimizer = AdamW(param_groups, weight_decay=config.weight_decay)
                logger.info(f"LoRA+ 优化器配置：A参数 lr={base_lr}, B参数 lr={base_lr * config.lora_plus_lr_ratio}")

            if config.use_galore:
                if config.deepspeed_stage > 0:
                    logger.warning("GaLore 与 DeepSpeed 不兼容，已自动禁用 DeepSpeed")
                    config.deepspeed_stage = 0

                if config.use_lora_plus:
                    logger.warning("GaLore 与 LoRA+ 同时启用可能存在冲突，建议关闭 LoRA+")

                try:
                    from galore_torch import GaLoreAdamW

                    logger.info(f"配置 GaLore: rank={config.galore_rank}, update_gap={config.galore_update_proj_gap}")

                    galore_params = []
                    for name, param in model.named_parameters():
                        if param.requires_grad and any(x in name for x in ['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj']):
                            galore_params.append(param)

                    if len(galore_params) > 0:
                        non_galore_params = [p for p in model.parameters() if p.requires_grad and p not in galore_params]

                        param_groups = [
                            {"params": galore_params, "rank": config.galore_rank, "update_proj_gap": config.galore_update_proj_gap},
                            {"params": non_galore_params}
                        ]

                        trainer.optimizer = GaLoreAdamW(
                            param_groups,
                            lr=config.learning_rate,
                            weight_decay=config.weight_decay
                        )

                        logger.info(f"GaLore 已启用，投影参数: {len(galore_params)} 个")
                    else:
                        logger.warning("未找到可使用 GaLore 的参数，跳过")

                except ImportError as e:
                    logger.warning("GaLore 未安装，请运行: pip install galore-torch")
                    logger.warning(f"将跳过 GaLore 优化，继续使用标准训练: {e}")

            if config.use_torch_compile and hasattr(model, 'forward'):
                try:
                    import torch
                    if hasattr(torch, 'compile'):
                        logger.info(f"使用 torch.compile 编译模型，模式: {config.torch_compile_mode}")
                        model = torch.compile(model, mode=config.torch_compile_mode)
                        logger.info("torch.compile 编译成功")
                    else:
                        logger.warning("PyTorch 版本不支持 torch.compile，需要 PyTorch 2.0+")
                except Exception as e:
                    logger.warning(f"torch.compile 编译失败，跳过: {e}")

            if config.use_tf32:
                try:
                    import torch
                    if torch.cuda.is_available() and hasattr(torch.cuda, 'set_float32_matmul_precision'):
                        device_name = torch.cuda.get_device_name(0).lower()
                        if any(arch in device_name for arch in ['30', '40', 'a10', 'a100', 'a30', 'l40', 'h100']):
                            torch.backends.cuda.matmul.allow_tf32 = True
                            torch.backends.cudnn.allow_tf32 = True
                            logger.info("已启用 TF32 加速（Ampere+ GPU）")
                        else:
                            logger.info(f"GPU {device_name} 不支持 TF32，跳过")
                except Exception as e:
                    logger.debug(f"TF32 启用失败: {e}")

            callback = ProgressCallback(
                total_steps, start_time, state, record, config,
                model=model, tokenizer=tokenizer, trainer=trainer,
                train_logger=train_logger, event_loop=event_loop
            )
            trainer.add_callback(callback)

            _queue_training_progress(
                state,
                epoch=0, step=0, total_steps=total_steps, loss=0.0, lr=0.0,
                vram_used=0.0, elapsed_time=0.0, eta=0.0,
                status="training",
                message="Starting training...",
            )

            try:
                trainer.train(resume_from_checkpoint=config.resume_from_checkpoint if config.resume_from_checkpoint else None)
            except torch.cuda.OutOfMemoryError as e:
                raise RecoverableError(f"训练时 OOM: {e}")
            except KeyboardInterrupt:
                raise UnrecoverableError("用户中断训练")
            except Exception as e:
                if "CUDA" in str(e) or "memory" in str(e).lower() or "NCCL" in str(e):
                    raise RecoverableError(f"GPU 错误：{e}")
                raise

            if state.should_stop():
                _finalize_stop_requested(
                    state=state,
                    record=record,
                    task_id=task_id,
                    model=model,
                    tokenizer=tokenizer,
                    trainer=trainer,
                )
                return

            output_dir = Path(record.output_path)
            lora_path = output_dir / "lora_adapter"
            lora_path.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(lora_path)
            tokenizer.save_pretrained(lora_path)
            logger.info(f"模型已保存到：{lora_path}")

            record.status = "completed"
            record.end_time = datetime.now().isoformat()
            record.checkpoint_path = str(lora_path)

            state.add_to_history_sync(record)
            logger.info(f"训练历史已保存：{record.id}")

            # Training succeeded - clean up and exit
            state.queue_training_state(False)
            if task_id:
                state.unregister_training_task(task_id)
                logger.debug(f"已注销训练任务线程：{task_id}")
            _cleanup_training_resources(model, tokenizer, trainer)
            return

        except RecoverableError as e:
            logger.warning(f"可恢复错误：{e}")
            if retry_count < MAX_RETRIES:
                retry_count += 1
                # Loop will handle cleanup and retry
            else:
                logger.error(f"重试次数耗尽 ({MAX_RETRIES}次)，训练失败")
                state.queue_training_state(False)
                if task_id:
                    state.unregister_training_task(task_id)
                _handle_training_failure(state, record, e, train_logger)
                _cleanup_training_resources(model, tokenizer, trainer)
                return

        except UnrecoverableError as e:
            logger.error(f"不可恢复错误：{e}")
            state.queue_training_state(False)
            if task_id:
                state.unregister_training_task(task_id)
            _handle_training_failure(state, record, e, train_logger)
            _cleanup_training_resources(model, tokenizer, trainer)
            return

        except Exception as e:
            logger.error(f"训练失败：{e}")
            logger.error(tb.format_exc())
            state.queue_training_state(False)
            if task_id:
                state.unregister_training_task(task_id)
            _handle_training_failure(state, record, e, train_logger)
            _cleanup_training_resources(model, tokenizer, trainer)
            return


def _apply_precision_preset(config: TrainingConfigInput) -> TrainingConfigInput:
    """应用精度预设配置

    预设选项:
    - max: 最高精度（全参数/DoRA, 余弦退火，早停）
    - balanced: 平衡精度和效率（高秩 LoRA）
    - fast: 快速训练（QLoRA）
    """
    cfg = config.model_copy()

    if cfg.precision_preset == "max":
        cfg.method = "full" if not cfg.use_dora else "dora"
        cfg.learning_rate = 1e-5
        cfg.lr_scheduler = "cosine"
        cfg.warmup_ratio = 0.1
        cfg.weight_decay = 0.01
        cfg.label_smoothing = 0.1
        cfg.gradient_checkpointing = True
        cfg.bf16 = True
        cfg.eval_steps = 100
        cfg.load_best_model = True
        cfg.lora_dropout = 0.05
        cfg.max_grad_norm = 1.0
        logger.info("应用最高精度配置（max）")

    elif cfg.precision_preset == "balanced":
        if cfg.use_dora:
            cfg.rank = 64
            cfg.alpha = 128
        else:
            cfg.rank = 32
            cfg.alpha = 64
        cfg.learning_rate = 2e-5 if cfg.use_dora else 3e-5
        cfg.lr_scheduler = "cosine"
        cfg.warmup_ratio = 0.1
        cfg.weight_decay = 0.01
        cfg.gradient_checkpointing = True
        cfg.bf16 = True
        cfg.eval_steps = 100
        cfg.load_best_model = True
        cfg.lora_dropout = 0.05
        logger.info("应用平衡精度配置 (balanced)")

    elif cfg.precision_preset == "fast":
        cfg.method = "qlora"
        cfg.rank = 16
        cfg.alpha = 32
        cfg.learning_rate = 5e-5
        cfg.lr_scheduler = "linear"
        cfg.warmup_ratio = 0.05
        cfg.weight_decay = 0.01
        cfg.gradient_checkpointing = True
        cfg.bf16 = True
        cfg.eval_steps = 200
        cfg.load_best_model = True
        cfg.lora_dropout = 0.1
        cfg.use_torch_compile = True
        cfg.torch_compile_mode = "default"
        cfg.dataloader_num_workers = 2
        cfg.dataloader_pin_memory = True
        cfg.dataloader_persistent_workers = True
        cfg.use_tf32 = True
        cfg.use_flash_attn = True
        logger.info("应用快速训练配置(fast) - 启用所有性能优化")

    if cfg.precision_preset == "fast":
        cfg.use_torch_compile = True
        cfg.use_tf32 = True

    return cfg


def _apply_memory_preset(config: TrainingConfigInput) -> TrainingConfigInput:
    """应用显存预设配置

    预设选项:
    - auto: 自动根据显存调整
    - 6gb: 6GB 显存优化 (极致压缩)
    - 8gb: 8GB 显存优化 (平衡)
    - 12gb: 12GB 显存优化 (高性能)
    """
    cfg = config.model_copy()

    if cfg.memory_preset == "6gb":
        cfg.gradient_checkpointing = True
        cfg.gradient_accumulation = 16
        cfg.batch_size = 1
        cfg.quantization = 4
        cfg.bf16 = True
        cfg.use_flash_attn = True
        logger.info("应用 6GB 显存优化配置")

    elif cfg.memory_preset == "8gb":
        cfg.gradient_checkpointing = True
        cfg.gradient_accumulation = 8
        cfg.batch_size = 2
        cfg.quantization = 8
        cfg.bf16 = True
        cfg.use_flash_attn = True
        logger.info("应用 8GB 显存优化配置")

    elif cfg.memory_preset == "12gb":
        cfg.gradient_checkpointing = True
        cfg.gradient_accumulation = 4
        cfg.batch_size = 2
        cfg.quantization = 0
        cfg.bf16 = True
        cfg.use_flash_attn = True
        cfg.deepspeed_stage = 2
        cfg.offload_optimizer = True
        logger.info("应用 12GB 显存优化配置 (DeepSpeed ZeRO-2)")

    elif cfg.memory_preset == "auto":
        try:
            import torch
            if torch.cuda.is_available():
                total_vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)

                if total_vram <= 6:
                    cfg.memory_preset = "6gb"
                    return _apply_memory_preset(cfg)
                elif total_vram <= 8:
                    cfg.memory_preset = "8gb"
                    return _apply_memory_preset(cfg)
                elif total_vram <= 12:
                    cfg.memory_preset = "12gb"
                    return _apply_memory_preset(cfg)
        except Exception as e:
            logger.debug(f"自动检测显存失败：{e}")

    return cfg


def _degrade_training_config(config: TrainingConfigInput) -> TrainingConfigInput:
    """智能降级训练配置

    根据当前显存情况自动调整参数
    """
    degraded = config.model_copy()

    try:
        import torch
        if torch.cuda.is_available():
            available_vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            allocated_vram = torch.cuda.memory_allocated(0) / (1024 ** 3)
            free_vram = available_vram - allocated_vram

            if free_vram < 4.0:
                if degraded.batch_size > 1:
                    degraded.batch_size = 1
                if degraded.gradient_accumulation > 8:
                    degraded.gradient_accumulation = 8
                if degraded.max_seq_length > 256:
                    degraded.max_seq_length = 256
            elif free_vram < 6.0:
                if degraded.batch_size > 2:
                    degraded.batch_size = 2
                if degraded.gradient_accumulation > 16:
                    degraded.gradient_accumulation = 16
    except Exception as e:
        logger.warning(f"降级配置失败：{e}")

    return degraded


def _handle_training_failure(state: TrainingState, record: TrainingRecord, error: Exception, train_logger: 'TrainingLogger' = None):
    """处理训练失败"""
    feedback = _build_failure_feedback(str(error))
    latest_progress = state.get_progress()
    _queue_training_progress(
        state,
        epoch=latest_progress.epoch,
        step=latest_progress.step,
        total_steps=latest_progress.total_steps,
        loss=latest_progress.loss,
        lr=latest_progress.lr,
        vram_used=latest_progress.vram_used,
        elapsed_time=latest_progress.elapsed_time,
        eta=latest_progress.eta,
        status="failed",
        message=f"Error: {str(error)}",
        **feedback,
    )

    record.status = "failed"
    record.end_time = datetime.now().isoformat()

    if train_logger:
        train_logger.log_error(error)

    state.add_to_history_sync(record)
    logger.info(f"训练失败记录已保存：{record.id}")


def _finalize_stop_requested(
    state: TrainingState,
    record: TrainingRecord,
    task_id: str | None,
    model=None,
    tokenizer=None,
    trainer=None,
    message: str = "Training stopped by user",
):
    """统一处理用户停止请求，保证状态与历史一致。"""
    latest_progress = state.get_progress()
    _queue_training_progress(
        state,
        epoch=latest_progress.epoch,
        step=latest_progress.step,
        total_steps=latest_progress.total_steps,
        loss=latest_progress.loss,
        lr=latest_progress.lr,
        vram_used=latest_progress.vram_used,
        elapsed_time=latest_progress.elapsed_time,
        eta=latest_progress.eta,
        status="stopped",
        message=message,
        stop_reason="user_requested",
    )

    record.status = "stopped"
    record.end_time = datetime.now().isoformat()
    state.add_to_history_sync(record)
    logger.info(f"训练已停止并保存历史：{record.id}")

    state.queue_training_state(False)
    if task_id:
        state.unregister_training_task(task_id)
        logger.debug(f"已注销训练任务线程：{task_id}")

    _cleanup_training_resources(model, tokenizer, trainer)


def _cleanup_training_resources(model, tokenizer, trainer):
    """清理训练资源"""
    try:
        from core.utils import cleanup_gpu_memory, safe_cleanup_model

        cleanup_gpu_memory(aggressive=True)

        if model is not None:
            safe_cleanup_model(model)

        del model, tokenizer, trainer
        import gc
        gc.collect()
    except Exception as e:
        logger.warning(f"清理资源失败：{e}")


class TrainingLogger:
    """训练日志记录器"""

    def __init__(self, task_id: str, output_dir: Path):
        self.task_id = task_id
        self.log_file = output_dir / "training.log"
        self.metrics_file = output_dir / "metrics.jsonl"
        self.events_file = output_dir / "events.jsonl"

        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(f"training.{task_id}")
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            handler = logging.FileHandler(self.log_file, encoding='utf-8')
            formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def log_start(self, config: TrainingConfigInput):
        """记录训练开始"""
        self.logger.info("=" * 60)
        self.logger.info("训练开始")
        self.logger.info("=" * 60)
        self.logger.info(f"任务 ID: {self.task_id}")
        self.logger.info(f"模型：{config.model_id}")
        self.logger.info(f"数据集：{config.dataset_id}")
        self.logger.info(f"方法：{config.method}")
        self.logger.info(f"Rank: {config.rank}, Alpha: {config.alpha}")
        self.logger.info(f"学习率：{config.learning_rate}")
        self.logger.info(f"批次大小：{config.batch_size}")
        self.logger.info(f"梯度累积：{config.gradient_accumulation}")
        self.logger.info(f"序列长度：{config.max_seq_length}")
        self.logger.info(f"训练轮数：{config.epochs}")

        self._log_event("training_started", {
            "config": config.model_dump()
        })

    def log_metrics(self, epoch: int, step: int, metrics: dict[str, Any]):
        """记录训练指标"""
        metrics_record = {
            "timestamp": datetime.now().isoformat(),
            "epoch": epoch,
            "step": step,
            **metrics
        }

        try:
            with open(self.metrics_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(metrics_record, ensure_ascii=False) + '\n')
        except Exception as e:
            self.logger.warning(f"记录指标失败：{e}")

    def log_event(self, event_type: str, data: dict[str, Any]):
        """记录训练事件"""
        self._log_event(event_type, data)

    def _log_event(self, event_type: str, data: dict[str, Any]):
        """内部事件记录"""
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "data": data
        }

        try:
            with open(self.events_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event, ensure_ascii=False) + '\n')
        except Exception as e:
            self.logger.warning(f"记录事件失败：{e}")

    def log_error(self, error: Exception, context: dict[str, Any] = None):
        """记录错误"""
        self.logger.error(f"错误：{error}", exc_info=True)
        self._log_event("error", {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or {}
        })

    def log_checkpoint_saved(self, step: int, path: str):
        """记录检查点保存"""
        self.logger.info(f"检查点保存：step={step}, path={path}")
        self._log_event("checkpoint_saved", {
            "step": step,
            "path": path
        })

    def log_completion(self, final_metrics: dict[str, Any]):
        """记录训练完成"""
        self.logger.info("=" * 60)
        self.logger.info("训练完成")
        self.logger.info("=" * 60)
        self.logger.info(f"最终 Loss: {final_metrics.get('loss', 'N/A')}")
        self.logger.info(f"训练时长：{final_metrics.get('elapsed_time', 'N/A')}")

        self._log_event("training_completed", {
            "final_metrics": final_metrics
        })


@router.post("/stop")
async def stop_training():
    """停止训练"""
    state = get_training_context().state

    if not state.is_training():
        raise HTTPException(status_code=400, detail="No training in progress")

    if state.should_stop():
        return {"message": "Stop already requested", "status": "stopping"}

    state.request_stop()
    _queue_training_progress(
        state,
        status="stopping",
        message="Stop requested, waiting for current step to finish",
    )
    logger.info("收到训练停止请求，等待训练线程安全退出")
    return {"message": "Stop requested", "status": "stopping"}


@router.get("/progress", response_model=TrainingProgressResponse)
async def get_progress():
    """获取训练进度"""
    state = get_training_context().state
    progress = state.get_progress()
    latest_event = get_training_event_hub_v2().get_latest()
    if latest_event:
        merged = _legacy_progress_from_v2_event(latest_event, progress)
        return TrainingProgressResponse(**merged)
    return TrainingProgressResponse(**progress.model_dump())


@router.get("/progress/stream")
async def progress_stream(
    timeout: int = Query(default=300, ge=30, le=3600, description="连接超时时间（秒）"),
    heartbeat: int = Query(default=30, ge=10, le=120, description="心跳间隔（秒）")
):
    """SSE 进度流 - 每次进度更新都发送（重构版）

    修复:
    - P1-2: 添加连接超时机制和心跳检测

    Args:
        timeout: 连接超时时间（秒），默认 300 秒
        heartbeat: 心跳间隔（秒），默认 30 秒
    """
    import asyncio
    import time

    state = get_training_context().state
    hub = get_training_event_hub_v2()

    async def event_generator():
        last_step = -1
        last_status = ""
        last_seq = 0
        idle_count = 0
        last_heartbeat = time.time()
        connection_start = time.time()
        last_activity = time.time()

        try:
            while True:
                current_time = time.time()

                if current_time - connection_start > timeout:
                    logger.info(f"SSE 连接超时：已运行 {timeout} 秒")
                    yield f"event: timeout\ndata: {{\"message\": \"Connection timeout after {timeout}s\"}}\n\n"
                    break

                if current_time - last_activity > timeout:
                    logger.warning(f"SSE 连接空闲超时：{current_time - last_activity:.0f} 秒无活动")
                    yield "event: timeout\ndata: {\"message\": \"Idle timeout\"}\n\n"
                    break

                latest_event = hub.get_latest()
                if latest_event and latest_event.sequence > last_seq:
                    merged = _legacy_progress_from_v2_event(latest_event, state.get_progress())
                    progress = TrainingProgressResponse(**merged)
                    last_seq = latest_event.sequence
                else:
                    progress = state.get_progress()

                should_send = (
                    progress.step != last_step or
                    progress.status != last_status
                )

                if should_send:
                    yield f"data: {progress.model_dump_json()}\n\n"
                    last_step = progress.step
                    last_status = progress.status
                    last_activity = current_time

                if current_time - last_heartbeat >= heartbeat:
                    yield f"event: heartbeat\ndata: {{\"timestamp\": {current_time}}}\n\n"
                    last_heartbeat = current_time

                if progress.status == "idle":
                    idle_count += 1
                    if idle_count > 3:
                        yield f"data: {progress.model_dump_json()}\n\n"
                        break
                else:
                    idle_count = 0

                if progress.status in ["completed", "failed", "stopped"]:
                    yield f"data: {progress.model_dump_json()}\n\n"
                    break

                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("SSE 连接被客户端取消")
        except Exception as e:
            logger.error(f"SSE 连接错误：{e}")
            yield f"event: error\ndata: {{\"message\": \"{str(e)}\"}}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/v2/events/stream")
async def stream_training_events_v2(
    task_id: str | None = Query(default=None, description="仅订阅指定任务"),
    last_event_id: str | None = Query(default=None, description="断线重连的 last_event_id"),
    sse_last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    timeout: int = Query(default=300, ge=30, le=3600, description="连接超时（秒）"),
    heartbeat: int = Query(default=15, ge=5, le=120, description="心跳间隔（秒）"),
):
    """训练事件流 V2（SSE）。"""
    import time

    hub = get_training_event_hub_v2()
    start_seq = hub.parse_last_event_id(last_event_id or sse_last_event_id)

    async def event_generator():
        connection_start = time.time()
        last_heartbeat = time.time()
        cursor = start_seq

        while True:
            now = time.time()
            if now - connection_start > timeout:
                break

            events = hub.list_since(cursor, task_id=task_id)
            if events:
                for event in events:
                    cursor = max(cursor, event.sequence)
                    payload = json.dumps(event.model_dump(), ensure_ascii=False)
                    yield f"id: {event.event_id}\nevent: {event.kind}\ndata: {payload}\n\n"

            if now - last_heartbeat >= heartbeat:
                heartbeat_payload = json.dumps(
                    {
                        "version": "v2",
                        "kind": "heartbeat",
                        "sequence": hub.current_sequence(),
                        "ts": datetime.now().isoformat(),
                    },
                    ensure_ascii=False,
                )
                yield f"event: heartbeat\ndata: {heartbeat_payload}\n\n"
                last_heartbeat = now

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.websocket("/v2/ws/{task_id}")
async def training_events_websocket_v2(websocket: WebSocket, task_id: str):
    """训练事件流 V2（WebSocket）。"""
    await websocket.accept()
    hub = get_training_event_hub_v2()
    cursor = hub.parse_last_event_id(websocket.query_params.get("last_event_id"))
    task_filter = None if task_id == "all" else task_id

    try:
        while True:
            for event in hub.list_since(cursor, task_id=task_filter):
                cursor = max(cursor, event.sequence)
                await websocket.send_text(json.dumps(event.model_dump(), ensure_ascii=False))

            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                if message == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        return


@router.get("/v2/overview")
async def get_training_overview_v2():
    """训练概览（队列 + 运行中 + 失败摘要 + 资源风险信号）。"""
    ctx = get_training_context()
    state = ctx.state
    queue = ctx.queue
    history = state.get_history()

    failed_records = [record for record in history if record.status == "failed"]
    recent_failed = sorted(
        failed_records,
        key=lambda record: record.start_time,
        reverse=True,
    )[:5]

    suspected_vram_pressure_count = 0
    long_context_failure_count = 0
    unquantized_failure_count = 0
    for record in failed_records:
        cfg = record.config or {}
        batch_size = int(cfg.get("batch_size", cfg.get("batchSize", 1)) or 1)
        max_seq_length = int(cfg.get("max_seq_length", cfg.get("maxSeqLength", 512)) or 512)
        quantization = int(cfg.get("quantization", 4) or 0)
        if batch_size >= 2 or max_seq_length > 1024 or quantization == 0:
            suspected_vram_pressure_count += 1
        if max_seq_length > 1024:
            long_context_failure_count += 1
        if quantization == 0:
            unquantized_failure_count += 1

    return {
        "version": "v2",
        "queue": queue.get_queue_status(),
        "running": {
            "is_training": state.is_training(),
            "record": state.get_current_record().model_dump() if state.get_current_record() else None,
            "progress": state.get_progress().model_dump(),
        },
        "recent_failures": [
            {
                "task_id": record.id,
                "model_name": record.model_name,
                "dataset_name": record.dataset_name,
                "method": record.method,
                "start_time": record.start_time,
            }
            for record in recent_failed
        ],
        "resource_signals": {
            "suspected_vram_pressure_count": suspected_vram_pressure_count,
            "long_context_failure_count": long_context_failure_count,
            "unquantized_failure_count": unquantized_failure_count,
        },
    }


@router.get("/v2/tasks/{task_id}/metrics")
async def get_training_metrics_v2(
    task_id: str,
    cursor: int = Query(default=0, ge=0, description="读取偏移"),
    limit: int = Query(default=200, ge=1, le=1000, description="本次最多返回条数"),
):
    """按游标分页读取训练指标，支持断线后回填。"""
    settings = get_settings()
    output_dir = settings.outputs_dir_resolved / f"train_{task_id[:8]}"
    metrics_file = output_dir / "metrics.jsonl"

    if not metrics_file.exists():
        return {
            "task_id": task_id,
            "cursor": cursor,
            "next_cursor": cursor,
            "has_more": False,
            "items": [],
        }

    items: list[dict[str, Any]] = []
    with open(metrics_file, encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx < cursor:
                continue
            if len(items) >= limit:
                break
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    next_cursor = cursor + len(items)
    has_more = False
    if items:
        with open(metrics_file, encoding="utf-8") as f:
            total = sum(1 for _ in f)
        has_more = next_cursor < total

    return {
        "task_id": task_id,
        "cursor": cursor,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "items": items,
    }


@router.get("/history")
async def get_history():
    """获取训练历史"""
    state = get_training_context().state
    records = state.get_history()
    return [TrainingRecordResponse(**r.model_dump()) for r in records]


@router.websocket("/ws/{task_id}")
async def training_websocket(websocket: WebSocket, task_id: str):
    """训练进度 WebSocket 推送"""
    ws_manager = get_ws_manager()

    await ws_manager.connect(task_id, websocket)

    try:
        while True:
            data = await websocket.receive_text()

            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await ws_manager.disconnect(task_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket 错误：{e}")
        await ws_manager.disconnect(task_id, websocket)


@router.get("/metrics/{task_id}")
async def get_training_metrics(task_id: str):
    """获取训练指标数据（用于图表展示）"""
    settings = get_settings()

    output_dir = settings.outputs_dir_resolved / f"train_{task_id[:8]}"
    metrics_file = output_dir / "metrics.jsonl"

    if not metrics_file.exists():
        return {
            "task_id": task_id,
            "metrics": [],
            "summary": {
                "total_steps": 0,
                "final_loss": 0,
                "elapsed_time": 0
            }
        }

    metrics = []
    try:
        with open(metrics_file, encoding='utf-8') as f:
            for line in f:
                try:
                    metric = json.loads(line.strip())
                    metrics.append(metric)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"读取指标文件失败：{e}")

    summary = {
        "total_steps": metrics[-1]["step"] if metrics else 0,
        "final_loss": metrics[-1].get("loss", 0) if metrics else 0,
        "elapsed_time": metrics[-1].get("elapsed_time", 0) if metrics else 0
    }

    return {
        "task_id": task_id,
        "metrics": metrics,
        "summary": summary
    }


@router.get("/chart-data/{task_id}")
async def get_chart_data(task_id: str):
    """获取图表数据（简化版，直接返回绘图数据）"""
    settings = get_settings()

    output_dir = settings.outputs_dir_resolved / f"train_{task_id[:8]}"
    metrics_file = output_dir / "metrics.jsonl"

    if not metrics_file.exists():
        return {
            "loss_chart": {"labels": [], "data": []},
            "lr_chart": {"labels": [], "data": []},
            "vram_chart": {"labels": [], "data": []}
        }

    labels = []
    loss_data = []
    lr_data = []
    vram_data = []

    try:
        with open(metrics_file, encoding='utf-8') as f:
            for line in f:
                try:
                    metric = json.loads(line.strip())
                    labels.append(metric.get("step", 0))
                    loss_data.append(metric.get("loss", 0))
                    lr_data.append(metric.get("lr", 0))
                    vram_data.append(metric.get("vram_used", 0))
                except Exception:
                    continue
    except Exception as e:
        logger.error(f"读取图表数据失败：{e}")

    return {
        "loss_chart": {
            "labels": labels,
            "data": loss_data,
            "name": "Loss"
        },
        "lr_chart": {
            "labels": labels,
            "data": lr_data,
            "name": "Learning Rate"
        },
        "vram_chart": {
            "labels": labels,
            "data": vram_data,
            "name": "VRAM Usage (GB)"
        }
    }


@router.get("/status")
async def get_status():
    """获取训练状态"""
    state = get_training_context().state
    status = state.get_status()
    latest_event = get_training_event_hub_v2().get_latest()
    if latest_event and isinstance(status, dict):
        progress = status.get("progress")
        if progress is not None:
            status["progress"] = _legacy_progress_from_v2_event(latest_event, progress)
    return status


class SwiftCheckResponse(BaseModel):
    """SWIFT 可用性检查响应"""
    available: bool
    version: str = ""
    message: str = ""


@router.get("/check-swift", response_model=SwiftCheckResponse)
async def check_swift():
    """检查 SWIFT 框架是否可用"""
    from backends.swift_backend import get_swift_backend

    swift_backend = get_swift_backend()

    if swift_backend.is_available():
        return SwiftCheckResponse(
            available=True,
            version=swift_backend.get_version(),
            message="SWIFT 框架已安装"
        )
    else:
        return SwiftCheckResponse(
            available=False,
            message="SWIFT 未安装，请运行：pip install ms-swift -U"
        )


@router.post("/start-swift", response_model=TrainingRecordResponse)
async def start_swift_training(
    config: TrainingConfigInput,
):
    """使用 SWIFT 框架启动训练"""
    from backends.swift_backend import SwiftTrainConfig, get_swift_backend

    settings = get_settings()
    state = get_training_context().state

    swift_backend = get_swift_backend()
    if not swift_backend.is_available():
        raise HTTPException(
            status_code=503,
            detail="SWIFT 框架未安装，请运行：pip install ms-swift -U"
        )

    if state.is_training():
        raise HTTPException(status_code=400, detail="Training already in progress")

    _validate_release_supported_features(config, backend="swift")

    model_path = settings.models_dir_resolved / config.model_id
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Model not found: {config.model_id}")

    dataset_path = settings.datasets_dir_resolved / config.dataset_id
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail=f"Dataset not found: {config.dataset_id}")

    resource_check = pre_training_resource_check(
        required_vram_gb=4.0 if config.method == "qlora" else 8.0,
        method=config.method,
        model_size=config.model_id
    )
    if not resource_check["passed"]:
        logger.warning(f"资源检查未通过：{resource_check.get('warnings', [])}")

    record_id = str(uuid.uuid4())
    output_path = settings.outputs_dir_resolved / f"train_{record_id[:8]}"
    output_path.mkdir(parents=True, exist_ok=True)

    record = TrainingRecord(
        id=record_id,
        model_name=config.model_id,
        dataset_name=config.dataset_id,
        method=f"swift_{config.method}",
        status="running",
        start_time=datetime.now().isoformat(),
        config=config.model_dump(),
        output_path=str(output_path),
        checkpoint_path=None,
    )

    swift_config = SwiftTrainConfig(
        model_id=str(model_path),
        dataset_id=config.dataset_id,
        method=config.method,
        learning_rate=config.learning_rate,
        epochs=config.epochs,
        batch_size=config.batch_size,
        gradient_accumulation=config.gradient_accumulation,
        max_seq_length=config.max_seq_length,
        lora_rank=config.rank,
        lora_alpha=config.alpha,
        lora_dropout=0.05,
        quantization_bit=config.quantization if config.method == "qlora" else 0,
        output_dir=str(output_path),
        save_steps=config.save_steps,
        logging_steps=config.logging_steps,
        warmup_steps=config.warmup_steps,
        warmup_ratio=0.1,
        weight_decay=0.01,
        max_grad_norm=1.0,
        val_size=0.0,
    )

    log_dir = output_path / "logs"
    success = swift_backend.start_training(swift_config, log_dir, record_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to start SWIFT training")

    state.add_to_history(record)

    asyncio.create_task(_monitor_swift_training(record_id, state, record, swift_backend))

    return TrainingRecordResponse(**record.model_dump())


async def _monitor_swift_training(
    task_id: str,
    state: TrainingState,
    record: TrainingRecord,
    swift_backend
):
    """后台监控 SWIFT 训练进度"""

    logger.info(f"开始监控 SWIFT 训练：{task_id}")

    state.queue_training_state(True)
    while True:
        await asyncio.sleep(3)

        status = swift_backend.get_training_status()
        current_status = status.get("status", "unknown")

        if current_status == "idle" or current_status == "unknown":
            logger.warning("SWIFT 后端状态异常")
            continue

        if current_status == "running":
            progress = swift_backend.parse_training_progress()

            if progress.get("step", 0) > 0:
                _queue_training_progress(
                    state,
                    status="running",
                    message=progress.get("message", "SWIFT Training..."),
                    epoch=progress.get("epoch", 0),
                    step=progress.get("step", 0),
                    total_steps=progress.get("total_steps", 0),
                    loss=progress.get("loss", 0.0),
                    lr=progress.get("lr", 0.0),
                    vram_used=get_vram_usage(),
                    elapsed_time=progress.get("elapsed_time", 0.0),
                    eta=0.0,
                )

                try:
                    ws_manager = get_ws_manager()
                    asyncio.create_task(ws_manager.broadcast_progress(task_id, {
                        **progress,
                        "status": "running"
                    }))
                except Exception as e:
                    logger.debug(f"WebSocket 推送失败：{e}")

        elif current_status == "completed":
            logger.info(f"SWIFT 训练完成：{task_id}")

            state.queue_training_state(False)
            _queue_training_progress(
                state,
                status="completed",
                message="SWIFT Training completed",
            )

            record.status = "completed"
            record.end_time = datetime.now().isoformat()
            record.checkpoint_path = str(Path(record.output_path) / "adapter_model")

            try:
                ws_manager = get_ws_manager()
                asyncio.create_task(ws_manager.broadcast_event(task_id, "training_completed", {
                    "framework": "swift",
                    "output_path": record.output_path
                }))
            except Exception as e:
                logger.debug(f"WebSocket 推送失败：{e}")

            state.add_to_history_sync(record)

            swift_backend.cleanup()
            break

        elif current_status == "failed":
            logger.error(f"SWIFT 训练失败：{task_id}, return_code={status.get('return_code')}")

            log_tail = swift_backend.get_log_tail(20)
            error_msg = "\n".join(log_tail) if log_tail else "Unknown error"

            state.queue_training_state(False)
            _queue_training_progress(
                state,
                status="failed",
                message=f"SWIFT Error: {error_msg[:200]}",
            )

            record.status = "failed"
            record.end_time = datetime.now().isoformat()

            try:
                ws_manager = get_ws_manager()
                asyncio.create_task(ws_manager.broadcast_event(task_id, "training_failed", {
                    "framework": "swift",
                    "error": error_msg[:500]
                }))
            except Exception as e:
                logger.debug(f"WebSocket 推送失败：{e}")

            state.add_to_history_sync(record)

            swift_backend.cleanup()
            break

        elif current_status == "stopped":
            logger.info(f"SWIFT 训练已停止：{task_id}")
            break



@router.post("/swift/stop")
async def stop_swift_training():
    """停止 SWIFT 训练"""
    from backends.swift_backend import get_swift_backend

    swift_backend = get_swift_backend()
    status = swift_backend.get_training_status()

    if status.get("status") != "running":
        raise HTTPException(status_code=400, detail="No SWIFT training in progress")

    success = swift_backend.stop_training()

    if success:
        training_state = get_training_context().state
        training_state.queue_training_state(False)
        _queue_training_progress(
            training_state,
            status="stopped",
            message="SWIFT training stopped by user",
        )
        return {"message": "SWIFT training stopped"}
    else:
        raise HTTPException(status_code=500, detail="Failed to stop SWIFT training")


@router.get("/swift/progress")
async def get_swift_progress():
    """获取 SWIFT 训练进度"""
    from backends.swift_backend import get_swift_backend

    swift_backend = get_swift_backend()
    status = swift_backend.get_training_status()
    progress = swift_backend.parse_training_progress()

    return {
        **status,
        **progress
    }


@router.get("/swift/logs/{task_id}")
async def get_swift_logs(task_id: str, lines: int = Query(default=50, ge=1, le=200)):
    """获取 SWIFT 训练日志（末尾 N 行）"""
    from backends.swift_backend import get_swift_backend

    swift_backend = get_swift_backend()
    log_lines = swift_backend.get_log_tail(lines)

    return {
        "task_id": task_id,
        "lines": log_lines,
        "count": len(log_lines)
    }


@router.get("/checkpoints/{task_id}")
async def get_checkpoints(task_id: str):
    """获取任务的检查点列表"""
    state = get_training_context().state
    settings = get_settings()
    return _load_checkpoints_for_task(state, settings, task_id)


@router.get("/recovery/options")
async def get_recovery_options(limit: int = Query(default=6, ge=1, le=20)):
    """聚合可恢复训练任务和检查点，减少前端多次请求拼装。"""
    state = get_training_context().state
    settings = get_settings()

    records = state.get_history()
    candidates = sorted(
        [record for record in records if record.status in ("failed", "stopped")],
        key=lambda item: _safe_parse_time(item.start_time),
        reverse=True,
    )

    options: list[dict[str, Any]] = []
    for record in candidates:
        checkpoints = _load_checkpoints_for_task(state, settings, record.id)
        if not checkpoints:
            continue

        latest_checkpoint = checkpoints[-1]
        config = record.config or {}
        options.append({
            "taskId": record.id,
            "status": record.status,
            "modelName": record.model_name,
            "datasetName": record.dataset_name,
            "startTime": record.start_time,
            "checkpoints": list(reversed(checkpoints)),
            "latestCheckpointName": latest_checkpoint["name"],
            "config": {
                "method": config.get("method", "qlora"),
                "batchSize": config.get("batch_size", config.get("batchSize", 1)),
                "maxSeqLength": config.get("max_seq_length", config.get("maxSeqLength", 512)),
                "gradientAccumulation": config.get("gradient_accumulation", config.get("gradientAccumulation", 16)),
                "quantization": config.get("quantization", 4),
            },
            "reason": "最近一次失败任务存在可恢复检查点"
            if record.status == "failed"
            else "最近一次停止任务存在可恢复检查点",
        })

        if len(options) >= limit:
            break

    return {
        "generatedAt": datetime.now().isoformat(),
        "options": options,
    }


@router.get("/failure/analytics")
async def get_failure_analytics():
    """返回训练失败画像统计，供前端直接展示。"""
    state = get_training_context().state
    records = state.get_history()
    return _build_failure_analytics_payload(records)


@router.post("/resume/{task_id}/{checkpoint_name}")
async def resume_training(task_id: str, checkpoint_name: str):
    """从检查点恢复训练"""
    state = get_training_context().state
    settings = get_settings()

    if state.is_training():
        raise HTTPException(status_code=400, detail="Training already in progress")

    original_record = _get_training_record_by_id(state, task_id)
    if not original_record:
        raise HTTPException(status_code=404, detail="Training record not found")

    output_dir = _resolve_training_output_dir(state, settings, task_id)
    checkpoint_path = output_dir / "checkpoints" / checkpoint_name

    if not checkpoint_path.exists():
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    config_dict = dict(original_record.config)
    config_dict["resume_from_checkpoint"] = str(checkpoint_path)
    config = TrainingConfigInput(**config_dict)
    model_path = settings.models_dir_resolved / config.model_id
    dataset_dir = settings.datasets_dir_resolved / config.dataset_id

    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Model not found: {config.model_id}")
    if not dataset_dir.exists():
        raise HTTPException(status_code=404, detail=f"Dataset not found: {config.dataset_id}")

    dataset_file = None
    for ext in [".json", ".jsonl"]:
        for pattern in [f"{config.dataset_id}{ext}", f"data{ext}", f"*{ext}"]:
            potential_file = dataset_dir / pattern
            if potential_file.exists():
                dataset_file = potential_file
                break
            for f in dataset_dir.glob(pattern):
                dataset_file = f
                break
            if dataset_file:
                break
        if dataset_file:
            break

    if not dataset_file:
        raise HTTPException(status_code=404, detail=f"Dataset file not found in: {config.dataset_id}")

    return _start_training_task(
        config=config,
        state=state,
        settings=settings,
        model_path=model_path,
        dataset_file=dataset_file,
        use_queue=False,
        priority="normal",
    )


@router.post("/check-resources", response_model=ResourceCheckResponse)
async def check_resources(
    method: str = Query(default="qlora", description="微调方法"),
    model_size: str = Query(default="7B", description="模型大小估计"),
    required_vram: float = Query(default=6.0, description="预计需要显存(GB)")
):
    """检查训练资源 - 在开始训练前检查系统资源，并提供智能降级建议
    """
    result = pre_training_resource_check(
        required_vram_gb=required_vram,
        method=method,
        model_size=model_size
    )

    return ResourceCheckResponse(**result)


class QueueTaskResponse(BaseModel):
    """队列任务响应"""
    task_id: str
    status: str
    priority: str
    queued_at: str
    message: str


class ValidationResult(BaseModel):
    """训练验证结果"""
    passed: bool = True
    errors: list[str] = []
    warnings: list[str] = []


class TrainingValidator:
    """训练验证器"""

    @staticmethod
    async def validate_config(config: TrainingConfigInput, settings: Settings) -> ValidationResult:
        """验证训练配置"""
        result = ValidationResult()

        TrainingValidator._validate_resources(config, result)

        await TrainingValidator._validate_dataset(config, settings, result)

        await TrainingValidator._validate_model(config, settings, result)

        TrainingValidator._validate_parameters(config, result)

        return result

    @staticmethod
    def _validate_resources(config: TrainingConfigInput, result: ValidationResult):
        """资源验证"""
        try:
            import torch

            if not torch.cuda.is_available():
                result.errors.append("CUDA 不可用，无法进行 GPU 训练")
                return

            estimated_vram = TrainingValidator._estimate_vram(
                config.model_id,
                config.method,
                config.batch_size,
                config.max_seq_length
            )

            available_vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            allocated_vram = torch.cuda.memory_allocated(0) / (1024 ** 3)
            free_vram = available_vram - allocated_vram

            if free_vram < estimated_vram * 0.9:
                result.warnings.append(
                    f"预计需要 {estimated_vram:.1f}GB VRAM, 可用 {free_vram:.1f}GB"
                )
        except Exception as e:
            result.warnings.append(f"资源检查失败：{e}")

    @staticmethod
    def _estimate_vram(model_id: str, method: str, batch_size: int, max_seq_length: int) -> float:
        """估算 VRAM 需求"""
        if "13B" in model_id or "14B" in model_id:
            base_vram = 8.0
        elif "7B" in model_id or "8B" in model_id:
            base_vram = 4.0
        elif "3B" in model_id:
            base_vram = 2.0
        else:
            base_vram = 4.0

        if method == "qlora" or (hasattr(method, 'lower') and 'qlora' in method.lower()):
            base_vram *= 0.6

        if batch_size > 4:
            base_vram *= 1.2

        if max_seq_length > 1024:
            base_vram *= 1.3

        return base_vram

    @staticmethod
    async def _validate_dataset(config: TrainingConfigInput, settings: Settings, result: ValidationResult):
        """数据集验证"""
        try:
            dataset_path = settings.datasets_dir_resolved / config.dataset_id

            if not dataset_path.exists():
                result.errors.append(f"数据集不存在：{config.dataset_id}")
                return

            dataset_file = None
            for ext in [".json", ".jsonl"]:
                for f in dataset_path.glob(f"*{ext}"):
                    dataset_file = f
                    break
                if dataset_file:
                    break

            if not dataset_file:
                result.errors.append("不支持的数据集格式，需要 .json 或 .jsonl")
                return

            import json
            with open(dataset_file, encoding='utf-8') as f:
                content = f.read()
                try:
                    data = json.loads(content)

                    if isinstance(data, list) and len(data) > 0:
                        first_item = data[0]
                        try:
                            detect_dataset_sample_format(first_item)
                        except ValueError as e:
                            result.errors.append(str(e))
                    elif isinstance(data, list):
                        result.errors.append("数据集至少需要包含一条样本")
                    elif isinstance(data, dict):
                        try:
                            detect_dataset_sample_format(data)
                        except ValueError as e:
                            result.errors.append(str(e))
                    else:
                        result.errors.append("数据集根节点必须是 JSON 对象或对象数组")
                except json.JSONDecodeError as e:
                    result.errors.append(f"JSON 格式错误：{e}")
        except Exception as e:
            result.errors.append(f"数据集验证失败：{e}")

    @staticmethod
    async def _validate_model(config: TrainingConfigInput, settings: Settings, result: ValidationResult):
        """模型验证"""
        try:
            model_path = settings.models_dir_resolved / config.model_id

            if not model_path.exists():
                result.errors.append(f"模型不存在：{config.model_id}")
                return

            config_file = model_path / "config.json"
            if config_file.exists():
                import json
                with open(config_file) as f:
                    model_config = json.load(f)

                model_type = model_config.get("model_type", "")
                supported_types = ["llama", "mistral", "gemma", "qwen", "chatglm", "baichuan"]
                if model_type and model_type not in supported_types:
                    result.warnings.append(
                        f"模型类型 '{model_type}' 可能不受支持，已知支持：{supported_types}"
                    )
        except Exception as e:
            result.warnings.append(f"模型验证失败：{e}")

    @staticmethod
    def _validate_parameters(config: TrainingConfigInput, result: ValidationResult):
        """参数合理性验证"""
        if not (1e-6 <= config.learning_rate <= 1e-3):
            result.warnings.append(
                f"学习率 {config.learning_rate} 可能不合理，推荐范围 1e-6 ~ 1e-3"
            )

        effective_batch = config.batch_size * config.gradient_accumulation
        if effective_batch < 4:
            result.warnings.append(
                f"有效批次大小 {effective_batch} 过小，可能影响训练稳定性"
            )
        elif effective_batch > 128:
            result.warnings.append(
                f"有效批次大小 {effective_batch} 过大，可能导致 OOM"
            )

        if config.rank > 64:
            result.warnings.append(
                f"LoRA rank={config.rank} 较高，可能导致过拟合"
            )

        if config.epochs > 10:
            result.warnings.append(
                f"训练轮数 {config.epochs} 较多，注意过拟合风险"
            )


def _start_training_task(
    config: TrainingConfigInput,
    state: TrainingState,
    settings: Settings,
    model_path: Path,
    dataset_file: Path,
    use_queue: bool,
    priority: str,
    record_id: str | None = None,
    output_path: Path | None = None,
) -> TrainingRecordResponse:
    """Internal helper to start or resume a training task with stable identifiers."""
    record_id = record_id or str(uuid.uuid4())
    output_path = output_path or (settings.outputs_dir_resolved / f"train_{record_id[:8]}")
    output_path.mkdir(parents=True, exist_ok=True)

    record = TrainingRecord(
        id=record_id,
        model_name=config.model_id,
        dataset_name=config.dataset_id,
        method=config.method,
        status="queued" if use_queue else "running",
        start_time=datetime.now().isoformat(),
        config=config.model_dump(),
        output_path=str(output_path),
        checkpoint_path=None,
    )

    state.set_current_record(record)
    config.output_path = str(output_path)
    hub_v2 = get_training_event_hub_v2()

    try:
        event_loop = asyncio.get_running_loop()
    except RuntimeError:
        event_loop = None

    def run_training():
        training_thread(
            config,
            str(model_path),
            str(dataset_file),
            state,
            record,
            event_loop=event_loop,
            task_id=record_id,
        )

    if use_queue:
        priority_map = {
            "urgent": TaskPriority.URGENT,
            "high": TaskPriority.HIGH,
            "normal": TaskPriority.NORMAL,
            "low": TaskPriority.LOW,
        }
        task_priority = priority_map.get(priority.lower(), TaskPriority.NORMAL)

        queue = get_training_context().queue
        success = queue.submit(
            task_id=record_id,
            config=config,
            callback=run_training,
            priority=task_priority
        )

        if not success:
            raise HTTPException(status_code=503, detail="Task queue is full")

        queue_status = queue.get_queue_status()
        queue_position = max(1, int(queue_status.get("queue_size", 1)))
        estimated_wait_seconds = max(0, queue_position - 1) * 60
        hub_v2.publish(
            task_id=record_id,
            phase="queued",
            kind="task_queued",
            payload={
                "priority": task_priority.name.lower(),
                "queue_position": queue_position,
                "estimated_wait_seconds": estimated_wait_seconds,
                "status": "queued",
                "message": f"Task queued at position {queue_position}",
            },
        )
        logger.info(f"训练任务已加入队列：{record_id}")
        return TrainingRecordResponse(**record.model_dump())

    thread = threading.Thread(
        target=run_training,
        daemon=True
    )
    state.register_training_task(record_id, thread)
    thread.start()
    hub_v2.publish(
        task_id=record_id,
        phase="loading",
        kind="task_started",
        payload={
            "status": "loading",
            "message": "Training task started and preparing runtime",
        },
    )

    logger.info(f"训练任务已启动：{record_id}")
    return TrainingRecordResponse(**record.model_dump())


@router.post("/start", response_model=TrainingRecordResponse)
async def start_training(
    config: TrainingConfigInput,
    skip_resource_check: bool = False,
    use_queue: bool = False,
    priority: str = "normal",
    apply_recommended_config: bool = False,
):
    """开始训练

    Args:
        config: 训练配置
        skip_resource_check: 是否跳过资源检查
        use_queue: 是否使用队列模式
        priority: 任务优先级(urgent/high/normal/low)
    """
    settings = get_settings()
    state = get_training_context().state

    if state.is_training():
        raise HTTPException(status_code=400, detail="Training already in progress")

    _validate_release_supported_features(config)

    model_path = settings.models_dir_resolved / config.model_id
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Model not found: {config.model_id}")

    dataset_path = settings.datasets_dir_resolved / config.dataset_id
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail=f"Dataset not found: {config.dataset_id}")

    dataset_file = None
    for ext in [".json", ".jsonl"]:
        for pattern in [f"{config.dataset_id}{ext}", f"data{ext}", f"*{ext}"]:
            potential_file = dataset_path / pattern
            if potential_file.exists():
                dataset_file = potential_file
                break
            for f in dataset_path.glob(pattern):
                dataset_file = f
                break
            if dataset_file:
                break
        if dataset_file:
            break

    if not dataset_file:
        raise HTTPException(status_code=404, detail=f"Dataset file not found in: {config.dataset_id}")

    config = _apply_memory_preset(config)

    config = _apply_precision_preset(config)

    if not skip_resource_check:
        validation_result = await TrainingValidator.validate_config(config, settings)

        for warning in validation_result.warnings:
            logger.warning(f"验证警告：{warning}")
        for error in validation_result.errors:
            logger.error(f"验证错误：{error}")

        if validation_result.errors:
            raise HTTPException(
                status_code=400,
                detail=f"配置验证失败：{'; '.join(validation_result.errors)}"
            )

        model_size_gb = 4.0
        if "13B" in config.model_id or "14B" in config.model_id:
            model_size_gb = 8.0
        elif "3B" in config.model_id:
            model_size_gb = 2.0
        elif "1.5B" in config.model_id or "1B" in config.model_id:
            model_size_gb = 1.0

        if config.method == "qlora" and config.quantization == 4:
            model_size_gb *= 0.6

        resource_check = pre_training_resource_check(
            required_vram_gb=model_size_gb,
            method=config.method,
            model_size=config.model_id
        )

        for warning in resource_check.get("warnings", []):
            logger.warning(f"资源检查警告：{warning}")

        if not resource_check["passed"] and resource_check["recommended_config"]:
            if not apply_recommended_config:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "resource_check_failed",
                        "message": "Resource check failed, recommended config available",
                        "recommended_config": resource_check["recommended_config"],
                        "warnings": resource_check.get("warnings", []),
                    },
                )
            recommended = resource_check["recommended_config"]
            logger.info(f"应用推荐配置：{recommended}")

            if "method" in recommended:
                config.method = recommended["method"]
            if "quantization" in recommended:
                config.quantization = recommended["quantization"]
            if "batch_size" in recommended:
                config.batch_size = recommended["batch_size"]
            if "max_seq_length" in recommended:
                config.max_seq_length = recommended["max_seq_length"]

    return _start_training_task(
        config=config,
        state=state,
        settings=settings,
        model_path=model_path,
        dataset_file=dataset_file,
        use_queue=use_queue,
        priority=priority,
    )


@router.get("/queue/status")
async def get_queue_status():
    """获取任务队列状态"""
    queue = get_training_context().queue
    return queue.get_queue_status()


@router.get("/queue/task/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态"""
    queue = get_training_context().queue
    status = queue.get_task_status(task_id)

    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return status


@router.post("/queue/cancel/{task_id}")
async def cancel_task(task_id: str):
    """取消队列中的任务"""
    ctx = get_training_context()
    queue = ctx.queue
    state = ctx.state

    if queue.cancel(task_id):
        hub = get_training_event_hub_v2()
        current_record = state.get_current_record()
        if current_record and current_record.id == task_id and state.is_training():
            state.request_stop()
            _queue_training_progress(
                state,
                status="stopping",
                message="Training cancellation requested by user",
            )
            hub.publish(
                task_id=task_id,
                phase="stopping",
                kind="task_cancellation_requested",
                payload={
                    "status": "stopping",
                    "message": "Training cancellation requested by user",
                },
            )
        else:
            hub.publish(
                task_id=task_id,
                phase="stopped",
                kind="task_cancelled",
                payload={
                    "status": "stopped",
                    "message": "Queued task cancelled by user",
                    "stop_reason": "user_cancelled_before_start",
                },
            )
        return {"message": f"Task {task_id} cancelled"}

    raise HTTPException(status_code=400, detail="Task not found or already running")

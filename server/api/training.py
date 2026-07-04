"""
训练管理 API - 路由层（重构版）

阶段一重构后，本文件仅保留：
- FastAPI 路由定义
- Pydantic 请求/响应模型（从新模块 re-export）
- WebSocket 管理器
- 请求参数校验与路由转发

业务逻辑已下沉至：
- training_engine/   模型加载、数据集处理、回调、训练线程
- services/training/ 验证、编排、报告
"""
import asyncio
import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from services.training.orchestrator import resolve_dataset_file, start_training_task
from services.training.validator import (
    TrainingValidator,
    estimate_preflight_required_vram,
    preflight_check,
    validate_release_supported_features,
)
from training_engine.callbacks import ProgressCallback
from training_engine.callbacks import queue_training_progress as _base_queue_training_progress
from training_engine.checkpoint_manager import _get_training_record_by_id, load_checkpoints_for_task
from training_engine.checkpoint_manager import (
    _resolve_training_output_dir as resolve_training_output_dir,
)
from training_engine.config_builder import (
    apply_memory_preset,
    apply_precision_preset,
    estimate_training_total_steps,
)
from training_engine.dataset_formatter import detect_dataset_sample_format
from training_engine.dataset_loader import load_dataset, split_train_test_dataset
from training_engine.errors import RecoverableError, UnrecoverableError
from training_engine.reporter import (
    _safe_parse_time,
    build_failure_analytics_payload,
    enrich_record_metrics,
    sync_training_record_metadata,
)

# === 从下沉模块导入业务逻辑，并在底部 re-export 以兼容测试 ===
from training_engine.schemas import (
    TRAINING_PROGRESS_STATUS_VALUES,
    QueueTaskResponse,
    ResourceCheckResponse,
    SwiftCheckResponse,
    TrainingConfigInput,
    TrainingPreflightCheck,
    TrainingPreflightResponse,
    TrainingProgressResponse,
    TrainingProgressStatus,
    TrainingRecordResponse,
    ValidationResult,
)
from training_engine.training_thread import finalize_stop_requested, handle_training_failure

from core.config import get_settings
from core.logging import get_logger
from core.training_context import get_training_context
from core.training_events_v2 import get_training_event_hub_v2
from core.training_state import TrainingRecord, TrainingState
from core.utils import pre_training_resource_check


def _load_checkpoints_for_task(state, settings, task_id):
    return load_checkpoints_for_task(state, settings, task_id)


logger = get_logger(__name__)

router = APIRouter()


def _worker_mode() -> bool:
    return getattr(get_settings(), "training_execution_mode", "in_process") == "worker"


def _training_job_repository():
    from training_worker.repository import get_training_job_repository

    return get_training_job_repository()


def _worker_progress(task_id: str | None = None) -> TrainingProgressResponse:
    repository = _training_job_repository()
    job = repository.get_job(task_id) if task_id else repository.active_job()
    if job is None and task_id is None:
        jobs = repository.list_jobs(limit=1)
        job = jobs[0] if jobs else None
    event = repository.latest_event(job.job_id) if job else None
    payload = dict(event.payload) if event else {}
    status = payload.get("status") or (job.status if job else "idle")
    if status == "running":
        status = "training"
    if status in {"leased", "queued"}:
        status = "loading"
    defaults = {
        "epoch": 0,
        "step": 0,
        "total_steps": 0,
        "loss": 0.0,
        "lr": 0.0,
        "vram_used": 0.0,
        "elapsed_time": 0.0,
        "eta": 0.0,
        "status": status,
        "message": payload.get("message") or (f"Training job {job.status}" if job else ""),
    }
    for field in TrainingProgressResponse.model_fields:
        if field in payload:
            defaults[field] = payload[field]
    return TrainingProgressResponse(**defaults)


def _training_records() -> list[TrainingRecord]:
    from services.training.records import list_training_records

    return list_training_records()


def _training_output_dir(task_id: str, state=None) -> Path:
    if _worker_mode():
        job = _training_job_repository().get_job(task_id)
        if job:
            return Path(job.output_path)
    state = state or get_training_context().state
    return resolve_training_output_dir(state, get_settings(), task_id)


def _config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config or {}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_resume_identity(
    *,
    original_record: TrainingRecord,
    config_dict: dict[str, Any],
    checkpoint_path: Path,
) -> list[str]:
    """Validate semantic identity for checkpoint resume when metadata is available."""
    warnings: list[str] = []
    metadata_path = checkpoint_path / "checkpoint_metadata.json"
    if not metadata_path.exists():
        warnings.append("checkpoint_metadata.json 不存在，已按旧检查点兼容路径恢复；无法强校验模型/数据集/配置版本")
        return warnings

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Checkpoint metadata is unreadable: {exc}") from exc

    expected_model = (
        getattr(original_record, "base_model_id", None)
        or config_dict.get("model_id")
        or config_dict.get("modelId")
        or original_record.model_name
    )
    expected_dataset = (
        getattr(original_record, "dataset_id", None)
        or config_dict.get("dataset_id")
        or config_dict.get("datasetId")
        or original_record.dataset_name
    )
    metadata_model = metadata.get("base_model_id") or metadata.get("model_id") or metadata.get("model")
    metadata_dataset = metadata.get("dataset_id") or metadata.get("dataset")
    metadata_config_hash = metadata.get("config_hash")

    mismatches = []
    if metadata_model and expected_model and metadata_model != expected_model:
        mismatches.append(f"base model mismatch: checkpoint={metadata_model}, record={expected_model}")
    if metadata_dataset and expected_dataset and metadata_dataset != expected_dataset:
        mismatches.append(f"dataset mismatch: checkpoint={metadata_dataset}, record={expected_dataset}")
    record_config_hash = getattr(original_record, "config_hash", None) or _config_hash(original_record.config or {})
    current_config_hash = _config_hash(config_dict)
    if metadata_config_hash and metadata_config_hash not in {record_config_hash, current_config_hash}:
        mismatches.append("training config hash mismatch")

    if mismatches:
        raise HTTPException(status_code=400, detail="Checkpoint identity validation failed: " + "; ".join(mismatches))
    return warnings


# ============================================================================
# 路由定义
# ============================================================================
@router.post("/stop")
async def stop_training():
    """停止训练"""
    from core.training_gateway import get_training_gateway

    try:
        return await get_training_gateway().stop()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/progress", response_model=TrainingProgressResponse)
async def get_progress():
    """获取训练进度"""
    from training_engine.schemas import TrainingProgressResponse

    from core.training_gateway import get_training_gateway

    gateway = get_training_gateway()
    progress = gateway.get_progress()
    if isinstance(progress, dict):
        return TrainingProgressResponse(**progress)
    return progress


@router.get("/progress/stream")
async def progress_stream(
    timeout: int = Query(default=300, ge=30, le=3600),
    heartbeat: int = Query(default=30, ge=10, le=120)
):
    """SSE 进度流"""
    from core.training_gateway import get_training_gateway

    gateway = get_training_gateway()

    async def event_generator():
        async for chunk in gateway.progress_stream(timeout=timeout, heartbeat=heartbeat):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/v2/events/stream")
async def stream_training_events_v2(
    task_id: str | None = Query(default=None),
    last_event_id: str | None = Query(default=None),
    sse_last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    timeout: int = Query(default=300, ge=30, le=3600),
    heartbeat: int = Query(default=15, ge=5, le=120),
):
    """训练事件流 V2（SSE）"""
    import time
    hub = get_training_event_hub_v2()
    start_seq = hub.parse_last_event_id(last_event_id or sse_last_event_id)

    async def event_generator():
        connection_start = time.time()
        last_heartbeat = time.time()
        cursor = start_seq

        try:
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
                    heartbeat_payload = json.dumps({
                        "version": "v2",
                        "kind": "heartbeat",
                        "sequence": hub.current_sequence(),
                        "ts": datetime.now().isoformat(),
                    }, ensure_ascii=False)
                    yield f"event: heartbeat\ndata: {heartbeat_payload}\n\n"
                    last_heartbeat = now
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"V2 SSE 错误：{e}")
            yield 'event: error\ndata: {"message": "Stream error"}\n\n'

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
    """训练事件流 V2（WebSocket）"""
    await websocket.accept()
    hub = get_training_event_hub_v2()
    cursor = hub.parse_last_event_id(websocket.query_params.get("last_event_id"))
    task_filter = None if task_id == "all" else task_id

    CONNECTION_TIMEOUT = 300
    HEARTBEAT_INTERVAL = 30
    connection_start = asyncio.get_event_loop().time()
    last_heartbeat = asyncio.get_event_loop().time()

    try:
        while True:
            now = asyncio.get_event_loop().time()
            if now - connection_start > CONNECTION_TIMEOUT:
                await websocket.send_text(json.dumps({"type": "timeout", "message": "Connection timeout"}))
                break

            for event in hub.list_since(cursor, task_id=task_filter):
                cursor = max(cursor, event.sequence)
                await websocket.send_text(json.dumps(event.model_dump(), ensure_ascii=False))

            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                await websocket.send_text(json.dumps({"type": "ping", "ts": now}))
                last_heartbeat = now

            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                if message == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                connection_start = now  # 重置超时
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        return
    except Exception as e:
        logger.debug(f"V2 WebSocket 错误：{e}")
        return


@router.get("/v2/overview")
async def get_training_overview_v2():
    """训练概览"""
    if _worker_mode():
        repository = _training_job_repository()
        active = repository.active_job()
        history = _training_records()
        queue_payload = repository.queue_status()
        running_payload = {
            "is_training": active is not None,
            "record": active.record if active else None,
            "progress": _worker_progress(active.job_id if active else None).model_dump(),
        }
    else:
        ctx = get_training_context()
        state = ctx.state
        queue = ctx.queue
        history = state.get_history()
        queue_payload = queue.get_queue_status()
        running_payload = {
            "is_training": state.is_training(),
            "record": state.get_current_record().model_dump() if state.get_current_record() else None,
            "progress": state.get_progress().model_dump(),
        }

    failed_records = [record for record in history if record.status == "failed"]
    recent_failed = sorted(failed_records, key=lambda record: record.start_time, reverse=True)[:5]

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
        "queue": queue_payload,
        "running": running_payload,
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
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
):
    """按游标分页读取训练指标"""
    settings = get_settings()
    output_dir = settings.outputs_dir_resolved / f"train_{task_id[:8]}"
    metrics_file = output_dir / "metrics.jsonl"

    if not metrics_file.exists():
        return {"task_id": task_id, "cursor": cursor, "next_cursor": cursor, "has_more": False, "items": []}

    items: list[dict[str, Any]] = []
    total = 0
    with open(metrics_file, encoding="utf-8") as f:
        for idx, line in enumerate(f):
            total = idx + 1
            if idx < cursor:
                continue
            if len(items) >= limit:
                continue  # 继续计数但不收集
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    next_cursor = cursor + len(items)
    has_more = next_cursor < total

    return {"task_id": task_id, "cursor": cursor, "next_cursor": next_cursor, "has_more": has_more, "items": items}


@router.get("/history")
async def get_history():
    """获取训练历史"""
    from core.training_gateway import get_training_gateway

    gateway = get_training_gateway()
    records = gateway.get_history()
    enriched = [enrich_record_metrics(r) for r in records]
    return [TrainingRecordResponse(**r.model_dump()) for r in enriched]


@router.get("/status")
async def get_status():
    """获取训练状态"""
    from training_engine.reporter import legacy_progress_from_v2_event

    from core.training_events_v2 import get_training_event_hub_v2
    from core.training_gateway import get_training_gateway

    gateway = get_training_gateway()
    status = gateway.get_status()
    if isinstance(status, dict) and "status" not in status:
        progress_status = (status.get("progress") or {}).get("status") if isinstance(status.get("progress"), dict) else None
        status["status"] = progress_status or ("running" if status.get("is_training") else "idle")
    latest_event = get_training_event_hub_v2().get_latest()
    if latest_event and isinstance(status, dict):
        progress = status.get("progress")
        if progress is not None:
            status["progress"] = legacy_progress_from_v2_event(latest_event, progress)
    return status


@router.get("/check-swift", response_model=SwiftCheckResponse)
async def check_swift():
    """检查 SWIFT 框架是否可用"""
    from backends.swift_backend import get_swift_backend
    swift_backend = get_swift_backend()
    if swift_backend.is_available():
        return SwiftCheckResponse(available=True, version=swift_backend.get_version(), message="SWIFT 框架已安装")
    return SwiftCheckResponse(available=False, message="SWIFT 未安装，请运行：pip install ms-swift -U")


@router.post("/start-swift", response_model=TrainingRecordResponse)
async def start_swift_training(config: TrainingConfigInput):
    """使用 SWIFT 框架启动训练（保持原有逻辑）"""
    from backends.swift_backend import SwiftTrainConfig, get_swift_backend

    settings = get_settings()
    state = get_training_context().state

    swift_backend = get_swift_backend()
    if not swift_backend.is_available():
        raise HTTPException(status_code=503, detail="SWIFT 框架未安装，请运行：pip install ms-swift -U")

    if state.is_training():
        raise HTTPException(status_code=400, detail="Training already in progress")

    validate_release_supported_features(config, backend="swift")

    model_path = settings.models_dir_resolved / config.model_id
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Model not found: {config.model_id}")

    dataset_path = settings.datasets_dir_resolved / config.dataset_id
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail=f"Dataset not found: {config.dataset_id}")
    dataset_file = resolve_dataset_file(settings, config.dataset_id)
    if not dataset_file:
        raise HTTPException(status_code=404, detail=f"Dataset file not found in: {config.dataset_id}")

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
    from training_engine.dataset_loader import write_evaluation_snapshot

    evaluation_snapshot_path, evaluation_snapshot_hash = write_evaluation_snapshot(
        str(dataset_file),
        output_path,
    )

    record = TrainingRecord(
        id=record_id,
        model_name=config.model_id,
        dataset_name=config.dataset_id,
        base_model_id=config.model_id,
        dataset_id=config.dataset_id,
        task_goal=config.task_goal,
        method=f"swift_{config.method}",
        status="running",
        start_time=datetime.now().isoformat(),
        config=config.model_dump(),
        output_path=str(output_path),
        adapter_path=None,
        checkpoint_path=None,
        evaluation_snapshot_path=evaluation_snapshot_path,
        evaluation_snapshot_hash=evaluation_snapshot_hash,
    )
    sync_training_record_metadata(record)

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
    if not state.try_claim_training_slot():
        raise HTTPException(status_code=400, detail="Training already in progress")
    try:
        success = swift_backend.start_training(swift_config, log_dir, record_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to start SWIFT training")
        state.add_to_history_sync(record)
        asyncio.create_task(_monitor_swift_training(record_id, state, record, swift_backend))
        return TrainingRecordResponse(**record.model_dump())
    except Exception:
        state.queue_training_state(False)
        raise


async def _monitor_swift_training(
    task_id: str,
    state: TrainingState,
    record: TrainingRecord,
    swift_backend
):
    """后台监控 SWIFT 训练进度（保持原有逻辑）"""
    logger.info(f"开始监控 SWIFT 训练：{task_id}")
    state.queue_training_state(True)
    last_progress: dict[str, Any] = {}
    max_idle_retries = 20  # 60 秒无响应退出
    idle_count = 0
    while True:
        await asyncio.sleep(3)
        status = swift_backend.get_training_status()
        current_status = status.get("status", "unknown")

        if current_status == "idle" or current_status == "unknown":
            idle_count += 1
            if idle_count >= max_idle_retries:
                logger.error("SWIFT 后端无响应，退出监控")
                state.queue_training_state(False)
                record.status = "failed"
                record.end_time = datetime.now().isoformat()
                record.final_loss = float(last_progress.get("loss", 0.0))
                record.final_lr = float(last_progress.get("lr", 0.0))
                record.elapsed_time = float(last_progress.get("elapsed_time", 0.0))
                record.total_steps = int(last_progress.get("step", 0))
                sync_training_record_metadata(record)
                enrich_record_metrics(record)
                state.add_to_history_sync(record)
                swift_backend.cleanup()
                break
            logger.warning(f"SWIFT 后端状态异常（{idle_count}/{max_idle_retries}）")
            continue
        idle_count = 0

        if current_status == "running":
            progress = swift_backend.parse_training_progress()
            if isinstance(progress, dict) and progress:
                last_progress = progress
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
                    vram_used=0.0,
                    elapsed_time=progress.get("elapsed_time", 0.0),
                    eta=0.0,
                )

        elif current_status == "completed":
            logger.info(f"SWIFT 训练完成：{task_id}")
            state.queue_training_state(False)
            _queue_training_progress(state, status="completed", message="SWIFT Training completed")
            record.status = "completed"
            record.end_time = datetime.now().isoformat()
            record.checkpoint_path = str(Path(record.output_path) / "adapter_model")
            record.adapter_path = record.checkpoint_path
            record.final_loss = float(last_progress.get("loss", 0.0))
            record.final_lr = float(last_progress.get("lr", 0.0))
            record.elapsed_time = float(last_progress.get("elapsed_time", 0.0))
            record.total_steps = int(last_progress.get("step", 0))
            sync_training_record_metadata(record)
            enrich_record_metrics(record)
            state.add_to_history_sync(record)
            swift_backend.cleanup()
            break

        elif current_status == "failed":
            logger.error(f"SWIFT 训练失败：{task_id}, return_code={status.get('return_code')}")
            log_tail = swift_backend.get_log_tail(20)
            error_msg = "\n".join(log_tail) if log_tail else "Unknown error"
            state.queue_training_state(False)
            _queue_training_progress(state, status="failed", message=f"SWIFT Error: {error_msg[:200]}")
            record.status = "failed"
            record.end_time = datetime.now().isoformat()
            record.final_loss = float(last_progress.get("loss", 0.0))
            record.final_lr = float(last_progress.get("lr", 0.0))
            record.elapsed_time = float(last_progress.get("elapsed_time", 0.0))
            record.total_steps = int(last_progress.get("step", 0))
            sync_training_record_metadata(record)
            enrich_record_metrics(record)
            state.add_to_history_sync(record)
            swift_backend.cleanup()
            break

        elif current_status == "stopped":
            logger.info(f"SWIFT 训练已停止：{task_id}")
            break


@router.get("/checkpoints/{task_id}")
async def get_checkpoints(task_id: str):
    """获取任务的检查点列表"""
    state = get_training_context().state
    settings = get_settings()
    if _worker_mode():
        checkpoint_dir = _training_output_dir(task_id, state) / "checkpoints"
        if not checkpoint_dir.exists():
            return []
    return load_checkpoints_for_task(state, settings, task_id)


@router.delete("/checkpoints/{task_id}/cleanup")
async def cleanup_checkpoints(task_id: str):
    """清理任务的无效检查点"""
    from training_engine.checkpoint_manager import cleanup_invalid_checkpoints

    state = get_training_context().state
    settings = get_settings()
    result = cleanup_invalid_checkpoints(state, settings, task_id)
    return {"task_id": task_id, **result}


@router.post("/checkpoints/compare")
async def compare_checkpoints_endpoint(payload: dict[str, Any] = Body(...)):
    """对比多个检查点的元数据"""
    from training_engine.checkpoint_manager import compare_checkpoints

    checkpoints = payload.get("checkpoints", [])
    if not checkpoints:
        raise HTTPException(status_code=400, detail="checkpoints 不能为空")
    result = compare_checkpoints(checkpoints)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/recovery/options")
async def get_recovery_options(limit: int = Query(default=6, ge=1, le=20)):
    """聚合可恢复训练任务和检查点"""
    state = get_training_context().state
    settings = get_settings()

    records = _training_records() if _worker_mode() else state.get_history()
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
        resumable_checkpoints = [
            cp for cp in checkpoints
            if cp.get("valid", True) and "recovery-exception" not in cp.get("name", "")
        ]
        all_resumable = resumable_checkpoints or [
            cp for cp in checkpoints if cp.get("valid", True)
        ]
        if not all_resumable:
            continue
        latest_checkpoint = all_resumable[-1]
        config = record.config or {}
        options.append({
            "taskId": record.id,
            "status": record.status,
            "modelName": record.model_name,
            "datasetName": record.dataset_name,
            "startTime": record.start_time,
            "checkpoints": list(reversed(all_resumable)),
            "latestCheckpointName": latest_checkpoint["name"],
            "config": {
                "method": config.get("method", "qlora"),
                "batchSize": config.get("batch_size", config.get("batchSize", 1)),
                "maxSeqLength": config.get("max_seq_length", config.get("maxSeqLength", 512)),
                "gradientAccumulation": config.get("gradient_accumulation", config.get("gradientAccumulation", 16)),
                "quantization": config.get("quantization", 4),
            },
            "reason": (
                "最近一次失败任务存在可恢复检查点"
                if record.status == "failed"
                else "最近一次停止任务存在可恢复检查点"
            ),
        })
        if len(options) >= limit:
            break

    return {"generatedAt": datetime.now().isoformat(), "options": options}


@router.get("/failure/analytics")
async def get_failure_analytics():
    """返回训练失败画像统计"""
    state = get_training_context().state
    records = _training_records() if _worker_mode() else state.get_history()
    return build_failure_analytics_payload(records)


@router.get("/logs/stream/{task_id}")
async def stream_training_logs(task_id: str, history: int = Query(default=50, ge=0, le=500)):
    """SSE 流式传输训练日志"""
    if _worker_mode():
        repository = _training_job_repository()

        async def durable_log_generator():
            cursor = 0
            if history > 0:
                initial = repository.recent_logs(task_id, limit=history)
                if initial:
                    cursor = int(initial[-1]["sequence"])
                    yield f"data: {json.dumps({'lines': [item['message'] for item in initial]}, ensure_ascii=False)}\n\n"
            heartbeat_counter = 0
            while True:
                await asyncio.sleep(0.2)
                rows = repository.list_logs(task_id, after_sequence=cursor)
                if rows:
                    cursor = int(rows[-1]["sequence"])
                    yield f"data: {json.dumps({'lines': [item['message'] for item in rows]}, ensure_ascii=False)}\n\n"
                heartbeat_counter += 1
                if heartbeat_counter >= 25:
                    heartbeat_counter = 0
                    yield ": keepalive\n\n"

        return StreamingResponse(
            durable_log_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    state = get_training_context().state
    log_path = _training_output_dir(task_id, state) / "training.log"

    async def log_generator():
        try:
            # 发送历史行（批量发送，减少 SSE 消息数）
            if log_path.exists() and history > 0:
                try:
                    with open(log_path, encoding="utf-8") as f:
                        lines = f.readlines()
                    tail = lines[-history:]
                    if tail:
                        yield f"data: {json.dumps({'lines': [line.rstrip() for line in tail]})}\n\n"
                except Exception:
                    pass

            # 流式跟踪新增行（200ms 轮询 + 每 5s 心跳保活）
            last_size = log_path.stat().st_size if log_path.exists() else 0
            heartbeat_counter = 0
            while True:
                await asyncio.sleep(0.2)
                heartbeat_counter += 1
                # 每 5 秒发送 SSE 注释作为 keep-alive
                if heartbeat_counter >= 25:
                    heartbeat_counter = 0
                    yield ": keepalive\n\n"
                if not log_path.exists():
                    continue
                try:
                    current_size = log_path.stat().st_size
                    if current_size > last_size:
                        with open(log_path, encoding="utf-8") as f:
                            f.seek(last_size)
                            new_data = f.read()
                        last_size = current_size
                        new_lines = new_data.splitlines()
                        if new_lines:
                            yield f"data: {json.dumps({'lines': new_lines})}\n\n"
                    elif current_size < last_size:
                        # 文件被截断或轮转
                        last_size = 0
                except Exception:
                    await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        log_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/resume/{task_id}/{checkpoint_name}")
async def resume_training(task_id: str, checkpoint_name: str):
    """从检查点恢复训练"""
    state = get_training_context().state
    settings = get_settings()

    if (_worker_mode() and _training_job_repository().active_job()) or (not _worker_mode() and state.is_training()):
        raise HTTPException(status_code=400, detail="Training already in progress")

    original_record = _get_training_record_by_id(state, task_id)
    if not original_record and _worker_mode():
        durable_job = _training_job_repository().get_job(task_id)
        if durable_job:
            original_record = TrainingRecord(**durable_job.record)
    if not original_record:
        raise HTTPException(status_code=404, detail="Training record not found")

    output_dir = _training_output_dir(task_id, state)
    checkpoint_path = output_dir / "checkpoints" / checkpoint_name
    if not checkpoint_path.exists():
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    from training_engine.checkpoint_manager import validate_checkpoint
    validation = validate_checkpoint(str(checkpoint_path))
    if not validation.get("valid"):
        missing = validation.get("missing", [])
        raise HTTPException(
            status_code=400,
            detail=f"Checkpoint is incomplete, missing: {', '.join(missing)}. "
                   f"Recovery-exception checkpoints may not contain full trainer state. "
                   f"Please start a fresh training instead.",
        )
    if not validation.get("has_trainer_state"):
        raise HTTPException(
            status_code=400,
            detail="Checkpoint is missing trainer_state.json and cannot be used for resumption. "
                   "Please start a fresh training instead.",
        )

    config_dict = dict(original_record.config)
    resume_identity_warnings = _validate_resume_identity(
        original_record=original_record,
        config_dict=config_dict,
        checkpoint_path=checkpoint_path,
    )
    config_dict["resume_from_checkpoint"] = str(checkpoint_path)
    if resume_identity_warnings:
        for warning in resume_identity_warnings:
            logger.warning(f"恢复训练语义校验警告：{warning}")
        config_dict["resume_identity_warnings"] = resume_identity_warnings
    try:
        config = TrainingConfigInput(**config_dict)
    except Exception as e:
        logger.warning(f"从旧记录重建配置失败，使用默认值补充：{e}")
        defaults = TrainingConfigInput.model_fields
        for name, field in defaults.items():
            if name not in config_dict and field.default is not None:
                config_dict[name] = field.default
        config = TrainingConfigInput(**config_dict)
    model_path = settings.models_dir_resolved / config.model_id
    dataset_dir = settings.datasets_dir_resolved / config.dataset_id

    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Model not found: {config.model_id}")
    if not dataset_dir.exists():
        raise HTTPException(status_code=404, detail=f"Dataset not found: {config.dataset_id}")

    dataset_file = resolve_dataset_file(settings, config.dataset_id)
    if not dataset_file:
        raise HTTPException(status_code=404, detail=f"Dataset file not found in: {config.dataset_id}")

    if not _worker_mode() and not state.try_claim_training_slot():
        raise HTTPException(status_code=400, detail="Training already in progress")
    try:
        return _start_training_task(
            config=config,
            state=state,
            settings=settings,
            model_path=model_path,
            dataset_file=dataset_file,
            use_queue=False,
            priority="normal",
        )
    except Exception:
        state.queue_training_state(False)
        raise


@router.post("/check-resources", response_model=ResourceCheckResponse)
async def check_resources(
    method: str = Query(default="qlora", description="微调方法"),
    model_size: str = Query(default="7B", description="模型大小估计"),
    required_vram: float = Query(default=6.0, description="预计需要显存(GB)")
):
    """检查训练资源"""
    result = pre_training_resource_check(
        required_vram_gb=required_vram,
        method=method,
        model_size=model_size
    )
    return ResourceCheckResponse(**result)


@router.post("/preflight", response_model=TrainingPreflightResponse)
async def preflight_training(config: TrainingConfigInput):
    """训练启动前预检"""
    settings = get_settings()
    state = None if _worker_mode() else get_training_context().state
    checks: list[TrainingPreflightCheck] = []
    blockers: list[str] = []
    warnings: list[str] = []
    suggestions: list[str] = []
    recommended_config: dict[str, Any] = {}
    available_vram: float | None = None
    required_vram: float | None = None
    device_name: str | None = None

    is_training = bool(_training_job_repository().active_job()) if _worker_mode() else state.is_training()
    if is_training:
        blockers.append("当前已有训练任务在运行，需等待结束或停止后再启动新任务")
        preflight_check(checks, "runtime_state", "训练运行状态", "blocked", "已有训练任务正在运行", "当前版本默认只允许一个训练任务活跃运行。")
    else:
        preflight_check(checks, "runtime_state", "训练运行状态", "passed", "当前没有活跃训练任务")

    try:
        validate_release_supported_features(config)
        preflight_check(checks, "release_features", "发布版能力边界", "passed", "当前配置只使用发布版开放的 LoRA / QLoRA 能力")
    except HTTPException as exc:
        message = str(exc.detail)
        blockers.append(message)
        preflight_check(checks, "release_features", "发布版能力边界", "blocked", "配置包含未开放的实验训练能力", message)

    model_path = settings.models_dir_resolved / config.model_id
    if model_path.exists():
        detail = str(model_path)
        config_file = model_path / "config.json"
        if config_file.exists():
            detail = f"{detail}，config.json 已找到"
        else:
            warnings.append("模型目录存在，但未找到 config.json，加载时可能失败")
        preflight_check(checks, "model", "基础模型", "warning" if not config_file.exists() else "passed",
                       "模型目录可访问" if config_file.exists() else "模型目录可访问，但配置文件不完整", detail)
    else:
        message = f"模型不存在：{config.model_id}"
        blockers.append(message)
        preflight_check(checks, "model", "基础模型", "blocked", message)

    dataset_file = resolve_dataset_file(settings, config.dataset_id)
    dataset_path = settings.datasets_dir_resolved / config.dataset_id
    if dataset_file:
        preflight_check(checks, "dataset", "训练数据集", "passed", "数据集文件可访问", str(dataset_file))
    elif dataset_path.exists():
        message = "数据集目录存在，但未找到 .json 或 .jsonl 数据文件"
        blockers.append(message)
        preflight_check(checks, "dataset", "训练数据集", "blocked", message, str(dataset_path))
    else:
        message = f"数据集不存在：{config.dataset_id}"
        blockers.append(message)
        preflight_check(checks, "dataset", "训练数据集", "blocked", message)

    validation_result = await TrainingValidator.validate_config(config, settings)
    for error in validation_result.errors:
        if error not in blockers:
            blockers.append(error)
    for warning in validation_result.warnings:
        if warning not in warnings:
            warnings.append(warning)

    if validation_result.errors:
        preflight_check(checks, "validator", "配置完整性", "blocked", "配置验证存在阻塞问题", "；".join(validation_result.errors))
    elif validation_result.warnings:
        preflight_check(checks, "validator", "配置完整性", "warning", "配置可启动，但存在训练质量或稳定性风险", "；".join(validation_result.warnings))
    else:
        preflight_check(checks, "validator", "配置完整性", "passed", "配置结构与参数范围通过")

    required_vram = estimate_preflight_required_vram(config)
    resource_check = pre_training_resource_check(
        required_vram_gb=required_vram,
        method=config.method,
        model_size=config.model_id,
    )
    available_vram = resource_check.get("available_vram")
    device_name = resource_check.get("device_name")
    recommended_config = resource_check.get("recommended_config") or {}
    for warning in resource_check.get("warnings", []):
        if warning not in warnings:
            warnings.append(warning)
    for suggestion in resource_check.get("suggestions", []):
        if suggestion not in suggestions:
            suggestions.append(suggestion)

    if resource_check.get("passed"):
        preflight_check(checks, "resources", "显存与设备", "passed", "资源预算通过", f"可用 {available_vram}GB，预计需要 {required_vram}GB")
    else:
        resource_message = f"预计需要 {required_vram}GB VRAM，可用 {available_vram}GB"
        if available_vram is not None and available_vram <= 0:
            blockers.append("未检测到可用于训练的 GPU/CUDA 环境")
            preflight_check(checks, "resources", "显存与设备", "blocked", resource_message)
        else:
            warnings.append(resource_message)
            preflight_check(checks, "resources", "显存与设备", "warning", "显存预算偏紧，建议应用保守配置", resource_message)

    try:
        output_root = settings.outputs_dir_resolved
        output_root.mkdir(parents=True, exist_ok=True)
        probe_file = output_root / ".preflight_write_probe"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
        preflight_check(checks, "output", "输出目录", "passed", "训练输出目录可写", str(output_root))
    except Exception as exc:
        message = f"训练输出目录不可写：{exc}"
        blockers.append(message)
        preflight_check(checks, "output", "输出目录", "blocked", message)

    if config.method == "lora" and config.quantization == 0 and required_vram and required_vram >= 6:
        suggestion = "低显存环境建议切换到 QLoRA + 4bit 量化"
        if suggestion not in suggestions:
            suggestions.append(suggestion)

    status = "blocked" if blockers else "warning" if warnings else "ready"
    summary = (
        "预检发现阻塞项，需修复后再启动训练。"
        if status == "blocked"
        else "预检通过但存在风险项，可调整配置后再启动。"
        if status == "warning"
        else "预检通过，当前配置可以启动训练。"
    )

    return TrainingPreflightResponse(
        passed=status != "blocked",
        status=status,
        summary=summary,
        checks=checks,
        blockers=blockers,
        warnings=warnings,
        suggestions=suggestions,
        recommended_config=recommended_config,
        available_vram=available_vram,
        required_vram=required_vram,
        device_name=device_name,
    )


@router.post("/start", response_model=TrainingRecordResponse)
async def start_training(
    config: TrainingConfigInput,
    skip_resource_check: bool = False,
    use_queue: bool = False,
    priority: str = "normal",
    apply_recommended_config: bool = False,
):
    """开始训练"""
    from core.training_gateway import get_training_gateway

    settings = get_settings()
    gateway = get_training_gateway()
    state = None if _worker_mode() else get_training_context().state

    if not use_queue and gateway.is_training_in_progress():
        raise HTTPException(status_code=400, detail="Training already in progress")

    validate_release_supported_features(config)

    model_path = settings.models_dir_resolved / config.model_id
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Model not found: {config.model_id}")

    dataset_path = settings.datasets_dir_resolved / config.dataset_id
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail=f"Dataset not found: {config.dataset_id}")

    dataset_file = resolve_dataset_file(settings, config.dataset_id)
    if not dataset_file:
        raise HTTPException(status_code=404, detail=f"Dataset file not found in: {config.dataset_id}")

    config = apply_memory_preset(config)
    config = apply_precision_preset(config)

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

        model_size_gb = estimate_preflight_required_vram(config)

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

    if not _worker_mode() and not use_queue and not state.try_claim_training_slot():
        raise HTTPException(status_code=400, detail="Training already in progress")
    try:
        return _start_training_task(
            config=config,
            state=state,
            settings=settings,
            model_path=model_path,
            dataset_file=dataset_file,
            use_queue=use_queue,
            priority=priority,
        )
    except Exception:
        if state is not None:
            state.queue_training_state(False)
        raise


@router.get("/queue/status")
async def get_queue_status():
    """获取任务队列状态"""
    if _worker_mode():
        return _training_job_repository().queue_status()
    queue = get_training_context().queue
    return queue.get_queue_status()


@router.get("/queue/task/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态"""
    if _worker_mode():
        job = _training_job_repository().get_job(task_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return {
            "task_id": job.job_id,
            "status": job.status,
            "priority": job.priority,
            "attempt": job.attempt,
            "max_attempts": job.max_attempts,
            "cancel_requested": job.cancel_requested,
            "error": job.error,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "completed_at": job.finished_at,
            "worker_id": job.lease_owner,
        }
    queue = get_training_context().queue
    status = queue.get_task_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return status


@router.post("/queue/cancel/{task_id}")
async def cancel_task(task_id: str):
    """取消队列中的任务"""
    if _worker_mode():
        result = _training_job_repository().request_cancel(task_id)
        if result is None:
            raise HTTPException(status_code=400, detail="Task not found or already terminal")
        return {"message": f"Task {task_id} cancellation requested", "status": result}

    ctx = get_training_context()
    queue = ctx.queue
    state = ctx.state

    if queue.cancel(task_id):
        hub = get_training_event_hub_v2()
        current_record = state.get_current_record()
        if current_record and current_record.id == task_id and state.is_training():
            state.request_stop()
            _queue_training_progress(state, status="stopping", message="Training cancellation requested by user")
            hub.publish(
                task_id=task_id,
                phase="stopping",
                kind="task_cancellation_requested",
                payload={"status": "stopping", "message": "Training cancellation requested by user"},
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


# ============================================================================
# 向后兼容：为测试保留旧的下划线命名别名
# ============================================================================
queue_training_progress = _base_queue_training_progress


def _queue_training_progress(state, *, status: str, message: str, **kwargs: Any) -> None:
    queue_training_progress(state, status=status, message=message, **kwargs)
    try:
        current_record = state.get_current_record() if hasattr(state, "get_current_record") else None
        task_id = getattr(current_record, "id", None) if current_record is not None else None
        if task_id:
            from core.training_events_v2 import normalize_phase_v2

            phase = normalize_phase_v2(status) or status
            get_training_event_hub_v2().publish(
                task_id=task_id,
                phase=phase,
                kind="progress_updated",
                payload={"status": status, "message": message, **kwargs},
            )
    except Exception as e:
        logger.debug(f"V2 事件发布失败（_queue_training_progress）：{e}")
_estimate_training_total_steps = estimate_training_total_steps
_validate_release_supported_features = validate_release_supported_features
_handle_training_failure = handle_training_failure
_finalize_stop_requested = finalize_stop_requested
_sync_training_record_metadata = sync_training_record_metadata
_start_training_task = start_training_task
_load_checkpoints_for_task = load_checkpoints_for_task

# ============================================================================
# 向后兼容：重新导出测试与外部代码可能直接引用的符号
# ============================================================================
__all__ = [
    "router",
    "TrainingConfigInput",
    "TrainingProgressResponse",
    "TrainingRecordResponse",
    "ResourceCheckResponse",
    "TrainingPreflightCheck",
    "TrainingPreflightResponse",
    "SwiftCheckResponse",
    "QueueTaskResponse",
    "ValidationResult",
    "TrainingProgressStatus",
    "TRAINING_PROGRESS_STATUS_VALUES",
    "RecoverableError",
    "UnrecoverableError",
    "detect_dataset_sample_format",
    "load_dataset",
    "split_train_test_dataset",
    "estimate_training_total_steps",
    "queue_training_progress",
    "resume_training",
    "stop_training",
    "validate_release_supported_features",
    "get_checkpoints",
    "handle_training_failure",
    "finalize_stop_requested",
    "sync_training_record_metadata",
    "ProgressCallback",
    "TrainingValidator",
    "start_training",
    "start_training_task",
    "preflight_training",
    "get_recovery_options",
    "get_failure_analytics",
]

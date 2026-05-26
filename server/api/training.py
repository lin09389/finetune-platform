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
import json
import threading
import uuid
from collections.abc import Mapping
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Header, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from core.config import get_settings
from core.logging import get_logger
from core.training_events_v2 import get_training_event_hub_v2
from core.training_state import TrainingRecord, TrainingState
from core.training_context import get_training_context
from core.utils import pre_training_resource_check

# === 从下沉模块导入业务逻辑，并在底部 re-export 以兼容测试 ===
from training_engine.schemas import (
    TrainingConfigInput,
    TrainingProgressResponse,
    TrainingRecordResponse,
    ResourceCheckResponse,
    TrainingPreflightCheck,
    TrainingPreflightResponse,
    SwiftCheckResponse,
    QueueTaskResponse,
    ValidationResult,
    TrainingProgressStatus,
    TRAINING_PROGRESS_STATUS_VALUES,
    RELEASE_EXPERIMENTAL_FEATURE_MESSAGES,
    SUPPORTED_DATASET_FORMATS,
)
from training_engine.errors import RecoverableError, UnrecoverableError
from training_engine.dataset_formatter import detect_dataset_sample_format
from training_engine.dataset_loader import load_dataset, split_train_test_dataset
from training_engine.checkpoint_manager import load_checkpoints_for_task, _get_training_record_by_id, _resolve_training_output_dir as resolve_training_output_dir


def _load_checkpoints_for_task(state, settings, task_id):
    return load_checkpoints_for_task(state, settings, task_id)
from training_engine.config_builder import estimate_training_total_steps, apply_precision_preset, apply_memory_preset
from training_engine.callbacks import ProgressCallback, queue_training_progress as _base_queue_training_progress
from training_engine.training_logger import TrainingLogger
from training_engine.training_thread import training_thread, handle_training_failure, finalize_stop_requested, cleanup_training_resources
from training_engine.reporter import (
    build_failure_feedback,
    legacy_progress_from_v2_event,
    read_latest_metric_point,
    enrich_record_metrics,
    sync_training_record_metadata,
    build_failure_analytics_payload,
    _safe_parse_time,
)
from services.training.validator import (
    TrainingValidator,
    validate_release_supported_features,
    estimate_preflight_required_vram,
    preflight_check,
)
from services.training.orchestrator import start_training_task, resolve_dataset_file

logger = get_logger(__name__)

router = APIRouter()


# ============================================================================
# WebSocket 管理器（保留在路由层，因为与推送相关）
# ============================================================================
class TrainingWebSocketManager:
    """训练 WebSocket 管理器 - 实时推送训练进度"""

    CONNECTION_TIMEOUT = 300
    HEARTBEAT_INTERVAL = 30
    SEND_TIMEOUT = 10

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self._connection_times: dict[str, dict[WebSocket, float]] = {}
        self._async_lock = asyncio.Lock()

    async def connect(self, task_id: str, websocket: WebSocket):
        await websocket.accept()
        async with self._async_lock:
            if task_id not in self._connections:
                self._connections[task_id] = []
                self._connection_times[task_id] = {}
            self._connections[task_id].append(websocket)
            self._connection_times[task_id][websocket] = asyncio.get_event_loop().time()
            logger.info(f"WebSocket 连接：task_id={task_id}, 连接数={len(self._connections[task_id])}")

    async def disconnect(self, task_id: str, websocket: WebSocket):
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
        # Lock内只复制连接列表，释放锁后逐一发送
        async with self._async_lock:
            if task_id not in self._connections:
                return
            targets = list(self._connections[task_id])
            conn_times = dict(self._connection_times.get(task_id, {}))

        message = json.dumps(data)
        disconnected = []
        current_time = asyncio.get_event_loop().time()

        for websocket in targets:
            try:
                conn_time = conn_times.get(websocket, 0)
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

        # 回收断开的连接
        if disconnected:
            async with self._async_lock:
                for ws in disconnected:
                    try:
                        if task_id in self._connections and ws in self._connections[task_id]:
                            self._connections[task_id].remove(ws)
                        if task_id in self._connection_times and ws in self._connection_times.get(task_id, {}):
                            del self._connection_times[task_id][ws]
                    except Exception as e:
                        logger.debug(f"清理断开的 WebSocket 连接失败：{e}")

                if task_id in self._connections and not self._connections[task_id]:
                    del self._connections[task_id]
                    if task_id in self._connection_times:
                        del self._connection_times[task_id]

    async def broadcast_progress(self, task_id: str, progress: dict[str, Any]):
        await self.broadcast(task_id, {"type": "progress", "data": progress})

    async def broadcast_event(self, task_id: str, event_type: str, data: dict[str, Any]):
        await self.broadcast(task_id, {"type": "event", "event": event_type, "data": data})

    async def cleanup_stale_connections(self):
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
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = TrainingWebSocketManager()
    return _ws_manager


# ============================================================================
# 路由定义
# ============================================================================
@router.post("/stop")
async def stop_training():
    """停止训练"""
    state = get_training_context().state
    if not state.is_training():
        raise HTTPException(status_code=400, detail="No training in progress")
    if state.should_stop():
        return {"message": "Stop already requested", "status": "stopping"}
    state.request_stop()
    queue_training_progress(
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
        merged = legacy_progress_from_v2_event(latest_event, progress)
        return TrainingProgressResponse(**merged)
    return TrainingProgressResponse(**progress.model_dump())


@router.get("/progress/stream")
async def progress_stream(
    timeout: int = Query(default=300, ge=30, le=3600),
    heartbeat: int = Query(default=30, ge=10, le=120)
):
    """SSE 进度流"""
    import time
    state = get_training_context().state
    hub = get_training_event_hub_v2()

    # 加载阶段强制发送间隔（秒）：即使 status/step 不变也推送，让前端感知到心跳
    FORCE_SEND_INTERVAL = 5

    async def event_generator():
        last_step = -1
        last_status = ""
        last_message = ""
        last_seq = 0
        idle_count = 0
        last_heartbeat = time.time()
        last_force_send = time.time()
        connection_start = time.time()
        last_activity = time.time()

        try:
            while True:
                current_time = time.time()
                if current_time - connection_start > timeout:
                    yield f"event: timeout\ndata: {{\"message\": \"Connection timeout after {timeout}s\"}}\n\n"
                    break
                if current_time - last_activity > timeout:
                    yield "event: timeout\ndata: {\"message\": \"Idle timeout\"}\n\n"
                    break

                latest_event = hub.get_latest()
                if latest_event and latest_event.sequence > last_seq:
                    merged = legacy_progress_from_v2_event(latest_event, state.get_progress())
                    progress = TrainingProgressResponse(**merged)
                    last_seq = latest_event.sequence
                else:
                    progress = state.get_progress()

                current_message = getattr(progress, "message", "") or ""
                # 状态/步骤变化 OR message 变化（心跳线程会更新 message）OR 强制周期发送
                force_send = (current_time - last_force_send) >= FORCE_SEND_INTERVAL
                should_send = (
                    progress.step != last_step
                    or progress.status != last_status
                    or current_message != last_message
                    or force_send
                )
                if should_send:
                    yield f"data: {progress.model_dump_json()}\n\n"
                    last_step = progress.step
                    last_status = progress.status
                    last_message = current_message
                    last_force_send = current_time
                    last_activity = current_time

                if current_time - last_heartbeat >= heartbeat:
                    yield f"event: heartbeat\ndata: {{\"timestamp\": {current_time}}}\n\n"
                    last_heartbeat = current_time

                if progress.status == "idle":
                    idle_count += 1
                    if idle_count > 30:
                        yield "event: idle_timeout\ndata: {\"message\": \"Idle timeout\"}\n\n"
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
            yield 'event: error\ndata: {"message": "Internal stream error"}\n\n'

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
    ctx = get_training_context()
    state = ctx.state
    queue = ctx.queue
    history = state.get_history()

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
    state = get_training_context().state
    records = state.get_history()
    enriched = [enrich_record_metrics(r) for r in records]
    return [TrainingRecordResponse(**r.model_dump()) for r in enriched]


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
    """获取训练指标数据"""
    settings = get_settings()
    output_dir = settings.outputs_dir_resolved / f"train_{task_id[:8]}"
    metrics_file = output_dir / "metrics.jsonl"

    if not metrics_file.exists():
        return {"task_id": task_id, "metrics": [], "summary": {"total_steps": 0, "final_loss": 0, "elapsed_time": 0}}

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
    return {"task_id": task_id, "metrics": metrics, "summary": summary}


@router.get("/chart-data/{task_id}")
async def get_chart_data(task_id: str):
    """获取图表数据"""
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
        "loss_chart": {"labels": labels, "data": loss_data, "name": "Loss"},
        "lr_chart": {"labels": labels, "data": lr_data, "name": "Learning Rate"},
        "vram_chart": {"labels": labels, "data": vram_data, "name": "VRAM Usage (GB)"}
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
                try:
                    ws_manager = get_ws_manager()
                    asyncio.create_task(ws_manager.broadcast_progress(task_id, {**progress, "status": "running"}))
                except Exception as e:
                    logger.debug(f"WebSocket 推送失败：{e}")

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
            try:
                ws_manager = get_ws_manager()
                asyncio.create_task(ws_manager.broadcast_event(task_id, "training_completed", {
                    "framework": "swift", "output_path": record.output_path
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
            _queue_training_progress(state, status="failed", message=f"SWIFT Error: {error_msg[:200]}")
            record.status = "failed"
            record.end_time = datetime.now().isoformat()
            record.final_loss = float(last_progress.get("loss", 0.0))
            record.final_lr = float(last_progress.get("lr", 0.0))
            record.elapsed_time = float(last_progress.get("elapsed_time", 0.0))
            record.total_steps = int(last_progress.get("step", 0))
            sync_training_record_metadata(record)
            enrich_record_metrics(record)
            try:
                ws_manager = get_ws_manager()
                asyncio.create_task(ws_manager.broadcast_event(task_id, "training_failed", {
                    "framework": "swift", "error": error_msg[:500]
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
        _queue_training_progress(training_state, status="stopped", message="SWIFT training stopped by user")
        return {"message": "SWIFT training stopped"}
    raise HTTPException(status_code=500, detail="Failed to stop SWIFT training")


@router.get("/swift/progress")
async def get_swift_progress():
    """获取 SWIFT 训练进度"""
    from backends.swift_backend import get_swift_backend
    swift_backend = get_swift_backend()
    status = swift_backend.get_training_status()
    progress = swift_backend.parse_training_progress()
    return {**status, **progress}


@router.get("/swift/logs/{task_id}")
async def get_swift_logs(task_id: str, lines: int = Query(default=50, ge=1, le=200)):
    """获取 SWIFT 训练日志"""
    from backends.swift_backend import get_swift_backend
    swift_backend = get_swift_backend()
    log_lines = swift_backend.get_log_tail(lines)
    return {"task_id": task_id, "lines": log_lines, "count": len(log_lines)}


@router.get("/checkpoints/{task_id}")
async def get_checkpoints(task_id: str):
    """获取任务的检查点列表"""
    state = get_training_context().state
    settings = get_settings()
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
    records = state.get_history()
    return build_failure_analytics_payload(records)


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

    output_dir = resolve_training_output_dir(state, settings, task_id)
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
    config_dict["resume_from_checkpoint"] = str(checkpoint_path)
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

    if not state.try_claim_training_slot():
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
    state = get_training_context().state
    checks: list[TrainingPreflightCheck] = []
    blockers: list[str] = []
    warnings: list[str] = []
    suggestions: list[str] = []
    recommended_config: dict[str, Any] = {}
    available_vram: float | None = None
    required_vram: float | None = None
    device_name: str | None = None

    if state.is_training():
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
    settings = get_settings()
    state = get_training_context().state

    if state.is_training():
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

    if not state.try_claim_training_slot():
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
        state.queue_training_state(False)
        raise


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
    "TrainingWebSocketManager",
    "get_ws_manager",
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

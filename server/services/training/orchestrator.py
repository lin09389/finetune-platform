"""
训练编排服务 - 任务启动、队列管理、恢复训练
"""
import asyncio
import threading
import uuid
from pathlib import Path

from fastapi import HTTPException

from core.config import Settings
from core.logging import get_logger
from core.training_events_v2 import get_training_event_hub_v2
from core.training_queue import TaskPriority
from core.training_state import TrainingRecord, TrainingState
from core.training_context import get_training_context
from training_engine.schemas import TrainingConfigInput, TrainingRecordResponse
from training_engine.training_thread import training_thread

logger = get_logger(__name__)


def start_training_task(
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

    from training_engine.reporter import sync_training_record_metadata
    record = TrainingRecord(
        id=record_id,
        model_name=config.model_id,
        dataset_name=config.dataset_id,
        base_model_id=config.model_id,
        dataset_id=config.dataset_id,
        task_goal=config.task_goal,
        method=config.method,
        status="queued" if use_queue else "running",
        start_time=__import__("datetime").datetime.now().isoformat(),
        config=config.model_dump(),
        output_path=str(output_path),
        adapter_path=None,
        checkpoint_path=None,
    )
    sync_training_record_metadata(record)

    state.set_current_record(record)
    config.output_path = str(output_path)
    hub_v2 = get_training_event_hub_v2()

    try:
        event_loop = asyncio.get_running_loop()
    except RuntimeError:
        event_loop = None

    def run_training():
        if use_queue:
            import time
            while not state.try_claim_training_slot():
                if state.should_stop():
                    logger.info(f"队列任务取消执行: {record_id}")
                    return
                time.sleep(5)

        state.register_training_task(record_id, threading.current_thread())
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


def resolve_dataset_file(settings: Settings, dataset_id: str) -> Path | None:
    """在数据集目录中查找数据文件。"""
    dataset_path = settings.datasets_dir_resolved / dataset_id
    if not dataset_path.exists():
        return None

    dataset_file = None
    for ext in [".json", ".jsonl"]:
        for pattern in [f"{dataset_id}{ext}", f"data{ext}", f"*{ext}"]:
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
    return dataset_file

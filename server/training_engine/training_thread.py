"""
训练执行线程 - 基于 TrainingPipeline 的策略驱动执行

保留 training_thread 函数以兼容现有调用方，但内部使用 TrainingPipeline 实现。
"""
import gc
import traceback as tb
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import Settings
from core.logging import get_logger
from core.training_state import TrainingRecord, TrainingState
from core.utils import cleanup_gpu_memory, safe_cleanup_model
from training_engine.callbacks import queue_training_progress
from training_engine.config_builder import degrade_training_config
from training_engine.errors import RecoverableError, UnrecoverableError
from training_engine.events import TrainingEventBus
from training_engine.pipeline import PipelineContext, TrainingPhase, TrainingPipeline
from training_engine.reporter import enrich_record_metrics, sync_training_record_metadata
from training_engine.schemas import TrainingConfigInput
from training_engine.strategies import (
    AutoDatasetFormatter,
    DefaultOptimizerBuilder,
    DefaultPostLoadModelProcessor,
    HuggingFaceModelLoader,
)
from training_engine.training_logger import TrainingLogger

logger = get_logger(__name__)


def handle_training_failure(state: TrainingState, record: TrainingRecord, error: Exception, train_logger: TrainingLogger = None):
    """处理训练失败（保留以兼容旧调用）"""
    from training_engine.reporter import build_failure_feedback
    feedback = build_failure_feedback(str(error))
    latest_progress = state.get_progress()
    queue_training_progress(
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
    record.final_loss = float(latest_progress.loss)
    record.final_lr = float(latest_progress.lr)
    record.elapsed_time = float(latest_progress.elapsed_time)
    record.total_steps = int(latest_progress.step)
    sync_training_record_metadata(record)
    enrich_record_metrics(record)

    if train_logger:
        train_logger.log_error(error)

    state.add_to_history_sync(record)
    logger.info(f"训练失败记录已保存：{record.id}")


def finalize_stop_requested(
    state: TrainingState,
    record: TrainingRecord,
    task_id: str | None,
    model=None,
    tokenizer=None,
    trainer=None,
    message: str = "Training stopped by user",
):
    """统一处理用户停止请求（保留以兼容旧调用）"""
    latest_progress = state.get_progress()
    queue_training_progress(
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
    record.final_loss = float(latest_progress.loss)
    record.final_lr = float(latest_progress.lr)
    record.elapsed_time = float(latest_progress.elapsed_time)
    record.total_steps = int(latest_progress.step)
    sync_training_record_metadata(record)
    enrich_record_metrics(record)
    state.add_to_history_sync(record)
    logger.info(f"训练已停止并保存历史：{record.id}")

    state.queue_training_state(False)
    if task_id:
        state.unregister_training_task(task_id)
        logger.debug(f"已注销训练任务线程：{task_id}")

    cleanup_training_resources(model, tokenizer, trainer)


def cleanup_training_resources(model, tokenizer, trainer):
    """清理训练资源"""
    try:
        cleanup_gpu_memory(aggressive=True)
        if model is not None:
            safe_cleanup_model(model)
        del model, tokenizer, trainer
        gc.collect()
    except Exception as e:
        logger.warning(f"清理资源失败：{e}")


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
    训练线程 - 使用 TrainingPipeline 实现

    保留原有参数签名以兼容调用方，内部通过 Pipeline + 策略模式执行。
    """
    import time

    MAX_RETRIES = 2
    retry_count = 0
    settings = None
    try:
        from core.config import get_settings
        settings = get_settings()
    except Exception:
        pass

    model = None
    tokenizer = None
    trainer = None

    while True:
        if state.should_stop():
            finalize_stop_requested(
                state=state, record=record, task_id=task_id,
                model=model, tokenizer=tokenizer, trainer=trainer,
                message="Training stopped before next retry",
            )
            return

        if retry_count > 0:
            logger.info(f"第 {retry_count} 次重试训练：{record.id}")

            # 重试前保存回退检查点（保留当前状态以便对比）
            if model is not None and tokenizer is not None:
                try:
                    from training_engine.checkpoint_manager import create_rollback_checkpoint
                    rollback_path = create_rollback_checkpoint(
                        model=model,
                        tokenizer=tokenizer,
                        output_dir=Path(record.output_path),
                        task_id=record.id,
                        step=state.get_progress().step,
                        reason=f"retry_{retry_count}",
                    )
                    if rollback_path:
                        logger.info(f"回退检查点已保存：{rollback_path}")
                except Exception as e:
                    logger.warning(f"保存回退检查点失败：{e}")

            cleanup_gpu_memory(aggressive=True)
            if model is not None:
                safe_cleanup_model(model)
            del model, tokenizer, trainer
            gc.collect()

            # 降级配置
            old_config = config.model_copy()
            config = degrade_training_config(config)
            logger.info(f"应用降级配置：batch_size={config.batch_size}, gradient_accumulation={config.gradient_accumulation}")

            # 尝试从最近的恢复检查点继续
            try:
                from training_engine.checkpoint_manager import get_latest_checkpoint
                from core.config import get_settings
                latest_cp = get_latest_checkpoint(state, get_settings(), record.id)
                if latest_cp and latest_cp.get("valid"):
                    cp_path = latest_cp["path"]
                    logger.info(f"重试时将从最近 Trainer 检查点恢复：{cp_path}")
                    config.resume_from_checkpoint = cp_path
                    config.resume_from_adapter = None
            except Exception as e:
                logger.debug(f"查找恢复检查点失败：{e}")

            # 发布重试事件
            bus_retry = TrainingEventBus(state=state, task_id=record.id)
            bus_retry.publish_event(
                phase="retry",
                kind="training_retry",
                payload={
                    "retry_count": retry_count,
                    "max_retries": MAX_RETRIES,
                    "degraded_config": {
                        "batch_size": config.batch_size,
                        "gradient_accumulation": config.gradient_accumulation,
                        "max_seq_length": config.max_seq_length,
                    },
                    "previous_config": {
                        "batch_size": old_config.batch_size,
                        "gradient_accumulation": old_config.gradient_accumulation,
                        "max_seq_length": old_config.max_seq_length,
                    },
                    "resume_from_checkpoint": config.resume_from_checkpoint,
                },
            )

            cooldown = 30 * retry_count
            logger.info(f"等待 {cooldown} 秒后重试...")
            for _ in range(cooldown):
                if state.should_stop():
                    finalize_stop_requested(
                        state=state, record=record, task_id=task_id,
                        model=model, tokenizer=tokenizer, trainer=trainer,
                        message="Training stopped during retry cooldown",
                    )
                    return
                time.sleep(1)

        try:
            # 构建 Pipeline 上下文
            ctx = PipelineContext(
                config=config,
                model_path=model_path,
                dataset_path=dataset_path,
                state=state,
                record=record,
                task_id=task_id,
                settings=settings,
            )

            # 构建事件总线
            bus = TrainingEventBus(
                state=state,
                task_id=record.id,
                event_loop=event_loop,
            )
            # 延迟绑定 ws_manager 以避免循环导入
            try:
                from api.training import get_ws_manager
                bus._ws_manager = get_ws_manager()
            except Exception:
                pass

            # 使用策略驱动的 Pipeline 执行训练
            with TrainingPipeline(
                ctx=ctx,
                event_bus=bus,
                model_loader=HuggingFaceModelLoader(),
                dataset_formatter=AutoDatasetFormatter(),
                optimizer_builder=DefaultOptimizerBuilder(),
                post_processor=DefaultPostLoadModelProcessor(),
            ) as pipeline:
                pipeline.run()

            # 训练成功，从 pipeline 上下文获取对象用于后续清理兼容
            model = ctx.model
            tokenizer = ctx.tokenizer
            trainer = ctx.trainer
            return

        except RecoverableError as e:
            logger.warning(f"可恢复错误：{e}")
            if retry_count < MAX_RETRIES:
                retry_count += 1
            else:
                logger.error(f"重试次数耗尽 ({MAX_RETRIES}次)，训练失败")
                state.queue_training_state(False)
                if task_id:
                    state.unregister_training_task(task_id)
                train_logger = TrainingLogger(record.id, Path(record.output_path))
                handle_training_failure(state, record, e, train_logger)
                cleanup_training_resources(model, tokenizer, trainer)
                return

        except UnrecoverableError as e:
            logger.error(f"不可恢复错误：{e}")
            state.queue_training_state(False)
            if task_id:
                state.unregister_training_task(task_id)
            train_logger = TrainingLogger(record.id, Path(record.output_path))
            handle_training_failure(state, record, e, train_logger)
            cleanup_training_resources(model, tokenizer, trainer)
            return

        except Exception as e:
            logger.error(f"训练失败：{e}")
            logger.error(tb.format_exc())
            state.queue_training_state(False)
            if task_id:
                state.unregister_training_task(task_id)
            train_logger = TrainingLogger(record.id, Path(record.output_path))
            handle_training_failure(state, record, e, train_logger)
            cleanup_training_resources(model, tokenizer, trainer)
            return

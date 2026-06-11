"""
训练流水线模块 - 可观测、可打断、策略驱动的训练执行

使用上下文管理器:
    with TrainingPipeline(...) as pipe:
        pipe.run()

每个阶段都会发布事件，外部可通过事件总线订阅进度。
"""
from __future__ import annotations

import gc
import inspect
import os
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import Settings
from core.logging import get_logger
from core.training_state import TrainingRecord, TrainingState
from core.utils import cleanup_gpu_memory, safe_cleanup_model
from training_engine.config_builder import estimate_training_total_steps
from training_engine.errors import RecoverableError, UnrecoverableError
from training_engine.events import TrainingEventBus
from training_engine.schemas import TrainingConfigInput
from training_engine.strategies import (
    AutoDatasetFormatter,
    DatasetFormatterStrategy,
    DefaultOptimizerBuilder,
    DefaultPostLoadModelProcessor,
    HuggingFaceModelLoader,
    ModelLoaderStrategy,
    OptimizerBuilderStrategy,
    PostLoadModelProcessor,
)
from training_engine.training_logger import TrainingLogger

logger = get_logger(__name__)


@dataclass
class PipelineContext:
    """Pipeline 执行上下文，保存各阶段产物"""
    config: TrainingConfigInput
    model_path: str
    dataset_path: str
    state: TrainingState
    record: TrainingRecord
    task_id: str | None = None
    settings: Settings | None = None

    model: Any = None
    tokenizer: Any = None
    dataset: Any = None
    trainer: Any = None
    training_args: Any = None
    total_steps: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    train_logger: TrainingLogger | None = None


class TrainingPhase:
    """训练阶段枚举"""
    SETUP = "setup"
    LOAD_MODEL = "load_model"
    LOAD_DATASET = "load_dataset"
    BUILD_TRAINER = "build_trainer"
    TRAIN = "train"
    SAVE = "save"
    CLEANUP = "cleanup"


class TrainingPipeline:
    """
    训练流水线 - 策略驱动、可观测、可打断

    Args:
        ctx: Pipeline 执行上下文
        event_bus: 事件总线（用于进度上报和观测）
        model_loader: 模型加载策略（默认 HuggingFace）
        dataset_formatter: 数据集格式化策略（默认 Auto）
        optimizer_builder: 优化器构建策略（默认支持 LoRA+/GaLore）
        post_processor: 模型加载后处理策略（默认 torch.compile/TF32）
    """

    def __init__(
        self,
        ctx: PipelineContext,
        event_bus: TrainingEventBus,
        model_loader: ModelLoaderStrategy | None = None,
        dataset_formatter: DatasetFormatterStrategy | None = None,
        optimizer_builder: OptimizerBuilderStrategy | None = None,
        post_processor: PostLoadModelProcessor | None = None,
    ):
        self.ctx = ctx
        self.bus = event_bus
        self.model_loader = model_loader or HuggingFaceModelLoader()
        self.dataset_formatter = dataset_formatter or AutoDatasetFormatter()
        self.optimizer_builder = optimizer_builder or DefaultOptimizerBuilder()
        self.post_processor = post_processor or DefaultPostLoadModelProcessor()
        self._current_phase: str = TrainingPhase.SETUP
        self._interrupted: bool = False
        self._stop_requested: bool = False
        self._exception_info: dict[str, Any] | None = None
        self._phase_timings: dict[str, float] = {}
        self._phase_start_times: dict[str, datetime] = {}

    def __enter__(self) -> TrainingPipeline:
        self.ctx.start_time = datetime.now()
        self.ctx.train_logger = TrainingLogger(self.ctx.record.id, Path(self.ctx.record.output_path))
        self.ctx.train_logger.log_start(self.ctx.config)
        self.bus.publish_training_state(True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                self._exception_info = {
                    "type": exc_type.__name__,
                    "message": str(exc_val) if exc_val else "",
                    "phase": self._current_phase,
                }
                self.bus.publish_event(
                    phase=TrainingPhase.CLEANUP,
                    kind="pipeline_exception",
                    payload=self._exception_info,
                )
                # 仅对不可恢复异常保存 recovery checkpoint
                if not isinstance(exc_val, RecoverableError):
                    self._try_save_recovery_checkpoint("exception")
        finally:
            # 记录最后阶段耗时
            if self._current_phase in self._phase_start_times:
                duration = (datetime.now() - self._phase_start_times[self._current_phase]).total_seconds()
                self._phase_timings[self._current_phase] = self._phase_timings.get(self._current_phase, 0) + duration
            # RecoverableError 时不执行 cleanup，留给 training_thread 的 retry 逻辑
            if exc_type is None or not isinstance(exc_val, RecoverableError):
                self._run_cleanup()
        return False

    def _check_stop(self) -> bool:
        """检查是否收到停止请求，触发优雅停止流程"""
        if self._stop_requested:
            return True
        if self.ctx.state.should_stop():
            self._stop_requested = True
            self._interrupted = True
            logger.info(f"Pipeline 检测到停止请求，当前阶段：{self._current_phase}")
            return True
        return False

    def _set_phase(self, phase: str) -> None:
        # 记录上一阶段耗时
        if self._current_phase in self._phase_start_times:
            duration = (datetime.now() - self._phase_start_times[self._current_phase]).total_seconds()
            self._phase_timings[self._current_phase] = self._phase_timings.get(self._current_phase, 0) + duration
            self.bus.publish_event(
                phase=self._current_phase,
                kind="phase_completed",
                payload={"phase": self._current_phase, "duration": duration, "timings": self._phase_timings},
            )
        self._current_phase = phase
        self._phase_start_times[phase] = datetime.now()
        self.bus.publish_event(phase=phase, kind="phase_changed", payload={"phase": phase, "timings": self._phase_timings})
        logger.info(f"Pipeline 进入阶段: {phase}")

    def run(self) -> None:
        """执行完整训练流水线"""
        try:
            self._phase_setup()
            if self._stop_requested:
                self._handle_stop()
                return
            self._phase_load_model()
            if self._stop_requested:
                self._handle_stop()
                return
            self._phase_load_dataset()
            if self._stop_requested:
                self._handle_stop()
                return
            self._phase_build_trainer()
            if self._stop_requested:
                self._handle_stop()
                return
            self._phase_train()
            # _phase_train 内部已调用 _handle_stop；跳过 _phase_save 避免 status 被改写为 completed
            if self._stop_requested:
                return
            self._phase_save()
        except RecoverableError:
            raise
        except UnrecoverableError:
            raise
        except Exception as e:
            logger.error(f"Pipeline 执行失败：{e}")
            raise

    def _phase_setup(self) -> None:
        self._set_phase(TrainingPhase.SETUP)

        from training_engine.config_builder import degrade_training_config
        original_config = self.ctx.config
        degraded_config = degrade_training_config(original_config, model_path=self.ctx.model_path)
        if degraded_config is not original_config and degraded_config != original_config:
            changed = []
            changed_details = {}
            for field in ("batch_size", "max_seq_length", "method", "quantization",
                          "gradient_checkpointing", "use_flash_attn", "gradient_accumulation"):
                old_val = getattr(original_config, field, None)
                new_val = getattr(degraded_config, field, None)
                if old_val != new_val:
                    changed.append(f"{field}: {old_val} -> {new_val}")
                    changed_details[field] = {"from": old_val, "to": new_val}
            if changed:
                logger.warning(f"显存预检触发智能降级: {', '.join(changed)}")
                self.bus.publish_event(
                    phase="setup",
                    kind="config_degraded",
                    payload={
                        "changes": changed_details,
                        "reason": "VRAM 不足，已自动降级训练配置",
                    },
                )
            self.ctx.config = degraded_config

        self.bus.publish_progress(
            status="loading",
            message="Initializing training pipeline...",
            epoch=0, step=0, total_steps=0,
            loss=0.0, lr=0.0, vram_used=0.0,
            elapsed_time=0.0, eta=0.0,
        )

    def _phase_load_model(self) -> None:
        self._set_phase(TrainingPhase.LOAD_MODEL)
        import threading
        import time as _time

        self.bus.publish_progress(
            status="loading", message="正在加载模型，首次加载可能需要数分钟...",
            epoch=0, step=0, total_steps=0,
            loss=0.0, lr=0.0, vram_used=0.0,
            elapsed_time=0.0, eta=0.0,
        )

        # 加载阶段心跳线程：每5秒向前端推送一次 elapsed_time，防止前端看起来卡死
        _load_start = _time.monotonic()
        _stop_heartbeat = threading.Event()

        def _loading_heartbeat() -> None:
            while not _stop_heartbeat.wait(5):
                elapsed = _time.monotonic() - _load_start
                self.bus.publish_progress(
                    status="loading",
                    message=f"正在加载模型... （已等待 {int(elapsed)}s）",
                    epoch=0, step=0, total_steps=0,
                    loss=0.0, lr=0.0, vram_used=0.0,
                    elapsed_time=elapsed, eta=0.0,
                )

        hb_thread = threading.Thread(target=_loading_heartbeat, daemon=True)
        hb_thread.start()
        try:
            self.ctx.model, self.ctx.tokenizer = self.model_loader.load(
                self.ctx.model_path, self.ctx.config
            )
        except Exception as e:
            _stop_heartbeat.set()
            self._handle_load_model_error(e)
        finally:
            _stop_heartbeat.set()

        elapsed_total = _time.monotonic() - _load_start
        logger.info(f"模型加载完成，耗时 {elapsed_total:.1f}s")

        if self._check_stop():
            # 由 run() 的 phase 间守卫调用 _handle_stop，这里仅 return
            return

        self.ctx.model = self.post_processor.process(self.ctx.model, self.ctx.config)
        self.bus.publish_event(phase=TrainingPhase.LOAD_MODEL, kind="model_loaded", payload={
            "model_path": self.ctx.model_path,
            "method": self.ctx.config.method,
            "load_elapsed_seconds": elapsed_total,
        })

    def _handle_load_model_error(self, error: Exception) -> None:
        import torch
        if isinstance(error, torch.cuda.OutOfMemoryError):
            raise RecoverableError(f"加载模型时 OOM: {error}") from error
        if isinstance(error, FileNotFoundError):
            raise UnrecoverableError(f"模型文件丢失：{error}") from error
        error_str = str(error)
        if "CUDA" in error_str or "memory" in error_str.lower():
            raise RecoverableError(f"GPU 错误：{error}") from error
        raise

    def _phase_load_dataset(self) -> None:
        self._set_phase(TrainingPhase.LOAD_DATASET)
        import threading
        import time as _time

        self.bus.publish_progress(
            status="loading", message="正在加载数据集...",
            epoch=0, step=0, total_steps=0,
            loss=0.0, lr=0.0, vram_used=0.0,
            elapsed_time=0.0, eta=0.0,
        )

        # 数据集加载心跳线程（大数据集 tokenize 可能较慢）
        _ds_start = _time.monotonic()
        _stop_ds_hb = threading.Event()

        def _dataset_heartbeat() -> None:
            while not _stop_ds_hb.wait(5):
                elapsed = _time.monotonic() - _ds_start
                self.bus.publish_progress(
                    status="loading",
                    message=f"正在加载数据集... （已等待 {int(elapsed)}s）",
                    epoch=0, step=0, total_steps=0,
                    loss=0.0, lr=0.0, vram_used=0.0,
                    elapsed_time=elapsed, eta=0.0,
                )

        hb_thread = threading.Thread(target=_dataset_heartbeat, daemon=True)
        hb_thread.start()
        try:
            self.ctx.dataset = self.dataset_formatter.load(
                self.ctx.dataset_path,
                self.ctx.tokenizer,
                self.ctx.config,
                self.ctx.settings,
            )
        except FileNotFoundError as e:
            _stop_ds_hb.set()
            raise UnrecoverableError(f"数据集文件丢失：{e}") from e
        except Exception as e:
            _stop_ds_hb.set()
            raise UnrecoverableError(f"数据集格式错误：{e}") from e
        finally:
            _stop_ds_hb.set()

        if self._check_stop():
            # 由 run() 的 phase 间守卫调用 _handle_stop，这里仅 return
            return

        self.bus.publish_event(phase=TrainingPhase.LOAD_DATASET, kind="dataset_loaded", payload={
            "dataset_path": self.ctx.dataset_path,
            "train_size": len(self.ctx.dataset["train"]),
            "test_size": len(self.ctx.dataset.get("test", [])),
        })

    def _phase_build_trainer(self) -> None:
        self._set_phase(TrainingPhase.BUILD_TRAINER)

        import torch
        from transformers import TrainingArguments
        try:
            from transformers import Trainer
        except ImportError:
            from transformers.trainer import Trainer

        config = self.ctx.config
        dataset = self.ctx.dataset
        model = self.ctx.model
        tokenizer = self.ctx.tokenizer

        try:
            self.ctx.total_steps = estimate_training_total_steps(
                train_size=len(dataset["train"]),
                batch_size=config.batch_size,
                epochs=config.epochs,
                gradient_accumulation=config.gradient_accumulation,
            )
        except ValueError as e:
            raise UnrecoverableError(str(e))

        eval_steps = config.eval_steps if config.eval_steps > 0 else None
        eval_strategy = "steps" if eval_steps else "no"
        use_best_model = config.load_best_model and eval_strategy == "steps"
        if config.load_best_model and eval_strategy != "steps":
            logger.warning("load_best_model 需要 eval_steps > 0，已自动禁用")

        normalized_save_steps = config.save_steps
        if use_best_model and eval_steps:
            if normalized_save_steps % eval_steps != 0:
                normalized_save_steps = max(
                    eval_steps,
                    ((normalized_save_steps + eval_steps - 1) // eval_steps) * eval_steps,
                )
                logger.warning(
                    "检测到 load_best_model_at_end 步长约束，自动调整 save_steps："
                    f"{config.save_steps} -> {normalized_save_steps}（eval_steps={eval_steps}）"
                )

        warmup_steps = config.warmup_steps
        warmup_ratio = None
        if warmup_steps == 0 and config.warmup_ratio > 0:
            warmup_ratio = config.warmup_ratio
        logger.info(f"学习率预热配置：warmup_steps={warmup_steps}, warmup_ratio={warmup_ratio}")

        deepspeed_config = self._build_deepspeed_config(config)
        output_dir = config.output_path if config.output_path else self.ctx.record.output_path
        dataloader_num_workers, dataloader_pin_memory, dataloader_persistent_workers = self._normalize_dataloader_config(config)

        base_training_args_kwargs = {
            "output_dir": output_dir,
            "num_train_epochs": config.epochs,
            "per_device_train_batch_size": config.batch_size,
            "gradient_accumulation_steps": config.gradient_accumulation,
            "learning_rate": config.learning_rate,
            "warmup_steps": warmup_steps,
            "warmup_ratio": warmup_ratio,
            "logging_steps": config.logging_steps,
            "save_steps": normalized_save_steps,
            "save_total_limit": 3,
            "load_best_model_at_end": use_best_model,
            "eval_steps": eval_steps,
            "report_to": "none",
            "fp16": not config.bf16,
            "bf16": config.bf16,
            "gradient_checkpointing": config.gradient_checkpointing,
            "dataloader_num_workers": dataloader_num_workers,
            "dataloader_pin_memory": dataloader_pin_memory,
            "dataloader_persistent_workers": dataloader_persistent_workers,
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
        self.ctx.training_args = TrainingArguments(**filtered_training_args_kwargs)

        early_stopping_callback = None
        if config.early_stopping_patience > 0 and use_best_model:
            try:
                from transformers import EarlyStoppingCallback
            except ImportError:
                from transformers.trainer_callback import EarlyStoppingCallback
            early_stopping_callback = EarlyStoppingCallback(
                early_stopping_patience=config.early_stopping_patience,
                early_stopping_threshold=config.early_stopping_threshold
            )
            logger.info(f"已启用早停：patience={config.early_stopping_patience}, threshold={config.early_stopping_threshold}")

        callbacks = []
        if early_stopping_callback:
            callbacks.append(early_stopping_callback)

        from transformers import DataCollatorForSeq2Seq

        data_collator = DataCollatorForSeq2Seq(
            tokenizer=tokenizer,
            padding=True,
            max_length=None,
            pad_to_multiple_of=8,
            label_pad_token_id=-100,
            return_tensors="pt",
        )

        self.ctx.trainer = Trainer(
            model=model,
            args=self.ctx.training_args,
            train_dataset=dataset["train"],
            eval_dataset=dataset.get("test"),
            processing_class=tokenizer,
            data_collator=data_collator,
            callbacks=callbacks,
        )

        self.optimizer_builder.build(model, self.ctx.trainer, config)

        self.bus.publish_event(phase=TrainingPhase.BUILD_TRAINER, kind="trainer_built", payload={
            "total_steps": self.ctx.total_steps,
            "eval_strategy": eval_strategy,
        })

    # DeepSpeed scheduler 类型名映射（HuggingFace 名称 → DeepSpeed 名称）
    _DS_SCHEDULER_MAP = {
        "linear": "Linear",
        "cosine": "Cosine",
        "cosine_with_restarts": "CosineWithRestarts",
        "polynomial": "Polynomial",
        "constant": "Constant",
        "constant_with_warmup": "ConstantWithWarmup",
        "inverse_sqrt": "InverseSqrt",
        "reduce_lr_on_plateau": "ReduceLRonPlateau",
    }

    def _build_deepspeed_config(self, config: TrainingConfigInput) -> dict[str, Any] | None:
        if config.deepspeed_stage > 0 and config.method != "qlora":
            logger.info(f"已配置 DeepSpeed ZeRO-{config.deepspeed_stage}, offload={config.offload_optimizer}")
            ds_scheduler_type = self._DS_SCHEDULER_MAP.get(config.lr_scheduler, config.lr_scheduler)
            return {
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
                "train_batch_size": config.batch_size * config.gradient_accumulation,
                "train_micro_batch_size_per_gpu": config.batch_size,
                "optimizer": {
                    "type": "AdamW",
                    "params": {
                        "lr": config.learning_rate,
                        "betas": [0.9, 0.999],
                        "eps": 1e-8,
                        "weight_decay": config.weight_decay,
                    },
                },
                "scheduler": {
                    "type": ds_scheduler_type,
                    "params": {
                        "warmup_min_lr": 0,
                        "warmup_max_lr": config.learning_rate,
                        "warmup_num_steps": config.warmup_steps,
                    },
                },
            }
        elif config.deepspeed_stage > 0 and config.method == "qlora":
            logger.warning("QLoRA 模式下不支持 DeepSpeed，将使用标准训练")
        return None

    def _normalize_dataloader_config(self, config: TrainingConfigInput) -> tuple[int, bool, bool]:
        dataloader_num_workers = config.dataloader_num_workers
        dataloader_pin_memory = config.dataloader_pin_memory
        dataloader_persistent_workers = (
            config.dataloader_persistent_workers if config.dataloader_num_workers > 0 else False
        )
        if os.name == "nt" and dataloader_num_workers > 0:
            import threading as _threading
            if _threading.current_thread() is _threading.main_thread():
                try:
                    import torch.multiprocessing as mp
                    mp.set_start_method("spawn", force=True)
                    logger.info(
                        f"Windows 环境已设置 multiprocessing start_method=spawn，"
                        f"保留 dataloader_num_workers={dataloader_num_workers}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Windows 环境 multiprocessing spawn 设置失败({e})，"
                        f"dataloader_num_workers 从 {dataloader_num_workers} 降为 0"
                    )
                    dataloader_num_workers = 0
                    dataloader_persistent_workers = False
                    dataloader_pin_memory = False
            else:
                logger.warning(
                    f"Windows 非主线程无法安全调用 mp.set_start_method，"
                    f"dataloader_num_workers 从 {dataloader_num_workers} 自动降为 0"
                )
                dataloader_num_workers = 0
                dataloader_persistent_workers = False
                dataloader_pin_memory = False
        return dataloader_num_workers, dataloader_pin_memory, dataloader_persistent_workers

    def _phase_train(self) -> None:
        self._set_phase(TrainingPhase.TRAIN)

        from training_engine.callbacks import ProgressCallback

        callback = ProgressCallback(
            total_steps=self.ctx.total_steps,
            start_time=self.ctx.start_time,
            state=self.ctx.state,
            record=self.ctx.record,
            config=self.ctx.config,
            model=self.ctx.model,
            tokenizer=self.ctx.tokenizer,
            trainer=self.ctx.trainer,
            train_logger=self.ctx.train_logger,
            event_loop=getattr(self.bus, "_event_loop", None),
        )
        self.ctx.trainer.add_callback(callback)

        self.bus.publish_progress(
            status="training", message="Starting training...",
            epoch=0, step=0, total_steps=self.ctx.total_steps,
            loss=0.0, lr=0.0, vram_used=0.0,
            elapsed_time=0.0, eta=0.0,
        )

        # 训练看门狗：检测 on_step_end 停止触发的卡死
        import threading as _wd_threading
        import time as _wd_time

        STALL_TIMEOUT_SECONDS = 300
        _watchdog_stop = _wd_threading.Event()

        def _training_watchdog() -> None:
            while not _watchdog_stop.wait(30):
                with self.ctx.state._lock:
                    last_hb = self.ctx.state._last_heartbeat
                if last_hb > 0:
                    elapsed_since_hb = _wd_time.time() - last_hb
                    if elapsed_since_hb > STALL_TIMEOUT_SECONDS:
                        progress = self.ctx.state.get_progress()
                        logger.warning(
                            f"训练可能卡死：{elapsed_since_hb:.0f}s 无进度更新 "
                            f"(阈值: {STALL_TIMEOUT_SECONDS}s)。"
                            f"当前 step={progress.step}/{progress.total_steps}"
                        )
                        self.bus.publish_event(
                            phase=TrainingPhase.TRAIN,
                            kind="training_stall_detected",
                            payload={
                                "stall_seconds": elapsed_since_hb,
                                "current_step": progress.step,
                                "total_steps": progress.total_steps,
                            },
                        )
                        if elapsed_since_hb > STALL_TIMEOUT_SECONDS * 2:
                            logger.error(
                                f"训练卡死超时 ({elapsed_since_hb:.0f}s)，自动触发停止"
                            )
                            self.ctx.state.request_stop()
                            _watchdog_stop.set()

        self.ctx.state.update_heartbeat()
        _watchdog_thread = _wd_threading.Thread(target=_training_watchdog, daemon=True)
        _watchdog_thread.start()

        train_exception = None
        try:
            self.ctx.trainer.train(
                resume_from_checkpoint=self.ctx.config.resume_from_checkpoint
                if self.ctx.config.resume_from_checkpoint
                else None
            )
        except Exception as e:
            train_exception = e
            callback.clear_references()
            import torch
            if isinstance(e, torch.cuda.OutOfMemoryError):
                train_exception = RecoverableError(f"训练时 OOM: {e}")
                train_exception.__cause__ = e
            elif isinstance(e, KeyboardInterrupt):
                train_exception = UnrecoverableError("用户中断训练")
                train_exception.__cause__ = e
            else:
                error_str = str(e)
                if "CUDA" in error_str or "memory" in error_str.lower() or "NCCL" in error_str:
                    train_exception = RecoverableError(f"GPU 错误：{e}")
                    train_exception.__cause__ = e
        finally:
            _watchdog_stop.set()

        # 检查是否是用户主动停止
        if self._stop_requested:
            logger.info("训练被用户停止，保存恢复检查点...")
            recovery_path = self._try_save_recovery_checkpoint("user_stopped")
            self.bus.publish_event(
                phase=TrainingPhase.TRAIN,
                kind="training_stopped",
                payload={
                    "reason": "user_requested",
                    "recovery_checkpoint": str(recovery_path) if recovery_path else None,
                    "current_step": self.ctx.state.get_progress().step,
                },
            )
            # 走停止流程而不是失败流程
            self._handle_stop()
            return

        if train_exception is not None:
            # 异常时保存恢复检查点
            recovery_path = self._try_save_recovery_checkpoint("exception")
            self.bus.publish_event(
                phase=TrainingPhase.TRAIN,
                kind="training_exception",
                payload={
                    "error": str(train_exception),
                    "recovery_checkpoint": str(recovery_path) if recovery_path else None,
                    "current_step": self.ctx.state.get_progress().step,
                },
            )
            raise train_exception

        self.bus.publish_event(phase=TrainingPhase.TRAIN, kind="training_completed", payload={
            "total_steps": self.ctx.total_steps,
        })

    def _handle_stop(self) -> None:
        """处理用户停止请求 - 保存状态并优雅退出"""
        progress = self.ctx.state.get_progress()
        self.ctx.record.status = "stopped"
        self.ctx.record.end_time = datetime.now().isoformat()
        self.ctx.record.final_loss = float(progress.loss)
        self.ctx.record.final_lr = float(progress.lr)
        self.ctx.record.elapsed_time = float(progress.elapsed_time)
        self.ctx.record.total_steps = int(progress.step)

        from training_engine.reporter import enrich_record_metrics, sync_training_record_metadata, write_training_artifact_manifest
        sync_training_record_metadata(self.ctx.record)
        enrich_record_metrics(self.ctx.record)
        write_training_artifact_manifest(self.ctx.record)
        self.ctx.state.add_to_history_sync(self.ctx.record)

        self.bus.publish_progress(
            status="stopped",
            message="Training stopped by user",
            epoch=progress.epoch,
            step=progress.step,
            total_steps=progress.total_steps,
            loss=progress.loss,
            lr=progress.lr,
            vram_used=progress.vram_used,
            elapsed_time=progress.elapsed_time,
            eta=progress.eta,
            stop_reason="user_requested",
        )
        logger.info(f"训练已停止并保存历史：{self.ctx.record.id}")

    def _phase_save(self) -> None:
        self._set_phase(TrainingPhase.SAVE)

        output_dir = Path(self.ctx.record.output_path)
        if self.ctx.config.method == "full":
            save_subdir = "full_model"
        else:
            save_subdir = "lora_adapter"
        save_path = output_dir / save_subdir
        save_path.mkdir(parents=True, exist_ok=True)
        self.ctx.model.save_pretrained(save_path)
        self.ctx.tokenizer.save_pretrained(save_path)
        logger.info(f"模型已保存到：{save_path}")

        self.ctx.record.status = "completed"
        self.ctx.record.end_time = datetime.now().isoformat()
        self.ctx.record.checkpoint_path = str(save_path)
        self.ctx.record.adapter_path = str(save_path) if self.ctx.config.method != "full" else None

        progress_snapshot = self.ctx.state.get_progress()
        self.ctx.record.final_loss = float(progress_snapshot.loss)
        self.ctx.record.final_lr = float(progress_snapshot.lr)
        self.ctx.record.elapsed_time = float(progress_snapshot.elapsed_time)
        self.ctx.record.total_steps = int(progress_snapshot.step or self.ctx.total_steps)

        from training_engine.reporter import enrich_record_metrics, sync_training_record_metadata, write_training_artifact_manifest
        sync_training_record_metadata(self.ctx.record)
        enrich_record_metrics(self.ctx.record)
        write_training_artifact_manifest(self.ctx.record)

        self.ctx.state.add_to_history_sync(self.ctx.record)
        logger.info(f"训练历史已保存：{self.ctx.record.id}")

        self.bus.publish_progress(
            status="completed", message="Training completed!",
            epoch=self.ctx.config.epochs, step=self.ctx.total_steps,
            total_steps=self.ctx.total_steps,
            loss=progress_snapshot.loss, lr=progress_snapshot.lr,
            vram_used=0.0, elapsed_time=progress_snapshot.elapsed_time, eta=0.0,
        )
        self.bus.publish_event(phase=TrainingPhase.SAVE, kind="model_saved", payload={
            "output_path": str(save_path),
        })

    def _try_save_recovery_checkpoint(self, reason: str) -> Path | None:
        """尝试保存恢复检查点"""
        try:
            from training_engine.checkpoint_manager import create_recovery_checkpoint
            progress = self.ctx.state.get_progress()
            return create_recovery_checkpoint(
                trainer=self.ctx.trainer,
                output_dir=Path(self.ctx.record.output_path),
                reason=reason,
                metadata={
                    "task_id": self.ctx.record.id,
                    "loss": progress.loss,
                    "lr": progress.lr,
                    "step": progress.step,
                    "phase": self._current_phase,
                },
            )
        except Exception as e:
            logger.warning(f"保存恢复检查点失败：{e}")
            return None

    def _try_save_rollback_checkpoint(self, reason: str) -> Path | None:
        """尝试保存回退检查点"""
        try:
            from training_engine.checkpoint_manager import create_rollback_checkpoint
            progress = self.ctx.state.get_progress()
            return create_rollback_checkpoint(
                model=self.ctx.model,
                tokenizer=self.ctx.tokenizer,
                output_dir=Path(self.ctx.record.output_path),
                task_id=self.ctx.record.id,
                step=progress.step,
                reason=reason,
            )
        except Exception as e:
            logger.warning(f"保存回退检查点失败：{e}")
            return None

    def _run_cleanup(self) -> None:
        self._set_phase(TrainingPhase.CLEANUP)

        # 【关键修复】立即设置训练状态为 False，让前端立即响应
        self.bus.publish_training_state(False)
        if self.ctx.task_id:
            self.ctx.state.unregister_training_task(self.ctx.task_id)
            logger.debug(f"已注销训练任务线程：{self.ctx.task_id}")

        # 关闭训练日志记录器，释放文件句柄
        train_logger = getattr(self.ctx, "train_logger", None)
        if train_logger:
            try:
                train_logger.close()
            except Exception as e:
                logger.warning(f"关闭训练日志记录器失败：{e}")

        # 【优化】将耗时的清理操作放到后台线程执行，不阻塞训练线程退出
        import threading
        model = self.ctx.model
        tokenizer = self.ctx.tokenizer
        trainer = self.ctx.trainer
        self.ctx.model = None
        self.ctx.tokenizer = None
        self.ctx.trainer = None

        def _async_cleanup(model_ref, _tokenizer_ref, _trainer_ref):
            try:
                if model_ref is not None:
                    safe_cleanup_model(model_ref)
                gc.collect()
                cleanup_gpu_memory(aggressive=True)
            except Exception as e:
                logger.warning(f"异步清理资源失败：{e}")

        cleanup_thread = threading.Thread(
            target=_async_cleanup,
            args=(model, tokenizer, trainer),
            daemon=False,
        )
        cleanup_thread.start()
        try:
            cleanup_thread.join(timeout=30)
        except Exception as e:
            logger.warning(f"等待清理线程完成超时：{e}")

    @property
    def current_phase(self) -> str:
        return self._current_phase

    @property
    def interrupted(self) -> bool:
        return self._interrupted

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested

    @property
    def exception_info(self) -> dict[str, Any] | None:
        return self._exception_info

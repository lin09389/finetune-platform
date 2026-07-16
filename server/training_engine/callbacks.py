"""
训练回调模块 - 进度上报、ETA 计算（事件总线驱动）
"""
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from core.logging import get_logger
from core.training_state import TrainingState
from core.utils import get_vram_usage
from training_engine.schemas import TRAINING_PROGRESS_STATUS_VALUES, TrainingConfigInput
from training_engine.training_logger import TrainingLogger


def get_training_event_hub_v2():
    from core.training_events_v2 import get_training_event_hub_v2 as _get_training_event_hub_v2

    return _get_training_event_hub_v2()

logger = get_logger(__name__)


def queue_training_progress(
    state: TrainingState,
    *,
    status: str,
    message: str,
    **kwargs: Any,
) -> None:
    """向后兼容：更新 TrainingState 进度并发布 V2 事件。"""
    if status not in TRAINING_PROGRESS_STATUS_VALUES:
        raise ValueError(f"Unsupported training progress status: {status}")
    state.queue_progress_update(status=status, message=message, **kwargs)

    try:
        from core.training_events_v2 import normalize_phase_v2

        current_record = state.get_current_record() if hasattr(state, "get_current_record") else None
        task_id = getattr(current_record, "id", None) if current_record is not None else None
        if task_id:
            phase = normalize_phase_v2(status) or status
            hub = get_training_event_hub_v2()
            payload = {"status": status, "message": message, **kwargs}
            hub.publish(task_id=task_id, phase=phase, kind="progress_updated", payload=payload)
    except Exception as e:
        logger.debug(f"V2 事件发布失败（queue_training_progress）：{e}")


class ProgressCallback:
    """训练进度回调 - 与 HuggingFace Trainer 集成"""

    def __init__(
        self,
        total_steps: int,
        start_time: datetime,
        state: TrainingState,
        record,
        config: TrainingConfigInput,
        model=None,
        tokenizer=None,
        trainer=None,
        train_logger: TrainingLogger = None,
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
        if self.total_steps > 0:
            self.update_interval = max(self.update_interval, self.total_steps // 50)
        self.update_interval = max(1, self.update_interval)

        self._vram_update_interval = max(5, self.update_interval * 3)
        self._last_vram_step = -1

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
        self.trainer = trainer

    def on_train_begin(self, args, state, control, **kwargs):
        logger.info(f"训练开始：总步数={self.total_steps}")
        queue_training_progress(
            self.state,
            epoch=0, step=0, total_steps=self.total_steps, loss=0.0, lr=0.0,
            vram_used=get_vram_usage(), elapsed_time=0.0, eta=0.0,
            status="training",
            message="Training started",
        )

    def on_init_end(self, args, state, control, **kwargs):
        logger.debug("Trainer 初始化完成")

    def on_epoch_begin(self, args, state, control, **kwargs):
        pass

    def on_epoch_end(self, args, state, control, **kwargs):
        pass

    def on_log(self, args, state, control, **kwargs):
        pass

    def on_step_begin(self, args, state, control, **kwargs):
        pass

    def on_prediction_step(self, args, state, control, **kwargs):
        pass

    def on_substep_end(self, args, state, control, **kwargs):
        pass

    def on_pre_optimizer_step(self, args, state, control, **kwargs):
        pass

    def on_optimizer_step(self, args, state, control, **kwargs):
        pass

    _save_checkpoint_metadata = None

    def _get_save_checkpoint_metadata(self):
        if ProgressCallback._save_checkpoint_metadata is None:
            try:
                from training_engine.checkpoint_manager import save_checkpoint_metadata
                ProgressCallback._save_checkpoint_metadata = save_checkpoint_metadata
            except Exception:
                pass
        return ProgressCallback._save_checkpoint_metadata

    def on_save(self, args, state, control, **kwargs):
        """检查点保存时发布事件"""
        save_checkpoint_metadata_fn = self._get_save_checkpoint_metadata()
        checkpoint_path = getattr(kwargs, "model", None)
        if checkpoint_path is None and hasattr(state, "global_step"):
            output_dir = getattr(args, "output_dir", "")
            checkpoint_path = f"{output_dir}/checkpoint-{state.global_step}"

        if save_checkpoint_metadata_fn is not None:
            try:
                save_checkpoint_metadata_fn(
                    Path(checkpoint_path),
                    task_id=self.record.id,
                    step=state.global_step,
                    epoch=float(state.epoch),
                    loss=self.current_loss,
                    lr=float(getattr(args, "learning_rate", self.config.learning_rate)),
                    config=self.config.model_dump() if hasattr(self.config, "model_dump") else {},
                    tags=["regular"],
                )
            except Exception as e:
                logger.debug(f"保存检查点元数据失败：{e}")

        # 通过 WebSocket / 事件总线通知前端
        try:
            queue_training_progress(
                self.state,
                epoch=int(state.epoch) + 1,
                step=state.global_step,
                total_steps=self.total_steps,
                loss=self.current_loss,
                lr=float(getattr(args, "learning_rate", self.config.learning_rate)),
                vram_used=get_vram_usage(),
                elapsed_time=(datetime.now() - self.start_time).total_seconds(),
                eta=0.0,
                status="running",
                message=f"Checkpoint saved at step {state.global_step}",
            )
        except Exception as e:
            logger.debug(f"WebSocket checkpoint 事件推送失败：{e}")

    def on_evaluate(self, args, state, control, **kwargs):
        pass

    def on_predict(self, args, state, control, metrics, **kwargs):
        pass

    def on_push_begin(self, args, state, control, **kwargs):
        logger.info("准备推送模型到 Hub")

    def on_step_end(self, args, state, control, **kwargs):
        if self.state.should_stop():
            logger.info(f"检测到停止信号，在第 {state.global_step} 步中断训练")
            control.should_training_stop = True
            return control

        self.current_step = state.global_step
        self.current_epoch = state.epoch
        self.state.update_heartbeat()
        try:
            from core.gpu_coordination import renew_training_gpu

            renew_training_gpu()
        except Exception:
            pass

        loss = kwargs.get("loss", 0.0)
        if loss and float(loss) > 0:
            self.current_loss = float(loss)
        else:
            log_history = getattr(state, "log_history", None) or []
            for log_item in reversed(log_history):
                if isinstance(log_item, dict) and "loss" in log_item:
                    try:
                        self.current_loss = float(log_item["loss"])
                    except (TypeError, ValueError):
                        pass
                    break

        should_force_update = self.current_step <= 5 or self.current_step >= self.total_steps
        if should_force_update or (self.current_step - self.last_update_step) >= self.update_interval:
            self._update_progress(state, args, kwargs)
            self.last_update_step = self.current_step

        return control

    def _update_progress(self, state, args, kwargs):
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

        should_query_vram = (
            self.current_step <= 5
            or self.current_step >= self.total_steps
            or (self.current_step - self._last_vram_step) >= self._vram_update_interval
        )
        if should_query_vram:
            vram = get_vram_usage()
            self._last_vram_step = self.current_step
            self._cached_vram = vram
        else:
            vram = getattr(self, "_cached_vram", 0.0)
        lr = getattr(args, "learning_rate", self.config.learning_rate)

        # 采集梯度范数
        grad_norm = None
        try:
            if hasattr(state, "grad_norm") and state.grad_norm is not None:
                grad_norm = float(state.grad_norm)
            elif hasattr(self.trainer, "get_grad_norm"):
                grad_norm = float(self.trainer.get_grad_norm())
        except Exception:
            pass

        # 计算 samples/sec
        samples_per_sec = 0.0
        try:
            batch_size = getattr(args, "per_device_train_batch_size", 1)
            grad_accum = getattr(args, "gradient_accumulation_steps", 1)
            samples_per_sec = self._steps_per_second * batch_size * grad_accum
        except Exception:
            pass

        queue_training_progress(
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
            grad_norm=grad_norm,
            speed=self._steps_per_second,
            samples_per_sec=samples_per_sec,
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
                    "eta": eta,
                    "grad_norm": grad_norm,
                    "speed": self._steps_per_second,
                    "samples_per_sec": samples_per_sec,
                }
            )

    def on_train_end(self, args, state, control, **kwargs):
        final_elapsed = (datetime.now() - self.start_time).total_seconds()
        final_lr = float(getattr(args, "learning_rate", self.config.learning_rate))
        if self.train_logger:
            self.train_logger.log_completion({
                "loss": self.current_loss,
                "lr": final_lr,
                "elapsed_time": final_elapsed,
                "total_steps": self.total_steps,
            })

        queue_training_progress(
            self.state,
            epoch=self.config.epochs,
            step=self.total_steps,
            total_steps=self.total_steps,
            loss=self.current_loss,
            lr=final_lr,
            vram_used=get_vram_usage(),
            elapsed_time=final_elapsed,
            eta=0.0,
            status="saving",
            message="Saving model...",
            final_loss=self.current_loss,
            final_lr=final_lr,
            final_elapsed_time=final_elapsed,
            final_steps=self.total_steps,
        )

        self.model = None
        self.trainer = None
        self.tokenizer = None

    def clear_references(self):
        """清除对大对象的引用，允许 GC 回收（异常路径使用）"""
        self.model = None
        self.trainer = None
        self.tokenizer = None

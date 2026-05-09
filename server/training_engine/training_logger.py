"""
训练日志记录器 - 指标、事件、结构化日志
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)


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

    def log_start(self, config):
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

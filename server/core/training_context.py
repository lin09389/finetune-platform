"""
训练上下文管理模块（重构版）

修复：
- P0-4: 统一全局状态管理，使用依赖注入

提供：
- 统一的状态管理入口
- 生命周期管理
- 资源清理
"""
import atexit
import threading
from typing import Any, Optional

from core.config import Settings, get_settings
from core.logging import get_logger
from core.training_queue import TrainingQueue, get_training_queue, shutdown_queue
from core.training_state import (
    TrainingProgress,
    TrainingRecord,
    TrainingState,
    get_training_state,
)

logger = get_logger(__name__)


class TrainingContext:
    """
    训练上下文管理器 - 统一管理所有训练相关状态

    修复：
    - P0-4: 统一全局状态管理
    - 使用依赖注入模式
    - 生命周期管理
    """

    _instance: Optional['TrainingContext'] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        settings: Settings | None = None,
        max_concurrent_training: int = 1,
        max_queue_size: int = 10
    ):
        if self._initialized:
            return

        self._settings = settings or get_settings()
        self._training_state: TrainingState | None = None
        self._training_queue: TrainingQueue | None = None
        self._max_concurrent_training = max_concurrent_training
        self._max_queue_size = max_queue_size
        self._initialized = True
        self._shutdown = False

        atexit.register(self.cleanup)

        logger.info("TrainingContext 初始化完成")

    @classmethod
    def get_instance(cls) -> 'TrainingContext':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """重置单例实例（用于测试）"""
        with cls._lock:
            if cls._instance:
                cls._instance.cleanup()
                cls._instance = None

    @property
    def settings(self) -> Settings:
        """获取配置"""
        return self._settings

    @property
    def state(self) -> TrainingState:
        """获取训练状态管理器"""
        if self._training_state is None:
            self._training_state = get_training_state(self._settings.outputs_dir_resolved)
        return self._training_state

    @property
    def queue(self) -> TrainingQueue:
        """获取训练队列"""
        if self._training_queue is None:
            self._training_queue = get_training_queue(
                max_concurrent=self._max_concurrent_training,
                max_queue_size=self._max_queue_size,
                state_file=self._settings.outputs_dir_resolved / "queue_state.json"
            )
        return self._training_queue

    def is_training(self) -> bool:
        """检查是否正在训练"""
        return self.state.is_training()

    def get_progress(self) -> TrainingProgress:
        """获取训练进度"""
        return self.state.get_progress()

    def get_current_record(self) -> TrainingRecord | None:
        """获取当前训练记录"""
        return self.state.get_current_record()

    def get_history(self) -> list:
        """获取训练历史"""
        return self.state.get_history()

    def get_status(self) -> dict[str, Any]:
        """获取完整状态"""
        return {
            "training": self.state.get_status(),
            "queue": self.queue.get_queue_status(),
            "settings": {
                "outputs_dir": str(self._settings.outputs_dir_resolved),
                "models_dir": str(self._settings.models_dir_resolved),
                "datasets_dir": str(self._settings.datasets_dir_resolved),
            }
        }

    def cleanup(self):
        """清理所有资源"""
        if self._shutdown:
            return

        self._shutdown = True
        logger.info("开始清理 TrainingContext 资源...")

        try:
            if self._training_state:
                self._training_state.cleanup()
                self._training_state = None
        except Exception as e:
            logger.error(f"清理 TrainingState 失败：{e}")

        try:
            shutdown_queue()
            self._training_queue = None
        except Exception as e:
            logger.error(f"清理 TrainingQueue 失败：{e}")

        logger.info("TrainingContext 资源清理完成")

    def __del__(self):
        """析构函数"""
        self.cleanup()


_context: TrainingContext | None = None
_context_lock = threading.Lock()


def get_training_context() -> TrainingContext:
    """获取训练上下文实例"""
    global _context

    with _context_lock:
        if _context is None:
            _context = TrainingContext.get_instance()
        return _context


def reset_training_context():
    """重置训练上下文（用于测试）"""
    global _context

    with _context_lock:
        if _context:
            _context.cleanup()
            _context = None
        TrainingContext.reset_instance()


def init_training_context(
    settings: Settings | None = None,
    max_concurrent_training: int = 1,
    max_queue_size: int = 10
) -> TrainingContext:
    """初始化训练上下文"""
    global _context

    with _context_lock:
        if _context is not None:
            _context.cleanup()

        _context = TrainingContext(
            settings=settings,
            max_concurrent_training=max_concurrent_training,
            max_queue_size=max_queue_size
        )
        return _context


def shutdown_training_context():
    """关闭训练上下文"""
    global _context

    with _context_lock:
        if _context:
            _context.cleanup()
            _context = None

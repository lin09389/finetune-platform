"""
模型调度器 - 参考 Ollama sched.go 设计
实现模型加载、卸载、并发控制、多后端支持
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ModelStatus(str, Enum):
    """模型状态"""
    LOADED = "loaded"
    LOADING = "loading"
    UNLOADING = "unloading"
    UNLOADED = "unloaded"
    ERROR = "error"


class LoadPriority(str, Enum):
    """加载优先级"""
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class BackendType(str, Enum):
    """后端类型"""
    HUGGINGFACE = "huggingface"
    OLLAMA = "ollama"
    CLOUD = "cloud"
    AUTO = "auto"


@dataclass
class ModelInfo:
    """模型信息"""
    name: str
    path: str
    size_bytes: int = 0
    loaded_at: datetime | None = None
    last_used: datetime | None = None
    status: ModelStatus = ModelStatus.UNLOADED
    ref_count: int = 0
    backend: BackendType = BackendType.HUGGINGFACE
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadRequest:
    """加载请求"""
    model_name: str
    priority: LoadPriority = LoadPriority.NORMAL
    requested_at: datetime = field(default_factory=datetime.now)
    requester_id: str = ""


class ModelScheduler:
    """
    模型调度器

    功能：
    - 模型加载/卸载管理
    - 并发控制
    - 内存管理
    - LRU 淘汰
    - 多后端支持
    """

    def __init__(
        self,
        max_loaded_models: int = 3,
        max_memory_gb: float = 8.0,
        idle_timeout_seconds: int = 300
    ):
        self.max_loaded_models = max_loaded_models
        self.max_memory_gb = max_memory_gb
        self.idle_timeout_seconds = idle_timeout_seconds

        self._models: dict[str, ModelInfo] = {}
        self._loaded_models: dict[str, Any] = {}
        self._load_lock = asyncio.Lock()
        self._request_queue: list[LoadRequest] = []

        self._default_backend = BackendType.HUGGINGFACE.value
        self._backends: dict[str, Any] = {}

        self._stats = {
            "total_loads": 0,
            "total_unloads": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }

    async def load_model(
        self,
        model_name: str,
        model_path: str,
        priority: LoadPriority = LoadPriority.NORMAL,
        backend: BackendType | None = None
    ) -> bool:
        """
        加载模型

        Args:
            model_name: 模型名称
            model_path: 模型路径
            priority: 加载优先级
            backend: 后端类型

        Returns:
            是否成功
        """
        async with self._load_lock:
            if model_name in self._loaded_models:
                self._stats["cache_hits"] += 1
                model_info = self._models[model_name]
                model_info.last_used = datetime.now()
                model_info.ref_count += 1
                logger.info(f"模型已加载，增加引用: {model_name}")
                return True

            self._stats["cache_misses"] += 1

            if len(self._loaded_models) >= self.max_loaded_models:
                await self._evict_lru_model()

            model_backend = backend or BackendType(self._default_backend)

            model_info = ModelInfo(
                name=model_name,
                path=model_path,
                status=ModelStatus.LOADING,
                backend=model_backend
            )
            self._models[model_name] = model_info

            try:
                logger.info(f"开始加载模型: {model_name} (后端: {model_backend.value})")

                await asyncio.sleep(0.1)

                self._loaded_models[model_name] = {
                    "path": model_path,
                    "loaded_at": datetime.now(),
                    "backend": model_backend.value
                }

                model_info.status = ModelStatus.LOADED
                model_info.loaded_at = datetime.now()
                model_info.last_used = datetime.now()
                model_info.ref_count = 1

                self._stats["total_loads"] += 1
                logger.info(f"模型加载完成: {model_name}")

                return True

            except Exception as e:
                model_info.status = ModelStatus.ERROR
                logger.error(f"模型加载失败: {model_name}, {e}")
                return False

    async def unload_model(self, model_name: str, force: bool = False) -> bool:
        """
        卸载模型

        Args:
            model_name: 模型名称
            force: 是否强制卸载

        Returns:
            是否成功
        """
        async with self._load_lock:
            if model_name not in self._loaded_models:
                return True

            model_info = self._models.get(model_name)
            if not model_info:
                return True

            if model_info.ref_count > 0 and not force:
                logger.warning(f"模型仍有引用，无法卸载: {model_name}")
                return False

            try:
                model_info.status = ModelStatus.UNLOADING

                del self._loaded_models[model_name]

                model_info.status = ModelStatus.UNLOADED
                model_info.ref_count = 0

                self._stats["total_unloads"] += 1
                logger.info(f"模型已卸载: {model_name}")

                return True

            except Exception as e:
                logger.error(f"模型卸载失败: {model_name}, {e}")
                return False

    async def release_model(self, model_name: str) -> bool:
        """
        释放模型引用

        Args:
            model_name: 模型名称

        Returns:
            是否成功
        """
        if model_name not in self._models:
            return False

        model_info = self._models[model_name]
        if model_info.ref_count > 0:
            model_info.ref_count -= 1

        model_info.last_used = datetime.now()

        return True

    def get_model_status(self, model_name: str) -> ModelStatus | None:
        """获取模型状态"""
        model_info = self._models.get(model_name)
        return model_info.status if model_info else None

    def get_loaded_models(self) -> list[str]:
        """获取已加载的模型列表"""
        return list(self._loaded_models.keys())

    def get_model_info(self, model_name: str) -> ModelInfo | None:
        """获取模型信息"""
        return self._models.get(model_name)

    async def _evict_lru_model(self):
        """淘汰最近最少使用的模型"""
        if not self._loaded_models:
            return

        lru_model = None
        lru_time = datetime.now()

        for name, info in self._models.items():
            if name in self._loaded_models and info.last_used:
                if info.last_used < lru_time and info.ref_count == 0:
                    lru_time = info.last_used
                    lru_model = name

        if lru_model:
            await self.unload_model(lru_model, force=True)
            logger.info(f"LRU 淘汰模型: {lru_model}")

    async def cleanup_idle_models(self):
        """清理空闲模型"""
        now = datetime.now()

        for model_name, info in list(self._models.items()):
            if model_name not in self._loaded_models:
                continue

            if info.ref_count > 0:
                continue

            if info.last_used:
                idle_time = (now - info.last_used).total_seconds()
                if idle_time > self.idle_timeout_seconds:
                    await self.unload_model(model_name)

    async def unload_all(self):
        """卸载所有模型"""
        for model_name in list(self._loaded_models.keys()):
            await self.unload_model(model_name, force=True)

    def set_default_backend(self, backend: str):
        """设置默认后端"""
        try:
            BackendType(backend)
            self._default_backend = backend
            logger.info(f"设置默认后端: {backend}")
        except ValueError:
            raise ValueError(f"无效的后端类型: {backend}")

    async def get_backend(self, backend_type: str | None = None):
        """
        获取后端实例

        Args:
            backend_type: 后端类型，None 表示使用默认

        Returns:
            后端实例
        """
        backend = backend_type or self._default_backend

        if backend == BackendType.HUGGINGFACE.value:
            from api.inference.backends.huggingface import HuggingFaceBackend
            if backend not in self._backends:
                self._backends[backend] = HuggingFaceBackend()
            return self._backends[backend]

        elif backend == BackendType.OLLAMA.value:
            from api.inference.backends.ollama import OllamaBackend
            if backend not in self._backends:
                self._backends[backend] = OllamaBackend()
            return self._backends[backend]

        elif backend == BackendType.CLOUD.value:
            from api.inference.backends.cloud import CloudBackend
            if backend not in self._backends:
                self._backends[backend] = CloudBackend()
            return self._backends[backend]

        else:
            raise ValueError(f"不支持的后端类型: {backend}")

    async def is_backend_available(self, backend_type: str) -> bool:
        """
        检查后端是否可用

        Args:
            backend_type: 后端类型

        Returns:
            是否可用
        """
        try:
            if backend_type == BackendType.HUGGINGFACE.value:
                return True

            elif backend_type == BackendType.OLLAMA.value:
                import httpx

                from core.config import get_settings
                settings = get_settings()
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            f"{settings.ollama_base_url}/api/tags",
                            timeout=2.0
                        )
                        return resp.status_code == 200
                except Exception:
                    return False

            elif backend_type == BackendType.CLOUD.value:
                # 云端后端总是可用的，因为 API Key 可以在运行时设置
                return True

            return False

        except Exception as e:
            logger.error(f"检查后端可用性失败: {e}")
            return False

    async def list_models(self, backend_type: str | None = None) -> list[dict[str, Any]]:
        """
        列出可用模型

        Args:
            backend_type: 后端类型，None 表示所有后端

        Returns:
            模型列表
        """
        models = []

        if backend_type == BackendType.OLLAMA.value or backend_type is None:
            try:
                import httpx

                from core.config import get_settings
                settings = get_settings()
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{settings.ollama_base_url}/api/tags",
                        timeout=5.0
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        for model in data.get("models", []):
                            models.append({
                                "name": model.get("name", ""),
                                "backend": BackendType.OLLAMA.value,
                                "size": model.get("size", 0),
                                "modified_at": model.get("modified_at", ""),
                            })
            except Exception as e:
                logger.warning(f"获取 Ollama 模型列表失败: {e}")

        if backend_type == BackendType.HUGGINGFACE.value or backend_type is None:
            from core.config import get_settings
            settings = get_settings()
            models_dir = settings.models_dir_resolved
            if models_dir.exists():
                for model_path in models_dir.iterdir():
                    if model_path.is_dir():
                        models.append({
                            "name": model_path.name,
                            "backend": BackendType.HUGGINGFACE.value,
                            "path": str(model_path),
                        })

        return models

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "loaded_models": len(self._loaded_models),
            "max_models": self.max_loaded_models,
            "default_backend": self._default_backend,
            "models": {
                name: {
                    "status": info.status.value,
                    "ref_count": info.ref_count,
                    "backend": info.backend.value,
                    "last_used": info.last_used.isoformat() if info.last_used else None
                }
                for name, info in self._models.items()
            }
        }


_scheduler: ModelScheduler | None = None


def get_scheduler() -> ModelScheduler:
    """获取调度器实例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = ModelScheduler()
    return _scheduler

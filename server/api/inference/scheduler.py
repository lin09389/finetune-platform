"""
模型调度器 - 参考 Ollama sched.go 设计
实现模型加载、卸载、并发控制、多后端支持
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
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
    LLAMACPP = "llama-cpp"
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
        self._release_cond = asyncio.Condition()
        self._request_queue: list[LoadRequest] = []

        self._default_backend = BackendType.HUGGINGFACE.value
        self._backends: dict[str, Any] = {}

        self._stats = {
            "total_loads": 0,
            "total_unloads": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "active_leases": 0,
        }

    def _resolve_backend_type(self, backend: BackendType | str | None) -> BackendType:
        if backend is None:
            return BackendType(self._default_backend)
        if isinstance(backend, BackendType):
            return backend
        return BackendType(backend)

    def _get_loaded_model_for_backend(self, backend: BackendType) -> str | None:
        for name, info in self._models.items():
            if name in self._loaded_models and info.backend == backend:
                return name
        return None

    def resolve_model_path(self, model_name: str, backend: BackendType | str | None = None) -> str:
        """将模型名解析为本地实际路径。"""
        model_backend = self._resolve_backend_type(backend)
        path = Path(model_name)
        if path.exists():
            return str(path)

        from core.config import get_settings

        settings = get_settings()
        candidate = settings.models_dir_resolved / model_name
        if candidate.exists():
            return str(candidate)

        if model_backend == BackendType.LLAMACPP:
            for suffix in (".gguf", ".ggml"):
                suffixed = settings.models_dir_resolved / f"{model_name}{suffix}"
                if suffixed.exists():
                    return str(suffixed)

        return model_name

    async def _wait_until_released(self, model_name: str, timeout: float = 120.0) -> bool:
        """Wait for active leases without ever invalidating an in-flight request."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            info = self._models.get(model_name)
            if info is None or info.ref_count == 0:
                return True
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                logger.warning("等待模型租约释放超时: %s", model_name)
                return False
            async with self._release_cond:
                try:
                    await asyncio.wait_for(self._release_cond.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    return False

    async def _ensure_model_loaded(
        self,
        model_name: str,
        model_path: str,
        backend: BackendType | None = None,
        **kwargs,
    ) -> bool:
        # Refuse new loads while training holds the cross-process GPU lease.
        # Claim only when actually loading; release when last model unloads or load fails idle.
        try:
            from core.gpu_coordination import (
                GpuCoordinationError,
                assert_inference_gpu_available,
                claim_inference_gpu,
                release_inference_gpu,
            )

            assert_inference_gpu_available()
        except GpuCoordinationError as exc:
            logger.warning("Inference load refused by GPU coordination: %s", exc)
            return False
        except Exception as exc:
            logger.debug("GPU coordination check skipped: %s", exc)

            def claim_inference_gpu(*_a, **_k):  # type: ignore[misc]
                return None

            def release_inference_gpu(*_a, **_k):  # type: ignore[misc]
                return None

        model_backend = self._resolve_backend_type(backend)
        now = datetime.now()

        existing = self._models.get(model_name)
        if existing and model_name in self._loaded_models and existing.status == ModelStatus.LOADED:
            loaded_policy = existing.metadata.get("runtime_policy") or {}
            loaded_adapter = loaded_policy.get("lora_adapter")
            requested_adapter = kwargs.get("lora_adapter")
            loaded_model_path = loaded_policy.get("model_path") or existing.path
            if (
                loaded_adapter == requested_adapter
                and loaded_model_path == model_path
                and existing.backend == model_backend
            ):
                self._stats["cache_hits"] += 1
                existing.last_used = now
                return True

            if existing.ref_count > 0:
                logger.info(
                    "模型运行时变体冲突，等待当前租约释放: %s "
                    "(loaded_path=%s, requested_path=%s, loaded_adapter=%s, requested_adapter=%s)",
                    model_name,
                    loaded_model_path,
                    model_path,
                    loaded_adapter,
                    requested_adapter,
                )
                if not await self._wait_until_released(model_name):
                    return False

            logger.info(
                "模型运行时变体变化，重新加载: %s "
                "(loaded_path=%s, requested_path=%s, loaded_adapter=%s, requested_adapter=%s)",
                model_name,
                loaded_model_path,
                model_path,
                loaded_adapter,
                requested_adapter,
            )
            if not await self._unload_model_locked(model_name, force=True):
                return False

        self._stats["cache_misses"] += 1

        if len(self._loaded_models) >= self.max_loaded_models:
            await self._evict_lru_model()

        current_backend_model = self._get_loaded_model_for_backend(model_backend)
        if current_backend_model and current_backend_model != model_name:
            if not await self._wait_until_released(current_backend_model):
                return False
            if not await self._unload_model_locked(current_backend_model, force=False):
                return False

        model_info = existing or ModelInfo(
            name=model_name,
            path=model_path,
            backend=model_backend,
        )
        model_info.path = model_path
        model_info.backend = model_backend
        model_info.status = ModelStatus.LOADING
        model_info.metadata.setdefault("warmup_runs", 0)
        self._models[model_name] = model_info

        from core.model_warmup import get_model_warmup_manager
        from core.runtime_policy import build_runtime_policy

        runtime_policy = build_runtime_policy(
            model_path=model_path,
            backend=model_backend.value,
            options=kwargs,
        )

        backend_instance = await self.get_backend(model_backend.value)
        load_started_at = datetime.now()
        claimed = False
        try:
            claim_inference_gpu(owner=f"inference:{model_name}")
            claimed = True
            logger.info(f"开始加载模型: {model_name} (后端: {model_backend.value})")
            success = await backend_instance.load_model(model_path, runtime_policy=runtime_policy, **kwargs)
            if not success:
                model_info.status = ModelStatus.ERROR
                if claimed and not self._loaded_models:
                    release_inference_gpu(owner=f"inference:{model_name}")
                return False

            model_info.status = ModelStatus.LOADED
            model_info.loaded_at = now
            model_info.last_used = now
            model_info.metadata["runtime_policy"] = runtime_policy
            model_info.metadata["quantization"] = runtime_policy.get("quantization", {})
            model_info.metadata["load_duration_ms"] = (
                datetime.now() - load_started_at
            ).total_seconds() * 1000

            if runtime_policy.get("warmup_enabled"):
                warmup_result = await get_model_warmup_manager().warmup_model(
                    model_name=model_name,
                    backend=backend_instance,
                    prompt=runtime_policy.get("warmup_prompt", "Hello"),
                )
                model_info.metadata["warmup"] = warmup_result
                if warmup_result.get("success"):
                    model_info.metadata["warmup_runs"] = model_info.metadata.get("warmup_runs", 0) + 1

            self._loaded_models[model_name] = {
                "path": model_path,
                "loaded_at": now,
                "backend": model_backend.value,
            }
            self._stats["total_loads"] += 1
            logger.info(f"模型加载完成: {model_name}")
            return True
        except Exception as exc:
            model_info.status = ModelStatus.ERROR
            model_info.metadata["error"] = str(exc)
            logger.error(f"模型加载失败: {model_name}, {exc}")
            if claimed and not self._loaded_models:
                try:
                    release_inference_gpu(owner=f"inference:{model_name}")
                except Exception:
                    pass
            return False

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
            return await self._ensure_model_loaded(
                model_name=model_name,
                model_path=model_path,
                backend=backend,
                priority=priority.value,
            )

    async def acquire_model(
        self,
        model_name: str,
        model_path: str,
        backend: BackendType | str | None = None,
        **kwargs,
    ) -> ModelInfo | None:
        """获取模型租约，确保模型已真实加载。"""
        acquired_info = None
        try:
            async with self._load_lock:
                success = await self._ensure_model_loaded(
                    model_name=model_name,
                    model_path=model_path,
                    backend=backend,
                    **kwargs,
                )
                if not success:
                    return None

                model_info = self._models[model_name]
                model_info.ref_count += 1
                model_info.last_used = datetime.now()
                self._stats["active_leases"] += 1
                acquired_info = model_info
                return model_info
        except asyncio.CancelledError:
            # 如果在获取到租约后被取消，必须同步回滚
            if acquired_info:
                acquired_info.ref_count -= 1
                if self._stats["active_leases"] > 0:
                    self._stats["active_leases"] -= 1

                if acquired_info.ref_count == 0:
                    # 异步通知其他等待的协程
                    async def _notify():
                        async with self._release_cond:
                            self._release_cond.notify_all()
                    # 把通知推入后台任务
                    asyncio.create_task(_notify())
            raise

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
            return await self._unload_model_locked(model_name, force=force)

    async def _unload_model_locked(self, model_name: str, force: bool = False) -> bool:
        if model_name not in self._loaded_models:
            return True

        model_info = self._models.get(model_name)
        if not model_info:
            return True

        if model_info.ref_count > 0 and not force:
            logger.warning(f"模型仍有引用，无法卸载: {model_name}")
            return False

        if force and model_info.ref_count > 0:
            logger.warning(f"强制卸载被占用的模型: {model_name} (引用计数: {model_info.ref_count})")
            if self._stats["active_leases"] >= model_info.ref_count:
                self._stats["active_leases"] -= model_info.ref_count
            else:
                self._stats["active_leases"] = 0
            model_info.ref_count = 0

        try:
            model_info.status = ModelStatus.UNLOADING
            backend = await self.get_backend(model_info.backend.value)
            if hasattr(backend, "unload_model"):
                await backend.unload_model()

            del self._loaded_models[model_name]

            model_info.status = ModelStatus.UNLOADED
            model_info.ref_count = 0

            self._stats["total_unloads"] += 1
            logger.info(f"模型已卸载: {model_name}")

            # Release cross-process inference lease when GPU is idle again.
            if not self._loaded_models:
                try:
                    from core.gpu_coordination import release_inference_gpu

                    release_inference_gpu()
                except Exception as lease_exc:
                    logger.debug("GPU inference lease release skipped: %s", lease_exc)

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
            if self._stats["active_leases"] > 0:
                self._stats["active_leases"] -= 1

        model_info.last_used = datetime.now()
        async with self._release_cond:
            self._release_cond.notify_all()

        return True

    async def unload_least_used(self) -> bool:
        """卸载当前最不活跃且无引用的模型。"""
        async with self._load_lock:
            candidates = [
                info for name, info in self._models.items()
                if name in self._loaded_models and info.ref_count == 0 and info.last_used is not None
            ]
            if not candidates:
                return False
            victim = min(candidates, key=lambda item: item.last_used or datetime.max)
            return await self._unload_model_locked(victim.name, force=True)

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
            if (
                name in self._loaded_models
                and info.last_used
                and info.last_used < lru_time
                and info.ref_count == 0
            ):
                lru_time = info.last_used
                lru_model = name

        if lru_model:
            await self._unload_model_locked(lru_model, force=True)
            logger.info(f"LRU 淘汰模型: {lru_model}")

    async def shutdown(self):
        """关闭调度器并清理所有后端资源"""
        logger.info("Shutting down ModelScheduler and cleaning up backends...")
        try:
            await self.unload_all()
        except Exception as e:
            logger.warning("unload_all during scheduler shutdown failed: %s", e)
        for name, backend in self._backends.items():
            try:
                if hasattr(backend, "cleanup"):
                    if asyncio.iscoroutinefunction(backend.cleanup):
                        await backend.cleanup()
                    else:
                        backend.cleanup()
                logger.info(f"Cleaned up backend: {name}")
            except Exception as e:
                logger.error(f"Error cleaning up backend {name}: {e}")
        self._backends.clear()
        try:
            from core.gpu_coordination import release_inference_gpu

            release_inference_gpu()
        except Exception as lease_exc:
            logger.debug("GPU inference lease release on shutdown skipped: %s", lease_exc)

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
        if backend == BackendType.AUTO.value:
            backend = self._default_backend

        if backend == BackendType.HUGGINGFACE.value:
            from api.inference.backends.huggingface import HuggingFaceBackend
            if backend not in self._backends:
                self._backends[backend] = HuggingFaceBackend()
            return self._backends[backend]

        elif backend == BackendType.OLLAMA.value:
            from api.inference.backends.ollama_resilient import OllamaResilientBackend
            if backend not in self._backends:
                from core.config import get_settings
                settings = get_settings()
                self._backends[backend] = OllamaResilientBackend({
                    "base_url": settings.ollama_base_url,
                    "timeout": settings.ollama_timeout_seconds,
                    "stream_read_timeout": settings.ollama_stream_read_timeout_seconds,
                    "max_connections": settings.ollama_max_connections,
                    "max_retries": settings.ollama_max_retries,
                    "retry_delay": settings.ollama_retry_delay_seconds,
                    "disable_thinking": settings.ollama_fast_mode,
                    "health_check_interval": 30,
                    "num_ctx": settings.ollama_num_ctx,
                    "num_batch": settings.ollama_num_batch,
                    "num_thread": settings.ollama_num_thread,
                    "num_gpu": settings.ollama_num_gpu
                })
            return self._backends[backend]

        elif backend == BackendType.CLOUD.value:
            from api.inference.backends.cloud import CloudBackend
            if backend not in self._backends:
                self._backends[backend] = CloudBackend()
            return self._backends[backend]

        elif backend == BackendType.LLAMACPP.value:
            from api.inference.backends.llama_cpp import LlamaCppBackend
            if backend not in self._backends:
                from core.config import get_settings
                settings = get_settings()
                self._backends[backend] = LlamaCppBackend({
                    "n_gpu_layers": getattr(settings, "llama_cpp_n_gpu_layers", -1),
                    "n_ctx": getattr(settings, "llama_cpp_n_ctx", 2048)
                })
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
                    # trust_env=False: Windows IE/system proxy must not intercept localhost Ollama.
                    async with httpx.AsyncClient(trust_env=False) as client:
                        resp = await client.get(
                            f"{settings.ollama_base_url}/api/tags",
                            timeout=2.0
                        )
                        return resp.status_code == 200
                except Exception:
                    return False

            elif backend_type == BackendType.LLAMACPP.value:
                import importlib.util

                return importlib.util.find_spec("llama_cpp") is not None

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
                # Bypass system HTTP proxy so local Ollama is reachable on Windows.
                async with httpx.AsyncClient(trust_env=False) as client:
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

        if backend_type == BackendType.HUGGINGFACE.value or backend_type == BackendType.LLAMACPP.value or backend_type is None:
            from core.config import get_settings
            settings = get_settings()
            models_dir = settings.models_dir_resolved
            if models_dir.exists():
                for model_path in models_dir.iterdir():
                    if backend_type == BackendType.LLAMACPP.value:
                        if model_path.is_file() and model_path.suffix.lower() in [".gguf", ".ggml"]:
                            models.append({
                                "name": model_path.name,
                                "backend": BackendType.LLAMACPP.value,
                                "path": str(model_path),
                            })
                    else:
                        if model_path.is_dir() or (model_path.is_file() and model_path.suffix.lower() in [".gguf", ".ggml"]):
                            models.append({
                                "name": model_path.name,
                                "backend": BackendType.LLAMACPP.value if model_path.is_file() else BackendType.HUGGINGFACE.value,
                                "path": str(model_path),
                            })

        return models

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        from core.model_warmup import get_model_warmup_manager

        return {
            **self._stats,
            "loaded_models": len(self._loaded_models),
            "max_models": self.max_loaded_models,
            "default_backend": self._default_backend,
            "queue_size": len(self._request_queue),
            "warmup": get_model_warmup_manager().get_all_results(),
            "models": {
                name: {
                    "status": info.status.value,
                    "ref_count": info.ref_count,
                    "backend": info.backend.value,
                    "path": info.path,
                    "last_used": info.last_used.isoformat() if info.last_used else None,
                    "loaded_at": info.loaded_at.isoformat() if info.loaded_at else None,
                    "metadata": info.metadata,
                }
                for name, info in self._models.items()
            },
            "backends": list(self._backends.keys()),
        }


_scheduler: ModelScheduler | None = None


def get_scheduler() -> ModelScheduler:
    """获取调度器实例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = ModelScheduler()
    return _scheduler

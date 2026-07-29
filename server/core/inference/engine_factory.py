"""
推理引擎工厂
实现开闭原则，支持动态注册新引擎
"""
import logging
from dataclasses import dataclass
from typing import Any

from .engine_base import (
    BaseInferenceEngine,
    ChatRequest,
    InferenceBackend,
    InferenceRequest,
    InferenceResponse,
)

logger = logging.getLogger(__name__)


@dataclass
class EngineConfig:
    """引擎配置"""
    backend: InferenceBackend
    model_id: str | None = None
    base_url: str | None = None
    device: str = "auto"
    load_in_8bit: bool = False
    load_in_4bit: bool = False
    timeout: int = 300
    extra: dict[str, Any] = None

    def __post_init__(self):
        if self.extra is None:
            self.extra = {}


class InferenceEngineFactory:
    """
    推理引擎工厂

    特性:
    - 支持动态注册新引擎类型
    - 支持多引擎实例管理
    - 支持配置驱动的引擎创建
    - 线程安全
    """

    _engines: dict[str, type[BaseInferenceEngine]] = {}
    _instances: dict[str, BaseInferenceEngine] = {}
    _default_engine: str | None = None

    @classmethod
    def register(cls, name: str, engine_class: type[BaseInferenceEngine]) -> None:
        """
        注册引擎类型

        Args:
            name: 引擎名称
            engine_class: 引擎类
        """
        cls._engines[name] = engine_class
        logger.info(f"注册推理引擎: {name} -> {engine_class.__name__}")

    @classmethod
    def unregister(cls, name: str) -> bool:
        """
        注销引擎类型

        Args:
            name: 引擎名称

        Returns:
            是否成功
        """
        if name in cls._engines:
            del cls._engines[name]
            if name in cls._instances:
                del cls._instances[name]
            return True
        return False

    @classmethod
    def create(cls, name: str, **kwargs) -> BaseInferenceEngine:
        """
        创建引擎实例

        Args:
            name: 引擎名称
            **kwargs: 引擎参数

        Returns:
            引擎实例

        Raises:
            ValueError: 引擎未注册
        """
        engine_class = cls._engines.get(name)
        if not engine_class:
            raise ValueError(f"未注册的引擎类型: {name}")

        return engine_class(**kwargs)

    @classmethod
    def get_or_create(cls, name: str, **kwargs) -> BaseInferenceEngine:
        """
        获取或创建引擎实例（单例模式）

        Args:
            name: 引擎名称
            **kwargs: 引擎参数

        Returns:
            引擎实例
        """
        instance_key = f"{name}:{hash(frozenset(kwargs.items()))}"

        if instance_key not in cls._instances:
            cls._instances[instance_key] = cls.create(name, **kwargs)

        return cls._instances[instance_key]

    @classmethod
    def create_from_config(cls, config: EngineConfig) -> BaseInferenceEngine:
        """
        从配置创建引擎

        Args:
            config: 引擎配置

        Returns:
            引擎实例
        """
        kwargs = {}

        if config.backend == InferenceBackend.HUGGINGFACE:
            kwargs.update({
                "device": config.device,
                "default_model": config.model_id,
            })
        elif config.backend == InferenceBackend.OLLAMA:
            kwargs.update({
                "base_url": config.base_url or "http://localhost:11434",
                "timeout": config.timeout,
                "default_model": config.model_id,
            })
        elif config.backend == InferenceBackend.LLAMACPP:
            kwargs.update({
                "default_model": config.model_id,
            })

        kwargs.update(config.extra)

        return cls.create(config.backend.value, **kwargs)

    @classmethod
    def get_registered_engines(cls) -> list[str]:
        """获取已注册的引擎列表"""
        return list(cls._engines.keys())

    @classmethod
    def set_default(cls, name: str) -> None:
        """设置默认引擎"""
        if name not in cls._engines:
            raise ValueError(f"未注册的引擎类型: {name}")
        cls._default_engine = name

    @classmethod
    def get_default(cls) -> BaseInferenceEngine | None:
        """获取默认引擎实例"""
        if cls._default_engine:
            return cls.get_or_create(cls._default_engine)
        return None

    @classmethod
    def clear_instances(cls) -> None:
        """清除所有实例"""
        cls._instances.clear()

    @classmethod
    def get_stats(cls) -> dict[str, Any]:
        """获取工厂统计信息"""
        return {
            "registered_engines": cls.get_registered_engines(),
            "instances_count": len(cls._instances),
            "default_engine": cls._default_engine,
        }


def register_default_engines() -> None:
    """注册默认引擎"""
    from .huggingface_engine import HuggingFaceEngine
    from .ollama_engine import OllamaEngine

    try:
        from .llama_cpp_engine import LlamaCppEngine
        InferenceEngineFactory.register("llama-cpp", LlamaCppEngine)
    except ImportError:
        logger.warning("未安装 llama-cpp-python，跳过 LlamaCppEngine 注册")

    InferenceEngineFactory.register("huggingface", HuggingFaceEngine)
    InferenceEngineFactory.register("ollama", OllamaEngine)

    InferenceEngineFactory.set_default("huggingface")

    logger.info("默认推理引擎已注册")


_factory_initialized = False


def get_engine_factory() -> type[InferenceEngineFactory]:
    """获取引擎工厂（自动初始化）"""
    global _factory_initialized
    if not _factory_initialized:
        register_default_engines()
        _factory_initialized = True
    return InferenceEngineFactory


def get_engine(backend: str | None = None, **kwargs) -> BaseInferenceEngine:
    """
    获取推理引擎实例

    Args:
        backend: 后端名称，None 使用默认
        **kwargs: 引擎参数

    Returns:
        引擎实例
    """
    factory = get_engine_factory()

    if backend:
        return factory.get_or_create(backend, **kwargs)

    engine = factory.get_default()
    if engine:
        return engine

    return factory.get_or_create("huggingface", **kwargs)


async def generate(
    prompt: str,
    model_id: str,
    backend: str | None = None,
    **kwargs,
) -> InferenceResponse:
    """
    快捷生成函数

    Args:
        prompt: 输入提示
        model_id: 模型 ID
        backend: 后端名称
        **kwargs: 其他参数

    Returns:
        推理响应
    """
    engine = get_engine(backend)

    request = InferenceRequest(
        model_id=model_id,
        prompt=prompt,
        **kwargs,
    )

    return await engine.generate(request)


async def chat(
    messages: list[dict[str, str]],
    model_id: str,
    backend: str | None = None,
    **kwargs,
) -> InferenceResponse:
    """
    快捷聊天函数

    Args:
        messages: 消息列表
        model_id: 模型 ID
        backend: 后端名称
        **kwargs: 其他参数

    Returns:
        推理响应
    """
    from .engine_base import ChatMessage

    engine = get_engine(backend)

    chat_messages = [
        ChatMessage(role=m["role"], content=m["content"])
        for m in messages
    ]

    request = ChatRequest(
        model_id=model_id,
        messages=chat_messages,
        **kwargs,
    )

    return await engine.chat(request)

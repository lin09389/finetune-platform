"""
推理引擎基类
定义统一的推理接口，实现开闭原则
"""
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class InferenceBackend(str, Enum):
    HUGGINGFACE = "huggingface"
    OLLAMA = "ollama"
    VLLM = "vllm"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    CUSTOM = "custom"


@dataclass
class InferenceRequest:
    """推理请求"""
    model_id: str
    prompt: str
    max_tokens: int = 1024
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 50
    repetition_penalty: float = 1.1
    stop_sequences: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatMessage:
    """聊天消息"""
    role: str
    content: str
    name: str | None = None


@dataclass
class ChatRequest:
    """聊天请求"""
    model_id: str
    messages: list[ChatMessage]
    max_tokens: int = 1024
    temperature: float = 0.7
    top_p: float = 0.9
    system_prompt: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InferenceResponse:
    """推理响应"""
    text: str
    tokens_generated: int
    processing_time_ms: float
    model_id: str
    backend: str
    finish_reason: str = "stop"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "tokens_generated": self.tokens_generated,
            "processing_time_ms": self.processing_time_ms,
            "model_id": self.model_id,
            "backend": self.backend,
            "finish_reason": self.finish_reason,
            "metadata": self.metadata,
        }


@dataclass
class StreamChunk:
    """流式响应块"""
    content: str
    done: bool = False
    tokens_so_far: int = 0
    finish_reason: str | None = None


class BaseInferenceEngine(ABC):
    """
    推理引擎抽象基类

    实现开闭原则：通过继承扩展新的推理后端
    实现接口隔离：分离必要方法和可选方法
    """

    def __init__(self):
        self._logger = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")
        self._loaded_models: dict[str, Any] = {}

    @property
    @abstractmethod
    def backend(self) -> InferenceBackend:
        """获取后端类型"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """获取引擎名称"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查引擎是否可用"""
        pass

    @abstractmethod
    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        """
        生成文本

        Args:
            request: 推理请求

        Returns:
            推理响应
        """
        pass

    @abstractmethod
    async def chat(self, request: ChatRequest) -> InferenceResponse:
        """
        聊天对话

        Args:
            request: 聊天请求

        Returns:
            推理响应
        """
        pass

    @abstractmethod
    def get_available_models(self) -> list[str]:
        """获取可用模型列表"""
        pass

    @abstractmethod
    def load_model(self, model_id: str) -> bool:
        """加载模型"""
        pass

    @abstractmethod
    def unload_model(self, model_id: str) -> bool:
        """卸载模型"""
        pass

    async def stream(self, request: InferenceRequest) -> AsyncGenerator[StreamChunk, None]:
        """
        流式生成（可选实现）

        默认实现：生成完整响应后一次性返回
        子类可重写以实现真正的流式输出
        """
        response = await self.generate(request)
        yield StreamChunk(
            content=response.text,
            done=True,
            tokens_so_far=response.tokens_generated,
            finish_reason=response.finish_reason,
        )

    def get_model_info(self, model_id: str) -> dict[str, Any] | None:
        """获取模型信息"""
        return self._loaded_models.get(model_id)

    def supports_streaming(self) -> bool:
        """是否支持流式生成"""
        return True

    def supports_chat(self) -> bool:
        """是否支持聊天模式"""
        return True

    def get_stats(self) -> dict[str, Any]:
        """获取引擎统计信息"""
        return {
            "backend": self.backend.value,
            "name": self.name,
            "available": self.is_available(),
            "models": self.get_available_models(),
            "loaded_models": list(self._loaded_models.keys()),
        }

    async def generate_with_retry(
        self,
        request: InferenceRequest,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> InferenceResponse:
        """
        带重试的生成

        Args:
            request: 推理请求
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）

        Returns:
            推理响应
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                return await self.generate(request)
            except Exception as e:
                last_error = e
                self._logger.warning(f"生成失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))

        raise RuntimeError(f"生成失败，已重试 {max_retries} 次: {last_error}")

    def _measure_time(self) -> 'TimeMeasurer':
        """创建时间测量器"""
        return TimeMeasurer()


class TimeMeasurer:
    """时间测量工具"""

    def __init__(self):
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, *args):
        self.end_time = time.time()

    @property
    def elapsed_ms(self) -> float:
        if self.start_time is None:
            return 0
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000


import asyncio  # noqa: E402

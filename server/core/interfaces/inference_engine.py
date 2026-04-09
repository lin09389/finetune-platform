"""
推理引擎接口 - 用于文本生成和对话
实现开闭原则，支持多种推理后端
"""
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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


@dataclass
class StreamChunk:
    """流式响应块"""
    content: str
    done: bool = False
    tokens_so_far: int = 0
    finish_reason: str | None = None


class InferenceEngineInterface(ABC):
    """
    推理引擎接口

    定义文本生成和对话的标准接口，支持多种后端：
    - HuggingFace Transformers
    - Ollama
    - vLLM
    - OpenAI API
    - Anthropic API
    """

    @property
    @abstractmethod
    def backend(self) -> InferenceBackend:
        """
        获取后端类型

        Returns:
            后端类型
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """
        获取引擎名称

        Returns:
            引擎名称
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        检查引擎是否可用

        Returns:
            是否可用
        """
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
    async def stream(
        self,
        request: InferenceRequest
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        流式生成

        Args:
            request: 推理请求

        Yields:
            流式响应块
        """
        pass

    @abstractmethod
    def get_available_models(self) -> list[str]:
        """
        获取可用模型列表

        Returns:
            模型 ID 列表
        """
        pass

    @abstractmethod
    def load_model(self, model_id: str) -> bool:
        """
        加载模型

        Args:
            model_id: 模型 ID

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    def unload_model(self, model_id: str) -> bool:
        """
        卸载模型

        Args:
            model_id: 模型 ID

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    def get_model_info(self, model_id: str) -> dict[str, Any] | None:
        """
        获取模型信息

        Args:
            model_id: 模型 ID

        Returns:
            模型信息
        """
        pass

    def supports_streaming(self) -> bool:
        """
        是否支持流式生成

        Returns:
            是否支持
        """
        return True

    def supports_chat(self) -> bool:
        """
        是否支持聊天模式

        Returns:
            是否支持
        """
        return True

    def get_stats(self) -> dict[str, Any]:
        """
        获取引擎统计信息

        Returns:
            统计信息
        """
        return {
            "backend": self.backend.value,
            "name": self.name,
            "available": self.is_available(),
            "models": self.get_available_models(),
        }

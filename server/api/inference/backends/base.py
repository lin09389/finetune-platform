"""
推理后端抽象基类 - 参考 Ollama 设计
"""
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import Any


class BackendType(str, Enum):
    """后端类型"""
    HUGGINGFACE = "huggingface"
    OLLAMA = "ollama"
    VLLM = "vllm"
    LLAMACPP = "llama-cpp"
    CLOUD = "cloud"


@dataclass
class GenerationConfig:
    """生成配置"""
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 50
    repetition_penalty: float = 1.0
    stop_sequences: list[str] = None
    stream: bool = False

    def __post_init__(self):
        if self.stop_sequences is None:
            self.stop_sequences = []


@dataclass
class GenerationResult:
    """生成结果"""
    text: str
    tokens_generated: int
    finish_reason: str
    model: str
    prompt_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class InferenceBackend(ABC):
    """
    推理后端抽象基类

    所有推理后端都需要实现此接口
    """

    backend_type: BackendType = None

    def __init__(self, config: dict[str, Any] = None):
        self.config = config or {}
        self._model = None
        self._tokenizer = None
        self._is_loaded = False

    @abstractmethod
    async def load_model(self, model_name: str, **kwargs) -> bool:
        """
        加载模型

        Args:
            model_name: 模型名称或路径
            **kwargs: 额外参数

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    async def unload_model(self) -> bool:
        """
        卸载模型

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        config: GenerationConfig = None
    ) -> GenerationResult:
        """
        生成文本

        Args:
            prompt: 输入提示
            config: 生成配置

        Returns:
            生成结果
        """
        pass

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        config: GenerationConfig = None
    ) -> AsyncIterator[str]:
        """
        流式生成文本

        Args:
            prompt: 输入提示
            config: 生成配置

        Yields:
            生成的文本片段
        """
        pass

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        config: GenerationConfig = None
    ) -> GenerationResult:
        """
        对话生成

        Args:
            messages: 消息列表
            config: 生成配置

        Returns:
            生成结果
        """
        pass

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        config: GenerationConfig = None
    ) -> AsyncIterator[str]:
        """
        流式对话生成

        Args:
            messages: 消息列表
            config: 生成配置

        Yields:
            生成的文本片段
        """
        pass

    @abstractmethod
    def get_model_info(self) -> dict[str, Any]:
        """
        获取模型信息

        Returns:
            模型信息字典
        """
        pass

    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        """
        计算 token 数量

        Args:
            text: 输入文本

        Returns:
            token 数量
        """
        pass

    def is_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self._is_loaded

    async def health_check(self) -> dict[str, Any]:
        """
        健康检查

        Returns:
            健康状态
        """
        return {
            "backend_type": self.backend_type.value if self.backend_type else "unknown",
            "is_loaded": self._is_loaded,
            "status": "healthy" if self._is_loaded else "not_loaded"
        }

    async def get_memory_usage(self) -> dict[str, Any]:
        """
        获取内存使用情况

        Returns:
            内存使用信息
        """
        return {
            "backend_type": self.backend_type.value if self.backend_type else "unknown",
            "memory_used_mb": 0,
            "memory_available_mb": 0
        }

    async def warmup(self, prompt: str = "Hello") -> bool:
        """
        预热模型

        Args:
            prompt: 预热提示

        Returns:
            是否成功
        """
        if not self._is_loaded:
            return False

        try:
            await self.generate(prompt, GenerationConfig(max_tokens=10))
            return True
        except Exception:
            return False

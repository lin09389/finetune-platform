"""
云端推理后端实现 - 支持 OpenAI、Anthropic 等
"""
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from ai.gateway import get_provider

from .base import BackendType, GenerationConfig, GenerationResult, InferenceBackend

logger = logging.getLogger(__name__)


class CloudBackend(InferenceBackend):
    """云端推理后端"""

    backend_type = BackendType.CLOUD

    PROVIDERS = {
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "default_model": "gpt-3.5-turbo"
        },
        "anthropic": {
            "base_url": "https://api.anthropic.com/v1",
            "default_model": "claude-3-sonnet-20240229"
        },
        "deepseek": {
            "base_url": "https://api.deepseek.com/v1",
            # deepseek-chat/reasoner are deprecated 2026-07-24; official names are v4-flash/v4-pro.
            "default_model": "deepseek-v4-flash",
        }
    }

    def __init__(self, config: dict[str, Any] = None):
        super().__init__(config)
        config = self.config

        self.provider = config.get("provider", "openai")
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url")
        self.model_name = config.get("model_name")

        self._client = None

    async def load_model(self, model_name: str, **kwargs) -> bool:
        """加载模型（云端模型无需加载）"""
        self.model_name = model_name or self.model_name

        if not self.api_key:
            logger.warning("API key not set")
            return False

        self._is_loaded = True
        logger.info(f"Cloud backend ready: {self.provider}/{self.model_name}")
        return True

    async def unload_model(self) -> bool:
        """卸载模型"""
        self._is_loaded = False
        self._client = None
        return True

    async def generate(
        self,
        prompt: str,
        config: GenerationConfig = None
    ) -> GenerationResult:
        """生成文本"""
        config = config or GenerationConfig()

        start_time = time.time()

        try:
            result = await self._call_api(
                messages=[{"role": "user", "content": prompt}],
                config=config
            )

            latency_ms = (time.time() - start_time) * 1000

            return GenerationResult(
                text=result.get("content", ""),
                tokens_generated=result.get("completion_tokens", 0),
                finish_reason=result.get("finish_reason", "stop"),
                model=self.model_name,
                prompt_tokens=result.get("prompt_tokens", 0),
                total_tokens=result.get("total_tokens", 0),
                latency_ms=latency_ms
            )

        except Exception as e:
            logger.error(f"Cloud generation failed: {e}")
            return GenerationResult(
                text="",
                tokens_generated=0,
                finish_reason="error",
                model=self.model_name,
                metadata={"error": str(e)}
            )

    async def generate_stream(
        self,
        prompt: str,
        config: GenerationConfig = None
    ) -> AsyncIterator[str]:
        """流式生成文本"""
        config = config or GenerationConfig()

        try:
            async for chunk in self._stream_api(
                messages=[{"role": "user", "content": prompt}],
                config=config
            ):
                yield chunk
        except Exception as e:
            logger.error(f"Cloud stream failed: {e}")
            yield f"[Error: {e}]"

    async def chat(
        self,
        messages: list[dict[str, str]],
        config: GenerationConfig = None
    ) -> GenerationResult:
        """对话生成"""
        config = config or GenerationConfig()

        start_time = time.time()

        try:
            result = await self._call_api(messages, config)

            latency_ms = (time.time() - start_time) * 1000

            return GenerationResult(
                text=result.get("content", ""),
                tokens_generated=result.get("completion_tokens", 0),
                finish_reason=result.get("finish_reason", "stop"),
                model=self.model_name,
                prompt_tokens=result.get("prompt_tokens", 0),
                total_tokens=result.get("total_tokens", 0),
                latency_ms=latency_ms
            )

        except Exception as e:
            logger.error(f"Cloud chat failed: {e}")
            return GenerationResult(
                text="",
                tokens_generated=0,
                finish_reason="error",
                model=self.model_name,
                metadata={"error": str(e)}
            )

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        config: GenerationConfig = None
    ) -> AsyncIterator[str]:
        """流式对话生成"""
        config = config or GenerationConfig()

        try:
            async for chunk in self._stream_api(messages, config):
                yield chunk
        except Exception as e:
            logger.error(f"Cloud chat stream failed: {e}")
            yield f"[Error: {e}]"

    def get_model_info(self) -> dict[str, Any]:
        """获取模型信息"""
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "is_loaded": self._is_loaded,
            "backend_type": self.backend_type.value
        }

    async def count_tokens(self, text: str) -> int:
        """计算 token 数量（估算）"""
        return len(text) // 4

    async def _call_api(
        self,
        messages: list[dict[str, str]],
        config: GenerationConfig
    ) -> dict[str, Any]:
        """调用 API"""
        provider = get_provider(
            self.provider,
            group_id=self.config.get("group_id", ""),
            base_url=self.base_url or "",
            version=self.config.get("version", ""),
        )
        if provider is None:
            raise ValueError(f"Unsupported cloud provider: {self.provider}")
        if not self.api_key:
            raise ValueError("API key not set")

        model = self.model_name or provider.get_default_model()
        response = await provider.chat(
            messages=messages,
            model=model,
            api_key=self.api_key,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            top_p=config.top_p,
        )
        usage = response.get("usage", {}) or {}
        return {
            "content": response.get("content", ""),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "finish_reason": response.get("finish_reason", "stop")
        }

    async def _stream_api(
        self,
        messages: list[dict[str, str]],
        config: GenerationConfig
    ) -> AsyncIterator[str]:
        """流式调用 API"""
        provider = get_provider(
            self.provider,
            group_id=self.config.get("group_id", ""),
            base_url=self.base_url or "",
            version=self.config.get("version", ""),
        )
        if provider is None:
            raise ValueError(f"Unsupported cloud provider: {self.provider}")
        if not self.api_key:
            raise ValueError("API key not set")

        model = self.model_name or provider.get_default_model()
        async for chunk in provider.chat_stream(
            messages=messages,
            model=model,
            api_key=self.api_key,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            top_p=config.top_p,
        ):
            content = chunk.get("content", "")
            if content:
                yield content

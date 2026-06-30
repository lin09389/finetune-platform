"""
Ollama 推理引擎
通过 HTTP API 与 Ollama 服务通信
"""
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp

from .engine_base import (
    BaseInferenceEngine,
    ChatRequest,
    InferenceBackend,
    InferenceRequest,
    InferenceResponse,
    StreamChunk,
)

logger = logging.getLogger(__name__)


class OllamaEngine(BaseInferenceEngine):
    """
    Ollama 推理引擎

    特性:
    - 支持远程 Ollama 服务
    - 支持流式生成
    - 自动检测服务可用性
    - 支持模型拉取和管理
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        timeout: int = 300,
        default_model: str | None = None,
    ):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.default_model = default_model
        self._available_models: list[str] = []

    @property
    def backend(self) -> InferenceBackend:
        return InferenceBackend.OLLAMA

    @property
    def name(self) -> str:
        return "Ollama"

    def is_available(self) -> bool:
        """检查 Ollama 服务是否可用"""
        import requests
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                self._available_models = [m["name"] for m in data.get("models", [])]
                return True
        except Exception:
            pass
        return False

    def get_available_models(self) -> list[str]:
        """获取可用模型列表"""
        if not self._available_models:
            self.is_available()
        return self._available_models

    def load_model(self, model_id: str) -> bool:
        """
        拉取/加载模型

        Args:
            model_id: 模型名称

        Returns:
            是否成功
        """
        import requests
        try:
            self._logger.info(f"正在拉取模型: {model_id}")

            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model_id},
                timeout=self.timeout,
            )

            if response.status_code == 200:
                self._loaded_models[model_id] = {"model_id": model_id}
                if model_id not in self._available_models:
                    self._available_models.append(model_id)
                self._logger.info(f"模型拉取成功: {model_id}")
                return True

            self._logger.error(f"模型拉取失败: {response.text}")
            return False

        except Exception as e:
            self._logger.error(f"模型拉取失败: {e}")
            return False

    def unload_model(self, model_id: str) -> bool:
        """
        卸载模型（从内存中移除）

        Args:
            model_id: 模型名称

        Returns:
            是否成功
        """
        try:
            import requests

            requests.delete(
                f"{self.base_url}/api/unload",
                json={"name": model_id},
                timeout=30,
            )

            if model_id in self._loaded_models:
                del self._loaded_models[model_id]

            self._logger.info(f"模型已卸载: {model_id}")
            return True

        except Exception as e:
            self._logger.error(f"模型卸载失败: {e}")
            return False

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        """生成文本"""
        with self._measure_time() as timer:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": request.model_id,
                    "prompt": request.prompt,
                    "stream": False,
                    "options": {
                        "num_predict": request.max_tokens,
                        "temperature": request.temperature,
                        "top_p": request.top_p,
                        "top_k": request.top_k,
                        "repeat_penalty": request.repetition_penalty,
                    },
                }

                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"Ollama 请求失败: {response.status}")

                    data = await response.json()

        return InferenceResponse(
            text=data.get("response", ""),
            tokens_generated=data.get("eval_count", 0),
            processing_time_ms=timer.elapsed_ms,
            model_id=request.model_id,
            backend=self.backend.value,
            finish_reason="stop" if data.get("done") else "length",
        )

    async def chat(self, request: ChatRequest) -> InferenceResponse:
        """聊天对话"""
        messages = []

        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})

        for msg in request.messages:
            messages.append({"role": msg.role, "content": msg.content})

        with self._measure_time() as timer:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": request.model_id,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "num_predict": request.max_tokens,
                        "temperature": request.temperature,
                        "top_p": request.top_p,
                    },
                }

                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"Ollama 请求失败: {response.status}")

                    data = await response.json()

        message = data.get("message", {})

        return InferenceResponse(
            text=message.get("content", ""),
            tokens_generated=data.get("eval_count", 0),
            processing_time_ms=timer.elapsed_ms,
            model_id=request.model_id,
            backend=self.backend.value,
            finish_reason="stop" if data.get("done") else "length",
        )

    async def stream(self, request: InferenceRequest) -> AsyncGenerator[StreamChunk, None]:
        """流式生成"""
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": request.model_id,
                "prompt": request.prompt,
                "stream": True,
                "options": {
                    "num_predict": request.max_tokens,
                    "temperature": request.temperature,
                    "top_p": request.top_p,
                    "top_k": request.top_k,
                    "repeat_penalty": request.repetition_penalty,
                },
            }

            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                tokens_so_far = 0

                async for line in response.content:
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if "response" in data:
                        tokens_so_far += 1
                        yield StreamChunk(
                            content=data["response"],
                            done=False,
                            tokens_so_far=tokens_so_far,
                        )

                    if data.get("done"):
                        yield StreamChunk(
                            content="",
                            done=True,
                            tokens_so_far=tokens_so_far,
                            finish_reason="stop",
                        )
                        break

    def get_model_info(self, model_id: str) -> dict[str, Any] | None:
        """获取模型信息"""
        import requests
        try:
            response = requests.post(
                f"{self.base_url}/api/show",
                json={"name": model_id},
                timeout=30,
            )

            if response.status_code == 200:
                return response.json()
        except Exception:
            pass

        return None

    async def embed(self, model_id: str, prompt: str) -> list[float]:
        """
        生成嵌入向量

        Args:
            model_id: 嵌入模型名称
            prompt: 输入文本

        Returns:
            嵌入向量
        """
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": model_id,
                "prompt": prompt,
            }

            async with session.post(
                f"{self.base_url}/api/embeddings",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status != 200:
                    raise RuntimeError(f"Ollama 嵌入请求失败: {response.status}")

                data = await response.json()
                return data.get("embedding", [])

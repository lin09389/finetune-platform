"""
Ollama 推理后端 - 增强版(连接稳定性优化)
"""
import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import aiohttp
from aiohttp import ClientTimeout, TCPConnector

from .base import BackendType, GenerationConfig, GenerationResult, InferenceBackend

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """断路器模式 - 防止频繁重试失败的服务"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time: float | None = None
        self.state = "closed"  # closed, open, half_open
    
    def call(self, func):
        """装饰器模式调用"""
        async def wrapper(*args, **kwargs):
            if self.state == "open":
                if time.time() - (self.last_failure_time or 0) > self.recovery_timeout:
                    self.state = "half_open"
                    logger.info("Circuit breaker entering half-open state")
                else:
                    raise Exception("Circuit breaker is OPEN - service unavailable")
            
            try:
                result = await func(*args, **kwargs)
                if self.state == "half_open":
                    self.state = "closed"
                    self.failure_count = 0
                    logger.info("Circuit breaker closed - service recovered")
                return result
            except self.expected_exception as e:
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                if self.failure_count >= self.failure_threshold:
                    self.state = "open"
                    logger.error(f"Circuit breaker opened after {self.failure_count} failures")
                
                raise e
        
        return wrapper



class OllamaResilientBackend(InferenceBackend):
    """Ollama 推理后端 - 增强连接稳定性"""

    backend_type = BackendType.OLLAMA

    def __init__(self, config: dict[str, Any] = None):
        super().__init__(config or {})

        self.base_url = (config or {}).get("base_url", "http://localhost:11434")
        self.timeout = (config or {}).get("timeout", 60)
        self.stream_read_timeout = (config or {}).get("stream_read_timeout", 120)
        self.disable_thinking = bool((config or {}).get("disable_thinking", False))
        self.model_name = (config or {}).get("model_name", "llama2")
        
        # 连接池配置
        self.max_connections = (config or {}).get("max_connections", 10)
        self.keepalive_timeout = (config or {}).get("keepalive_timeout", 30)
        
        # 重试配置
        self.max_retries = (config or {}).get("max_retries", 3)
        self.retry_delay = (config or {}).get("retry_delay", 1.0)
        
        # 健康检查配置
        self.health_check_interval = (config or {}).get("health_check_interval", 30)
        self.last_health_check: float = 0
        self.is_healthy = True
        
        # 创建持久化的 ClientSession
        self._session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()
        
        # 断路器
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0,
            expected_exception=Exception
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建持久化的 ClientSession"""
        async with self._session_lock:
            if self._session is None or self._session.closed:
                connector = TCPConnector(
                    limit=self.max_connections,
                    limit_per_host=self.max_connections,
                    ttl_dns_cache=300,
                    keepalive_timeout=self.keepalive_timeout,
                    force_close=False,
                    enable_cleanup_closed=True
                )
                
                timeout = ClientTimeout(
                    total=self.timeout,
                    connect=10,
                    sock_read=self.stream_read_timeout,
                    sock_connect=10
                )
                
                self._session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                    raise_for_status=False
                )
                logger.info("Created new persistent aiohttp session for Ollama")
            
            return self._session

    async def _close_session(self):
        """关闭 ClientSession"""
        async with self._session_lock:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None
                logger.info("Closed aiohttp session for Ollama")

    async def _health_check_if_needed(self) -> bool:
        """按需健康检查"""
        now = time.time()
        if now - self.last_health_check < self.health_check_interval:
            return self.is_healthy
        
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/tags",
                timeout=ClientTimeout(total=5)
            ) as response:
                self.is_healthy = response.status == 200
                self.last_health_check = now
                return self.is_healthy
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            self.is_healthy = False
            self.last_health_check = now
            return False

    async def _retry_with_backoff(self, func, *args, **kwargs):
        """带指数退避的重试机制"""
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Ollama request failed (attempt {attempt + 1}/{self.max_retries}), "
                        f"retrying in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Ollama request failed after {self.max_retries} attempts")
        
        raise last_exception or Exception("Request failed")

    async def _iter_ndjson_objects(self, response: aiohttp.ClientResponse):
        """Iterate NDJSON objects from a chunked response safely."""
        import json

        buffer = b""
        async for chunk in response.content.iter_any():
            if not chunk:
                continue
            buffer += chunk
            while b"\n" in buffer:
                raw_line, buffer = buffer.split(b"\n", 1)
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line.decode("utf-8", errors="ignore"))
                except json.JSONDecodeError:
                    continue

        trailing = buffer.strip()
        if trailing:
            try:
                yield json.loads(trailing.decode("utf-8", errors="ignore"))
            except json.JSONDecodeError:
                pass


    async def load_model(self, model_name: str, **kwargs) -> bool:
        """加载模型"""
        self.model_name = model_name or self.model_name
        if not await self._health_check_if_needed():
            logger.warning("Ollama service is not healthy, attempting to load model anyway")

        async def _load():
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/pull",
                json={"name": self.model_name},
                timeout=ClientTimeout(total=self.timeout)
            ) as response:
                if response.status == 200:
                    self._is_loaded = True
                    logger.info(f"Ollama model loaded: {self.model_name}")
                    return True
                else:
                    logger.error(f"Failed to pull Ollama model: {response.status}")
                    return False

        try:
            return await self._retry_with_backoff(_load)
        except Exception as e:
            logger.warning(f"Ollama model pull failed, assuming model exists: {e}")
            self._is_loaded = True
            return True

    async def unload_model(self) -> bool:
        """卸载模型"""
        self._is_loaded = False
        return True

    async def generate(self, prompt: str, config: GenerationConfig = None) -> GenerationResult:
        """生成文本"""
        if not self._is_loaded:
            return GenerationResult(
                text="", tokens_generated=0, finish_reason="error",
                model=self.model_name, metadata={"error": "Model not loaded"}
            )

        config = config or GenerationConfig()
        start_time = time.time()

        async def _generate():
            session = await self._get_session()
            payload = {
                "model": self.model_name, "prompt": prompt, "stream": False,
                "options": {
                    "num_predict": config.max_tokens,
                    "temperature": config.temperature,
                    "top_p": config.top_p,
                    "top_k": config.top_k,
                    "repeat_penalty": config.repetition_penalty,
                    "stop": config.stop_sequences
                }
            }
            if self.disable_thinking:
                payload["think"] = False

            async with session.post(f"{self.base_url}/api/generate", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama API error {response.status}: {error_text}")

                result = await response.json()
                latency_ms = (time.time() - start_time) * 1000

                return GenerationResult(
                    text=result.get("response", ""),
                    tokens_generated=result.get("eval_count", 0),
                    finish_reason="stop",
                    model=self.model_name,
                    prompt_tokens=result.get("prompt_eval_count", 0),
                    total_tokens=result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
                    latency_ms=latency_ms
                )

        try:
            return await self.circuit_breaker.call(lambda: self._retry_with_backoff(_generate))()
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            return GenerationResult(
                text="", tokens_generated=0, finish_reason="error",
                model=self.model_name, metadata={"error": str(e)}
            )

    async def generate_stream(self, prompt: str, config: GenerationConfig = None) -> AsyncIterator[str]:
        """流式生成文本"""
        if not self._is_loaded:
            yield "[Error: Model not loaded]"
            return

        config = config or GenerationConfig()

        async def _stream():
            session = await self._get_session()
            payload = {
                "model": self.model_name, "prompt": prompt, "stream": True,
                "options": {
                    "num_predict": config.max_tokens,
                    "temperature": config.temperature,
                    "top_p": config.top_p,
                    "top_k": config.top_k,
                    "repeat_penalty": config.repetition_penalty,
                    "stop": config.stop_sequences
                },
                "keep_alive": "5m"
            }
            if self.disable_thinking:
                payload["think"] = False

            async with session.post(f"{self.base_url}/api/generate", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama API error {response.status}: {error_text}")

                async for data in self._iter_ndjson_objects(response):
                    if "response" in data:
                        yield data["response"]

        try:
            async for chunk in _stream():
                yield chunk
        except Exception as e:
            logger.error(f"Ollama stream failed: {e}")
            yield f"[Error: {e}]"


    async def chat(self, request, context=None) -> GenerationResult:
        """对话生成"""
        if hasattr(request, 'model'):
            model_name = request.model
            if model_name and model_name != self.model_name:
                self.model_name = model_name

            messages = [
                {"role": m.role.value if hasattr(m.role, 'value') else m.role, "content": m.content}
                for m in request.messages
            ]

            config = GenerationConfig(
                max_tokens=request.options.max_tokens if hasattr(request, 'options') and request.options else 512,
                temperature=request.options.temperature if hasattr(request, 'options') and request.options else 0.7,
                top_p=request.options.top_p if hasattr(request, 'options') and request.options else 0.9,
                top_k=request.options.top_k if hasattr(request, 'options') and request.options else 50,
                repetition_penalty=request.options.repetition_penalty if hasattr(request, 'options') and request.options else 1.0,
            )
        else:
            messages = request if isinstance(request, list) else []
            config = GenerationConfig()

        if not self._is_loaded:
            await self.load_model(self.model_name)

        start_time = time.time()

        async def _chat():
            session = await self._get_session()
            payload = {
                "model": self.model_name, "messages": messages, "stream": False,
                "options": {
                    "num_predict": config.max_tokens,
                    "temperature": config.temperature,
                    "top_p": config.top_p,
                    "top_k": config.top_k,
                    "repeat_penalty": config.repetition_penalty,
                    "stop": config.stop_sequences
                },
                "keep_alive": "5m"
            }
            if self.disable_thinking:
                payload["think"] = False

            async with session.post(f"{self.base_url}/api/chat", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama API error {response.status}: {error_text}")

                result = await response.json()
                latency_ms = (time.time() - start_time) * 1000
                message = result.get("message", {})
                text = message.get("content", "") or message.get("thinking", "")

                return GenerationResult(
                    text=text,
                    tokens_generated=result.get("eval_count", 0),
                    finish_reason="stop",
                    model=self.model_name,
                    prompt_tokens=result.get("prompt_eval_count", 0),
                    total_tokens=result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
                    latency_ms=latency_ms
                )

        try:
            return await self.circuit_breaker.call(lambda: self._retry_with_backoff(_chat))()
        except Exception as e:
            logger.error(f"Ollama chat failed: {e}")
            return GenerationResult(
                text="", tokens_generated=0, finish_reason="error",
                model=self.model_name, metadata={"error": str(e)}
            )

    async def chat_stream(self, messages: list[dict[str, str]], config: GenerationConfig = None) -> AsyncIterator[str]:
        """流式对话生成"""
        if not self._is_loaded:
            loaded = await self.load_model(self.model_name)
            if not loaded:
                raise RuntimeError(f"Model not loaded: {self.model_name}")

        config = config or GenerationConfig()

        async def _stream():
            session = await self._get_session()
            payload = {
                "model": self.model_name, "messages": messages, "stream": True,
                "options": {
                    "num_predict": config.max_tokens,
                    "temperature": config.temperature,
                    "top_p": config.top_p,
                    "top_k": config.top_k,
                    "repeat_penalty": config.repetition_penalty,
                    "stop": config.stop_sequences
                },
                "keep_alive": "5m"
            }
            if self.disable_thinking:
                payload["think"] = False

            async with session.post(f"{self.base_url}/api/chat", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Ollama API error {response.status}: {error_text}")

                async for data in self._iter_ndjson_objects(response):
                    message = data.get("message", {})
                    content = message.get("content", "") or message.get("thinking", "")
                    if content:
                        yield content

        try:
            async for chunk in _stream():
                yield chunk
        except Exception as e:
            logger.error(f"Ollama chat stream failed: {e}")
            raise

    def get_model_info(self) -> dict[str, Any]:
        """获取模型信息"""
        return {
            "backend_type": self.backend_type.value,
            "is_loaded": self._is_loaded,
            "model_name": self.model_name,
            "base_url": self.base_url,
            "is_healthy": self.is_healthy,
            "circuit_breaker_state": self.circuit_breaker.state
        }

    async def count_tokens(self, text: str) -> int:
        """计算 token 数量"""
        return len(text) // 4

    async def health_check(self) -> dict[str, Any]:
        """健康检查"""
        is_healthy = await self._health_check_if_needed()
        return {
            "backend_type": self.backend_type.value,
            "is_loaded": self._is_loaded,
            "status": "healthy" if is_healthy else "unhealthy",
            "circuit_breaker_state": self.circuit_breaker.state,
            "last_check": self.last_health_check
        }

    async def cleanup(self):
        """清理资源"""
        await self._close_session()

    def __del__(self):
        """析构函数"""
        if self._session and not self._session.closed:
            try:
                asyncio.create_task(self._close_session())
            except RuntimeError:
                pass

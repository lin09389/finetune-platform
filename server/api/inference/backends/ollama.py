# -*- coding: utf-8 -*-
"""
Ollama 推理后端实现
"""
from typing import Dict, List, Optional, Any, AsyncIterator
import asyncio
import aiohttp
import logging
import time

from .base import (
    InferenceBackend,
    BackendType,
    GenerationConfig,
    GenerationResult
)

logger = logging.getLogger(__name__)


class OllamaBackend(InferenceBackend):
    """Ollama 推理后端"""
    
    backend_type = BackendType.OLLAMA
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.timeout = config.get("timeout", 300)
        self.model_name = config.get("model_name", "llama2")
    
    async def load_model(self, model_name: str, **kwargs) -> bool:
        """加载模型"""
        self.model_name = model_name or self.model_name
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/pull",
                    json={"name": self.model_name},
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        self._is_loaded = True
                        logger.info(f"Ollama model loaded: {self.model_name}")
                        return True
                    else:
                        logger.error(f"Failed to pull Ollama model: {response.status}")
                        return False
                        
        except Exception as e:
            logger.warning(f"Ollama model pull failed, assuming model exists: {e}")
            self._is_loaded = True
            return True
    
    async def unload_model(self) -> bool:
        """卸载模型"""
        self._is_loaded = False
        return True
    
    async def generate(
        self,
        prompt: str,
        config: GenerationConfig = None
    ) -> GenerationResult:
        """生成文本"""
        if not self._is_loaded:
            return GenerationResult(
                text="",
                tokens_generated=0,
                finish_reason="error",
                model=self.model_name,
                metadata={"error": "Model not loaded"}
            )
        
        config = config or GenerationConfig()
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": config.max_tokens,
                        "temperature": config.temperature,
                        "top_p": config.top_p,
                        "top_k": config.top_k,
                        "repeat_penalty": config.repetition_penalty,
                        "stop": config.stop_sequences
                    }
                }
                
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status != 200:
                        raise Exception(f"Ollama API error: {response.status}")
                    
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
                    
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
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
        if not self._is_loaded:
            yield "[Error: Model not loaded]"
            return
        
        config = config or GenerationConfig()
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "num_predict": config.max_tokens,
                        "temperature": config.temperature,
                        "top_p": config.top_p,
                        "top_k": config.top_k,
                        "repeat_penalty": config.repetition_penalty,
                        "stop": config.stop_sequences
                    }
                }
                
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status != 200:
                        yield f"[Error: Ollama API returned {response.status}]"
                        return
                    
                    async for line in response.content:
                        if line:
                            try:
                                import json
                                data = json.loads(line)
                                if "response" in data:
                                    yield data["response"]
                            except json.JSONDecodeError:
                                continue
                                
        except Exception as e:
            logger.error(f"Ollama stream failed: {e}")
            yield f"[Error: {e}]"
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        config: GenerationConfig = None
    ) -> GenerationResult:
        """对话生成"""
        if not self._is_loaded:
            return GenerationResult(
                text="",
                tokens_generated=0,
                finish_reason="error",
                model=self.model_name,
                metadata={"error": "Model not loaded"}
            )
        
        config = config or GenerationConfig()
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.model_name,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "num_predict": config.max_tokens,
                        "temperature": config.temperature,
                        "top_p": config.top_p,
                        "top_k": config.top_k,
                        "repeat_penalty": config.repetition_penalty,
                        "stop": config.stop_sequences
                    }
                }
                
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status != 200:
                        raise Exception(f"Ollama API error: {response.status}")
                    
                    result = await response.json()
                    
                    latency_ms = (time.time() - start_time) * 1000
                    
                    message = result.get("message", {})
                    
                    return GenerationResult(
                        text=message.get("content", ""),
                        tokens_generated=result.get("eval_count", 0),
                        finish_reason="stop",
                        model=self.model_name,
                        prompt_tokens=result.get("prompt_eval_count", 0),
                        total_tokens=result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
                        latency_ms=latency_ms
                    )
                    
        except Exception as e:
            logger.error(f"Ollama chat failed: {e}")
            return GenerationResult(
                text="",
                tokens_generated=0,
                finish_reason="error",
                model=self.model_name,
                metadata={"error": str(e)}
            )
    
    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        config: GenerationConfig = None
    ) -> AsyncIterator[str]:
        """流式对话生成"""
        if not self._is_loaded:
            yield "[Error: Model not loaded]"
            return
        
        config = config or GenerationConfig()
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.model_name,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "num_predict": config.max_tokens,
                        "temperature": config.temperature,
                        "top_p": config.top_p,
                        "top_k": config.top_k,
                        "repeat_penalty": config.repetition_penalty,
                        "stop": config.stop_sequences
                    }
                }
                
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status != 200:
                        yield f"[Error: Ollama API returned {response.status}]"
                        return
                    
                    async for line in response.content:
                        if line:
                            try:
                                import json
                                data = json.loads(line)
                                message = data.get("message", {})
                                if "content" in message:
                                    yield message["content"]
                            except json.JSONDecodeError:
                                continue
                                
        except Exception as e:
            logger.error(f"Ollama chat stream failed: {e}")
            yield f"[Error: {e}]"
    
    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "backend_type": self.backend_type.value,
            "is_loaded": self._is_loaded,
            "model_name": self.model_name,
            "base_url": self.base_url
        }
    
    async def count_tokens(self, text: str) -> int:
        """计算 token 数量"""
        return len(text) // 4
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        return {
                            "backend_type": self.backend_type.value,
                            "is_loaded": self._is_loaded,
                            "status": "healthy"
                        }
        except Exception:
            pass
        
        return {
            "backend_type": self.backend_type.value,
            "is_loaded": False,
            "status": "unhealthy"
        }

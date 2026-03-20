"""
Ollama 推理后端实现
"""
import asyncio
import logging
import time
import json
from typing import Dict, Any, Optional, List, AsyncGenerator

from api.inference.backends.base import BaseBackend, InferenceContext
from api.types import (
    ChatRequest, ChatResponse, GenerateRequest, GenerateResponse,
    Message, MessageRole, TokenUsage
)
from api.errors import OllamaNotRunningError, OllamaUnavailableError, InferenceFailedError
from core.config import get_settings

logger = logging.getLogger(__name__)


class OllamaBackend(BaseBackend):
    """Ollama 推理后端"""
    
    def __init__(self):
        self.settings = get_settings()
        self._base_url = self.settings.ollama_base_url
        self._timeout = 300
    
    @property
    def name(self) -> str:
        return "ollama"
    
    async def is_available(self) -> bool:
        """检�?Ollama 是否可用"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """列出可用模型"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    return [
                        {
                            "id": m.get("name", ""),
                            "name": m.get("name", ""),
                            "size": m.get("size", 0),
                            "modified_at": m.get("modified_at", ""),
                            "backend": "ollama"
                        }
                        for m in data.get("models", [])
                    ]
            return []
        except Exception as e:
            logger.error(f"获取 Ollama 模型列表失败: {e}")
            return []
    
    async def is_model_loaded(self, model_id: str) -> bool:
        """Ollama 自动管理模型加载"""
        return True
    
    async def load_model(self, model_id: str) -> Dict[str, Any]:
        """Ollama 自动加载模型"""
        return {"model_id": model_id, "backend": "ollama"}
    
    async def unload_model(self, model_id: str) -> bool:
        """Ollama 自动管理模型卸载"""
        return True
    
    async def generate(
        self,
        request: GenerateRequest,
        context: Optional[InferenceContext] = None
    ) -> GenerateResponse:
        """生成文本"""
        start_time = time.time()
        
        if not await self.is_available():
            raise OllamaNotRunningError()
        
        try:
            import httpx
            
            payload = {
                "model": request.model,
                "prompt": request.prompt,
                "stream": False,
                "options": {
                    "num_predict": request.options.max_tokens,
                    "temperature": request.options.temperature,
                    "top_p": request.options.top_p,
                    "top_k": request.options.top_k,
                    "repeat_penalty": request.options.repetition_penalty,
                }
            }
            
            if request.system:
                payload["system"] = request.system
            
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/api/generate",
                    json=payload
                )
                
                if response.status_code != 200:
                    raise OllamaUnavailableError(response.text)
                
                result = response.json()
                response_text = result.get("response", "")
                response_text = self.clean_response(response_text)
                
                elapsed_time = time.time() - start_time
                
                return GenerateResponse(
                    model=request.model,
                    response=response_text,
                    usage=TokenUsage(
                        prompt_tokens=result.get("prompt_eval_count", 0),
                        completion_tokens=result.get("eval_count", 0),
                        total_tokens=result.get("prompt_eval_count", 0) + result.get("eval_count", 0)
                    ),
                    total_duration=elapsed_time,
                    eval_duration=result.get("eval_duration", 0) / 1e9
                )
                
        except OllamaNotRunningError:
            raise
        except OllamaUnavailableError:
            raise
        except Exception as e:
            logger.error(f"Ollama 生成失败: {e}", exc_info=True)
            raise InferenceFailedError(request.model, str(e))
    
    async def chat(
        self,
        request: ChatRequest,
        context: Optional[InferenceContext] = None
    ) -> ChatResponse:
        """聊天对话"""
        start_time = time.time()
        
        if not await self.is_available():
            raise OllamaNotRunningError()
        
        try:
            import httpx
            
            messages = []
            for msg in request.messages:
                role = msg.role if isinstance(msg.role, str) else msg.role.value
                messages.append({"role": role, "content": msg.content})
            
            payload = {
                "model": request.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "num_predict": request.options.max_tokens,
                    "temperature": request.options.temperature,
                    "top_p": request.options.top_p,
                }
            }
            
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/api/chat",
                    json=payload
                )
                
                if response.status_code != 200:
                    raise OllamaUnavailableError(response.text)
                
                result = response.json()
                message = result.get("message", {})
                response_text = message.get("content", "")
                
                if not response_text and message.get("thinking"):
                    response_text = message.get("thinking", "")
                    logger.info("使用 thinking 字段作为响应")
                
                response_text = self.clean_response(response_text)
                
                elapsed_time = time.time() - start_time
                
                return ChatResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content=response_text
                    ),
                    model=request.model,
                    backend="ollama",
                    usage=TokenUsage(
                        prompt_tokens=result.get("prompt_eval_count", 0),
                        completion_tokens=result.get("eval_count", 0),
                        total_tokens=result.get("prompt_eval_count", 0) + result.get("eval_count", 0)
                    ),
                    total_duration=elapsed_time,
                    eval_duration=result.get("eval_duration", 0) / 1e9
                )
                
        except OllamaNotRunningError:
            raise
        except OllamaUnavailableError:
            raise
        except Exception as e:
            logger.error(f"Ollama 聊天失败: {e}", exc_info=True)
            raise InferenceFailedError(request.model, str(e))
    
    async def generate_stream(
        self,
        request: GenerateRequest,
        context: Optional[InferenceContext] = None
    ) -> AsyncGenerator[str, None]:
        """流式生成"""
        if not await self.is_available():
            yield f'data: {{"error": "Ollama 未运�?, "done": true}}\n\n'
            return
        
        try:
            import httpx
            
            payload = {
                "model": request.model,
                "prompt": request.prompt,
                "stream": True,
                "options": {
                    "num_predict": request.options.max_tokens,
                    "temperature": request.options.temperature,
                    "top_p": request.options.top_p,
                }
            }
            
            in_think_block = False
            
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/api/generate",
                    json=payload
                ) as response:
                    if response.status_code != 200:
                        yield f'data: {{"error": "请求失败", "done": true}}\n\n'
                        return
                    
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        
                        try:
                            data = json.loads(line)
                            chunk = data.get("response", "")
                            
                            if chunk:
                                if " Olym" in chunk or "<|im_start|>" in chunk:
                                    in_think_block = True
                                
                                if in_think_block:
                                    if "</Olympus>" in chunk or "<|im_end|>" in chunk:
                                        in_think_block = False
                                    continue
                                
                                chunk = self.clean_response(chunk)
                                if chunk:
                                    yield f'data: {json.dumps({"content": chunk, "done": False})}\n\n'
                            
                            if data.get("done", False):
                                yield f'data: {json.dumps({"done": True})}\n\n'
                                break
                                
                        except json.JSONDecodeError:
                            continue
                            
        except Exception as e:
            logger.error(f"Ollama 流式生成失败: {e}", exc_info=True)
            yield f'data: {json.dumps({"error": str(e), "done": true})}\n\n'
    
    async def chat_stream(
        self,
        request: ChatRequest,
        context: Optional[InferenceContext] = None
    ) -> AsyncGenerator[str, None]:
        """流式聊天"""
        if not await self.is_available():
            yield f'data: {{"error": "Ollama 未运�?, "done": true}}\n\n'
            return
        
        try:
            import httpx
            
            messages = []
            for msg in request.messages:
                role = msg.role if isinstance(msg.role, str) else msg.role.value
                messages.append({"role": role, "content": msg.content})
            
            payload = {
                "model": request.model,
                "messages": messages,
                "stream": True,
                "options": {
                    "num_predict": request.options.max_tokens,
                    "temperature": request.options.temperature,
                    "top_p": request.options.top_p,
                }
            }
            
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/api/chat",
                    json=payload
                ) as response:
                    if response.status_code != 200:
                        yield f'data: {{"error": "请求失败", "done": true}}\n\n'
                        return
                    
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        
                        try:
                            data = json.loads(line)
                            message = data.get("message", {})
                            chunk = message.get("content", "")
                            
                            if chunk:
                                chunk = self.clean_response(chunk)
                                if chunk:
                                    yield f'data: {json.dumps({"content": chunk, "done": False})}\n\n'
                            
                            if data.get("done", False):
                                yield f'data: {json.dumps({"done": True})}\n\n'
                                break
                                
                        except json.JSONDecodeError:
                            continue
                            
        except Exception as e:
            logger.error(f"Ollama 流式聊天失败: {e}", exc_info=True)
            yield f'data: {json.dumps({"error": str(e), "done": true})}\n\n'

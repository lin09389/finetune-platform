"""
云端推理后端实现 - 支持 OpenAI、Anthropic、Minimax 等云�?AI
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
from api.errors import InferenceFailedError, ServiceUnavailableError
from core.config import get_settings

logger = logging.getLogger(__name__)


class CloudBackend(BaseBackend):
    """云端推理后端"""
    
    def __init__(self):
        self.settings = get_settings()
        self._http_client = None
    
    @property
    def name(self) -> str:
        return "cloud"
    
    async def _get_client(self):
        """获取 HTTP 客户�?""
        if self._http_client is None:
            import httpx
            self._http_client = httpx.AsyncClient(timeout=120)
        return self._http_client
    
    async def is_available(self) -> bool:
        """检查云端后端是否可�?""
        return True
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """列出可用模型"""
        return [
            {"id": "gpt-4", "name": "GPT-4", "backend": "cloud", "provider": "openai"},
            {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "backend": "cloud", "provider": "openai"},
            {"id": "claude-3-opus", "name": "Claude 3 Opus", "backend": "cloud", "provider": "anthropic"},
            {"id": "claude-3-sonnet", "name": "Claude 3 Sonnet", "backend": "cloud", "provider": "anthropic"},
        ]
    
    async def is_model_loaded(self, model_id: str) -> bool:
        """云端模型始终可用"""
        return True
    
    async def load_model(self, model_id: str) -> Dict[str, Any]:
        """云端模型无需加载"""
        return {"model_id": model_id, "backend": "cloud"}
    
    async def unload_model(self, model_id: str) -> bool:
        """云端模型无需卸载"""
        return True
    
    def _get_provider(self, model_id: str) -> str:
        """根据模型 ID 判断提供�?""
        model_lower = model_id.lower()
        if "gpt" in model_lower or "openai" in model_lower:
            return "openai"
        elif "claude" in model_lower or "anthropic" in model_lower:
            return "anthropic"
        elif "minimax" in model_lower:
            return "minimax"
        elif "glm" in model_lower or "zhipu" in model_lower:
            return "zhipu"
        return "openai"
    
    async def generate(
        self,
        request: GenerateRequest,
        context: Optional[InferenceContext] = None
    ) -> GenerateResponse:
        """生成文本"""
        start_time = time.time()
        
        try:
            provider = self._get_provider(request.model)
            
            if provider == "openai":
                return await self._openai_generate(request)
            elif provider == "anthropic":
                return await self._anthropic_generate(request)
            else:
                raise ServiceUnavailableError(provider, f"不支持的云端提供�? {provider}")
                
        except Exception as e:
            logger.error(f"云端生成失败: {e}", exc_info=True)
            raise InferenceFailedError(request.model, str(e))
    
    async def chat(
        self,
        request: ChatRequest,
        context: Optional[InferenceContext] = None
    ) -> ChatResponse:
        """聊天对话"""
        start_time = time.time()
        
        try:
            provider = self._get_provider(request.model)
            
            if provider == "openai":
                return await self._openai_chat(request)
            elif provider == "anthropic":
                return await self._anthropic_chat(request)
            else:
                raise ServiceUnavailableError(provider, f"不支持的云端提供�? {provider}")
                
        except Exception as e:
            logger.error(f"云端聊天失败: {e}", exc_info=True)
            raise InferenceFailedError(request.model, str(e))
    
    async def _openai_generate(self, request: GenerateRequest) -> GenerateResponse:
        """OpenAI 文本生成"""
        client = await self._get_client()
        
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        
        payload = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.options.max_tokens,
            "temperature": request.options.temperature,
            "top_p": request.options.top_p,
        }
        
        api_key = getattr(self.settings, 'openai_api_key', None)
        if not api_key:
            raise InferenceFailedError(request.model, "OpenAI API key not configured. Please set OPENAI_API_KEY environment variable.")
        
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        )
        
        if response.status_code == 401:
            raise InferenceFailedError(request.model, "Invalid OpenAI API key")
        if response.status_code != 200:
            raise InferenceFailedError(request.model, response.text)
        
        data = response.json()
        choice = data.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        
        return GenerateResponse(
            model=request.model,
            response=content,
            usage=TokenUsage(
                prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                completion_tokens=data.get("usage", {}).get("completion_tokens", 0),
                total_tokens=data.get("usage", {}).get("total_tokens", 0)
            )
        )
    
    async def _openai_chat(self, request: ChatRequest) -> ChatResponse:
        """OpenAI 聊天"""
        client = await self._get_client()
        
        messages = []
        for msg in request.messages:
            role = msg.role if isinstance(msg.role, str) else msg.role.value
            messages.append({"role": role, "content": msg.content})
        
        payload = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.options.max_tokens,
            "temperature": request.options.temperature,
            "top_p": request.options.top_p,
        }
        
        api_key = getattr(self.settings, 'openai_api_key', None)
        if not api_key:
            raise InferenceFailedError(request.model, "OpenAI API key not configured. Please set OPENAI_API_KEY environment variable.")
        
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        )
        
        if response.status_code == 401:
            raise InferenceFailedError(request.model, "Invalid OpenAI API key")
        
        if response.status_code != 200:
            raise InferenceFailedError(request.model, response.text)
        
        data = response.json()
        choice = data.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        
        return ChatResponse(
            message=Message(
                role=MessageRole.ASSISTANT,
                content=content
            ),
            model=request.model,
            backend="cloud",
            usage=TokenUsage(
                prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                completion_tokens=data.get("usage", {}).get("completion_tokens", 0),
                total_tokens=data.get("usage", {}).get("total_tokens", 0)
            )
        )
    
    async def _anthropic_generate(self, request: GenerateRequest) -> GenerateResponse:
        """Anthropic 文本生成"""
        client = await self._get_client()
        
        payload = {
            "model": request.model,
            "max_tokens": request.options.max_tokens,
            "messages": [
                {"role": "user", "content": request.prompt}
            ]
        }
        
        if request.system:
            payload["system"] = request.system
        
        api_key = getattr(self.settings, 'anthropic_api_key', None)
        if not api_key:
            raise InferenceFailedError(request.model, "Anthropic API key not configured. Please set ANTHROPIC_API_KEY environment variable.")
        
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
        )
        
        if response.status_code == 401:
            raise InferenceFailedError(request.model, "Invalid Anthropic API key")
        
        if response.status_code != 200:
            raise InferenceFailedError(request.model, response.text)
        
        data = response.json()
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
        
        return GenerateResponse(
            model=request.model,
            response=content,
            usage=TokenUsage(
                prompt_tokens=data.get("usage", {}).get("input_tokens", 0),
                completion_tokens=data.get("usage", {}).get("output_tokens", 0),
                total_tokens=data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)
            )
        )
    
    async def _anthropic_chat(self, request: ChatRequest) -> ChatResponse:
        """Anthropic 聊天"""
        client = await self._get_client()
        
        messages = []
        system_prompt = None
        
        for msg in request.messages:
            role = msg.role if isinstance(msg.role, str) else msg.role.value
            if role == "system":
                system_prompt = msg.content
            else:
                messages.append({"role": role, "content": msg.content})
        
        payload = {
            "model": request.model,
            "max_tokens": request.options.max_tokens,
            "messages": messages
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        api_key = getattr(self.settings, 'anthropic_api_key', None)
        if not api_key:
            raise InferenceFailedError(request.model, "Anthropic API key not configured. Please set ANTHROPIC_API_KEY environment variable.")
        
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
        )
        
        if response.status_code == 401:
            raise InferenceFailedError(request.model, "Invalid Anthropic API key")
        if response.status_code != 200:
            raise InferenceFailedError(request.model, response.text)
        
        data = response.json()
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
        
        return ChatResponse(
            message=Message(
                role=MessageRole.ASSISTANT,
                content=content
            ),
            model=request.model,
            backend="cloud",
            usage=TokenUsage(
                prompt_tokens=data.get("usage", {}).get("input_tokens", 0),
                completion_tokens=data.get("usage", {}).get("output_tokens", 0),
                total_tokens=data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)
            )
        )
    
    async def generate_stream(
        self,
        request: GenerateRequest,
        context: Optional[InferenceContext] = None
    ) -> AsyncGenerator[str, None]:
        """流式生成"""
        yield f'data: {{"error": "云端后端暂不支持流式生成", "done": true}}\n\n'
    
    async def chat_stream(
        self,
        request: ChatRequest,
        context: Optional[InferenceContext] = None
    ) -> AsyncGenerator[str, None]:
        """流式聊天"""
        yield f'data: {{"error": "云端后端暂不支持流式聊天", "done": true}}\n\n'

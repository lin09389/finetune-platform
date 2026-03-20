"""
推理后端抽象基类 - 参�?Ollama 设计模式
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
import logging

from api.types import (
    ChatRequest, ChatResponse, GenerateRequest, GenerateResponse,
    Message, MessageRole, TokenUsage, KnowledgeSource
)

logger = logging.getLogger(__name__)


@dataclass
class InferenceContext:
    """推理上下�?""
    model_id: str
    prompt: str
    system_prompt: Optional[str] = None
    messages: List[Message] = None
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 50
    max_tokens: int = 1024
    repetition_penalty: float = 1.1
    stop: Optional[List[str]] = None
    seed: Optional[int] = None
    
    knowledge_sources: Optional[List[KnowledgeSource]] = None
    
    @classmethod
    def from_chat_request(cls, request: ChatRequest) -> "InferenceContext":
        return cls(
            model_id=request.model,
            prompt="",
            messages=request.messages,
            temperature=request.options.temperature,
            top_p=request.options.top_p,
            top_k=request.options.top_k,
            max_tokens=request.options.max_tokens,
            repetition_penalty=request.options.repetition_penalty,
            stop=request.options.stop,
            seed=request.options.seed,
        )
    
    @classmethod
    def from_generate_request(cls, request: GenerateRequest) -> "InferenceContext":
        return cls(
            model_id=request.model,
            prompt=request.prompt,
            system_prompt=request.system,
            temperature=request.options.temperature,
            top_p=request.options.top_p,
            top_k=request.options.top_k,
            max_tokens=request.options.max_tokens,
            repetition_penalty=request.options.repetition_penalty,
            stop=request.options.stop,
            seed=request.options.seed,
        )


class BaseBackend(ABC):
    """
    推理后端抽象基类
    
    所有推理后端必须实现此接口
    """
    
    name: str = "base"
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._initialized = False
    
    @abstractmethod
    async def is_available(self) -> bool:
        """检查后端是否可�?""
        pass
    
    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """聊天推理"""
        pass
    
    @abstractmethod
    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        """文本生成"""
        pass
    
    @abstractmethod
    async def chat_stream(
        self, request: ChatRequest
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式聊天"""
        pass
    
    @abstractmethod
    async def generate_stream(
        self, request: GenerateRequest
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式生成"""
        pass
    
    @abstractmethod
    async def list_models(self) -> List[Dict[str, Any]]:
        """列出可用模型"""
        pass
    
    @abstractmethod
    async def load_model(self, model_id: str) -> bool:
        """加载模型"""
        pass
    
    @abstractmethod
    async def unload_model(self, model_id: str) -> bool:
        """卸载模型"""
        pass
    
    def build_system_prompt(
        self,
        base_prompt: Optional[str],
        knowledge_context: Optional[str] = None,
        project_context: Optional[str] = None
    ) -> str:
        """构建系统提示"""
        parts = []
        
        if base_prompt:
            parts.append(base_prompt)
        
        if knowledge_context:
            parts.append(f"\n参考资�?\n{knowledge_context}")
        
        if project_context:
            parts.append(f"\n项目上下�?\n{project_context}")
        
        return "\n".join(parts) if parts else ""
    
    def apply_chat_template(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None,
        model_id: str = ""
    ) -> str:
        """应用聊天模板"""
        model_lower = model_id.lower()
        
        if "qwen" in model_lower:
            return self._apply_qwen_template(messages, system_prompt)
        
        return self._apply_default_template(messages, system_prompt)
    
    def _apply_qwen_template(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None
    ) -> str:
        """应用 Qwen 模板"""
        parts = []
        
        if system_prompt:
            parts.append(f"<|im_start|>system\n{system_prompt}<|im_end|>\n")
        
        for msg in messages:
            role = msg.role if isinstance(msg.role, str) else msg.role.value
            parts.append(f"<|im_start|>{role}\n{msg.content}<|im_end|>\n")
        
        parts.append("<|im_start|>assistant\n")
        return "".join(parts)
    
    def _apply_default_template(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None
    ) -> str:
        """应用默认模板"""
        parts = []
        
        if system_prompt:
            parts.append(f"System: {system_prompt}\n\n")
        
        for msg in messages:
            role = msg.role if isinstance(msg.role, str) else msg.role.value
            parts.append(f"{role.capitalize()}: {msg.content}\n")
        
        parts.append("Assistant: ")
        return "".join(parts)
    
    def clean_response(self, text: str) -> str:
        """清理响应文本"""
        import re
        
        if not text:
            return ""
        
        text = re.sub(r'<think[^>]*>.*?</think\s*>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<\|im_start\|>.*?<\|im_end\|>', '', text, flags=re.DOTALL)
        text = text.replace('<|im_start|>', '').replace('<|im_end|>', '')
        
        return text.strip()

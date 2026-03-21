"""
推理引擎抽象基类

定义统一的推理接口，支持多种后端实现
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncGenerator, Dict, Any, List, Optional
from pathlib import Path
import time


@dataclass
class EngineConfig:
    """引擎配置"""
    model_id: str
    model_path: Optional[Path] = None
    device: str = "auto"
    torch_dtype: str = "float16"
    trust_remote_code: bool = True
    low_cpu_mem_usage: bool = True
    max_cache_size: int = 3
    lora_path: Optional[str] = None
    
    def __post_init__(self):
        if self.model_path is None:
            from core.config import get_settings
            settings = get_settings()
            self.model_path = settings.models_dir_resolved / self.model_id


@dataclass
class GenerationConfig:
    """生成配置"""
    max_new_tokens: int = 1024
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 50
    repetition_penalty: float = 1.1
    do_sample: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_new_tokens": self.max_new_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "repetition_penalty": self.repetition_penalty,
            "do_sample": self.do_sample,
        }


@dataclass
class GenerationResult:
    """生成结果"""
    text: str
    tokens: int
    time: float
    model_id: str
    backend: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "tokens": self.tokens,
            "time": self.time,
            "model_id": self.model_id,
            "backend": self.backend,
            "metadata": self.metadata,
        }


class InferenceEngine(ABC):
    """
    推理引擎抽象基类
    
    所有推理后端（HuggingFace、Ollama、vLLM、llama.cpp）都需要实现此接口
    """
    
    engine_type: str = "base"
    
    def __init__(self, config: EngineConfig):
        self.config = config
        self._model = None
        self._tokenizer = None
        self._is_loaded = False
        self._load_time: Optional[float] = None
    
    @abstractmethod
    async def load(self) -> None:
        """
        加载模型和分词器
        
        Raises:
            RuntimeError: 模型加载失败
        """
        pass
    
    @abstractmethod
    async def unload(self) -> None:
        """
        卸载模型并释放资源
        """
        pass
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> GenerationResult:
        """
        同步生成文本
        
        Args:
            prompt: 输入提示
            config: 生成配置
            **kwargs: 额外参数
            
        Returns:
            GenerationResult: 生成结果
        """
        pass
    
    @abstractmethod
    async def stream(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        流式生成文本
        
        Args:
            prompt: 输入提示
            config: 生成配置
            **kwargs: 额外参数
            
        Yields:
            str: 生成的文本片段
        """
        pass
    
    @abstractmethod
    async def apply_lora(self, lora_path: str) -> None:
        """
        应用 LoRA 适配器
        
        Args:
            lora_path: LoRA 适配器路径
        """
        pass
    
    @abstractmethod
    async def remove_lora(self) -> None:
        """
        移除 LoRA 适配器
        """
        pass
    
    @property
    def is_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self._is_loaded
    
    @property
    def model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "model_id": self.config.model_id,
            "engine_type": self.engine_type,
            "is_loaded": self._is_loaded,
            "load_time": self._load_time,
        }
    
    async def apply_chat_template(self, prompt: str, messages: Optional[List[Dict[str, str]]] = None) -> str:
        """
        应用聊天模板
        
        Args:
            prompt: 输入提示
            messages: 消息历史（可选）
            
        Returns:
            str: 格式化后的提示
        """
        model_lower = self.config.model_id.lower()
        
        if "qwen3.5" in model_lower or "qwen3_5" in model_lower:
            if "<|im_start|>" in prompt:
                return prompt
            return f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
        
        if "qwen2.5" in model_lower or "qwen2_5" in model_lower:
            if "<|im_start|>" in prompt:
                return prompt
            return f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
        
        if self._tokenizer and hasattr(self._tokenizer, 'apply_chat_template'):
            try:
                chat_messages = messages or [{"role": "user", "content": prompt}]
                formatted = self._tokenizer.apply_chat_template(
                    chat_messages, tokenize=False, add_generation_prompt=True
                )
                if formatted:
                    return formatted
            except Exception:
                pass
        
        return prompt
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(model_id={self.config.model_id}, loaded={self._is_loaded})>"

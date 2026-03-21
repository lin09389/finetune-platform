"""
推理引擎工厂

根据配置创建正确的引擎实例
"""
import logging
from typing import Dict, Any, Optional, Type, Literal
from pathlib import Path

from .engine_base import InferenceEngine, EngineConfig

logger = logging.getLogger(__name__)


EngineType = Literal["huggingface", "vllm", "llamacpp", "ollama"]


class EngineFactory:
    """
    推理引擎工厂
    
    支持：
    - 根据类型创建引擎实例
    - 引擎可用性检查
    - 自动降级到可用引擎
    """
    
    _registry: Dict[str, Type[InferenceEngine]] = {}
    _availability_cache: Dict[str, bool] = {}
    
    @classmethod
    def register(cls, engine_type: str, engine_class: Type[InferenceEngine]) -> None:
        """
        注册引擎类型
        
        Args:
            engine_type: 引擎类型标识
            engine_class: 引擎类
        """
        cls._registry[engine_type] = engine_class
        logger.info(f"注册推理引擎：{engine_type}")
    
    @classmethod
    def create(
        cls,
        engine_type: EngineType,
        config: EngineConfig,
        **kwargs
    ) -> InferenceEngine:
        """
        创建引擎实例
        
        Args:
            engine_type: 引擎类型
            config: 引擎配置
            **kwargs: 额外参数
            
        Returns:
            InferenceEngine: 引擎实例
            
        Raises:
            ValueError: 不支持的引擎类型
            RuntimeError: 引擎不可用
        """
        if engine_type not in cls._registry:
            available = list(cls._registry.keys())
            raise ValueError(f"不支持的引擎类型：{engine_type}，可用引擎：{available}")
        
        engine_class = cls._registry[engine_type]
        
        try:
            engine = engine_class(config, **kwargs)
            logger.info(f"创建引擎实例：{engine_type}，模型：{config.model_id}")
            return engine
        except Exception as e:
            logger.error(f"创建引擎失败：{engine_type}，错误：{e}")
            raise RuntimeError(f"创建引擎失败：{e}")
    
    @classmethod
    def create_with_fallback(
        cls,
        preferred_type: EngineType,
        config: EngineConfig,
        fallback_types: Optional[list] = None,
        **kwargs
    ) -> InferenceEngine:
        """
        创建引擎实例（支持降级）
        
        Args:
            preferred_type: 首选引擎类型
            config: 引擎配置
            fallback_types: 降级引擎列表
            **kwargs: 额外参数
            
        Returns:
            InferenceEngine: 引擎实例
        """
        fallback_types = fallback_types or ["huggingface"]
        
        types_to_try = [preferred_type] + [t for t in fallback_types if t != preferred_type]
        
        last_error = None
        for engine_type in types_to_try:
            try:
                if cls.is_available(engine_type):
                    return cls.create(engine_type, config, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning(f"引擎 {engine_type} 创建失败，尝试下一个：{e}")
        
        raise RuntimeError(f"所有引擎都不可用，最后错误：{last_error}")
    
    @classmethod
    def is_available(cls, engine_type: str) -> bool:
        """
        检查引擎是否可用
        
        Args:
            engine_type: 引擎类型
            
        Returns:
            bool: 是否可用
        """
        if engine_type in cls._availability_cache:
            return cls._availability_cache[engine_type]
        
        available = cls._check_availability(engine_type)
        cls._availability_cache[engine_type] = available
        return available
    
    @classmethod
    def _check_availability(cls, engine_type: str) -> bool:
        """检查引擎依赖是否可用"""
        if engine_type not in cls._registry:
            return False
        
        try:
            if engine_type == "huggingface":
                import torch
                import transformers
                return True
            
            elif engine_type == "vllm":
                import vllm
                return True
            
            elif engine_type == "llamacpp":
                import llama_cpp
                return True
            
            elif engine_type == "ollama":
                import requests
                from core.config import get_settings
                settings = get_settings()
                try:
                    response = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=3)
                    return response.status_code == 200
                except Exception:
                    return False
            
            return True
            
        except ImportError:
            return False
        except Exception as e:
            logger.warning(f"检查引擎可用性失败：{engine_type}，错误：{e}")
            return False
    
    @classmethod
    def get_available_engines(cls) -> Dict[str, Dict[str, Any]]:
        """
        获取所有可用引擎
        
        Returns:
            Dict: 引擎信息字典
        """
        result = {}
        for engine_type in cls._registry:
            result[engine_type] = {
                "type": engine_type,
                "available": cls.is_available(engine_type),
                "class": cls._registry[engine_type].__name__,
            }
        return result
    
    @classmethod
    def clear_cache(cls) -> None:
        """清除可用性缓存"""
        cls._availability_cache.clear()


def create_engine(
    model_id: str,
    engine_type: Optional[EngineType] = None,
    **config_kwargs
) -> InferenceEngine:
    """
    便捷函数：创建推理引擎
    
    Args:
        model_id: 模型 ID
        engine_type: 引擎类型（默认从配置读取）
        **config_kwargs: 引擎配置参数
        
    Returns:
        InferenceEngine: 引擎实例
    """
    from core.config import get_settings
    settings = get_settings()
    
    if engine_type is None:
        engine_type = settings.inference_backend
    
    config = EngineConfig(model_id=model_id, **config_kwargs)
    
    return EngineFactory.create(engine_type, config)


def create_engine_with_fallback(
    model_id: str,
    preferred_type: Optional[EngineType] = None,
    **config_kwargs
) -> InferenceEngine:
    """
    便捷函数：创建推理引擎（支持降级）
    
    Args:
        model_id: 模型 ID
        preferred_type: 首选引擎类型
        **config_kwargs: 引擎配置参数
        
    Returns:
        InferenceEngine: 引擎实例
    """
    from core.config import get_settings
    settings = get_settings()
    
    if preferred_type is None:
        preferred_type = settings.inference_backend
    
    config = EngineConfig(model_id=model_id, **config_kwargs)
    
    return EngineFactory.create_with_fallback(
        preferred_type,
        config,
        fallback_types=["huggingface"]
    )


try:
    from .huggingface_engine import HuggingFaceEngine
    EngineFactory.register("huggingface", HuggingFaceEngine)
except ImportError as e:
    logger.warning(f"HuggingFace 引擎注册失败：{e}")

try:
    from .vllm_engine import VLLMEngine
    EngineFactory.register("vllm", VLLMEngine)
except ImportError:
    pass

try:
    from .llamacpp_engine import LlamaCppEngine
    EngineFactory.register("llamacpp", LlamaCppEngine)
except ImportError:
    pass

try:
    from .ollama_engine import OllamaEngine
    EngineFactory.register("ollama", OllamaEngine)
except ImportError:
    pass

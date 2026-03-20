"""
推理引擎模块

提供统一的推理接口，支持多种后端实现
"""
from .engine_base import (
    InferenceEngine,
    EngineConfig,
    GenerationConfig,
    GenerationResult,
)
from .engine_factory import (
    EngineFactory,
    EngineType,
    create_engine,
    create_engine_with_fallback,
)
from .flash_attention import (
    is_flash_attn_2_available,
    get_attention_implementation,
    get_flash_attention_info,
    reset_detection_cache,
)

__all__ = [
    "InferenceEngine",
    "EngineConfig",
    "GenerationConfig",
    "GenerationResult",
    "EngineFactory",
    "EngineType",
    "create_engine",
    "create_engine_with_fallback",
    "is_flash_attn_2_available",
    "get_attention_implementation",
    "get_flash_attention_info",
    "reset_detection_cache",
]

try:
    from .huggingface_engine import HuggingFaceEngine
    __all__.append("HuggingFaceEngine")
except ImportError:
    pass

try:
    from .vllm_engine import VLLMEngine
    __all__.append("VLLMEngine")
except ImportError:
    pass

try:
    from .llamacpp_engine import LlamaCppEngine
    __all__.append("LlamaCppEngine")
except ImportError:
    pass

try:
    from .ollama_engine import OllamaEngine
    __all__.append("OllamaEngine")
except ImportError:
    pass

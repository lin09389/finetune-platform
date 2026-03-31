"""
推理引擎模块
实现开闭原则，支持多种推理后端
"""
from .engine_base import BaseInferenceEngine
from .engine_factory import InferenceEngineFactory, get_engine_factory
from .huggingface_engine import HuggingFaceEngine
from .ollama_engine import OllamaEngine

__all__ = [
    "BaseInferenceEngine",
    "HuggingFaceEngine",
    "OllamaEngine",
    "InferenceEngineFactory",
    "get_engine_factory",
]

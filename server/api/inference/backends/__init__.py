"""
推理后端模块
"""
from .base import BackendType, GenerationConfig, GenerationResult, InferenceBackend
from .cloud import CloudBackend
from .huggingface import HuggingFaceBackend
from .ollama import OllamaBackend

__all__ = [
    "InferenceBackend",
    "BackendType",
    "GenerationConfig",
    "GenerationResult",
    "HuggingFaceBackend",
    "OllamaBackend",
    "CloudBackend",
]

"""
推理后端模块
"""
from api.inference.backends.base import BaseBackend
from api.inference.backends.huggingface import HuggingFaceBackend
from api.inference.backends.ollama import OllamaBackend
from api.inference.backends.cloud import CloudBackend

__all__ = [
    "BaseBackend",
    "HuggingFaceBackend",
    "OllamaBackend",
    "CloudBackend",
]

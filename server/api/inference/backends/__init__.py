# -*- coding: utf-8 -*-
"""
推理后端模块
"""
from .base import InferenceBackend, BackendType, GenerationConfig, GenerationResult
from .huggingface import HuggingFaceBackend
from .ollama import OllamaBackend
from .cloud import CloudBackend

__all__ = [
    "InferenceBackend",
    "BackendType",
    "GenerationConfig",
    "GenerationResult",
    "HuggingFaceBackend",
    "OllamaBackend",
    "CloudBackend",
]

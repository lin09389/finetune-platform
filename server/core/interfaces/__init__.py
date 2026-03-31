"""
核心接口定义模块
用于实现依赖倒置原则，解耦高层模块与低层实现
"""
from .cache import CacheInterface
from .embedder import EmbedderInterface
from .inference_engine import InferenceEngineInterface
from .vector_store import VectorStoreInterface

__all__ = [
    "EmbedderInterface",
    "VectorStoreInterface",
    "InferenceEngineInterface",
    "CacheInterface",
]

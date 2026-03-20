"""
推理模块 - 参�?Ollama server 设计模式
"""
from api.inference.routes import router
from api.inference.scheduler import get_scheduler

__all__ = ["router", "get_scheduler"]

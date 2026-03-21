# -*- coding: utf-8 -*-
"""
推理模块 - 参考 Ollama server 设计模式
"""
from api.inference.routes import router
from api.inference.scheduler import get_scheduler

__all__ = ["router", "get_scheduler"]

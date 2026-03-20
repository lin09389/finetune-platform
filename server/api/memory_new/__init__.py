"""
记忆模块 - 统一记忆管理
整合�?memory.py, enhanced_memory.py 功能
"""
from api.memory_new.routes import router
from api.memory_new.service import get_memory_service

__all__ = ["router", "get_memory_service"]

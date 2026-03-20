"""
知识模块 - 统一知识库管�?整合�?rag.py, knowledge_base.py 功能
"""
from api.knowledge.routes import router
from api.knowledge.service import get_knowledge_service

__all__ = ["router", "get_knowledge_service"]

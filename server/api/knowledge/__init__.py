"""
知识库模块 - 整合 RAG 功能
"""
from .models import Chunk, Document, KnowledgeBase
from .routes import router
from .service import KnowledgeService, get_knowledge_service

__all__ = [
    "router",
    "KnowledgeService",
    "get_knowledge_service",
    "KnowledgeBase",
    "Document",
    "Chunk",
]

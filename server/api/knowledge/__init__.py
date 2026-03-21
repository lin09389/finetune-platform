# -*- coding: utf-8 -*-
"""
知识库模块 - 整合 RAG 功能
"""
from .routes import router
from .service import KnowledgeService, get_knowledge_service
from .models import KnowledgeBase, Document, Chunk

__all__ = [
    "router",
    "KnowledgeService",
    "get_knowledge_service",
    "KnowledgeBase",
    "Document",
    "Chunk",
]

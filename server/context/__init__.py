# -*- coding: utf-8 -*-
"""
项目上下文理解模块
功能：
- 项目扫描：检测技术栈、分析结构、解析依赖
- 代码索引：提取符号、向量化、构建索引
- 上下文检索：语义搜索、相关代码片段
"""
from context.service import (
    ContextService,
    get_context_service,
)
from context.models import (
    ProjectInfo,
    FileInfo,
    SymbolInfo,
    ContextResult,
    TechStack,
    ProjectStructure,
    GitInfo,
)
from context.project_scanner import (
    ProjectScanner,
    scan_project,
)
from context.context_retriever import (
    ContextRetriever,
    get_context_retriever,
)

__all__ = [
    "ContextService",
    "get_context_service",
    "ProjectInfo",
    "FileInfo",
    "SymbolInfo",
    "ContextResult",
    "TechStack",
    "ProjectStructure",
    "GitInfo",
    "ProjectScanner",
    "scan_project",
    "ContextRetriever",
    "get_context_retriever",
]

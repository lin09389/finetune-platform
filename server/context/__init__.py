"""
项目上下文理解模块
功能：
- 项目扫描：检测技术栈、分析结构、解析依赖
- 代码索引：提取符号、向量化、构建索引
- 上下文检索：语义搜索、相关代码片段
"""
from context.budget import ContextBuildOptions, estimate_tokens
from context.builder import ContextBuilder, get_context_builder
from context.deepagents import DeepAgentsContextPack, build_deepagents_context_pack
from context.models import (
    ContextResult,
    FileInfo,
    GitInfo,
    ProjectInfo,
    ProjectStructure,
    SymbolInfo,
    TechStack,
)
from context.pack import (
    ContextBudget,
    ContextBuildResult,
    ContextConflict,
    ContextDecision,
    ContextPack,
    ContextSection,
    ContextSource,
    ContextTiming,
    ContextTrace,
    PromptArtifact,
)
from context.project_scanner import (
    ProjectScanner,
    scan_project,
)
from context.service import (
    ContextService,
    get_context_service,
)

__all__ = [
    "ContextService",
    "get_context_service",
    "ContextBuilder",
    "get_context_builder",
    "ContextPack",
    "ContextSource",
    "ContextSection",
    "ContextBudget",
    "ContextTiming",
    "ContextDecision",
    "ContextConflict",
    "ContextTrace",
    "PromptArtifact",
    "ContextBuildOptions",
    "ContextBuildResult",
    "estimate_tokens",
    "DeepAgentsContextPack",
    "build_deepagents_context_pack",
    "ProjectInfo",
    "FileInfo",
    "SymbolInfo",
    "ContextResult",
    "TechStack",
    "ProjectStructure",
    "GitInfo",
    "ProjectScanner",
    "scan_project",
]

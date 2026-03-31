"""
智能记忆系统
三级记忆架构：工作记忆、短期记忆、长期记忆
支持知识图谱、MCP协议、智能提示
"""

from .enhanced_memory_service import (
    EnhancedMemoryService,
    get_enhanced_memory_service,
    reset_enhanced_memory_service,
)
from .intelligent_extractor import (
    ExtractionResult,
    IntelligentMemoryExtractor,
    LLMExtractor,
    RuleBasedExtractor,
    extract_memories,
    get_memory_extractor,
)
from .knowledge_graph import (
    Entity,
    KnowledgeGraph,
    Relation,
    get_knowledge_graph,
    reset_knowledge_graph,
)
from .mcp_server import (
    MCPResource,
    MCPResourceContent,
    MCPResourceType,
    MCPSearchResult,
    MCPServer,
    get_mcp_server,
)
from .memory_extractor import MemoryExtractor
from .memory_merger import (
    MemoryDeduplicator,
    MemoryMerger,
    MemoryUpdater,
    get_memory_merger,
    get_memory_updater,
)
from .memory_service import MemoryService, get_memory_service
from .models import MEMORY_IMPORTANCE, MEMORY_TYPE_LABELS, Memory, MemoryType
from .short_term_memory import (
    ConversationMessage,
    ShortTermMemory,
    ShortTermMemoryManager,
    get_short_term_memory,
    get_stm_manager,
)

__all__ = [
    'get_memory_service',
    'MemoryService',
    'MemoryExtractor',
    'MemoryType',
    'Memory',
    'MEMORY_IMPORTANCE',
    'MEMORY_TYPE_LABELS',

    'KnowledgeGraph',
    'Entity',
    'Relation',
    'get_knowledge_graph',
    'reset_knowledge_graph',

    'ShortTermMemory',
    'ShortTermMemoryManager',
    'ConversationMessage',
    'get_short_term_memory',
    'get_stm_manager',

    'IntelligentMemoryExtractor',
    'ExtractionResult',
    'RuleBasedExtractor',
    'LLMExtractor',
    'get_memory_extractor',
    'extract_memories',

    'MemoryMerger',
    'MemoryUpdater',
    'MemoryDeduplicator',
    'get_memory_merger',
    'get_memory_updater',

    'EnhancedMemoryService',
    'get_enhanced_memory_service',
    'reset_enhanced_memory_service',

    'MCPServer',
    'MCPResource',
    'MCPResourceContent',
    'MCPSearchResult',
    'MCPResourceType',
    'get_mcp_server',
]

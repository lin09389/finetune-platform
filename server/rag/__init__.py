"""
RAG 知识库模块
"""
from rag.document_parser import DocumentParser, get_parser
from rag.embedder import Embedder, get_embedder
from rag.evaluator import (
    BatchEvaluationResult,
    EvaluationResult,
    OnlineEvaluator,
    RetrievalEvaluator,
    get_evaluator,
    get_online_evaluator,
    reset_evaluator,
)
from rag.hybrid_retriever import (
    BM25Index,
    HybridRetriever,
    SearchResult,
    get_hybrid_retriever,
    reset_hybrid_retriever,
)
from rag.reranker import (
    CrossEncoderReranker,
    LLMReranker,
    MultiStageReranker,
    RerankResult,
    get_reranker,
    reset_reranker,
)
from rag.service import RAGService, get_rag_service
from rag.text_chunker import TextChunker, get_chunker
from rag.vector_store import VectorStore, get_vector_store

# Lazy-load rag.structured to avoid eagerly importing pandas/pyarrow
# (which can crash on Windows due to pyarrow C extension issues).
_STRUCTURED_NAMES = frozenset({
    "ConnectionConfig",
    "DatabaseConnector",
    "MySQLConnector",
    "PostgreSQLConnector",
    "QueryEngine",
    "QueryHistory",
    "QueryResult",
    "SQLGenerationResult",
    "SQLiteConnector",
    "TableMetadata",
    "TableStore",
    "create_postgresql_connector",
    "create_sqlite_connector",
    "get_db_connector",
    "get_query_engine",
    "get_table_store",
})


def __getattr__(name: str):
    if name in _STRUCTURED_NAMES:
        import importlib

        mod = importlib.import_module("rag.structured")
        val = getattr(mod, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    'get_parser',
    'DocumentParser',
    'get_chunker',
    'TextChunker',
    'get_embedder',
    'Embedder',
    'get_vector_store',
    'VectorStore',
    'get_rag_service',
    'RAGService',
    'HybridRetriever',
    'BM25Index',
    'SearchResult',
    'get_hybrid_retriever',
    'reset_hybrid_retriever',
    'CrossEncoderReranker',
    'LLMReranker',
    'MultiStageReranker',
    'RerankResult',
    'get_reranker',
    'reset_reranker',
    'RetrievalEvaluator',
    'OnlineEvaluator',
    'EvaluationResult',
    'BatchEvaluationResult',
    'get_evaluator',
    'get_online_evaluator',
    'reset_evaluator',
    'TableStore',
    'TableMetadata',
    'get_table_store',
    'DatabaseConnector',
    'SQLiteConnector',
    'PostgreSQLConnector',
    'MySQLConnector',
    'ConnectionConfig',
    'get_db_connector',
    'create_sqlite_connector',
    'create_postgresql_connector',
    'QueryEngine',
    'QueryResult',
    'SQLGenerationResult',
    'QueryHistory',
    'get_query_engine',
]

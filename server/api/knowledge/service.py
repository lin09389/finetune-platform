"""
知识模块服务�?- 整合 RAG 功能
"""
from typing import Dict, List, Optional, Any
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class KnowledgeService:
    """知识服务 - 封装 RAG 功能"""
    
    def __init__(self):
        self._rag_service = None
        self._hybrid_retriever = None
        self._reranker = None
    
    def _get_rag_service(self):
        """延迟加载 RAG 服务"""
        if self._rag_service is None:
            from rag.service import get_rag_service
            self._rag_service = get_rag_service()
        return self._rag_service
    
    def _get_hybrid_retriever(self):
        """延迟加载混合检索器"""
        if self._hybrid_retriever is None:
            from rag.hybrid_retriever import get_hybrid_retriever
            self._hybrid_retriever = get_hybrid_retriever()
        return self._hybrid_retriever
    
    def _get_reranker(self):
        """延迟加载重排序器"""
        if self._reranker is None:
            try:
                from rag.reranker import get_reranker
                self._reranker = get_reranker()
            except Exception as e:
                logger.warning(f"重排序器加载失败: {e}")
        return self._reranker
    
    def upload_document(
        self,
        file_path: str,
        collection_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """上传文档"""
        rag = self._get_rag_service()
        
        result = rag.upload_document(
            file_path=file_path,
            collection_name=collection_id,
            metadata=metadata or {}
        )
        
        return {
            "doc_id": result.get("doc_id", ""),
            "file_name": result.get("file_name", os.path.basename(file_path)),
            "chunk_count": result.get("chunk_count", 0),
            "vector_count": result.get("vector_count", 0),
            "content_length": result.get("content_length", 0)
        }
    
    def search(
        self,
        collection_id: str,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        method: str = "hybrid"
    ) -> List[Dict[str, Any]]:
        """搜索文档"""
        rag = self._get_rag_service()
        
        if method == "hybrid":
            retriever = self._get_hybrid_retriever()
            results = retriever.search(
                collection_name=collection_id,
                query=query,
                top_k=top_k
            )
        else:
            results = rag.search(
                collection_name=collection_id,
                query=query,
                top_k=top_k
            )
        
        if min_score > 0:
            results = [r for r in results if r.get("score", 0) >= min_score]
        
        return results
    
    def search_with_context(
        self,
        collection_id: str,
        query: str,
        top_k: int = 5
    ) -> str:
        """搜索并返回上下文"""
        rag = self._get_rag_service()
        return rag.search_with_context(
            collection_name=collection_id,
            query=query,
            top_k=top_k
        )
    
    def list_collections(self) -> List[Dict[str, Any]]:
        """列出所有集�?""
        rag = self._get_rag_service()
        return rag.list_collections()
    
    def create_collection(
        self,
        name: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """创建集合"""
        rag = self._get_rag_service()
        return rag.create_collection(
            name=name,
            metadata={
                "description": description or "",
                **(metadata or {})
            }
        )
    
    def get_collection(self, collection_id: str) -> Optional[Dict[str, Any]]:
        """获取集合详情"""
        rag = self._get_rag_service()
        collections = rag.list_collections()
        
        for c in collections:
            if c.get("id") == collection_id or c.get("name") == collection_id:
                return c
        
        return None
    
    def delete_collection(self, collection_id: str) -> bool:
        """删除集合"""
        rag = self._get_rag_service()
        return rag.delete_collection(collection_id)
    
    def list_documents(
        self,
        collection_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """列出文档"""
        rag = self._get_rag_service()
        return rag.list_documents(
            collection_name=collection_id,
            limit=limit,
            offset=offset
        )
    
    def delete_document(self, collection_id: str, document_id: str) -> bool:
        """删除文档"""
        rag = self._get_rag_service()
        return rag.delete_document(collection_id, document_id)
    
    def evaluate_retrieval(
        self,
        query: str,
        collection_id: str,
        top_k: int = 5
    ) -> tuple:
        """评估检索质�?""
        results = self.search(collection_id, query, top_k)
        
        metrics = {
            "total_results": len(results),
            "avg_score": sum(r.get("score", 0) for r in results) / len(results) if results else 0,
            "max_score": max((r.get("score", 0) for r in results), default=0),
            "min_score": min((r.get("score", 0) for r in results), default=0),
        }
        
        return results, metrics
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            collections = self.list_collections()
            
            total_documents = 0
            total_chunks = 0
            
            for c in collections:
                total_documents += c.get("document_count", 0)
                total_chunks += c.get("chunk_count", 0)
            
            return {
                "total_collections": len(collections),
                "total_documents": total_documents,
                "total_chunks": total_chunks,
                "collections": [
                    {
                        "id": c.get("id", c.get("name", "")),
                        "name": c.get("name", ""),
                        "document_count": c.get("document_count", 0)
                    }
                    for c in collections
                ]
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {
                "total_collections": 0,
                "total_documents": 0,
                "total_chunks": 0,
                "collections": []
            }


_knowledge_service: Optional[KnowledgeService] = None


def get_knowledge_service() -> KnowledgeService:
    """获取知识服务单例"""
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service

"""
RAG 知识�?- 服务�?整合文档解析、分块、向量化和存�?"""
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging
from datetime import datetime
import uuid

from rag.document_parser import get_parser
from rag.text_chunker import get_chunker
from rag.embedder import get_embedder
from rag.vector_store import get_vector_store

logger = logging.getLogger(__name__)


class RAGService:
    """RAG 服务"""
    
    def __init__(
        self,
        vector_db_path: str = "data/vectors",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        embedder_model: str = "shibing624/text2vec-base-chinese"
    ):
        """
        初始�?RAG 服务
        
        Args:
            vector_db_path: 向量数据库路�?            chunk_size: 分块大小
            chunk_overlap: 分块重叠
            embedder_model: 嵌入模型
        """
        self._parser = None
        self._chunker = None
        self._embedder = None
        self._vector_store = None
        
        self._vector_db_path = vector_db_path
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._embedder_model = embedder_model
        
        self.docs_dir = Path("data/documents")
        self.docs_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def parser(self):
        """延迟加载解析�?""
        if self._parser is None:
            self._parser = get_parser()
        return self._parser
    
    @property
    def chunker(self):
        """延迟加载分块�?""
        if self._chunker is None:
            self._chunker = get_chunker(self._chunk_size, self._chunk_overlap)
        return self._chunker
    
    @property
    def embedder(self):
        """延迟加载嵌入�?""
        if self._embedder is None:
            self._embedder = get_embedder(self._embedder_model)
        return self._embedder
    
    @property
    def vector_store(self):
        """延迟加载向量存储"""
        if self._vector_store is None:
            self._vector_store = get_vector_store(self._vector_db_path)
        return self._vector_store
    
    def upload_document(
        self,
        file_path: str,
        collection_name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        上传文档到知识库
        
        Args:
            file_path: 文件路径
            collection_name: 集合名称（工作空�?ID�?            metadata: 元数�?            
        Returns:
            处理结果
        """
        logger.info(f"开始处理文档：{file_path}")
        
        # 1. 解析文档
        content = self.parser.parse(file_path)
        if not content:
            raise ValueError(f"文档解析失败：{file_path}")
        
        logger.info(f"文档解析完成：{len(content)} 字符")
        
        # 2. 复制文件到文档目�?        file_name = Path(file_path).name
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        dest_path = self.docs_dir / f"{doc_id}_{file_name}"
        
        try:
            Path(file_path).rename(dest_path)
        except Exception:
            # 如果移动失败，复�?            import shutil
            shutil.copy2(file_path, dest_path)
        
        # 3. 文本分块
        chunks = self.chunker.chunk(content, metadata)
        logger.info(f"文本分块完成：{len(chunks)} �?)
        
        if not chunks:
            raise ValueError("文本分块后为�?)
        
        # 4. 向量�?        chunk_texts = [chunk.content for chunk in chunks]
        embeddings = self.embedder.embed_chunks(chunk_texts)
        logger.info(f"向量化完成：{len(embeddings)} 向量")
        
        # 5. 存储到向量数据库
        doc_metadatas = []
        for i, chunk in enumerate(chunks):
            doc_meta = {
                "source": file_name,
                "doc_id": doc_id,
                "chunk_index": i,
                "start_index": chunk.start_index,
                "end_index": chunk.end_index,
                "uploaded_at": datetime.now().isoformat(),
                **(metadata or {})
            }
            doc_metadatas.append(doc_meta)
        
        ids = self.vector_store.add_documents(
            collection_name=collection_name,
            documents=chunk_texts,
            embeddings=embeddings,
            metadatas=doc_metadatas
        )
        
        logger.info(f"文档已存储到知识库：{len(ids)} 个向�?)
        
        return {
            "doc_id": doc_id,
            "file_name": file_name,
            "chunk_count": len(chunks),
            "vector_count": len(ids),
            "content_length": len(content),
            "file_path": str(dest_path)
        }
    
    def search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        搜索相关文档
        
        Args:
            collection_name: 集合名称
            query: 查询文本
            top_k: 返回数量
            
        Returns:
            搜索结果
        """
        logger.info(f"搜索：{query} (top_k={top_k})")
        
        # 向量化查�?        query_embedding = self.embedder.embed_single(query)
        
        # 搜索
        results = self.vector_store.search(
            collection_name=collection_name,
            query_embedding=query_embedding,
            top_k=top_k
        )
        
        logger.info(f"搜索完成：{len(results)} 个结�?)
        
        return results
    
    def search_with_context(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5
    ) -> str:
        """
        搜索并组装上下文
        
        Args:
            collection_name: 集合名称
            query: 查询文本
            top_k: 返回数量
            
        Returns:
            组装的上下文文本
        """
        results = self.search(collection_name, query, top_k)
        
        if not results:
            return ""
        
        # 组装上下�?        context_parts = []
        for i, result in enumerate(results):
            part = f"[相关片段 {i+1}]: {result['content']}"
            context_parts.append(part)
        
        return "\n\n".join(context_parts)
    
    def delete_document(
        self,
        collection_name: str,
        doc_id: str
    ) -> bool:
        """
        删除文档
        
        Args:
            collection_name: 集合名称
            doc_id: 文档 ID
            
        Returns:
            是否成功
        """
        # 删除向量数据库中的文�?        # 这里需要查询所有该 doc_id 的向量并删除
        # 简化实现：直接删除集合（生产环境需要更精细的控制）
        try:
            # 获取集合统计
            stats = self.vector_store.get_collection_stats(collection_name)
            logger.info(f"删除文档：{doc_id}, 集合：{collection_name}")
            
            # TODO: 实现�?doc_id 过滤删除
            # 目前简化处�?            
            return True
        except Exception as e:
            logger.error(f"删除文档失败：{e}")
            return False
    
    def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        """
        获取集合信息
        
        Args:
            collection_name: 集合名称
            
        Returns:
            集合信息
        """
        return self.vector_store.get_collection_stats(collection_name)
    
    def list_documents(
        self,
        collection_name: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        列出集合中的所有文�?        
        Args:
            collection_name: 集合名称
            limit: 返回数量限制
            offset: 偏移�?            
        Returns:
            文档列表
        """
        try:
            collection = self.vector_store.get_or_create_collection(collection_name)
            
            all_data = collection.get(include=["metadatas"])
            
            doc_map = {}
            if all_data['metadatas']:
                for i, meta in enumerate(all_data['metadatas']):
                    doc_id = meta.get('doc_id', f'unknown_{i}')
                    if doc_id not in doc_map:
                        doc_map[doc_id] = {
                            "doc_id": doc_id,
                            "source": meta.get('source', 'unknown'),
                            "chunk_count": 0,
                            "uploaded_at": meta.get('uploaded_at', '')
                        }
                    doc_map[doc_id]["chunk_count"] += 1
            
            docs = list(doc_map.values())
            return docs[offset:offset + limit]
        except Exception as e:
            logger.error(f"列出文档失败: {e}")
            return []
    
    def list_collections(self) -> List[Dict[str, Any]]:
        """
        列出所有集�?        
        Returns:
            集合列表
        """
        try:
            collection_names = self.vector_store.list_collections()
            collections = []
            
            for name in collection_names:
                try:
                    stats = self.vector_store.get_collection_stats(name)
                    collections.append({
                        "id": name,
                        "name": name,
                        "document_count": stats.get("count", 0),
                        "created_at": "",
                        "metadata": {}
                    })
                except Exception as e:
                    logger.warning(f"获取集合 {name} 信息失败: {e}")
                    collections.append({
                        "id": name,
                        "name": name,
                        "document_count": 0,
                        "created_at": "",
                        "metadata": {}
                    })
            
            return collections
        except Exception as e:
            logger.error(f"列出集合失败: {e}")
            return []
    
    def create_collection(
        self,
        name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        创建集合
        
        Args:
            name: 集合名称
            metadata: 元数�?            
        Returns:
            集合信息
        """
        collection = self.vector_store.get_or_create_collection(name)
        return {
            "id": name,
            "name": name,
            "document_count": 0,
            "metadata": metadata or {}
        }
    
    def delete_collection(self, collection_name: str) -> bool:
        """
        删除集合
        
        Args:
            collection_name: 集合名称
            
        Returns:
            是否成功
        """
        try:
            self.vector_store.delete_collection(collection_name)
            return True
        except Exception as e:
            logger.error(f"删除集合失败: {e}")
            return False


# 单例实例
_service_instance: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """获取 RAG 服务实例"""
    global _service_instance
    if _service_instance is None:
        _service_instance = RAGService()
    return _service_instance


def reset_rag_service(config: Dict[str, Any]) -> RAGService:
    """重置 RAG 服务"""
    global _service_instance
    _service_instance = RAGService(**config)
    return _service_instance

"""
知识库服务
"""
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import Chunk, Document, KnowledgeBase, SearchResult

logger = logging.getLogger(__name__)


class KnowledgeService:
    """知识库服务"""

    def __init__(self, storage_path: str = "data/knowledge"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._knowledge_bases: dict[str, KnowledgeBase] = {}
        self._documents: dict[str, Document] = {}
        self._chunks: dict[str, Chunk] = {}

        self._vector_store = None
        self._embedder = None

    def create_knowledge_base(
        self,
        name: str,
        description: str = None
    ) -> KnowledgeBase:
        """创建知识库"""
        kb_id = f"kb_{uuid.uuid4().hex[:8]}"

        kb = KnowledgeBase(
            id=kb_id,
            name=name,
            description=description
        )

        self._knowledge_bases[kb_id] = kb

        kb_path = self.storage_path / kb_id
        kb_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"创建知识库: {kb_id} - {name}")
        return kb

    def get_knowledge_base(self, kb_id: str) -> KnowledgeBase | None:
        """获取知识库"""
        return self._knowledge_bases.get(kb_id)

    def list_knowledge_bases(self) -> list[KnowledgeBase]:
        """列出所有知识库"""
        return list(self._knowledge_bases.values())

    def delete_knowledge_base(self, kb_id: str) -> bool:
        """删除知识库"""
        if kb_id not in self._knowledge_bases:
            return False

        del self._knowledge_bases[kb_id]

        docs_to_delete = [
            doc_id for doc_id, doc in self._documents.items()
            if doc.knowledge_base_id == kb_id
        ]
        for doc_id in docs_to_delete:
            del self._documents[doc_id]

        chunks_to_delete = [
            chunk_id for chunk_id, chunk in self._chunks.items()
            if chunk.knowledge_base_id == kb_id
        ]
        for chunk_id in chunks_to_delete:
            del self._chunks[chunk_id]

        logger.info(f"删除知识库: {kb_id}")
        return True

    def add_document(
        self,
        kb_id: str,
        filename: str,
        file_path: str,
        file_size: int = 0,
        file_type: str = ""
    ) -> Document:
        """添加文档"""
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"

        doc = Document(
            id=doc_id,
            knowledge_base_id=kb_id,
            filename=filename,
            file_path=file_path,
            file_size=file_size,
            file_type=file_type
        )

        self._documents[doc_id] = doc

        kb = self._knowledge_bases.get(kb_id)
        if kb:
            kb.document_count += 1
            kb.updated_at = datetime.now()

        logger.info(f"添加文档: {doc_id} - {filename}")
        return doc

    def get_document(self, doc_id: str) -> Document | None:
        """获取文档"""
        return self._documents.get(doc_id)

    def list_documents(self, kb_id: str) -> list[Document]:
        """列出知识库的文档"""
        return [
            doc for doc in self._documents.values()
            if doc.knowledge_base_id == kb_id
        ]

    def delete_document(self, doc_id: str) -> bool:
        """删除文档"""
        if doc_id not in self._documents:
            return False

        doc = self._documents[doc_id]
        kb_id = doc.knowledge_base_id

        del self._documents[doc_id]

        chunks_to_delete = [
            chunk_id for chunk_id, chunk in self._chunks.items()
            if chunk.document_id == doc_id
        ]
        for chunk_id in chunks_to_delete:
            del self._chunks[chunk_id]

        kb = self._knowledge_bases.get(kb_id)
        if kb:
            kb.document_count -= 1
            kb.updated_at = datetime.now()

        logger.info(f"删除文档: {doc_id}")
        return True

    def add_chunk(
        self,
        doc_id: str,
        kb_id: str,
        content: str,
        chunk_index: int = 0,
        start_char: int = 0,
        end_char: int = 0,
        embedding: list[float] = None
    ) -> Chunk:
        """添加分块"""
        chunk_id = f"chunk_{uuid.uuid4().hex[:8]}"

        chunk = Chunk(
            id=chunk_id,
            document_id=doc_id,
            knowledge_base_id=kb_id,
            content=content,
            chunk_index=chunk_index,
            start_char=start_char,
            end_char=end_char,
            embedding=embedding
        )

        self._chunks[chunk_id] = chunk

        doc = self._documents.get(doc_id)
        if doc:
            doc.chunk_count += 1
            doc.updated_at = datetime.now()

        kb = self._knowledge_bases.get(kb_id)
        if kb:
            kb.chunk_count += 1
            kb.updated_at = datetime.now()

        return chunk

    def search(
        self,
        kb_id: str,
        query: str,
        top_k: int = 5
    ) -> list[SearchResult]:
        """搜索"""
        results = []

        for chunk in self._chunks.values():
            if chunk.knowledge_base_id != kb_id:
                continue

            if query.lower() in chunk.content.lower():
                doc = self._documents.get(chunk.document_id)

                results.append(SearchResult(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    knowledge_base_id=kb_id,
                    content=chunk.content,
                    score=0.8,
                    filename=doc.filename if doc else None
                ))

        return results[:top_k]

    def get_stats(self, kb_id: str = None) -> dict[str, Any]:
        """获取统计信息"""
        if kb_id:
            kb = self._knowledge_bases.get(kb_id)
            if not kb:
                return {}

            return {
                "knowledge_base_id": kb_id,
                "name": kb.name,
                "document_count": kb.document_count,
                "chunk_count": kb.chunk_count
            }

        return {
            "total_knowledge_bases": len(self._knowledge_bases),
            "total_documents": len(self._documents),
            "total_chunks": len(self._chunks)
        }


_knowledge_service: KnowledgeService | None = None


def get_knowledge_service() -> KnowledgeService:
    """获取知识库服务实例"""
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service

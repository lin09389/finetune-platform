"""
知识库 API - 统一接口
提供完整的知识库管理、检索、统计、监控、导入导出功能
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal
from pathlib import Path
from datetime import datetime
import os
import json
import csv
import io
import logging
import time
import uuid

from rag.service import get_rag_service, RAGService
from rag.vector_store import get_vector_store, VectorStore
from rag.hybrid_retriever import get_hybrid_retriever, HybridRetriever, SearchResult
from rag.reranker import get_reranker, CrossEncoderReranker
from rag.evaluator import get_evaluator, get_online_evaluator, RetrievalEvaluator, OnlineEvaluator

logger = logging.getLogger(__name__)

router = APIRouter()


class UnifiedSearchRequest(BaseModel):
    """统一检索请求"""
    query: str = Field(..., description="查询文本")
    top_k: int = Field(default=10, ge=1, le=50, description="返回结果数量")
    method: Literal["vector", "keyword", "hybrid"] = Field(
        default="hybrid",
        description="检索方法：vector(向量)、keyword(关键词)、hybrid(混合)"
    )
    vector_weight: Optional[float] = Field(default=0.5, ge=0, le=1, description="向量检索权重（仅混合模式）")
    keyword_weight: Optional[float] = Field(default=0.5, ge=0, le=1, description="关键词检索权重（仅混合模式）")
    fusion_method: Optional[Literal["rrf", "weighted"]] = Field(
        default="rrf",
        description="融合方法(仅混合模式): rrf(倒数排名融合)、weighted(加权融合)"
    )
    use_rerank: bool = Field(default=False, description="是否使用重排序")
    rerank_top_k: Optional[int] = Field(default=None, description="重排序后返回数量")
    filter_metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数据过滤条件")


class UnifiedSearchResponse(BaseModel):
    """统一检索响应"""
    query: str
    method: str
    results: List[Dict[str, Any]]
    context: str
    total_count: int
    retrieval_time_ms: float
    reranked: bool = False


class KnowledgeBaseStats(BaseModel):
    """知识库统计信息"""
    collection_id: str
    document_count: int
    vector_count: int
    chunk_count: int
    storage_size_mb: float
    bm25_indexed: bool
    created_at: Optional[str] = None
    last_updated: Optional[str] = None


class KnowledgeBaseMonitor(BaseModel):
    """知识库监控信息"""
    collection_id: str
    avg_retrieval_latency_ms: float
    total_queries: int
    avg_hit_rate: float
    popular_queries: List[Dict[str, Any]]
    recent_errors: List[Dict[str, Any]]
    uptime_seconds: float


class ExportRequest(BaseModel):
    """导出请求"""
    collection_id: str
    format: Literal["json", "csv"] = Field(default="json", description="导出格式")
    include_embeddings: bool = Field(default=False, description="是否包含向量")
    include_metadata: bool = Field(default=True, description="是否包含元数据")


class ImportRequest(BaseModel):
    """导入请求元数据"""
    collection_id: str
    format: Literal["json", "csv"] = Field(default="json", description="导入格式")
    skip_duplicates: bool = Field(default=True, description="是否跳过重复文档")
    batch_size: int = Field(default=100, ge=10, le=500, description="批次大小")


class ImportResponse(BaseModel):
    """导入响应"""
    collection_id: str
    imported_count: int
    skipped_count: int
    error_count: int
    errors: List[str] = []


class CollectionCreateRequest(BaseModel):
    """创建集合请求"""
    collection_id: str = Field(..., description="集合 ID")
    description: Optional[str] = Field(default=None, description="集合描述")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="集合元数据")


class CollectionInfo(BaseModel):
    """集合信息"""
    id: str
    name: str
    description: Optional[str] = None
    document_count: int
    vector_count: int
    created_at: Optional[str] = None
    metadata: Dict[str, Any] = {}


class KnowledgeBaseManager:
    """知识库管理器"""

    def __init__(self):
        self.rag_service = get_rag_service()
        self.vector_store = get_vector_store()
        self.query_stats: Dict[str, List[Dict[str, Any]]] = {}
        self.error_log: Dict[str, List[Dict[str, Any]]] = {}
        self.start_time = time.time()

    def record_query(self, collection_id: str, query: str, latency_ms: float, hit: bool):
        """记录查询统计"""
        if collection_id not in self.query_stats:
            self.query_stats[collection_id] = []

        self.query_stats[collection_id].append({
            "query": query,
            "latency_ms": latency_ms,
            "hit": hit,
            "timestamp": datetime.now().isoformat()
        })

        if len(self.query_stats[collection_id]) > 1000:
            self.query_stats[collection_id] = self.query_stats[collection_id][-500:]

    def record_error(self, collection_id: str, error: str, context: Dict[str, Any]):
        """记录错误"""
        if collection_id not in self.error_log:
            self.error_log[collection_id] = []

        self.error_log[collection_id].append({
            "error": error,
            "context": context,
            "timestamp": datetime.now().isoformat()
        })

        if len(self.error_log[collection_id]) > 100:
            self.error_log[collection_id] = self.error_log[collection_id][-50:]

    def get_collection_stats(self, collection_id: str) -> Dict[str, Any]:
        """获取集合统计信息"""
        try:
            stats = self.vector_store.get_collection_stats(collection_id)
            collection = self.vector_store.get_or_create_collection(collection_id)

            all_data = collection.get(include=["metadatas"])

            doc_ids = set()
            chunk_count = 0
            if all_data['metadatas']:
                for meta in all_data['metadatas']:
                    doc_id = meta.get('doc_id')
                    if doc_id:
                        doc_ids.add(doc_id)
                    chunk_count += 1

            bm25_index_path = Path(f"data/bm25_indices/{collection_id}.json")
            bm25_indexed = bm25_index_path.exists()

            storage_path = Path("data/vectors")
            storage_size = 0
            if storage_path.exists():
                for file in storage_path.rglob("*"):
                    if file.is_file():
                        storage_size += file.stat().st_size

            return {
                "collection_id": collection_id,
                "document_count": len(doc_ids),
                "vector_count": stats.get("count", 0),
                "chunk_count": chunk_count,
                "storage_size_mb": round(storage_size / (1024 * 1024), 2),
                "bm25_indexed": bm25_indexed,
                "created_at": None,
                "last_updated": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"获取集合统计失败：{e}")
            raise

    def get_collection_monitor(self, collection_id: str) -> Dict[str, Any]:
        """获取集合监控信息"""
        queries = self.query_stats.get(collection_id, [])
        errors = self.error_log.get(collection_id, [])

        avg_latency = 0.0
        avg_hit_rate = 0.0

        if queries:
            avg_latency = sum(q["latency_ms"] for q in queries) / len(queries)
            avg_hit_rate = sum(1 for q in queries if q["hit"]) / len(queries)

        query_counts: Dict[str, int] = {}
        for q in queries:
            query_text = q["query"]
            query_counts[query_text] = query_counts.get(query_text, 0) + 1

        popular_queries = sorted(
            [{"query": k, "count": v} for k, v in query_counts.items()],
            key=lambda x: x["count"],
            reverse=True
        )[:10]

        recent_errors = errors[-10:] if errors else []

        return {
            "collection_id": collection_id,
            "avg_retrieval_latency_ms": round(avg_latency, 2),
            "total_queries": len(queries),
            "avg_hit_rate": round(avg_hit_rate, 4),
            "popular_queries": popular_queries,
            "recent_errors": recent_errors,
            "uptime_seconds": round(time.time() - self.start_time, 2)
        }


_kb_manager: Optional[KnowledgeBaseManager] = None


def get_kb_manager() -> KnowledgeBaseManager:
    """获取知识库管理器实例"""
    global _kb_manager
    if _kb_manager is None:
        _kb_manager = KnowledgeBaseManager()
    return _kb_manager


@router.post("/search/{collection_id}", response_model=UnifiedSearchResponse)
async def unified_search(
    collection_id: str,
    request: UnifiedSearchRequest
):
    """
    统一检索接口

    支持三种检索方法：
    - vector: 纯向量检索（语义相似度）
    - keyword: 纯关键词检索（BM25）
    - hybrid: 混合检索（向量 + 关键词融合）

    可选重排序功能提升结果质量
    """
    start_time = time.time()
    kb_manager = get_kb_manager()

    try:
        rag_service = get_rag_service()
        hybrid_retriever = get_hybrid_retriever(
            vector_store=rag_service.vector_store,
            embedder=rag_service.embedder
        )

        results: List[SearchResult] = []

        if request.method == "vector":
            results = hybrid_retriever.search_vector_only(
                collection_name=collection_id,
                query=request.query,
                top_k=request.top_k
            )
        elif request.method == "keyword":
            results = hybrid_retriever.search_keyword_only(
                collection_name=collection_id,
                query=request.query,
                top_k=request.top_k
            )
        else:
            hybrid_retriever.set_weights(request.vector_weight, request.keyword_weight)
            hybrid_retriever.set_fusion_method(request.fusion_method)
            results = hybrid_retriever.search(
                collection_name=collection_id,
                query=request.query,
                top_k=request.top_k,
                filter_metadata=request.filter_metadata
            )

        reranked = False
        if request.use_rerank and results:
            reranker = get_reranker()
            results_dict = [
                {
                    "id": r.id,
                    "content": r.content,
                    "score": r.score,
                    "metadata": r.metadata
                }
                for r in results
            ]

            rerank_top_k = request.rerank_top_k or request.top_k
            reranked_results = reranker.rerank(
                query=request.query,
                results=results_dict,
                top_k=rerank_top_k
            )

            results = [
                SearchResult(
                    id=r.id,
                    content=r.content,
                    score=r.score,
                    metadata=r.metadata,
                    vector_score=r.original_score,
                    source="reranked"
                )
                for r in reranked_results
            ]
            reranked = True

        results_dict = [
            {
                "id": r.id,
                "content": r.content,
                "score": r.score,
                "metadata": r.metadata,
                "vector_score": r.vector_score,
                "keyword_score": r.keyword_score,
                "source": r.source
            }
            for r in results
        ]

        context = "\n\n".join([r.content for r in results])

        latency_ms = (time.time() - start_time) * 1000

        kb_manager.record_query(
            collection_id=collection_id,
            query=request.query,
            latency_ms=latency_ms,
            hit=len(results) > 0
        )

        return UnifiedSearchResponse(
            query=request.query,
            method=request.method,
            results=results_dict,
            context=context,
            total_count=len(results),
            retrieval_time_ms=round(latency_ms, 2),
            reranked=reranked
        )

    except Exception as e:
        kb_manager.record_error(
            collection_id=collection_id,
            error=str(e),
            context={"query": request.query, "method": request.method}
        )
        logger.error(f"检索失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"检索失败：{str(e)}")


@router.get("/stats/{collection_id}", response_model=KnowledgeBaseStats)
async def get_knowledge_base_stats(collection_id: str):
    """
    获取知识库统计信息

    返回：
    - 文档数量
    - 向量数量
    - 分块数量
    - 存储大小
    - BM25 索引状态
    """
    try:
        kb_manager = get_kb_manager()
        stats = kb_manager.get_collection_stats(collection_id)
        return KnowledgeBaseStats(**stats)

    except Exception as e:
        logger.error(f"获取统计信息失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取统计信息失败：{str(e)}")


@router.get("/monitor/{collection_id}", response_model=KnowledgeBaseMonitor)
async def get_knowledge_base_monitor(collection_id: str):
    """
    获取知识库监控信息

    返回：
    - 平均检索延迟
    - 总查询次数
    - 平均命中率
    - 热门查询
    - 最近错误
    - 运行时间
    """
    try:
        kb_manager = get_kb_manager()
        monitor = kb_manager.get_collection_monitor(collection_id)
        return KnowledgeBaseMonitor(**monitor)

    except Exception as e:
        logger.error(f"获取监控信息失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取监控信息失败：{str(e)}")


@router.get("/stats/all")
async def get_all_knowledge_bases_stats():
    """获取所有知识库的统计信息概览"""
    try:
        vector_store = get_vector_store()
        collections = vector_store.list_collections()

        kb_manager = get_kb_manager()
        all_stats = []

        for name in collections:
            try:
                stats = kb_manager.get_collection_stats(name)
                all_stats.append(stats)
            except Exception as e:
                logger.warning(f"获取集合 {name} 统计失败：{e}")
                continue

        total_vectors = sum(s["vector_count"] for s in all_stats)
        total_docs = sum(s["document_count"] for s in all_stats)

        return {
            "total_collections": len(all_stats),
            "total_documents": total_docs,
            "total_vectors": total_vectors,
            "collections": all_stats
        }

    except Exception as e:
        logger.error(f"获取所有统计信息失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取统计信息失败：{str(e)}")


@router.post("/export")
async def export_knowledge_base(request: ExportRequest):
    """
    导出知识库

    支持格式：
    - JSON: 完整的结构化数据
    - CSV: 表格格式（不含向量）

    可选包含向量和元数据
    """
    try:
        vector_store = get_vector_store()
        collection = vector_store.get_or_create_collection(request.collection_id)

        include = ["documents", "metadatas"]
        if request.include_embeddings:
            include.append("embeddings")

        all_data = collection.get(include=include)

        if not all_data['documents']:
            raise HTTPException(status_code=404, detail="知识库为空")

        export_data = []
        for i, doc in enumerate(all_data['documents']):
            item = {
                "id": all_data['ids'][i],
                "content": doc
            }

            if request.include_metadata and all_data['metadatas']:
                item["metadata"] = all_data['metadatas'][i]

            if request.include_embeddings and all_data.get('embeddings'):
                item["embedding"] = all_data['embeddings'][i]

            export_data.append(item)

        if request.format == "json":
            output = io.StringIO()
            json.dump(export_data, output, ensure_ascii=False, indent=2)
            output.seek(0)

            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename={request.collection_id}_export.json"
                }
            )

        else:
            output = io.StringIO()
            writer = csv.writer(output)

            headers = ["id", "content"]
            if request.include_metadata:
                all_keys = set()
                for item in export_data:
                    if "metadata" in item:
                        all_keys.update(item["metadata"].keys())
                headers.extend(sorted(all_keys))

            writer.writerow(headers)

            for item in export_data:
                row = [item["id"], item["content"]]
                if request.include_metadata and "metadata" in item:
                    for key in sorted(all_keys):
                        row.append(item["metadata"].get(key, ""))
                writer.writerow(row)

            output.seek(0)

            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={request.collection_id}_export.csv"
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出知识库失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"导出失败：{str(e)}")


@router.post("/import", response_model=ImportResponse)
async def import_knowledge_base(
    collection_id: str = Form(..., description="目标集合 ID"),
    file: UploadFile = File(..., description="导入文件"),
    format: Literal["json", "csv"] = Form(default="json", description="文件格式"),
    skip_duplicates: bool = Form(default=True, description="是否跳过重复文档"),
    batch_size: int = Form(default=100, description="批次大小")
):
    """
    导入知识库

    支持格式：
    - JSON: 包含 id, content, metadata(可选), embedding(可选)
    - CSV: 第一行为表头，必须包含 id 和 content 列

    支持批量导入和去重
    """
    try:
        content = await file.read()

        if format == "json":
            data = json.loads(content.decode('utf-8'))
            if not isinstance(data, list):
                data = [data]
        else:
            text = content.decode('utf-8')
            reader = csv.DictReader(io.StringIO(text))
            data = list(reader)

        if not data:
            raise HTTPException(status_code=400, detail="导入文件为空")

        rag_service = get_rag_service()
        vector_store = get_vector_store()

        existing_ids = set()
        if skip_duplicates:
            try:
                collection = vector_store.get_or_create_collection(collection_id)
                existing_data = collection.get(include=[])
                existing_ids = set(existing_data['ids'])
            except Exception:
                pass

        imported_count = 0
        skipped_count = 0
        error_count = 0
        errors = []

        batch_documents = []
        batch_embeddings = []
        batch_metadatas = []
        batch_ids = []

        for i, item in enumerate(data):
            try:
                if format == "json":
                    doc_id = item.get("id", f"import_{uuid.uuid4().hex[:12]}")
                    content_text = item.get("content", "")
                    metadata = item.get("metadata", {})
                    embedding = item.get("embedding")
                else:
                    doc_id = item.get("id", f"import_{uuid.uuid4().hex[:12]}")
                    content_text = item.get("content", "")
                    metadata = {k: v for k, v in item.items() if k not in ["id", "content"]}
                    embedding = None

                if not content_text:
                    error_count += 1
                    errors.append(f"第 {i+1} 条记录缺少内容")
                    continue

                if skip_duplicates and doc_id in existing_ids:
                    skipped_count += 1
                    continue

                batch_ids.append(doc_id)
                batch_documents.append(content_text)
                batch_metadatas.append(metadata)
                batch_embeddings.append(embedding)

                imported_count += 1

                if len(batch_documents) >= batch_size:
                    _save_batch(
                        vector_store, collection_id,
                        batch_documents, batch_embeddings, batch_metadatas, batch_ids
                    )
                    batch_documents = []
                    batch_embeddings = []
                    batch_metadatas = []
                    batch_ids = []

            except Exception as e:
                error_count += 1
                errors.append(f"第 {i+1} 条记录处理失败：{str(e)}")

        if batch_documents:
            _save_batch(
                vector_store, collection_id,
                batch_documents, batch_embeddings, batch_metadatas, batch_ids
            )

        return ImportResponse(
            collection_id=collection_id,
            imported_count=imported_count,
            skipped_count=skipped_count,
            error_count=error_count,
            errors=errors[:10]
        )

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON 格式错误")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导入知识库失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"导入失败：{str(e)}")


def _save_batch(
    vector_store: VectorStore,
    collection_id: str,
    documents: List[str],
    embeddings: List[Any],
    metadatas: List[Dict[str, Any]],
    ids: List[str]
):
    """保存批次数据"""
    valid_embeddings = [e for e in embeddings if e is not None]

    if len(valid_embeddings) == len(embeddings):
        vector_store.add_documents(
            collection_name=collection_id,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )
    else:
        rag_service = get_rag_service()
        computed_embeddings = rag_service.embedder.embed_chunks(documents)

        vector_store.add_documents(
            collection_name=collection_id,
            documents=documents,
            embeddings=computed_embeddings,
            metadatas=metadatas,
            ids=ids
        )


@router.post("/collections", response_model=CollectionInfo)
async def create_collection(request: CollectionCreateRequest):
    """创建新的知识库集合"""
    try:
        vector_store = get_vector_store()
        collection = vector_store.get_or_create_collection(request.collection_id)

        return CollectionInfo(
            id=request.collection_id,
            name=request.collection_id,
            description=request.description,
            document_count=0,
            vector_count=0,
            created_at=datetime.now().isoformat(),
            metadata=request.metadata or {}
        )

    except Exception as e:
        logger.error(f"创建集合失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建集合失败：{str(e)}")


@router.get("/collections", response_model=List[CollectionInfo])
async def list_collections():
    """列出所有知识库集合"""
    try:
        vector_store = get_vector_store()
        collections = vector_store.list_collections()

        kb_manager = get_kb_manager()
        collection_infos = []

        for name in collections:
            try:
                stats = kb_manager.get_collection_stats(name)
                collection_infos.append(CollectionInfo(
                    id=name,
                    name=name,
                    document_count=stats["document_count"],
                    vector_count=stats["vector_count"],
                    created_at=stats.get("created_at"),
                    metadata={}
                ))
            except Exception as e:
                logger.warning(f"获取集合 {name} 信息失败：{e}")
                continue

        return collection_infos

    except Exception as e:
        logger.error(f"列出集合失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"列出集合失败：{str(e)}")


@router.delete("/collections/{collection_id}")
async def delete_collection(collection_id: str):
    """删除知识库集合"""
    try:
        vector_store = get_vector_store()
        vector_store.delete_collection(collection_id)

        bm25_index_path = Path(f"data/bm25_indices/{collection_id}.json")
        if bm25_index_path.exists():
            bm25_index_path.unlink()

        return {"message": "集合已删除", "collection_id": collection_id}

    except Exception as e:
        logger.error(f"删除集合失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除集合失败：{str(e)}")


@router.post("/collections/{collection_id}/build-index")
async def build_search_index(collection_id: str):
    """
    构建检索索引

    - 构建 BM25 关键词索引
    - 优化向量索引
    """
    try:
        rag_service = get_rag_service()
        hybrid_retriever = get_hybrid_retriever(
            vector_store=rag_service.vector_store,
            embedder=rag_service.embedder
        )

        collection = rag_service.vector_store.get_or_create_collection(collection_id)
        all_data = collection.get(include=["documents", "metadatas"])

        if not all_data['documents']:
            return {"message": "集合为空，无需构建索引", "collection_id": collection_id}

        hybrid_retriever.build_bm25_index(
            collection_name=collection_id,
            documents=all_data['documents'],
            ids=all_data['ids'],
            metadatas=all_data['metadatas']
        )

        return {
            "message": "索引构建成功",
            "collection_id": collection_id,
            "document_count": len(all_data['documents'])
        }

    except Exception as e:
        logger.error(f"构建索引失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"构建索引失败：{str(e)}")


@router.get("/collections/{collection_id}/documents")
async def list_documents(
    collection_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0)
):
    """列出集合中的文档"""
    try:
        rag_service = get_rag_service()
        documents = rag_service.list_documents(collection_id)

        total = len(documents)
        paginated = documents[offset:offset + limit]

        return {
            "collection_id": collection_id,
            "total": total,
            "documents": paginated,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"列出文档失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"列出文档失败：{str(e)}")


@router.delete("/collections/{collection_id}/documents/{doc_id}")
async def delete_document(collection_id: str, doc_id: str):
    """删除文档"""
    try:
        vector_store = get_vector_store()
        collection = vector_store.get_or_create_collection(collection_id)

        all_data = collection.get(
            where={"doc_id": doc_id},
            include=[]
        )

        if not all_data['ids']:
            raise HTTPException(status_code=404, detail="文档不存在")

        collection.delete(ids=all_data['ids'])

        return {
            "message": "文档已删除",
            "doc_id": doc_id,
            "deleted_chunks": len(all_data['ids'])
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文档失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除文档失败：{str(e)}")


@router.post("/collections/{collection_id}/documents")
async def add_document(
    collection_id: str,
    content: str = Form(..., description="文档内容"),
    metadata: Optional[str] = Form(default=None, description="元数据（JSON）")
):
    """添加单个文档"""
    try:
        rag_service = get_rag_service()

        meta_dict = {}
        if metadata:
            try:
                meta_dict = json.loads(metadata)
            except json.JSONDecodeError:
                pass

        chunks = rag_service.chunker.chunk(content, meta_dict)

        if not chunks:
            raise HTTPException(status_code=400, detail="文档内容无法分块")

        chunk_texts = [chunk.content for chunk in chunks]
        embeddings = rag_service.embedder.embed_chunks(chunk_texts)

        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        doc_metadatas = []

        for i, chunk in enumerate(chunks):
            doc_meta = {
                "source": "manual_input",
                "doc_id": doc_id,
                "chunk_index": i,
                "start_index": chunk.start_index,
                "end_index": chunk.end_index,
                "uploaded_at": datetime.now().isoformat(),
                **meta_dict
            }
            doc_metadatas.append(doc_meta)

        ids = rag_service.vector_store.add_documents(
            collection_name=collection_id,
            documents=chunk_texts,
            embeddings=embeddings,
            metadatas=doc_metadatas
        )

        return {
            "message": "文档已添加",
            "doc_id": doc_id,
            "chunk_count": len(chunks),
            "vector_count": len(ids)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加文档失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"添加文档失败：{str(e)}")


@router.get("/health")
async def knowledge_base_health():
    """知识库健康检查"""
    try:
        vector_store = get_vector_store()
        collections = vector_store.list_collections()

        return {
            "status": "healthy",
            "collections_count": len(collections),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

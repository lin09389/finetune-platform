"""
RAG 知识库 API
提供文档上传、搜索、管理等功能
支持混合检索、重排序、质量评估
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
import tempfile
import logging
import shutil

from rag.service import get_rag_service, RAGService
from rag.hybrid_retriever import get_hybrid_retriever, HybridRetriever, SearchResult
from rag.reranker import get_reranker, CrossEncoderReranker, RerankResult
from rag.evaluator import get_evaluator, get_online_evaluator, RetrievalEvaluator, OnlineEvaluator

logger = logging.getLogger(__name__)

router = APIRouter()


class UploadResponse(BaseModel):
    """上传响应"""
    doc_id: str
    file_name: str
    chunk_count: int
    vector_count: int
    content_length: int
    message: str = "上传成功"


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str = Field(..., description="查询文本")
    top_k: int = Field(default=5, ge=1, le=20, description="返回结果数量")


class SearchResponse(BaseModel):
    """搜索响应"""
    query: str
    results: List[Dict[str, Any]]
    context: str


class DocumentInfo(BaseModel):
    """文档信息"""
    doc_id: str
    source: str
    chunk_count: int
    uploaded_at: str


class CollectionInfo(BaseModel):
    """集合信息"""
    name: str
    count: int
    documents: List[DocumentInfo]


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    collection_id: str = Form(..., description="集合 ID/工作空间 ID"),
    file: UploadFile = File(..., description="上传的文件")
):
    """
    上传文档到知识库
    
    - 支持格式：PDF, DOCX, TXT, MD
    - 自动解析、分块、向量化
    """
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name
        
        try:
            rag_service = get_rag_service()
            result = rag_service.upload_document(
                file_path=tmp_path,
                collection_name=collection_id,
                metadata={"original_filename": file.filename}
            )
            
            return UploadResponse(
                doc_id=result["doc_id"],
                file_name=result["file_name"],
                chunk_count=result["chunk_count"],
                vector_count=result["vector_count"],
                content_length=result["content_length"],
                message="文档上传成功"
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    except Exception as e:
        logger.error(f"上传文档失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"上传失败：{str(e)}")


@router.post("/search", response_model=SearchResponse)
async def search_documents(request: SearchRequest, collection_id: str = Form(...)):
    """
    搜索知识库文档
    
    - 语义搜索（向量相似度）
    - 返回最相关的文档片段
    """
    try:
        rag_service = get_rag_service()
        
        results = rag_service.search(
            collection_name=collection_id,
            query=request.query,
            top_k=request.top_k
        )
        
        context = rag_service.search_with_context(
            collection_name=collection_id,
            query=request.query,
            top_k=request.top_k
        )
        
        return SearchResponse(
            query=request.query,
            results=results,
            context=context
        )
    
    except Exception as e:
        logger.error(f"搜索失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"搜索失败：{str(e)}")


@router.get("/collection/{collection_id}")
async def get_collection_info(collection_id: str):
    """获取集合信息"""
    try:
        rag_service = get_rag_service()
        
        stats = rag_service.get_collection_info(collection_id)
        documents = rag_service.list_documents(collection_id)
        
        return {
            "name": collection_id,
            "count": stats.get("count", 0),
            "documents": documents
        }
    
    except Exception as e:
        logger.error(f"获取集合信息失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取失败：{str(e)}")


@router.delete("/collection/{collection_id}/document/{doc_id}")
async def delete_document(collection_id: str, doc_id: str):
    """删除文档"""
    try:
        rag_service = get_rag_service()
        success = rag_service.delete_document(collection_id, doc_id)
        
        if success:
            return {"message": "删除成功", "doc_id": doc_id}
        else:
            raise HTTPException(status_code=404, detail="文档不存在")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文档失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除失败：{str(e)}")


@router.get("/collections")
async def list_collections():
    """列出所有集合"""
    try:
        vector_store = get_rag_service().vector_store
        collections = vector_store.list_collections()
        
        collection_infos = []
        for name in collections:
            try:
                stats = vector_store.get_collection_stats(name)
                collection_infos.append({
                    "name": name,
                    "count": stats.get("count", 0)
                })
            except Exception:
                continue
        
        return {"collections": collection_infos}
    
    except Exception as e:
        logger.error(f"列出集合失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取失败：{str(e)}")


class RAGChatRequest(BaseModel):
    """RAG 聊天请求"""
    query: str = Field(..., description="用户问题")
    collection_id: str = Field(..., description="集合 ID")
    top_k: int = Field(default=5, description="检索文档数量")
    system_prompt: Optional[str] = Field(default=None, description="系统提示词")


class RAGChatResponse(BaseModel):
    """RAG 聊天响应"""
    answer: str
    context: str
    sources: List[Dict[str, Any]]


@router.post("/chat", response_model=RAGChatResponse)
async def rag_chat(request: RAGChatRequest):
    """
    RAG 增强的聊天
    
    - 先检索相关知识
    - 组装上下文后调用 LLM
    """
    try:
        rag_service = get_rag_service()
        
        results = rag_service.search(
            collection_name=request.collection_id,
            query=request.query,
            top_k=request.top_k
        )
        
        context = "\n\n".join([r["content"] for r in results])
        
        system_prompt = request.system_prompt or """你是一个有帮助的助手。请基于以下上下文回答问题。如果上下文中没有相关信息，请说明你不知道。"""

        prompt = f"""{system_prompt}

上下文：
{context}

问题：{request.query}

回答："""
        
        import requests
        from core.config import get_settings
        
        settings = get_settings()
        
        try:
            response = requests.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": "qwen:4b",
                    "prompt": prompt,
                    "stream": False
                },
                timeout=60
            )
            
            if response.status_code == 200:
                answer = response.json().get("response", "")
            else:
                answer = f"[LLM 调用失败：{response.status_code}]"
        except Exception as e:
            answer = f"[LLM 调用失败：{str(e)}]"
        
        return RAGChatResponse(
            answer=answer,
            context=context,
            sources=results
        )
    
    except Exception as e:
        logger.error(f"RAG 聊天失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"RAG 聊天失败：{str(e)}")


class HybridSearchRequest(BaseModel):
    """混合检索请求"""
    query: str = Field(..., description="查询文本")
    top_k: int = Field(default=10, ge=1, le=50, description="返回结果数量")
    vector_weight: Optional[float] = Field(default=0.5, ge=0, le=1, description="向量检索权重")
    keyword_weight: Optional[float] = Field(default=0.5, ge=0, le=1, description="关键词检索权重")
    fusion_method: Optional[str] = Field(default="rrf", description="融合方法: rrf/weighted")


class HybridSearchResponse(BaseModel):
    """混合检索响应"""
    query: str
    results: List[Dict[str, Any]]
    context: str
    retrieval_method: str


@router.post("/hybrid-search", response_model=HybridSearchResponse)
async def hybrid_search(
    request: HybridSearchRequest,
    collection_id: str = Form(..., description="集合 ID")
):
    """
    混合检索
    
    - 结合向量检索和 BM25 关键词检索
    - 支持 RRF 和加权融合两种方式
    - 可调节向量/关键词权重
    """
    try:
        rag_service = get_rag_service()
        hybrid_retriever = get_hybrid_retriever(
            vector_store=rag_service.vector_store,
            embedder=rag_service.embedder
        )
        
        hybrid_retriever.set_weights(request.vector_weight, request.keyword_weight)
        hybrid_retriever.set_fusion_method(request.fusion_method)
        
        results = hybrid_retriever.search(
            collection_name=collection_id,
            query=request.query,
            top_k=request.top_k
        )
        
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
        
        return HybridSearchResponse(
            query=request.query,
            results=results_dict,
            context=context,
            retrieval_method=f"hybrid_{request.fusion_method}"
        )
    
    except Exception as e:
        logger.error(f"混合检索失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"混合检索失败：{str(e)}")


@router.get("/search/vector/{collection_id}")
async def vector_search(
    collection_id: str,
    query: str = Query(..., description="查询文本"),
    top_k: int = Query(default=10, ge=1, le=50)
):
    """仅向量检索"""
    try:
        rag_service = get_rag_service()
        hybrid_retriever = get_hybrid_retriever(
            vector_store=rag_service.vector_store,
            embedder=rag_service.embedder
        )
        
        results = hybrid_retriever.search_vector_only(
            collection_name=collection_id,
            query=query,
            top_k=top_k
        )
        
        return {
            "query": query,
            "results": [
                {
                    "id": r.id,
                    "content": r.content,
                    "score": r.score,
                    "metadata": r.metadata
                }
                for r in results
            ]
        }
    
    except Exception as e:
        logger.error(f"向量检索失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"向量检索失败：{str(e)}")


@router.get("/search/keyword/{collection_id}")
async def keyword_search(
    collection_id: str,
    query: str = Query(..., description="查询文本"),
    top_k: int = Query(default=10, ge=1, le=50)
):
    """仅关键词检索（BM25）"""
    try:
        rag_service = get_rag_service()
        hybrid_retriever = get_hybrid_retriever(
            vector_store=rag_service.vector_store,
            embedder=rag_service.embedder
        )
        
        results = hybrid_retriever.search_keyword_only(
            collection_name=collection_id,
            query=query,
            top_k=top_k
        )
        
        return {
            "query": query,
            "results": [
                {
                    "id": r.id,
                    "content": r.content,
                    "score": r.score,
                    "metadata": r.metadata
                }
                for r in results
            ]
        }
    
    except Exception as e:
        logger.error(f"关键词检索失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"关键词检索失败：{str(e)}")


class RerankRequest(BaseModel):
    """重排序请求"""
    query: str = Field(..., description="查询文本")
    results: List[Dict[str, Any]] = Field(..., description="待重排序的检索结果")
    top_k: Optional[int] = Field(default=None, description="返回数量")
    threshold: Optional[float] = Field(default=None, ge=0, le=1, description="分数阈值")


class RerankResponse(BaseModel):
    """重排序响应"""
    query: str
    results: List[Dict[str, Any]]
    reranked_count: int


@router.post("/rerank", response_model=RerankResponse)
async def rerank_results(request: RerankRequest):
    """
    对检索结果进行重排序
    
    - 使用 Cross-Encoder 模型计算相关性
    - 支持设置分数阈值过滤低质量结果
    """
    try:
        reranker = get_reranker()
        
        if request.threshold is not None:
            results = reranker.rerank_with_threshold(
                query=request.query,
                results=request.results,
                threshold=request.threshold,
                min_results=3
            )
        else:
            results = reranker.rerank(
                query=request.query,
                results=request.results,
                top_k=request.top_k
            )
        
        results_dict = [
            {
                "id": r.id,
                "content": r.content,
                "score": r.score,
                "original_score": r.original_score,
                "original_rank": r.original_rank,
                "metadata": r.metadata
            }
            for r in results
        ]
        
        return RerankResponse(
            query=request.query,
            results=results_dict,
            reranked_count=len(results)
        )
    
    except Exception as e:
        logger.error(f"重排序失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"重排序失败：{str(e)}")


class SearchAndRerankRequest(BaseModel):
    """检索并重排序请求"""
    query: str = Field(..., description="查询文本")
    top_k: int = Field(default=5, ge=1, le=20, description="最终返回数量")
    retrieval_top_k: int = Field(default=20, ge=1, le=50, description="初始检索数量")
    use_hybrid: bool = Field(default=True, description="是否使用混合检索")
    vector_weight: float = Field(default=0.5, ge=0, le=1, description="向量检索权重")
    keyword_weight: float = Field(default=0.5, ge=0, le=1, description="关键词检索权重")


class SearchAndRerankResponse(BaseModel):
    """检索并重排序响应"""
    query: str
    results: List[Dict[str, Any]]
    context: str
    retrieval_method: str
    reranked: bool


@router.post("/search-rerank/{collection_id}", response_model=SearchAndRerankResponse)
async def search_and_rerank(
    collection_id: str,
    request: SearchAndRerankRequest
):
    """
    检索并重排序（一体化接口）
    
    - 先进行混合检索或向量检索
    - 再使用 Cross-Encoder 重排序
    - 返回最终的高质量结果
    """
    try:
        rag_service = get_rag_service()
        hybrid_retriever = get_hybrid_retriever(
            vector_store=rag_service.vector_store,
            embedder=rag_service.embedder
        )
        reranker = get_reranker()
        
        if request.use_hybrid:
            hybrid_retriever.set_weights(request.vector_weight, request.keyword_weight)
            initial_results = hybrid_retriever.search(
                collection_name=collection_id,
                query=request.query,
                top_k=request.retrieval_top_k
            )
            retrieval_method = "hybrid"
        else:
            initial_results = hybrid_retriever.search_vector_only(
                collection_name=collection_id,
                query=request.query,
                top_k=request.retrieval_top_k
            )
            retrieval_method = "vector"
        
        initial_results_dict = [
            {
                "id": r.id,
                "content": r.content,
                "score": r.score,
                "metadata": r.metadata
            }
            for r in initial_results
        ]
        
        reranked_results = reranker.rerank(
            query=request.query,
            results=initial_results_dict,
            top_k=request.top_k
        )
        
        results_dict = [
            {
                "id": r.id,
                "content": r.content,
                "score": r.score,
                "original_score": r.original_score,
                "original_rank": r.original_rank,
                "metadata": r.metadata
            }
            for r in reranked_results
        ]
        
        context = "\n\n".join([r.content for r in reranked_results])
        
        return SearchAndRerankResponse(
            query=request.query,
            results=results_dict,
            context=context,
            retrieval_method=retrieval_method,
            reranked=True
        )
    
    except Exception as e:
        logger.error(f"检索重排序失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"检索重排序失败：{str(e)}")


class EvaluateRequest(BaseModel):
    """评估请求"""
    queries: List[str] = Field(..., description="查询列表")
    retrieved_ids_list: List[List[str]] = Field(..., description="各查询的检索结果 ID 列表")
    relevant_ids_list: List[List[str]] = Field(..., description="各查询的相关文档 ID 列表")
    k_values: Optional[List[int]] = Field(default=[1, 3, 5, 10], description="评估的 K 值")


class EvaluateResponse(BaseModel):
    """评估响应"""
    total_queries: int
    avg_metrics: Dict[str, float]
    individual_count: int


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_retrieval(request: EvaluateRequest):
    """
    评估检索质量
    
    - 计算 MRR、MAP、Precision@K、Recall@K、NDCG@K 等指标
    - 支持批量评估多个查询
    """
    try:
        evaluator = get_evaluator(k_values=request.k_values)
        
        result = evaluator.evaluate_batch(
            queries=request.queries,
            retrieved_ids_list=request.retrieved_ids_list,
            relevant_ids_list=request.relevant_ids_list
        )
        
        return EvaluateResponse(
            total_queries=result.total_queries,
            avg_metrics=result.avg_metrics,
            individual_count=len(result.individual_results)
        )
    
    except Exception as e:
        logger.error(f"评估失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"评估失败：{str(e)}")


class FeedbackRequest(BaseModel):
    """用户反馈请求"""
    query: str = Field(..., description="查询文本")
    retrieved_ids: List[str] = Field(..., description="检索结果 ID 列表")
    clicked_ids: List[str] = Field(..., description="用户点击的文档 ID 列表")
    relevant_ids: Optional[List[str]] = Field(default=None, description="用户标记的相关文档 ID")


@router.post("/feedback")
async def record_feedback(request: FeedbackRequest):
    """
    记录用户反馈
    
    - 用于在线评估和持续改进
    - 记录点击和相关性标记
    """
    try:
        online_evaluator = get_online_evaluator()
        
        online_evaluator.record_feedback(
            query=request.query,
            retrieved_ids=request.retrieved_ids,
            clicked_ids=request.clicked_ids,
            relevant_ids=request.relevant_ids
        )
        
        return {"message": "反馈已记录", "query": request.query}
    
    except Exception as e:
        logger.error(f"记录反馈失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"记录反馈失败：{str(e)}")


@router.get("/metrics/online")
async def get_online_metrics():
    """获取在线评估指标"""
    try:
        online_evaluator = get_online_evaluator()
        metrics = online_evaluator.get_recent_metrics()
        popular_docs = online_evaluator.get_popular_documents(top_k=10)
        
        return {
            "metrics": metrics,
            "popular_documents": [
                {"doc_id": doc_id, "clicks": clicks}
                for doc_id, clicks in popular_docs
            ]
        }
    
    except Exception as e:
        logger.error(f"获取在线指标失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取在线指标失败：{str(e)}")


@router.get("/evaluation/history")
async def get_evaluation_history():
    """获取评估历史"""
    try:
        evaluator = get_evaluator()
        history = evaluator.get_evaluation_history()
        
        return {"history": history}
    
    except Exception as e:
        logger.error(f"获取评估历史失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取评估历史失败：{str(e)}")


@router.post("/bm25/build/{collection_id}")
async def build_bm25_index(collection_id: str):
    """
    构建 BM25 索引
    
    - 从向量数据库读取文档
    - 构建 BM25 倒排索引
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
            "message": "BM25 索引构建成功",
            "collection_id": collection_id,
            "document_count": len(all_data['documents'])
        }
    
    except Exception as e:
        logger.error(f"构建 BM25 索引失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"构建 BM25 索引失败：{str(e)}")


@router.get("/bm25/stats/{collection_id}")
async def get_bm25_stats(collection_id: str):
    """获取 BM25 索引统计信息"""
    try:
        rag_service = get_rag_service()
        hybrid_retriever = get_hybrid_retriever(
            vector_store=rag_service.vector_store,
            embedder=rag_service.embedder
        )
        
        bm25_index = hybrid_retriever._get_bm25_index(collection_id)
        
        return {
            "collection_id": collection_id,
            "document_count": bm25_index.N,
            "vocabulary_size": len(bm25_index.df),
            "avg_doc_length": bm25_index.avg_doc_length,
            "parameters": {
                "k1": bm25_index.k1,
                "b": bm25_index.b,
                "language": bm25_index.language
            }
        }
    
    except Exception as e:
        logger.error(f"获取 BM25 统计失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取 BM25 统计失败：{str(e)}")

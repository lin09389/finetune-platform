"""
知识模块路由 - 整合 RAG 知识库功�?"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
import tempfile
import logging
import shutil

from api.types import (
    KnowledgeDocument, KnowledgeCollection, KnowledgeSearchRequest,
    KnowledgeSearchResult, KnowledgeSearchResponse
)
from api.errors import CollectionNotFoundError, DocumentNotFoundError, UploadFailedError
from api.knowledge.service import get_knowledge_service

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


class CollectionCreateRequest(BaseModel):
    """创建集合请求"""
    name: str = Field(..., description="集合名称")
    description: Optional[str] = Field(None, description="集合描述")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数�?)


class CollectionUpdateRequest(BaseModel):
    """更新集合请求"""
    name: Optional[str] = Field(None, description="集合名称")
    description: Optional[str] = Field(None, description="集合描述")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数�?)


class CollectionListResponse(BaseModel):
    """集合列表响应"""
    collections: List[KnowledgeCollection]
    total: int


class DocumentListResponse(BaseModel):
    """文档列表响应"""
    documents: List[KnowledgeDocument]
    total: int


class EvaluationRequest(BaseModel):
    """评估请求"""
    query: str = Field(..., description="查询文本")
    collection_id: str = Field(..., description="集合 ID")
    top_k: int = Field(default=5, description="返回数量")


class EvaluationResponse(BaseModel):
    """评估响应"""
    query: str
    results: List[Dict[str, Any]]
    metrics: Dict[str, Any]


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    collection_id: str = Form(..., description="集合 ID"),
    file: UploadFile = File(..., description="上传的文�?)
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
            service = get_knowledge_service()
            result = service.upload_document(
                file_path=tmp_path,
                collection_id=collection_id,
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
        raise UploadFailedError(file.filename, str(e))


@router.post("/search", response_model=KnowledgeSearchResponse)
async def search_documents(request: KnowledgeSearchRequest):
    """
    搜索知识库文�?    
    - 支持向量检索、关键词检索、混合检�?    - 支持重排�?    """
    try:
        service = get_knowledge_service()
        
        import time
        start_time = time.time()
        
        results = service.search(
            collection_id=request.collection_id,
            query=request.query,
            top_k=request.top_k,
            min_score=request.min_score,
            method=request.method
        )
        
        retrieval_time = time.time() - start_time
        
        search_results = [
            KnowledgeSearchResult(
                id=r.get("id", ""),
                content=r.get("content", ""),
                source=r.get("source", ""),
                score=r.get("score", 0),
                metadata=r.get("metadata", {})
            )
            for r in results
        ]
        
        return KnowledgeSearchResponse(
            query=request.query,
            results=search_results,
            total_count=len(search_results),
            retrieval_time=round(retrieval_time, 3),
            method=request.method
        )
    
    except Exception as e:
        logger.error(f"搜索失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"搜索失败：{str(e)}")


@router.get("/collections", response_model=CollectionListResponse)
async def list_collections():
    """列出所有知识库集合"""
    try:
        service = get_knowledge_service()
        collections = service.list_collections()
        
        return CollectionListResponse(
            collections=[
                KnowledgeCollection(
                    id=c.get("id", c.get("name", "")),
                    name=c.get("name", ""),
                    description=c.get("description", ""),
                    document_count=c.get("document_count", c.get("count", 0)),
                    # created_at 使用默认值，不传
                    metadata=c.get("metadata", {})
                )
                for c in collections
            ],
            total=len(collections)
        )
    except Exception as e:
        logger.error(f"获取集合列表失败：{e}")
        raise HTTPException(status_code=500, detail=f"获取失败：{str(e)}")


@router.post("/collections", response_model=KnowledgeCollection)
async def create_collection(data: CollectionCreateRequest):
    """创建知识库集�?""
    try:
        service = get_knowledge_service()
        collection = service.create_collection(
            name=data.name,
            description=data.description,
            metadata=data.metadata
        )
        
        return KnowledgeCollection(
            id=collection.get("id", collection.get("name", "")),
            name=collection.get("name", data.name),
            description=collection.get("description", data.description or ""),
            document_count=0,
            metadata=collection.get("metadata", data.metadata)
        )
    except Exception as e:
        logger.error(f"创建集合失败：{e}")
        raise HTTPException(status_code=500, detail=f"创建失败：{str(e)}")


@router.get("/collections/{collection_id}")
async def get_collection(collection_id: str):
    """获取集合详情"""
    try:
        service = get_knowledge_service()
        collection = service.get_collection(collection_id)
        
        if not collection:
            raise CollectionNotFoundError(collection_id)
        
        return collection
    except CollectionNotFoundError:
        raise
    except Exception as e:
        logger.error(f"获取集合失败：{e}")
        raise HTTPException(status_code=500, detail=f"获取失败：{str(e)}")


@router.delete("/collections/{collection_id}")
async def delete_collection(collection_id: str):
    """删除集合"""
    try:
        service = get_knowledge_service()
        success = service.delete_collection(collection_id)
        
        if not success:
            raise CollectionNotFoundError(collection_id)
        
        return {"message": "集合已删�?, "collection_id": collection_id}
    except CollectionNotFoundError:
        raise
    except Exception as e:
        logger.error(f"删除集合失败：{e}")
        raise HTTPException(status_code=500, detail=f"删除失败：{str(e)}")


@router.get("/collections/{collection_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    collection_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """列出集合中的文档"""
    try:
        service = get_knowledge_service()
        documents = service.list_documents(collection_id, limit=limit, offset=offset)
        
        return DocumentListResponse(
            documents=[
                KnowledgeDocument(
                    id=d.get("id", ""),
                    filename=d.get("filename", d.get("source", "")),
                    content=d.get("content"),
                    collection_id=collection_id,
                    chunk_count=d.get("chunk_count", 0),
                    metadata=d.get("metadata", {})
                )
                for d in documents
            ],
            total=len(documents)
        )
    except Exception as e:
        logger.error(f"获取文档列表失败：{e}")
        raise HTTPException(status_code=500, detail=f"获取失败：{str(e)}")


@router.delete("/collections/{collection_id}/documents/{document_id}")
async def delete_document(collection_id: str, document_id: str):
    """删除文档"""
    try:
        service = get_knowledge_service()
        success = service.delete_document(collection_id, document_id)
        
        if not success:
            raise DocumentNotFoundError(document_id)
        
        return {"message": "文档已删�?, "document_id": document_id}
    except DocumentNotFoundError:
        raise
    except Exception as e:
        logger.error(f"删除文档失败：{e}")
        raise HTTPException(status_code=500, detail=f"删除失败：{str(e)}")


@router.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_retrieval(request: EvaluationRequest):
    """评估检索质�?""
    try:
        service = get_knowledge_service()
        results, metrics = service.evaluate_retrieval(
            query=request.query,
            collection_id=request.collection_id,
            top_k=request.top_k
        )
        
        return EvaluationResponse(
            query=request.query,
            results=results,
            metrics=metrics
        )
    except Exception as e:
        logger.error(f"评估失败：{e}")
        raise HTTPException(status_code=500, detail=f"评估失败：{str(e)}")


@router.get("/stats")
async def get_stats():
    """获取知识库统计信�?""
    try:
        service = get_knowledge_service()
        stats = service.get_stats()
        return stats
    except Exception as e:
        logger.error(f"获取统计信息失败：{e}")
        raise HTTPException(status_code=500, detail=f"获取失败：{str(e)}")

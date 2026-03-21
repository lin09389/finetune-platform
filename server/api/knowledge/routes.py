# -*- coding: utf-8 -*-
"""
知识库 API 路由
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from .service import get_knowledge_service
from .models import KnowledgeBase, Document, DocumentStatus

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


class CreateKBRequest(BaseModel):
    """创建知识库请求"""
    name: str = Field(..., description="知识库名称")
    description: Optional[str] = Field(default=None, description="描述")


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str = Field(..., description="查询文本")
    top_k: int = Field(default=5, ge=1, le=20, description="返回数量")


@router.get("/bases")
async def list_knowledge_bases():
    """列出所有知识库"""
    service = get_knowledge_service()
    bases = service.list_knowledge_bases()
    
    return {
        "bases": [
            {
                "id": kb.id,
                "name": kb.name,
                "description": kb.description,
                "document_count": kb.document_count,
                "chunk_count": kb.chunk_count,
                "created_at": kb.created_at.isoformat()
            }
            for kb in bases
        ],
        "total": len(bases)
    }


@router.post("/bases")
async def create_knowledge_base(request: CreateKBRequest):
    """创建知识库"""
    service = get_knowledge_service()
    kb = service.create_knowledge_base(
        name=request.name,
        description=request.description
    )
    
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description,
        "created_at": kb.created_at.isoformat()
    }


@router.get("/bases/{kb_id}")
async def get_knowledge_base(kb_id: str):
    """获取知识库详情"""
    service = get_knowledge_service()
    kb = service.get_knowledge_base(kb_id)
    
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description,
        "document_count": kb.document_count,
        "chunk_count": kb.chunk_count,
        "created_at": kb.created_at.isoformat(),
        "updated_at": kb.updated_at.isoformat()
    }


@router.delete("/bases/{kb_id}")
async def delete_knowledge_base(kb_id: str):
    """删除知识库"""
    service = get_knowledge_service()
    success = service.delete_knowledge_base(kb_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    
    return {"success": True, "kb_id": kb_id}


@router.get("/bases/{kb_id}/documents")
async def list_documents(kb_id: str):
    """列出知识库的文档"""
    service = get_knowledge_service()
    documents = service.list_documents(kb_id)
    
    return {
        "documents": [
            {
                "id": doc.id,
                "filename": doc.filename,
                "file_size": doc.file_size,
                "status": doc.status.value,
                "chunk_count": doc.chunk_count,
                "created_at": doc.created_at.isoformat()
            }
            for doc in documents
        ],
        "total": len(documents)
    }


@router.post("/bases/{kb_id}/documents")
async def upload_document(kb_id: str, file: UploadFile = File(...)):
    """上传文档"""
    service = get_knowledge_service()
    
    kb = service.get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    
    content = await file.read()
    
    doc = service.add_document(
        kb_id=kb_id,
        filename=file.filename,
        file_path="",
        file_size=len(content),
        file_type=file.content_type or ""
    )
    
    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status.value
    }


@router.delete("/bases/{kb_id}/documents/{doc_id}")
async def delete_document(kb_id: str, doc_id: str):
    """删除文档"""
    service = get_knowledge_service()
    success = service.delete_document(doc_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {"success": True, "doc_id": doc_id}


@router.post("/bases/{kb_id}/search")
async def search_knowledge(kb_id: str, request: SearchRequest):
    """搜索知识库"""
    service = get_knowledge_service()
    
    kb = service.get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    
    results = service.search(
        kb_id=kb_id,
        query=request.query,
        top_k=request.top_k
    )
    
    return {
        "results": [
            {
                "chunk_id": r.chunk_id,
                "document_id": r.document_id,
                "content": r.content,
                "score": r.score,
                "filename": r.filename
            }
            for r in results
        ],
        "query": request.query,
        "total": len(results)
    }


@router.get("/stats")
async def get_stats():
    """获取统计信息"""
    service = get_knowledge_service()
    return service.get_stats()

"""
知识库 API 路由
整合 RAG 功能，支持文档上传、搜索、管理
"""
import asyncio
import logging
import os
import shutil
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .service import get_knowledge_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Knowledge"])

_upload_tasks: dict[str, dict[str, Any]] = {}
_executor = ThreadPoolExecutor(max_workers=2)


class CreateKBRequest(BaseModel):
    """创建知识库请求"""
    name: str = Field(..., description="知识库名称")
    description: str | None = Field(default=None, description="描述")


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str = Field(..., description="查询文本")
    collection_id: str = Field(..., description="集合 ID")
    top_k: int = Field(default=5, ge=1, le=20, description="返回数量")


class UploadResponse(BaseModel):
    """上传响应"""
    doc_id: str
    file_name: str
    chunk_count: int
    vector_count: int
    content_length: int
    message: str = "上传成功"


class UploadStartResponse(BaseModel):
    """上传开始响应"""
    task_id: str
    status: str = "processing"
    message: str = "文档上传中，请稍后查询状态"


class UploadStatusResponse(BaseModel):
    """上传状态响应"""
    task_id: str
    status: str
    progress: int
    message: str
    result: dict[str, Any] | None = None
    error: str | None = None


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
    documents: list[DocumentInfo]


def _process_upload(task_id: str, tmp_path: str, collection_id: str, filename: str):
    """后台处理上传任务"""
    global _upload_tasks
    try:
        _upload_tasks[task_id]["status"] = "parsing"
        _upload_tasks[task_id]["progress"] = 10
        _upload_tasks[task_id]["message"] = "正在解析文档..."

        from rag.service import get_rag_service
        rag_service = get_rag_service()

        _upload_tasks[task_id]["status"] = "embedding"
        _upload_tasks[task_id]["progress"] = 30
        _upload_tasks[task_id]["message"] = "正在向量化..."

        result = rag_service.upload_document(
            file_path=tmp_path,
            collection_name=collection_id,
            metadata={"original_filename": filename}
        )

        _upload_tasks[task_id]["status"] = "completed"
        _upload_tasks[task_id]["progress"] = 100
        _upload_tasks[task_id]["message"] = "上传成功"
        _upload_tasks[task_id]["result"] = result

        logger.info(f"文档上传成功: {filename}, task_id: {task_id}")

    except Exception as e:
        logger.error(f"上传处理失败: {e}", exc_info=True)
        _upload_tasks[task_id]["status"] = "failed"
        _upload_tasks[task_id]["progress"] = 0
        _upload_tasks[task_id]["message"] = "上传失败"
        _upload_tasks[task_id]["error"] = str(e)

    finally:
        if os.path.exists(tmp_path):
            with suppress(Exception):
                os.unlink(tmp_path)


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    collection_id: str = Form(..., description="集合 ID/工作空间 ID"),
    file: UploadFile = File(..., description="上传的文件")
):
    """
    上传文档到知识库（同步模式）

    - 支持格式：PDF, DOCX, TXT, MD
    - 自动解析、分块、向量化
    """
    try:
        valid_extensions = ['.pdf', '.docx', '.doc', '.txt', '.md', '.markdown']
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in valid_extensions:
            raise HTTPException(status_code=400, detail=f"不支持的文件格式：{ext}")

        if file.size and file.size > 50 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件大小超过 50MB 限制")

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        try:
            from rag.service import get_rag_service
            rag_service = get_rag_service()

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                _executor,
                rag_service.upload_document,
                tmp_path,
                collection_id,
                {"original_filename": file.filename}
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传文档失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"上传失败：{str(e)}")


@router.post("/upload/async", response_model=UploadStartResponse)
async def upload_document_async(
    background_tasks: BackgroundTasks,
    collection_id: str = Form(..., description="集合 ID/工作空间 ID"),
    file: UploadFile = File(..., description="上传的文件")
):
    """
    上传文档到知识库（异步模式）

    - 立即返回 task_id
    - 通过 /upload/status/{task_id} 查询进度
    """
    global _upload_tasks

    valid_extensions = ['.pdf', '.docx', '.doc', '.txt', '.md', '.markdown']
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in valid_extensions:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式：{ext}")

    task_id = f"upload_{uuid.uuid4().hex[:8]}"

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    _upload_tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "message": "任务已创建",
        "filename": file.filename,
        "result": None,
        "error": None
    }

    _executor.submit(_process_upload, task_id, tmp_path, collection_id, file.filename)

    return UploadStartResponse(
        task_id=task_id,
        status="processing",
        message="文档上传中，请稍后查询状态"
    )


@router.get("/upload/status/{task_id}", response_model=UploadStatusResponse)
async def get_upload_status(task_id: str):
    """获取上传任务状态"""
    global _upload_tasks

    if task_id not in _upload_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = _upload_tasks[task_id]

    return UploadStatusResponse(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"],
        message=task["message"],
        result=task.get("result"),
        error=task.get("error")
    )


@router.get("/embedder/status")
async def get_embedder_status():
    """获取嵌入模型状态"""
    try:
        from rag.embedder import get_embedder
        embedder = get_embedder()

        return {
            "loaded": embedder.model is not None,
            "model_name": embedder.model_name,
            "dimension": embedder._dimension
        }
    except Exception as e:
        return {
            "loaded": False,
            "error": str(e)
        }


@router.post("/embedder/preload")
async def preload_embedder():
    """预加载嵌入模型"""
    try:
        from rag.embedder import get_embedder
        embedder = get_embedder()
        _ = embedder.dimension

        return {
            "success": True,
            "message": "嵌入模型已加载",
            "dimension": embedder._dimension
        }
    except Exception as e:
        logger.error(f"预加载嵌入模型失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"预加载失败：{str(e)}")


async def _run_blocking(func, /, *args, **kwargs):
    """Run sync RAG/service work off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


@router.get("/collections/{collection_id}", response_model=CollectionInfo)
async def get_collection_info(collection_id: str):
    """获取集合信息"""
    try:
        from rag.service import get_rag_service
        rag_service = get_rag_service()

        stats = await _run_blocking(rag_service.get_collection_info, collection_id)
        documents = await _run_blocking(rag_service.list_documents, collection_id)

        return CollectionInfo(
            name=collection_id,
            count=stats.get("count", 0),
            documents=[
                DocumentInfo(
                    doc_id=doc.get("doc_id", ""),
                    source=doc.get("source", ""),
                    chunk_count=doc.get("chunk_count", 0),
                    uploaded_at=doc.get("uploaded_at", "")
                )
                for doc in documents
            ]
        )

    except Exception as e:
        logger.error(f"获取集合信息失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取失败：{str(e)}")


@router.delete("/collections/{collection_id}/documents/{doc_id}")
async def delete_document(collection_id: str, doc_id: str):
    """删除文档"""
    try:
        from rag.service import get_rag_service
        rag_service = get_rag_service()
        success = await _run_blocking(rag_service.delete_document, collection_id, doc_id)

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
        from rag.service import get_rag_service
        rag_service = get_rag_service()
        collections = await _run_blocking(rag_service.list_collections)

        return {"collections": collections}

    except Exception as e:
        logger.error(f"列出集合失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取失败：{str(e)}")


@router.post("/search")
async def search_documents(request: SearchRequest):
    """
    搜索知识库文档

    - 语义搜索（向量相似度）
    - 返回最相关的文档片段
    """
    try:
        from rag.service import get_rag_service
        rag_service = get_rag_service()

        results = await _run_blocking(
            rag_service.search,
            collection_name=request.collection_id,
            query=request.query,
            top_k=request.top_k,
        )

        context = await _run_blocking(
            rag_service.search_with_context,
            collection_name=request.collection_id,
            query=request.query,
            top_k=request.top_k,
        )

        return {
            "query": request.query,
            "collection_id": request.collection_id,
            "results": results,
            "context": context
        }

    except Exception as e:
        logger.error(f"搜索失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"搜索失败：{str(e)}")


@router.get("/bases")
async def list_knowledge_bases():
    """列出所有知识库"""
    service = get_knowledge_service()
    bases = await _run_blocking(service.list_knowledge_bases)

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
    kb = await _run_blocking(
        service.create_knowledge_base,
        name=request.name,
        description=request.description,
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
    kb = await _run_blocking(service.get_knowledge_base, kb_id)

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
    success = await _run_blocking(service.delete_knowledge_base, kb_id)

    if not success:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    return {"success": True, "kb_id": kb_id}


@router.get("/bases/{kb_id}/documents")
async def list_documents(kb_id: str):
    """列出知识库的文档"""
    service = get_knowledge_service()
    documents = await _run_blocking(service.list_documents, kb_id)

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
async def upload_document_to_kb(kb_id: str, file: UploadFile = File(...)):
    """上传文档到知识库"""
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
async def delete_document_from_kb(kb_id: str, doc_id: str):
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

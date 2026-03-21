"""
文件解析 API 端点
支持文件上传、解析、向量化、检索
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging
import os
import tempfile
import shutil
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["文件解析"])


class FileUploadResponse(BaseModel):
    """文件上传响应"""
    file_id: str
    filename: str
    file_type: str
    file_size: int
    total_chars: int
    total_chunks: int
    created_at: str
    message: str = "文件上传并解析成功"


class FileInfoResponse(BaseModel):
    """文件信息响应"""
    file_id: str
    filename: str
    file_type: str
    file_size: int
    total_chars: int
    total_chunks: int
    created_at: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FileContentResponse(BaseModel):
    """文件内容响应"""
    file_id: str
    filename: str
    content: str
    chunks: List[Dict[str, Any]] = Field(default_factory=list)


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str = Field(..., description="搜索查询文本")
    file_ids: Optional[List[str]] = Field(None, description="指定文件ID列表，为空则搜索所有文件")
    top_k: int = Field(5, ge=1, le=20, description="返回结果数量")


class SearchResult(BaseModel):
    """搜索结果"""
    content: str
    score: float
    file_id: str
    filename: str
    chunk_index: int
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """搜索响应"""
    query: str
    results: List[SearchResult]
    total: int


class MultiFileUploadResponse(BaseModel):
    """多文件上传响应"""
    files: List[FileUploadResponse]
    total_files: int
    success_count: int
    failed_count: int
    message: str


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    enable_vectorization: bool = Form(True, description="是否启用向量化")
):
    """
    上传并解析文件
    
    支持的文件类型：
    - PDF (.pdf)
    - Word (.docx, .doc)
    - Excel (.xlsx, .xls)
    - 文本 (.txt, .md, .markdown)
    - 数据 (.csv, .json)
    """
    from core.file_parser import get_file_parser, get_file_vector_service
    
    parser = get_file_parser()
    
    if not parser.is_supported(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {file.filename}。支持的类型: PDF, Word, Excel, TXT, MD, CSV, JSON"
        )
    
    temp_dir = tempfile.mkdtemp()
    temp_file_path = os.path.join(temp_dir, file.filename)
    
    try:
        content = await file.read()
        with open(temp_file_path, 'wb') as f:
            f.write(content)
        
        parsed_file = await parser.parse_file(temp_file_path, file.filename)
        
        parser.save_file_content(parsed_file.file_id, parsed_file.content)
        
        if enable_vectorization:
            try:
                vector_service = get_file_vector_service()
                collection_name, doc_ids = await vector_service.index_file(parsed_file)
                parsed_file.vector_collection = collection_name
                logger.info(f"文件已向量化: {parsed_file.file_id}, 集合: {collection_name}")
            except Exception as e:
                logger.warning(f"文件向量化失败: {e}")
        
        return FileUploadResponse(
            file_id=parsed_file.file_id,
            filename=parsed_file.filename,
            file_type=parsed_file.file_type.value,
            file_size=parsed_file.file_size,
            total_chars=len(parsed_file.content),
            total_chunks=len(parsed_file.chunks),
            created_at=parsed_file.created_at
        )
    
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/upload/multiple", response_model=MultiFileUploadResponse)
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    enable_vectorization: bool = Form(True, description="是否启用向量化")
):
    """
    批量上传并解析多个文件
    
    最多同时上传10个文件
    """
    if len(files) > 10:
        raise HTTPException(
            status_code=400,
            detail="最多同时上传10个文件"
        )
    
    from core.file_parser import get_file_parser, get_file_vector_service
    
    parser = get_file_parser()
    vector_service = get_file_vector_service() if enable_vectorization else None
    
    results = []
    success_count = 0
    failed_count = 0
    
    for file in files:
        temp_dir = tempfile.mkdtemp()
        temp_file_path = os.path.join(temp_dir, file.filename)
        
        try:
            if not parser.is_supported(file.filename):
                failed_count += 1
                logger.warning(f"跳过不支持的文件类型: {file.filename}")
                continue
            
            content = await file.read()
            with open(temp_file_path, 'wb') as f:
                f.write(content)
            
            parsed_file = await parser.parse_file(temp_file_path, file.filename)
            parser.save_file_content(parsed_file.file_id, parsed_file.content)
            
            if vector_service:
                try:
                    collection_name, doc_ids = await vector_service.index_file(parsed_file)
                    parsed_file.vector_collection = collection_name
                except Exception as e:
                    logger.warning(f"文件向量化失败 ({file.filename}): {e}")
            
            results.append(FileUploadResponse(
                file_id=parsed_file.file_id,
                filename=parsed_file.filename,
                file_type=parsed_file.file_type.value,
                file_size=parsed_file.file_size,
                total_chars=len(parsed_file.content),
                total_chunks=len(parsed_file.chunks),
                created_at=parsed_file.created_at
            ))
            success_count += 1
        
        except Exception as e:
            logger.error(f"文件处理失败 ({file.filename}): {e}")
            failed_count += 1
        
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    return MultiFileUploadResponse(
        files=results,
        total_files=len(files),
        success_count=success_count,
        failed_count=failed_count,
        message=f"成功上传 {success_count} 个文件，失败 {failed_count} 个"
    )


@router.get("", response_model=List[FileInfoResponse])
async def list_files():
    """
    列出所有已上传的文件
    """
    from core.file_parser import get_file_parser
    
    parser = get_file_parser()
    files = parser.list_files()
    
    return [
        FileInfoResponse(
            file_id=f["file_id"],
            filename=f["filename"],
            file_type=f["file_type"],
            file_size=f["file_size"],
            total_chars=f["total_chars"],
            total_chunks=f["total_chunks"],
            created_at=f["created_at"],
            metadata=f.get("metadata", {})
        )
        for f in files
    ]


@router.get("/{file_id}", response_model=FileInfoResponse)
async def get_file_info(file_id: str):
    """
    获取文件信息
    """
    from core.file_parser import get_file_parser
    
    parser = get_file_parser()
    metadata = parser.get_file_metadata(file_id)
    
    if not metadata:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
    
    return FileInfoResponse(
        file_id=metadata["file_id"],
        filename=metadata["filename"],
        file_type=metadata["file_type"],
        file_size=metadata["file_size"],
        total_chars=metadata["total_chars"],
        total_chunks=metadata["total_chunks"],
        created_at=metadata["created_at"],
        metadata=metadata.get("metadata", {})
    )


@router.get("/{file_id}/content", response_model=FileContentResponse)
async def get_file_content(
    file_id: str,
    include_chunks: bool = Query(True, description="是否包含分块信息")
):
    """
    获取文件内容
    
    Args:
        file_id: 文件ID
        include_chunks: 是否包含分块信息
    """
    from core.file_parser import get_file_parser
    
    parser = get_file_parser()
    metadata = parser.get_file_metadata(file_id)
    
    if not metadata:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
    
    content = parser.get_file_content(file_id)
    
    if content is None:
        raise HTTPException(status_code=404, detail=f"文件内容不存在: {file_id}")
    
    chunks = []
    if include_chunks:
        chunks_file = parser.storage_dir / f"{file_id}_chunks.json"
        if chunks_file.exists():
            import json
            with open(chunks_file, 'r', encoding='utf-8') as f:
                chunks = json.load(f)
    
    return FileContentResponse(
        file_id=file_id,
        filename=metadata["filename"],
        content=content,
        chunks=chunks
    )


@router.get("/{file_id}/chunks")
async def get_file_chunks(file_id: str):
    """
    获取文件分块列表
    """
    from core.file_parser import get_file_parser
    
    parser = get_file_parser()
    metadata = parser.get_file_metadata(file_id)
    
    if not metadata:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
    
    chunks_file = parser.storage_dir / f"{file_id}_chunks.json"
    if chunks_file.exists():
        import json
        with open(chunks_file, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        return {"file_id": file_id, "chunks": chunks, "total": len(chunks)}
    
    return {"file_id": file_id, "chunks": [], "total": 0}


@router.delete("/{file_id}")
async def delete_file(file_id: str):
    """
    删除文件
    
    同时删除文件内容、元数据和向量索引
    """
    from core.file_parser import get_file_parser, get_file_vector_service
    
    parser = get_file_parser()
    metadata = parser.get_file_metadata(file_id)
    
    if not metadata:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
    
    try:
        vector_service = get_file_vector_service()
        await vector_service.delete_file_vectors(file_id)
    except Exception as e:
        logger.warning(f"删除文件向量失败: {e}")
    
    content_file = parser.storage_dir / f"{file_id}.txt"
    if content_file.exists():
        content_file.unlink()
    
    chunks_file = parser.storage_dir / f"{file_id}_chunks.json"
    if chunks_file.exists():
        chunks_file.unlink()
    
    parser.delete_file(file_id)
    
    return {"message": f"文件已删除: {file_id}", "file_id": file_id}


@router.post("/search", response_model=SearchResponse)
async def search_files(request: SearchRequest):
    """
    在文件中搜索内容
    
    支持在指定文件或所有文件中搜索
    """
    from core.file_parser import get_file_vector_service
    
    vector_service = get_file_vector_service()
    
    all_results = []
    
    if request.file_ids:
        for file_id in request.file_ids:
            try:
                results = await vector_service.search_file_content(
                    file_id=file_id,
                    query=request.query,
                    top_k=request.top_k
                )
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"搜索文件 {file_id} 失败: {e}")
    else:
        all_results = await vector_service.search_all_files(
            query=request.query,
            top_k=request.top_k
        )
    
    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    top_results = all_results[:request.top_k]
    
    search_results = [
        SearchResult(
            content=r["content"],
            score=r["score"],
            file_id=r["metadata"].get("file_id", ""),
            filename=r["metadata"].get("filename", ""),
            chunk_index=r["metadata"].get("chunk_index", 0),
            metadata=r["metadata"]
        )
        for r in top_results
    ]
    
    return SearchResponse(
        query=request.query,
        results=search_results,
        total=len(search_results)
    )


@router.get("/{file_id}/search")
async def search_in_file(
    file_id: str,
    query: str = Query(..., description="搜索查询文本"),
    top_k: int = Query(5, ge=1, le=20, description="返回结果数量")
):
    """
    在指定文件中搜索内容
    """
    from core.file_parser import get_file_parser, get_file_vector_service
    
    parser = get_file_parser()
    metadata = parser.get_file_metadata(file_id)
    
    if not metadata:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
    
    vector_service = get_file_vector_service()
    
    try:
        results = await vector_service.search_file_content(
            file_id=file_id,
            query=query,
            top_k=top_k
        )
        
        search_results = [
            {
                "content": r["content"],
                "score": r["score"],
                "chunk_index": r["metadata"].get("chunk_index", 0),
                "metadata": r["metadata"]
            }
            for r in results
        ]
        
        return {
            "file_id": file_id,
            "filename": metadata["filename"],
            "query": query,
            "results": search_results,
            "total": len(search_results)
        }
    
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@router.post("/{file_id}/reindex")
async def reindex_file(file_id: str):
    """
    重新索引文件
    
    重新向量化文件内容
    """
    from core.file_parser import get_file_parser, get_file_vector_service
    
    parser = get_file_parser()
    metadata = parser.get_file_metadata(file_id)
    
    if not metadata:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
    
    content = parser.get_file_content(file_id)
    if not content:
        raise HTTPException(status_code=404, detail=f"文件内容不存在: {file_id}")
    
    from core.file_parser import ParsedFile, FileType
    
    parsed_file = ParsedFile(
        file_id=file_id,
        filename=metadata["filename"],
        file_type=FileType(metadata["file_type"]),
        file_size=metadata["file_size"],
        content=content,
        chunks=[],
        metadata=metadata.get("metadata", {})
    )
    
    chunks = parser._create_chunks(content, file_id)
    parsed_file.chunks = [{
        "chunk_id": c.chunk_id,
        "content": c.content,
        "chunk_index": c.chunk_index,
        "start_char": c.start_char,
        "end_char": c.end_char,
        "metadata": c.metadata
    } for c in chunks]
    
    import json
    chunks_file = parser.storage_dir / f"{file_id}_chunks.json"
    with open(chunks_file, 'w', encoding='utf-8') as f:
        json.dump(parsed_file.chunks, f, ensure_ascii=False, indent=2)
    
    vector_service = get_file_vector_service()
    await vector_service.delete_file_vectors(file_id)
    
    collection_name, doc_ids = await vector_service.index_file(parsed_file)
    
    return {
        "message": f"文件重新索引成功",
        "file_id": file_id,
        "collection": collection_name,
        "total_chunks": len(doc_ids)
    }


@router.get("/supported-types")
async def get_supported_types():
    """
    获取支持的文件类型列表
    """
    from core.file_parser import FileParser
    
    parser = FileParser()
    
    return {
        "supported_types": [
            {"extension": ext, "type": ft.value}
            for ext, ft in parser.SUPPORTED_EXTENSIONS.items()
        ],
        "description": {
            "pdf": "PDF 文档，使用 pdfplumber 或 PyPDF2 解析",
            "word": "Word 文档 (.docx, .doc)，使用 python-docx 解析",
            "excel": "Excel 表格 (.xlsx, .xls)，使用 openpyxl 解析",
            "txt": "纯文本文件",
            "markdown": "Markdown 文档",
            "csv": "CSV 数据文件",
            "json": "JSON 数据文件"
        }
    }

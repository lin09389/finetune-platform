"""
文件操作 API 端点
提供文件上传、下载、预览、编辑和版本管理功能
"""
import hashlib
import logging
import mimetypes
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import Response
from pydantic import BaseModel, Field

from workspace.file_manager import get_file_manager
from workspace.models import FileInfo, FileVersion
from workspace.project_manager import get_project_manager
from workspace.version_control import get_version_control

logger = logging.getLogger(__name__)

router = APIRouter()


CHUNK_SIZE = 1024 * 1024  # 1MB
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
MAX_CHUNK_SIZE = 10 * 1024 * 1024  # 10MB


class ChunkUploadInit(BaseModel):
    """分块上传初始化请求"""
    project_id: str = Field(..., description="项目ID")
    file_path: str = Field(..., description="文件路径")
    file_size: int = Field(..., description="文件总大小")
    file_hash: str | None = Field(default=None, description="文件哈希（用于秒传）")
    chunk_count: int = Field(..., description="分块数量")
    chunk_size: int = Field(default=CHUNK_SIZE, description="分块大小")


class ChunkUploadInitResponse(BaseModel):
    """分块上传初始化响应"""
    upload_id: str = Field(..., description="上传ID")
    chunk_size: int = Field(..., description="分块大小")
    uploaded_chunks: list[int] = Field(default_factory=list, description="已上传的分块索引")


class ChunkUploadComplete(BaseModel):
    """分块上传完成请求"""
    upload_id: str = Field(..., description="上传ID")
    file_hash: str = Field(..., description="文件完整哈希")


class FileEditRequest(BaseModel):
    """文件编辑请求"""
    content: str = Field(..., description="文件内容")
    message: str | None = Field(default=None, description="版本说明")
    author: str | None = Field(default=None, description="作者")


class FilePreviewRequest(BaseModel):
    """文件预览请求"""
    file_id: str = Field(..., description="文件ID")
    version: int | None = Field(default=None, description="版本号")
    start_line: int | None = Field(default=None, description="起始行")
    end_line: int | None = Field(default=None, description="结束行")


class FileSearchRequest(BaseModel):
    """文件搜索请求"""
    project_id: str = Field(..., description="项目ID")
    query: str = Field(..., description="搜索关键词")
    file_types: list[str] | None = Field(default=None, description="文件类型筛选")
    path_prefix: str | None = Field(default=None, description="路径前缀")


class AutoSaveRequest(BaseModel):
    """自动保存请求"""
    file_id: str = Field(..., description="文件ID")
    content: str = Field(..., description="文件内容")
    cursor_position: dict[str, int] | None = Field(default=None, description="光标位置")


class AutoSaveResponse(BaseModel):
    """自动保存响应"""
    success: bool = Field(..., description="是否成功")
    saved_at: str = Field(..., description="保存时间")
    version: int = Field(..., description="版本号")
    message: str = Field(default="自动保存成功", description="消息")


upload_sessions: dict[str, dict[str, Any]] = {}
auto_save_cache: dict[str, dict[str, Any]] = {}


@router.post("/upload", response_model=dict[str, Any])
async def upload_file(
    project_id: str = Form(...),
    file_path: str = Form(...),
    file: UploadFile = File(...),
    message: str | None = Form(default=None),
    author: str | None = Form(default=None),
):
    """
    上传文件（小文件 < 10MB）

    适用于小文件的快速上传
    """
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，最大支持 {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    file_manager = get_file_manager()

    try:
        result = file_manager.upload_file(
            project_id=project_id,
            file_path=file_path,
            content=content,
            message=message or f"上传文件 {file.filename}",
            author=author,
        )

        return {
            "success": True,
            "file_id": result.file_id,
            "path": result.path,
            "size": result.size,
            "version": result.version,
            "is_new": result.is_new,
            "message": result.message,
        }
    except Exception as e:
        logger.error(f"上传文件失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload/chunk/init", response_model=ChunkUploadInitResponse)
async def init_chunk_upload(data: ChunkUploadInit):
    """
    初始化分块上传

    用于大文件的分块上传，支持断点续传
    """
    if data.file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，最大支持 {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    if data.chunk_size > MAX_CHUNK_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"分块过大，最大支持 {MAX_CHUNK_SIZE // (1024*1024)}MB"
        )

    project_manager = get_project_manager()
    project = project_manager.get_project(data.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    upload_id = f"upload_{uuid.uuid4().hex[:12]}"

    file_manager = get_file_manager()
    existing_file = file_manager.get_file_by_path(data.project_id, data.file_path)

    if existing_file and data.file_hash and existing_file.content_hash == data.file_hash:
        return ChunkUploadInitResponse(
            upload_id=upload_id,
            chunk_size=data.chunk_size,
            uploaded_chunks=list(range(data.chunk_count)),
        )

    upload_sessions[upload_id] = {
        "project_id": data.project_id,
        "file_path": data.file_path,
        "file_size": data.file_size,
        "file_hash": data.file_hash,
        "chunk_count": data.chunk_count,
        "chunk_size": data.chunk_size,
        "uploaded_chunks": [],
        "chunks": {},
        "created_at": datetime.now().isoformat(),
    }

    logger.info(f"分块上传已初始化：{upload_id}, 文件：{data.file_path}")

    return ChunkUploadInitResponse(
        upload_id=upload_id,
        chunk_size=data.chunk_size,
        uploaded_chunks=[],
    )


@router.post("/upload/chunk/{upload_id}/{chunk_index}")
async def upload_chunk(
    upload_id: str,
    chunk_index: int,
    chunk: UploadFile = File(...),
):
    """
    上传分块

    上传文件的指定分块
    """
    if upload_id not in upload_sessions:
        raise HTTPException(status_code=404, detail="上传会话不存在")

    session = upload_sessions[upload_id]

    if chunk_index < 0 or chunk_index >= session["chunk_count"]:
        raise HTTPException(status_code=400, detail="分块索引无效")

    if chunk_index in session["uploaded_chunks"]:
        return {"success": True, "message": "分块已存在", "chunk_index": chunk_index}

    chunk_data = await chunk.read()

    if len(chunk_data) > session["chunk_size"]:
        raise HTTPException(status_code=400, detail="分块大小超过限制")

    session["chunks"][chunk_index] = chunk_data
    session["uploaded_chunks"].append(chunk_index)

    logger.debug(f"分块已上传：{upload_id}, 索引：{chunk_index}")

    return {
        "success": True,
        "chunk_index": chunk_index,
        "uploaded_count": len(session["uploaded_chunks"]),
        "total_chunks": session["chunk_count"],
    }


@router.post("/upload/chunk/complete", response_model=dict[str, Any])
async def complete_chunk_upload(data: ChunkUploadComplete):
    """
    完成分块上传

    合并所有分块并创建文件
    """
    if data.upload_id not in upload_sessions:
        raise HTTPException(status_code=404, detail="上传会话不存在")

    session = upload_sessions[data.upload_id]

    if len(session["uploaded_chunks"]) != session["chunk_count"]:
        raise HTTPException(
            status_code=400,
            detail=f"分块不完整，已上传 {len(session['uploaded_chunks'])}/{session['chunk_count']}"
        )

    content = b""
    for i in range(session["chunk_count"]):
        content += session["chunks"][i]

    actual_hash = hashlib.sha256(content).hexdigest()
    if data.file_hash and actual_hash != data.file_hash:
        del upload_sessions[data.upload_id]
        raise HTTPException(status_code=400, detail="文件哈希不匹配")

    file_manager = get_file_manager()

    try:
        result = file_manager.upload_file(
            project_id=session["project_id"],
            file_path=session["file_path"],
            content=content,
            message="分块上传完成",
        )

        del upload_sessions[data.upload_id]

        logger.info(f"分块上传已完成：{data.upload_id}, 文件：{session['file_path']}")

        return {
            "success": True,
            "file_id": result.file_id,
            "path": result.path,
            "size": result.size,
            "version": result.version,
            "is_new": result.is_new,
            "message": result.message,
        }
    except Exception as e:
        logger.error(f"完成分块上传失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{file_id}")
async def download_file(
    file_id: str,
    version: int | None = Query(default=None, description="版本号"),
):
    """
    下载文件

    支持下载指定版本或最新版本
    """
    file_manager = get_file_manager()
    result = file_manager.download_file(file_id, version)

    if not result:
        raise HTTPException(status_code=404, detail="文件不存在")

    content, file_info = result

    mime_type, _ = mimetypes.guess_type(file_info.path)
    if not mime_type:
        mime_type = "application/octet-stream"

    return Response(
        content=content,
        media_type=mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_info.name}"',
            "Content-Length": str(len(content)),
        }
    )


@router.get("/preview/{file_id}")
async def preview_file(
    file_id: str,
    version: int | None = Query(default=None, description="版本号"),
    start_line: int | None = Query(default=None, description="起始行"),
    end_line: int | None = Query(default=None, description="结束行"),
    highlight: bool = Query(default=True, description="是否启用代码高亮"),
):
    """
    预览文件

    支持文本预览、代码高亮、图片预览
    """
    file_manager = get_file_manager()
    result = file_manager.download_file(file_id, version)

    if not result:
        raise HTTPException(status_code=404, detail="文件不存在")

    content, file_info = result

    ext = Path(file_info.path).suffix.lower()

    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'}
    if ext in image_extensions:
        mime_type, _ = mimetypes.guess_type(file_info.path)
        if not mime_type:
            mime_type = "application/octet-stream"

        return Response(
            content=content,
            media_type=mime_type,
            headers={
                "Content-Type": mime_type,
                "Content-Length": str(len(content)),
            }
        )

    text_extensions = {
        '.txt', '.md', '.json', '.jsonl', '.xml', '.yaml', '.yml',
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c',
        '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.sh', '.bat',
        '.html', '.css', '.scss', '.less', '.sql', '.env', '.ini',
        '.toml', '.cfg', '.conf', '.log',
    }

    if ext not in text_extensions:
        return {
            "file_id": file_id,
            "file_name": file_info.name,
            "file_type": "binary",
            "size": file_info.size,
            "message": "二进制文件，无法预览",
        }

    try:
        text_content = content.decode('utf-8')
    except UnicodeDecodeError:
        try:
            text_content = content.decode('gbk')
        except UnicodeDecodeError:
            return {
                "file_id": file_id,
                "file_name": file_info.name,
                "file_type": "binary",
                "size": file_info.size,
                "message": "无法解码文件内容",
            }

    lines = text_content.splitlines()
    total_lines = len(lines)

    if start_line is not None:
        start_line = max(1, start_line)
    else:
        start_line = 1

    if end_line is not None:
        end_line = min(total_lines, end_line)
    else:
        end_line = min(total_lines, 1000)

    preview_lines = lines[start_line - 1:end_line]

    language = detect_language(ext)

    preview_result = {
        "file_id": file_id,
        "file_name": file_info.name,
        "file_type": "text",
        "size": file_info.size,
        "language": language,
        "total_lines": total_lines,
        "preview_lines": len(preview_lines),
        "start_line": start_line,
        "end_line": end_line,
        "content": "\n".join(preview_lines),
        "lines": [
            {"number": i + start_line, "content": line}
            for i, line in enumerate(preview_lines)
        ],
    }

    if highlight and language:
        preview_result["highlighted"] = True
        preview_result["highlighted_lines"] = [
            {"number": i + start_line, "content": line, "tokens": tokenize_code(line, language)}
            for i, line in enumerate(preview_lines)
        ]

    return preview_result


@router.put("/edit/{file_id}")
async def edit_file(
    file_id: str,
    data: FileEditRequest,
):
    """
    编辑文件

    保存文件内容并创建新版本
    """
    file_manager = get_file_manager()
    file_info = file_manager.get_file(file_id)

    if not file_info:
        raise HTTPException(status_code=404, detail="文件不存在")

    content = data.content.encode('utf-8')

    try:
        result = file_manager.upload_file(
            project_id=file_info.project_id,
            file_path=file_info.path,
            content=content,
            message=data.message or "编辑文件",
            author=data.author,
        )

        logger.info(f"文件已编辑：{file_id}, 版本：{result.version}")

        return {
            "success": True,
            "file_id": file_id,
            "version": result.version,
            "size": result.size,
            "message": "文件已保存",
        }
    except Exception as e:
        logger.error(f"编辑文件失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/autosave", response_model=AutoSaveResponse)
async def auto_save_file(data: AutoSaveRequest):
    """
    自动保存文件

    定期自动保存，避免数据丢失
    """
    file_manager = get_file_manager()
    file_info = file_manager.get_file(data.file_id)

    if not file_info:
        raise HTTPException(status_code=404, detail="文件不存在")

    cache_key = f"autosave_{data.file_id}"

    if cache_key in auto_save_cache:
        cached = auto_save_cache[cache_key]
        if cached["content"] == data.content:
            return AutoSaveResponse(
                success=True,
                saved_at=cached["saved_at"],
                version=cached["version"],
                message="内容未变化，跳过保存",
            )

    content = data.content.encode('utf-8')
    content_hash = hashlib.sha256(content).hexdigest()

    if content_hash == file_info.content_hash:
        return AutoSaveResponse(
            success=True,
            saved_at=datetime.now().isoformat(),
            version=file_info.current_version,
            message="内容与当前版本相同",
        )

    try:
        result = file_manager.upload_file(
            project_id=file_info.project_id,
            file_path=file_info.path,
            content=content,
            message="自动保存",
        )

        auto_save_cache[cache_key] = {
            "content": data.content,
            "saved_at": datetime.now().isoformat(),
            "version": result.version,
            "cursor_position": data.cursor_position,
        }

        logger.debug(f"文件已自动保存：{data.file_id}, 版本：{result.version}")

        return AutoSaveResponse(
            success=True,
            saved_at=datetime.now().isoformat(),
            version=result.version,
            message="自动保存成功",
        )
    except Exception as e:
        logger.error(f"自动保存失败：{e}")
        return AutoSaveResponse(
            success=False,
            saved_at=datetime.now().isoformat(),
            version=file_info.current_version,
            message=f"自动保存失败：{str(e)}",
        )


@router.get("/history/{file_id}", response_model=list[FileVersion])
async def get_file_history(
    file_id: str,
    limit: int = Query(default=50, ge=1, le=200, description="返回数量"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
):
    """
    获取文件版本历史

    返回文件的所有版本记录
    """
    version_control = get_version_control()
    versions = version_control.get_version_history(file_id, limit, offset)

    return versions


@router.get("/history/{file_id}/{version_number}")
async def get_file_version(
    file_id: str,
    version_number: int,
):
    """
    获取文件指定版本

    返回指定版本的文件内容
    """
    version_control = get_version_control()
    version = version_control.get_version(file_id, version_number)

    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    content = version_control.get_version_content(version.version_id)

    if content is None:
        raise HTTPException(status_code=404, detail="版本内容不存在")

    file_manager = get_file_manager()
    file_info = file_manager.get_file(file_id)

    return {
        "version": version,
        "file_info": file_info,
        "content": content.decode('utf-8') if file_info and is_text_file(file_info.path) else None,
        "size": len(content),
    }


@router.get("/diff/{file_id}")
async def compare_versions(
    file_id: str,
    version_from: int = Query(..., description="起始版本"),
    version_to: int = Query(..., description="目标版本"),
):
    """
    对比文件版本

    返回两个版本之间的差异
    """
    version_control = get_version_control()
    diff = version_control.compare_versions(file_id, version_from, version_to)

    if not diff:
        raise HTTPException(status_code=404, detail="无法对比版本")

    return diff


@router.post("/rollback/{file_id}/{version_number}")
async def rollback_file(
    file_id: str,
    version_number: int,
    message: str | None = Query(default=None, description="回滚说明"),
):
    """
    回滚文件到指定版本

    将文件恢复到历史版本
    """
    version_control = get_version_control()
    content = version_control.rollback_to_version(file_id, version_number)

    if content is None:
        raise HTTPException(status_code=404, detail="版本不存在")

    file_manager = get_file_manager()
    file_info = file_manager.get_file(file_id)

    if not file_info:
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        result = file_manager.upload_file(
            project_id=file_info.project_id,
            file_path=file_info.path,
            content=content,
            message=message or f"回滚到版本 {version_number}",
        )

        logger.info(f"文件已回滚：{file_id}, 到版本：{version_number}")

        return {
            "success": True,
            "file_id": file_id,
            "new_version": result.version,
            "rolled_back_to": version_number,
            "message": f"已回滚到版本 {version_number}",
        }
    except Exception as e:
        logger.error(f"回滚文件失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/history/{file_id}/{version_number}")
async def delete_file_version(
    file_id: str,
    version_number: int,
):
    """
    删除文件版本

    删除指定的历史版本
    """
    version_control = get_version_control()
    version = version_control.get_version(file_id, version_number)

    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    if version_control.get_version_count(file_id) <= 1:
        raise HTTPException(status_code=400, detail="不能删除最后一个版本")

    success = version_control.delete_version(version.version_id)

    if not success:
        raise HTTPException(status_code=500, detail="删除版本失败")

    logger.info(f"版本已删除：{file_id}, 版本号：{version_number}")

    return {
        "success": True,
        "file_id": file_id,
        "deleted_version": version_number,
        "message": "版本已删除",
    }


@router.post("/search")
async def search_files(data: FileSearchRequest):
    """
    搜索文件

    按关键词、类型、路径搜索文件
    """
    file_manager = get_file_manager()

    all_files = file_manager.list_files(data.project_id)

    results = []
    query_lower = data.query.lower()

    for file_info in all_files:
        if data.path_prefix and not file_info.path.startswith(data.path_prefix):
            continue

        if data.file_types and file_info.file_type not in data.file_types:
            continue

        if query_lower in file_info.name.lower() or query_lower in file_info.path.lower():
            results.append({
                "file": file_info,
                "match_type": "name_or_path",
                "relevance": 1.0 if query_lower in file_info.name.lower() else 0.5,
            })

    results.sort(key=lambda x: x["relevance"], reverse=True)

    return {
        "query": data.query,
        "total": len(results),
        "results": results[:100],
    }


@router.get("/info/{file_id}", response_model=FileInfo)
async def get_file_info(file_id: str):
    """
    获取文件信息

    返回文件的详细元数据
    """
    file_manager = get_file_manager()
    file_info = file_manager.get_file(file_id)

    if not file_info:
        raise HTTPException(status_code=404, detail="文件不存在")

    return file_info


@router.delete("/{file_id}")
async def delete_file(file_id: str):
    """
    删除文件

    删除文件及其所有版本
    """
    file_manager = get_file_manager()
    success = file_manager.delete_file(file_id)

    if not success:
        raise HTTPException(status_code=404, detail="文件不存在")

    logger.info(f"文件已删除：{file_id}")

    return {
        "success": True,
        "file_id": file_id,
        "message": "文件已删除",
    }


@router.post("/move/{file_id}")
async def move_file(
    file_id: str,
    new_path: str = Query(..., description="新路径"),
):
    """
    移动文件

    移动文件到新路径
    """
    file_manager = get_file_manager()
    file_info = file_manager.move_file(file_id, new_path)

    if not file_info:
        raise HTTPException(status_code=404, detail="文件不存在")

    logger.info(f"文件已移动：{file_id} -> {new_path}")

    return {
        "success": True,
        "file_id": file_id,
        "new_path": new_path,
        "file_info": file_info,
    }


@router.post("/copy/{file_id}")
async def copy_file(
    file_id: str,
    new_path: str = Query(..., description="新路径"),
):
    """
    复制文件

    复制文件到新路径
    """
    file_manager = get_file_manager()
    file_info = file_manager.copy_file(file_id, new_path)

    if not file_info:
        raise HTTPException(status_code=404, detail="文件不存在")

    logger.info(f"文件已复制：{file_id} -> {new_path}")

    return {
        "success": True,
        "original_file_id": file_id,
        "new_file_id": file_info.id,
        "new_path": new_path,
        "file_info": file_info,
    }


def detect_language(extension: str) -> str | None:
    """根据扩展名检测编程语言"""
    language_map = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.jsx': 'jsx',
        '.tsx': 'tsx',
        '.java': 'java',
        '.cpp': 'cpp',
        '.c': 'c',
        '.h': 'c',
        '.hpp': 'cpp',
        '.go': 'go',
        '.rs': 'rust',
        '.rb': 'ruby',
        '.php': 'php',
        '.swift': 'swift',
        '.kt': 'kotlin',
        '.sh': 'bash',
        '.bat': 'batch',
        '.ps1': 'powershell',
        '.html': 'html',
        '.css': 'css',
        '.scss': 'scss',
        '.less': 'less',
        '.json': 'json',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.xml': 'xml',
        '.sql': 'sql',
        '.md': 'markdown',
        '.toml': 'toml',
        '.ini': 'ini',
    }
    return language_map.get(extension.lower())


def tokenize_code(line: str, language: str) -> list[dict[str, Any]]:
    """简单的代码语法高亮分词"""
    tokens = []

    keywords = {
        'python': {'def', 'class', 'if', 'else', 'elif', 'for', 'while', 'return', 'import', 'from', 'as', 'try', 'except', 'finally', 'with', 'lambda', 'yield', 'raise', 'pass', 'break', 'continue', 'True', 'False', 'None', 'and', 'or', 'not', 'in', 'is'},
        'javascript': {'function', 'class', 'if', 'else', 'for', 'while', 'return', 'import', 'export', 'from', 'try', 'catch', 'finally', 'const', 'let', 'var', 'true', 'false', 'null', 'undefined', 'async', 'await', 'new', 'this'},
        'typescript': {'function', 'class', 'if', 'else', 'for', 'while', 'return', 'import', 'export', 'from', 'try', 'catch', 'finally', 'const', 'let', 'var', 'true', 'false', 'null', 'undefined', 'async', 'await', 'new', 'this', 'interface', 'type', 'enum', 'implements', 'extends', 'private', 'public', 'protected'},
    }

    lang_keywords = keywords.get(language, set())

    patterns = [
        (r'(["\'])(?:(?=(\\?))\2.)*?\1', 'string'),
        (r'#.*$', 'comment'),
        (r'//.*$', 'comment'),
        (r'/\*.*?\*/', 'comment'),
        (r'\b\d+\.?\d*\b', 'number'),
        (r'\b(true|false|null|True|False|None)\b', 'boolean'),
        (r'\b[a-zA-Z_]\w*(?=\s*\()', 'function'),
        (r'\b[a-zA-Z_]\w*\b', 'identifier'),
    ]

    for pattern, token_type in patterns:
        for match in re.finditer(pattern, line):
            value = match.group()

            if token_type == 'identifier' and value in lang_keywords:
                token_type = 'keyword'

            tokens.append({
                'type': token_type,
                'value': value,
                'start': match.start(),
                'end': match.end(),
            })

    tokens.sort(key=lambda x: x['start'])

    return tokens


def is_text_file(file_path: str) -> bool:
    """判断是否为文本文件"""
    text_extensions = {
        '.txt', '.md', '.json', '.jsonl', '.xml', '.yaml', '.yml',
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c',
        '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.sh', '.bat',
        '.html', '.css', '.scss', '.less', '.sql', '.env', '.ini',
        '.toml', '.cfg', '.conf', '.log',
    }
    ext = Path(file_path).suffix.lower()
    return ext in text_extensions

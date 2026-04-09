"""
文件操作处理器
负责文件相关的所有操作
"""
import hashlib
import logging
import shutil
from pathlib import Path
from typing import Any

import aiofiles

from .base import (
    OperationContext,
    OperationHandler,
    OperationResult,
)

logger = logging.getLogger(__name__)


class FileOperationHandler(OperationHandler):
    """
    文件操作处理器

    支持的操作:
    - file_create: 创建文件
    - file_read: 读取文件
    - file_write: 写入文件
    - file_delete: 删除文件
    - file_copy: 复制文件
    - file_move: 移动文件
    - file_exists: 检查文件是否存在
    - file_info: 获取文件信息
    - dir_create: 创建目录
    - dir_list: 列出目录内容
    - dir_delete: 删除目录
    """

    def __init__(
        self,
        context: OperationContext | None = None,
        allowed_extensions: list[str] | None = None,
        max_file_size: int = 100 * 1024 * 1024,
    ):
        super().__init__(context)
        self.allowed_extensions = allowed_extensions
        self.max_file_size = max_file_size

    def get_supported_actions(self) -> list[str]:
        return [
            "file_create",
            "file_read",
            "file_write",
            "file_delete",
            "file_copy",
            "file_move",
            "file_exists",
            "file_info",
            "dir_create",
            "dir_list",
            "dir_delete",
        ]

    def get_action_descriptions(self) -> dict[str, str]:
        return {
            "file_create": "创建新文件",
            "file_read": "读取文件内容",
            "file_write": "写入文件内容",
            "file_delete": "删除文件",
            "file_copy": "复制文件",
            "file_move": "移动文件",
            "file_exists": "检查文件是否存在",
            "file_info": "获取文件详细信息",
            "dir_create": "创建目录",
            "dir_list": "列出目录内容",
            "dir_delete": "删除目录",
        }

    def validate_params(self, action: str, params: dict[str, Any]) -> str | None:
        validators = {
            "file_create": self._validate_file_create,
            "file_read": self._validate_file_read,
            "file_write": self._validate_file_write,
            "file_delete": self._validate_file_delete,
            "file_copy": self._validate_file_copy,
            "file_move": self._validate_file_move,
            "file_exists": self._validate_path_param,
            "file_info": self._validate_path_param,
            "dir_create": self._validate_path_param,
            "dir_list": self._validate_path_param,
            "dir_delete": self._validate_path_param,
        }

        validator = validators.get(action)
        if validator:
            return validator(params)

        return None

    def _validate_path_param(self, params: dict[str, Any]) -> str | None:
        if "path" not in params:
            return "缺少必需参数: path"
        return None

    def _validate_file_create(self, params: dict[str, Any]) -> str | None:
        if "path" not in params:
            return "缺少必需参数: path"
        if "content" not in params:
            return "缺少必需参数: content"
        return self._validate_extension(params["path"])

    def _validate_file_read(self, params: dict[str, Any]) -> str | None:
        if "path" not in params:
            return "缺少必需参数: path"
        return self._validate_extension(params["path"])

    def _validate_file_write(self, params: dict[str, Any]) -> str | None:
        if "path" not in params:
            return "缺少必需参数: path"
        if "content" not in params:
            return "缺少必需参数: content"
        return self._validate_extension(params["path"])

    def _validate_file_delete(self, params: dict[str, Any]) -> str | None:
        if "path" not in params:
            return "缺少必需参数: path"
        return None

    def _validate_file_copy(self, params: dict[str, Any]) -> str | None:
        if "source" not in params:
            return "缺少必需参数: source"
        if "destination" not in params:
            return "缺少必需参数: destination"
        return self._validate_extension(params["destination"])

    def _validate_file_move(self, params: dict[str, Any]) -> str | None:
        if "source" not in params:
            return "缺少必需参数: source"
        if "destination" not in params:
            return "缺少必需参数: destination"
        return self._validate_extension(params["destination"])

    def _validate_extension(self, path: str) -> str | None:
        if self.allowed_extensions:
            ext = Path(path).suffix.lower()
            if ext and ext not in self.allowed_extensions:
                return f"不支持的文件扩展名: {ext}"
        return None

    def _resolve_path(self, path: str) -> Path:
        """解析路径（确保在工作空间内）"""
        if self.context and self.context.workspace:
            workspace = Path(self.context.workspace).resolve()
            target = (workspace / path).resolve()

            if not str(target).startswith(str(workspace)):
                raise PermissionError(f"路径越界: {path}")

            return target

        return Path(path).resolve()

    async def execute(self, action: str, params: dict[str, Any]) -> OperationResult:
        handlers = {
            "file_create": self._file_create,
            "file_read": self._file_read,
            "file_write": self._file_write,
            "file_delete": self._file_delete,
            "file_copy": self._file_copy,
            "file_move": self._file_move,
            "file_exists": self._file_exists,
            "file_info": self._file_info,
            "dir_create": self._dir_create,
            "dir_list": self._dir_list,
            "dir_delete": self._dir_delete,
        }

        handler = handlers.get(action)
        if handler:
            return await handler(params)

        return OperationResult.fail(
            error=f"未实现的操作: {action}",
            error_code="NOT_IMPLEMENTED"
        )

    async def _file_create(self, params: dict[str, Any]) -> OperationResult:
        """创建文件"""
        path = self._resolve_path(params["path"])
        content = params["content"]
        encoding = params.get("encoding", "utf-8")

        if path.exists():
            return OperationResult.fail(
                error=f"文件已存在: {path}",
                error_code="FILE_EXISTS"
            )

        path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(path, "w", encoding=encoding) as f:
            await f.write(content)

        return OperationResult.ok(
            message=f"文件创建成功: {path}",
            data={"path": str(path), "size": len(content.encode(encoding))}
        )

    async def _file_read(self, params: dict[str, Any]) -> OperationResult:
        """读取文件"""
        path = self._resolve_path(params["path"])
        encoding = params.get("encoding", "utf-8")

        if not path.exists():
            return OperationResult.fail(
                error=f"文件不存在: {path}",
                error_code="FILE_NOT_FOUND"
            )

        if not path.is_file():
            return OperationResult.fail(
                error=f"不是文件: {path}",
                error_code="NOT_A_FILE"
            )

        async with aiofiles.open(path, encoding=encoding) as f:
            content = await f.read()

        return OperationResult.ok(
            message="文件读取成功",
            data={"path": str(path), "content": content}
        )

    async def _file_write(self, params: dict[str, Any]) -> OperationResult:
        """写入文件"""
        path = self._resolve_path(params["path"])
        content = params["content"]
        encoding = params.get("encoding", "utf-8")
        append = params.get("append", False)

        mode = "a" if append else "w"

        path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(path, mode, encoding=encoding) as f:
            await f.write(content)

        return OperationResult.ok(
            message=f"文件写入成功: {path}",
            data={"path": str(path), "size": len(content.encode(encoding))}
        )

    async def _file_delete(self, params: dict[str, Any]) -> OperationResult:
        """删除文件"""
        path = self._resolve_path(params["path"])

        if not path.exists():
            return OperationResult.fail(
                error=f"文件不存在: {path}",
                error_code="FILE_NOT_FOUND"
            )

        if path.is_file():
            path.unlink()
        elif path.is_dir():
            if params.get("recursive", False):
                shutil.rmtree(path)
            else:
                path.rmdir()

        return OperationResult.ok(message=f"删除成功: {path}")

    async def _file_copy(self, params: dict[str, Any]) -> OperationResult:
        """复制文件"""
        source = self._resolve_path(params["source"])
        destination = self._resolve_path(params["destination"])

        if not source.exists():
            return OperationResult.fail(
                error=f"源文件不存在: {source}",
                error_code="SOURCE_NOT_FOUND"
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

        return OperationResult.ok(
            message="文件复制成功",
            data={"source": str(source), "destination": str(destination)}
        )

    async def _file_move(self, params: dict[str, Any]) -> OperationResult:
        """移动文件"""
        source = self._resolve_path(params["source"])
        destination = self._resolve_path(params["destination"])

        if not source.exists():
            return OperationResult.fail(
                error=f"源文件不存在: {source}",
                error_code="SOURCE_NOT_FOUND"
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))

        return OperationResult.ok(
            message="文件移动成功",
            data={"source": str(source), "destination": str(destination)}
        )

    async def _file_exists(self, params: dict[str, Any]) -> OperationResult:
        """检查文件是否存在"""
        path = self._resolve_path(params["path"])
        exists = path.exists()

        return OperationResult.ok(
            message="检查完成",
            data={"path": str(path), "exists": exists}
        )

    async def _file_info(self, params: dict[str, Any]) -> OperationResult:
        """获取文件信息"""
        path = self._resolve_path(params["path"])

        if not path.exists():
            return OperationResult.fail(
                error=f"路径不存在: {path}",
                error_code="PATH_NOT_FOUND"
            )

        stat = path.stat()

        def compute_hash(file_path: Path) -> str:
            hasher = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()

        info = {
            "path": str(path),
            "name": path.name,
            "is_file": path.is_file(),
            "is_dir": path.is_dir(),
            "size": stat.st_size,
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
            "accessed": stat.st_atime,
        }

        if path.is_file():
            info["extension"] = path.suffix
            info["md5"] = compute_hash(path)

        return OperationResult.ok(message="获取文件信息成功", data=info)

    async def _dir_create(self, params: dict[str, Any]) -> OperationResult:
        """创建目录"""
        path = self._resolve_path(params["path"])
        path.mkdir(parents=True, exist_ok=True)

        return OperationResult.ok(message=f"目录创建成功: {path}")

    async def _dir_list(self, params: dict[str, Any]) -> OperationResult:
        """列出目录内容"""
        path = self._resolve_path(params["path"])

        if not path.exists():
            return OperationResult.fail(
                error=f"目录不存在: {path}",
                error_code="DIR_NOT_FOUND"
            )

        if not path.is_dir():
            return OperationResult.fail(
                error=f"不是目录: {path}",
                error_code="NOT_A_DIR"
            )

        items = []
        for item in path.iterdir():
            items.append({
                "name": item.name,
                "path": str(item),
                "is_file": item.is_file(),
                "is_dir": item.is_dir(),
            })

        return OperationResult.ok(
            message="列出目录内容",
            data={"path": str(path), "items": items, "count": len(items)}
        )

    async def _dir_delete(self, params: dict[str, Any]) -> OperationResult:
        """删除目录"""
        path = self._resolve_path(params["path"])

        if not path.exists():
            return OperationResult.fail(
                error=f"目录不存在: {path}",
                error_code="DIR_NOT_FOUND"
            )

        if params.get("recursive", False):
            shutil.rmtree(path)
        else:
            path.rmdir()

        return OperationResult.ok(message=f"目录删除成功: {path}")

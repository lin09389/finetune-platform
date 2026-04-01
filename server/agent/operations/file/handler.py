"""File operation handler for unified executor."""

import fnmatch
import shutil
from pathlib import Path
from typing import Any

import aiofiles

from ...core.interfaces import ErrorCode, OperationContext, UnifiedResult
from ..base import OperationHandler

DANGEROUS_PATH_PATTERNS: list[str] = []
DANGEROUS_PATHS: list[str] = []


def get_desktop_path() -> str:
    return str(Path.home() / "Desktop")


def get_recycle_bin_path() -> Path:
    recycle = Path.home() / ".finetune_recycle_bin"
    recycle.mkdir(parents=True, exist_ok=True)
    return recycle


class FileOperationHandler(OperationHandler):
    def __init__(
        self,
        context: OperationContext | None = None,
        workspace: str | None = None,
        allowed_extensions: list[str] | None = None,
        max_file_size: int = 100 * 1024 * 1024,
    ):
        if context is None and workspace is not None:
            context = OperationContext(workspace=workspace)
        super().__init__(context)
        self.allowed_extensions = [x.lower() for x in allowed_extensions] if allowed_extensions else None
        self.max_file_size = max_file_size
        self.safe_paths: list[Path] = []
        self._init_safe_paths()

    def _init_safe_paths(self) -> None:
        self.safe_paths = [Path.home() / "Desktop", Path.home() / "Documents", Path.home() / "Downloads"]
        if self.context and self.context.workspace:
            self.safe_paths.append(Path(self.context.workspace).resolve())

    def get_supported_actions(self) -> list[str]:
        return [
            "file_create",
            "file_read",
            "file_write",
            "file_delete",
            "file_copy",
            "file_move",
            "file_rename",
            "file_exists",
            "file_info",
            "file_list",
            "file_search",
            "dir_create",
            "dir_delete",
            "dir_list",
            "directory_create",
            "directory_delete",
        ]

    def set_context(self, context: OperationContext) -> None:
        super().set_context(context)
        self._init_safe_paths()

    def _resolve_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if not path.is_absolute() and self.context and self.context.workspace:
            path = Path(self.context.workspace) / path
        return path.resolve()

    def _is_safe_path(self, path: Path) -> bool:
        for safe in self.safe_paths:
            try:
                path.relative_to(safe.resolve())
                return True
            except Exception:
                continue
        return False

    def _validate_extension(self, path: Path) -> str | None:
        if not self.allowed_extensions:
            return None
        ext = path.suffix.lower()
        if ext and ext not in self.allowed_extensions:
            return f"Unsupported extension: {ext}"
        return None

    async def execute(self, action: str, params: dict[str, Any]) -> UnifiedResult:
        handlers = {
            "file_create": self._file_create,
            "file_read": self._file_read,
            "file_write": self._file_write,
            "file_delete": self._file_delete,
            "file_copy": self._file_copy,
            "file_move": self._file_move,
            "file_rename": self._file_rename,
            "file_exists": self._file_exists,
            "file_info": self._file_info,
            "file_list": self._file_list,
            "file_search": self._file_search,
            "dir_create": self._dir_create,
            "dir_delete": self._dir_delete,
            "dir_list": self._file_list,
            "directory_create": self._dir_create,
            "directory_delete": self._dir_delete,
        }
        handler = handlers.get(action)
        if not handler:
            return UnifiedResult.fail(action=action, error=f"Unsupported action: {action}", error_code=ErrorCode.NOT_IMPLEMENTED)
        return await handler(params)

    async def _file_create(self, params: dict[str, Any]) -> UnifiedResult:
        raw = params.get("path") or params.get("file_path")
        if not raw:
            return UnifiedResult.fail(action="file_create", error="Missing file path", error_code=ErrorCode.VALIDATION_ERROR)
        path = self._resolve_path(raw)
        if not self._is_safe_path(path):
            return UnifiedResult.fail(action="file_create", error=f"Path outside safe scope: {path}", error_code=ErrorCode.PERMISSION_DENIED)
        ext_error = self._validate_extension(path)
        if ext_error:
            return UnifiedResult.fail(action="file_create", error=ext_error, error_code=ErrorCode.VALIDATION_ERROR)
        if path.exists():
            return UnifiedResult.fail(action="file_create", error=f"File exists: {path}", error_code=ErrorCode.FILE_EXISTS)

        content = params.get("content", "")
        encoding = params.get("encoding", "utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "w", encoding=encoding) as f:
            await f.write(content)
        return UnifiedResult.ok(action="file_create", message=f"Created {raw}", data={"path": str(path)})

    async def _file_read(self, params: dict[str, Any]) -> UnifiedResult:
        raw = params.get("path") or params.get("file_path")
        if not raw:
            return UnifiedResult.fail(action="file_read", error="Missing file path", error_code=ErrorCode.VALIDATION_ERROR)
        path = self._resolve_path(raw)
        if not self._is_safe_path(path):
            return UnifiedResult.fail(action="file_read", error=f"Path outside safe scope: {path}", error_code=ErrorCode.PERMISSION_DENIED)
        if not path.exists():
            return UnifiedResult.fail(action="file_read", error=f"File not found: {path}", error_code="FILE_NOT_FOUND")
        if not path.is_file():
            return UnifiedResult.fail(action="file_read", error=f"Not a file: {path}", error_code=ErrorCode.NOT_A_FILE)
        if path.stat().st_size > self.max_file_size:
            return UnifiedResult.fail(action="file_read", error=f"File too large: {path}", error_code=ErrorCode.VALIDATION_ERROR)

        encoding = params.get("encoding", "utf-8")
        async with aiofiles.open(path, "r", encoding=encoding) as f:
            content = await f.read()
        return UnifiedResult.ok(action="file_read", message=f"Read {raw}", data={"path": str(path), "content": content})

    async def _file_write(self, params: dict[str, Any]) -> UnifiedResult:
        raw = params.get("path") or params.get("file_path")
        if not raw:
            return UnifiedResult.fail(action="file_write", error="Missing file path", error_code=ErrorCode.VALIDATION_ERROR)
        path = self._resolve_path(raw)
        if not self._is_safe_path(path):
            return UnifiedResult.fail(action="file_write", error=f"Path outside safe scope: {path}", error_code=ErrorCode.PERMISSION_DENIED)

        ext_error = self._validate_extension(path)
        if ext_error:
            return UnifiedResult.fail(action="file_write", error=ext_error, error_code=ErrorCode.VALIDATION_ERROR)

        content = params.get("content", "")
        mode = params.get("mode", "overwrite")
        io_mode = "a" if mode == "append" else "w"
        encoding = params.get("encoding", "utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, io_mode, encoding=encoding) as f:
            await f.write(content)
        return UnifiedResult.ok(action="file_write", message=f"Wrote {raw}", data={"path": str(path)})

    async def _file_delete(self, params: dict[str, Any]) -> UnifiedResult:
        raw = params.get("path") or params.get("file_path")
        if not raw:
            return UnifiedResult.fail(action="file_delete", error="Missing file path", error_code=ErrorCode.VALIDATION_ERROR)
        path = self._resolve_path(raw)
        if not self._is_safe_path(path):
            return UnifiedResult.fail(action="file_delete", error=f"Path outside safe scope: {path}", error_code=ErrorCode.PERMISSION_DENIED)
        if not params.get("confirmed", True):
            return UnifiedResult.fail(action="file_delete", error="Delete requires confirmation", error_code=ErrorCode.PERMISSION_DENIED, data={"need_confirm": True})
        if not path.exists():
            return UnifiedResult.fail(action="file_delete", error=f"File not found: {path}", error_code=ErrorCode.FILE_NOT_FOUND)

        if path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
        return UnifiedResult.ok(action="file_delete", message=f"Deleted {raw}")

    async def _file_copy(self, params: dict[str, Any]) -> UnifiedResult:
        src = params.get("source") or params.get("src")
        dst = params.get("destination") or params.get("dest")
        if not src or not dst:
            return UnifiedResult.fail(action="file_copy", error="Missing source or destination", error_code=ErrorCode.VALIDATION_ERROR)

        source = self._resolve_path(src)
        target = self._resolve_path(dst)
        if not source.exists():
            return UnifiedResult.fail(action="file_copy", error=f"Source not found: {source}", error_code=ErrorCode.SOURCE_NOT_FOUND)
        if not (self._is_safe_path(source) and self._is_safe_path(target)):
            return UnifiedResult.fail(action="file_copy", error="Path outside safe scope", error_code=ErrorCode.PERMISSION_DENIED)

        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
        return UnifiedResult.ok(action="file_copy", message=f"Copied {src} to {dst}")

    async def _file_move(self, params: dict[str, Any]) -> UnifiedResult:
        src = params.get("source") or params.get("src")
        dst = params.get("destination") or params.get("dest")
        if not src or not dst:
            return UnifiedResult.fail(action="file_move", error="Missing source or destination", error_code=ErrorCode.VALIDATION_ERROR)

        source = self._resolve_path(src)
        target = self._resolve_path(dst)
        if not source.exists():
            return UnifiedResult.fail(action="file_move", error=f"Source not found: {source}", error_code=ErrorCode.SOURCE_NOT_FOUND)
        if not (self._is_safe_path(source) and self._is_safe_path(target)):
            return UnifiedResult.fail(action="file_move", error="Path outside safe scope", error_code=ErrorCode.PERMISSION_DENIED)

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        return UnifiedResult.ok(action="file_move", message=f"Moved {src} to {dst}")

    async def _file_rename(self, params: dict[str, Any]) -> UnifiedResult:
        src = params.get("source") or params.get("path") or params.get("file_path")
        new_name = params.get("new_name")
        if not src or not new_name:
            return UnifiedResult.fail(action="file_rename", error="Missing source or new_name", error_code=ErrorCode.VALIDATION_ERROR)

        source = self._resolve_path(src)
        if not source.exists():
            return UnifiedResult.fail(action="file_rename", error=f"Source not found: {source}", error_code=ErrorCode.SOURCE_NOT_FOUND)
        target = source.with_name(new_name)
        if not (self._is_safe_path(source) and self._is_safe_path(target)):
            return UnifiedResult.fail(action="file_rename", error="Path outside safe scope", error_code=ErrorCode.PERMISSION_DENIED)

        source.rename(target)
        return UnifiedResult.ok(action="file_rename", message=f"Renamed to {new_name}", data={"path": str(target)})

    async def _file_exists(self, params: dict[str, Any]) -> UnifiedResult:
        raw = params.get("path") or params.get("file_path")
        if not raw:
            return UnifiedResult.fail(action="file_exists", error="Missing file path", error_code=ErrorCode.VALIDATION_ERROR)
        path = self._resolve_path(raw)
        return UnifiedResult.ok(action="file_exists", data={"path": str(path), "exists": path.exists()})

    async def _file_info(self, params: dict[str, Any]) -> UnifiedResult:
        raw = params.get("path") or params.get("file_path")
        if not raw:
            return UnifiedResult.fail(action="file_info", error="Missing file path", error_code=ErrorCode.VALIDATION_ERROR)
        path = self._resolve_path(raw)
        if not path.exists():
            return UnifiedResult.fail(action="file_info", error=f"Path not found: {path}", error_code=ErrorCode.PATH_NOT_FOUND)
        stat = path.stat()
        return UnifiedResult.ok(
            action="file_info",
            data={
                "path": str(path),
                "exists": True,
                "is_file": path.is_file(),
                "is_dir": path.is_dir(),
                "size": stat.st_size,
            },
        )

    async def _file_list(self, params: dict[str, Any]) -> UnifiedResult:
        raw = params.get("directory") or params.get("path") or "."
        directory = self._resolve_path(raw)
        if not directory.exists():
            return UnifiedResult.fail(action="file_list", error=f"Directory not found: {directory}", error_code=ErrorCode.DIR_NOT_FOUND)
        if not directory.is_dir():
            return UnifiedResult.fail(action="file_list", error=f"Not a directory: {directory}", error_code=ErrorCode.NOT_A_DIR)
        if not self._is_safe_path(directory):
            return UnifiedResult.fail(action="file_list", error="Path outside safe scope", error_code=ErrorCode.PERMISSION_DENIED)

        pattern = params.get("pattern", "*")
        items = []
        for p in directory.iterdir():
            if fnmatch.fnmatch(p.name, pattern):
                items.append({"name": p.name, "path": str(p), "is_dir": p.is_dir()})
        return UnifiedResult.ok(action="file_list", data={"items": items, "count": len(items)})

    async def _file_search(self, params: dict[str, Any]) -> UnifiedResult:
        raw = params.get("directory") or params.get("path") or "."
        directory = self._resolve_path(raw)
        if not directory.exists() or not directory.is_dir():
            return UnifiedResult.fail(action="file_search", error=f"Directory not found: {directory}", error_code=ErrorCode.DIR_NOT_FOUND)
        if not self._is_safe_path(directory):
            return UnifiedResult.fail(action="file_search", error="Path outside safe scope", error_code=ErrorCode.PERMISSION_DENIED)

        pattern = params.get("pattern", "*")
        recursive = params.get("recursive", True)
        iterator = directory.rglob(pattern) if recursive else directory.glob(pattern)
        matches = [{"name": p.name, "path": str(p), "is_dir": p.is_dir()} for p in iterator]
        return UnifiedResult.ok(action="file_search", data={"items": matches, "count": len(matches)})

    async def _dir_create(self, params: dict[str, Any]) -> UnifiedResult:
        raw = params.get("directory") or params.get("path")
        if not raw:
            return UnifiedResult.fail(action="dir_create", error="Missing directory path", error_code=ErrorCode.VALIDATION_ERROR)
        directory = self._resolve_path(raw)
        if not self._is_safe_path(directory):
            return UnifiedResult.fail(action="dir_create", error="Path outside safe scope", error_code=ErrorCode.PERMISSION_DENIED)
        directory.mkdir(parents=True, exist_ok=True)
        return UnifiedResult.ok(action="dir_create", message=f"Created directory {raw}")

    async def _dir_delete(self, params: dict[str, Any]) -> UnifiedResult:
        raw = params.get("directory") or params.get("path")
        if not raw:
            return UnifiedResult.fail(action="dir_delete", error="Missing directory path", error_code=ErrorCode.VALIDATION_ERROR)
        directory = self._resolve_path(raw)
        if not self._is_safe_path(directory):
            return UnifiedResult.fail(action="dir_delete", error="Path outside safe scope", error_code=ErrorCode.PERMISSION_DENIED)
        if not params.get("confirmed", False):
            return UnifiedResult.fail(action="dir_delete", error="Delete requires confirmation", error_code=ErrorCode.PERMISSION_DENIED, data={"need_confirm": True})
        if not directory.exists():
            return UnifiedResult.fail(action="dir_delete", error=f"Directory not found: {directory}", error_code=ErrorCode.DIR_NOT_FOUND)
        shutil.rmtree(directory)
        return UnifiedResult.ok(action="dir_delete", message=f"Deleted directory {raw}")


def get_file_handler(context: OperationContext | None = None) -> FileOperationHandler:
    return FileOperationHandler(context=context)


def get_file_executor(context: OperationContext | None = None) -> FileOperationHandler:
    return get_file_handler(context=context)


FileExecutor = FileOperationHandler
FileResult = UnifiedResult

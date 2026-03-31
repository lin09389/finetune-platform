import asyncio
import shutil
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class DirectoryResult(BaseModel):
    success: bool = Field(default=True)
    path: str = ""
    error: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class DirectoryInfo(BaseModel):
    path: str
    name: str
    is_dir: bool = True
    size: int = 0
    file_count: int = 0
    dir_count: int = 0
    modified: str = ""
    children: list["DirectoryInfo"] = Field(default_factory=list)


class TreeResult(BaseModel):
    success: bool = Field(default=True)
    root: DirectoryInfo | None = None
    total_files: int = 0
    total_dirs: int = 0
    total_size: int = 0
    error: str | None = None


class DirectoryExecutor:
    def __init__(
        self,
        progress_callback: Callable[[str, float, str], Awaitable[None]] | None = None,
    ):
        self.progress_callback = progress_callback

    async def create(
        self,
        path: str,
        parents: bool = True,
        exist_ok: bool = True,
    ) -> DirectoryResult:
        dir_path = Path(path)

        try:
            if self.progress_callback:
                await self.progress_callback(
                    path,
                    0.0,
                    f"开始创建目录: {dir_path.name}",
                )

            if parents:
                dir_path.mkdir(parents=True, exist_ok=exist_ok)
            else:
                dir_path.mkdir(exist_ok=exist_ok)

            if self.progress_callback:
                await self.progress_callback(
                    path,
                    1.0,
                    f"目录创建完成: {dir_path.name}",
                )

            return DirectoryResult(
                success=True,
                path=str(dir_path),
            )

        except FileExistsError:
            return DirectoryResult(
                success=False,
                path=path,
                error=f"目录已存在: {path}",
            )
        except FileNotFoundError:
            return DirectoryResult(
                success=False,
                path=path,
                error=f"父目录不存在: {path}",
            )
        except Exception as e:
            return DirectoryResult(
                success=False,
                path=path,
                error=f"创建目录失败: {str(e)}",
            )

    async def delete(
        self,
        path: str,
        recursive: bool = False,
        force: bool = False,
    ) -> DirectoryResult:
        dir_path = Path(path)

        if not dir_path.exists():
            return DirectoryResult(
                success=False,
                path=path,
                error=f"目录不存在: {path}",
            )

        if not dir_path.is_dir():
            return DirectoryResult(
                success=False,
                path=path,
                error=f"路径不是目录: {path}",
            )

        try:
            if self.progress_callback:
                await self.progress_callback(
                    path,
                    0.0,
                    f"开始删除目录: {dir_path.name}",
                )

            if recursive or force:
                await asyncio.to_thread(shutil.rmtree, dir_path)
            else:
                try:
                    dir_path.rmdir()
                except OSError as e:
                    if "not empty" in str(e).lower() or "非空" in str(e):
                        return DirectoryResult(
                            success=False,
                            path=path,
                            error="目录不为空，请使用 recursive=True 进行递归删除",
                        )
                    raise

            if self.progress_callback:
                await self.progress_callback(
                    path,
                    1.0,
                    f"目录删除完成: {dir_path.name}",
                )

            return DirectoryResult(
                success=True,
                path=str(dir_path),
            )

        except Exception as e:
            return DirectoryResult(
                success=False,
                path=path,
                error=f"删除目录失败: {str(e)}",
            )

    async def list_contents(
        self,
        path: str,
        pattern: str = "*",
        include_hidden: bool = False,
        sort_by: str = "name",
        reverse: bool = False,
    ) -> DirectoryResult:
        dir_path = Path(path)

        if not dir_path.exists():
            return DirectoryResult(
                success=False,
                path=path,
                error=f"目录不存在: {path}",
            )

        if not dir_path.is_dir():
            return DirectoryResult(
                success=False,
                path=path,
                error=f"路径不是目录: {path}",
            )

        try:
            items = []
            for item in dir_path.glob(pattern):
                if not include_hidden and item.name.startswith("."):
                    continue

                try:
                    stat = item.stat()
                    items.append({
                        "name": item.name,
                        "path": str(item),
                        "is_dir": item.is_dir(),
                        "size": stat.st_size if item.is_file() else 0,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
                except Exception:
                    continue

            sort_keys = {
                "name": lambda x: (not x["is_dir"], x["name"].lower()),
                "size": lambda x: (not x["is_dir"], x["size"]),
                "modified": lambda x: (not x["is_dir"], x["modified"]),
                "type": lambda x: (not x["is_dir"], x["name"].lower()),
            }

            if sort_by in sort_keys:
                items.sort(key=sort_keys[sort_by], reverse=reverse)

            return DirectoryResult(
                success=True,
                path=str(dir_path),
            )

        except Exception as e:
            return DirectoryResult(
                success=False,
                path=path,
                error=f"列出目录失败: {str(e)}",
            )

    async def tree(
        self,
        path: str,
        max_depth: int = -1,
        include_files: bool = True,
        include_hidden: bool = False,
    ) -> TreeResult:
        dir_path = Path(path)

        if not dir_path.exists():
            return TreeResult(
                success=False,
                error=f"目录不存在: {path}",
            )

        if not dir_path.is_dir():
            return TreeResult(
                success=False,
                error=f"路径不是目录: {path}",
            )

        try:
            total_files = 0
            total_dirs = 0
            total_size = 0

            def build_tree(current_path: Path, depth: int) -> DirectoryInfo | None:
                nonlocal total_files, total_dirs, total_size

                if max_depth >= 0 and depth > max_depth:
                    return None

                try:
                    stat = current_path.stat()
                except Exception:
                    return None

                if not include_hidden and current_path.name.startswith("."):
                    return None

                info = DirectoryInfo(
                    path=str(current_path),
                    name=current_path.name,
                    is_dir=current_path.is_dir(),
                    modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                )

                if current_path.is_file():
                    info.size = stat.st_size
                    total_files += 1
                    total_size += stat.st_size
                    return info

                total_dirs += 1

                try:
                    children = []
                    for child in sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                        child_info = build_tree(child, depth + 1)
                        if child_info:
                            children.append(child_info)
                            info.file_count += child_info.file_count
                            info.dir_count += child_info.dir_count
                            info.size += child_info.size

                    info.children = children
                    info.dir_count += len([c for c in children if c.is_dir])
                    info.file_count += len([c for c in children if not c.is_dir])

                except PermissionError:
                    pass

                return info

            if self.progress_callback:
                await self.progress_callback(
                    path,
                    0.0,
                    f"开始生成目录树: {dir_path.name}",
                )

            root = build_tree(dir_path, 0)

            if self.progress_callback:
                await self.progress_callback(
                    path,
                    1.0,
                    "目录树生成完成",
                )

            return TreeResult(
                success=True,
                root=root,
                total_files=total_files,
                total_dirs=total_dirs,
                total_size=total_size,
            )

        except Exception as e:
            return TreeResult(
                success=False,
                error=f"生成目录树失败: {str(e)}",
            )

    async def get_size(self, path: str) -> dict[str, Any]:
        dir_path = Path(path)

        if not dir_path.exists():
            return {
                "success": False,
                "error": f"目录不存在: {path}",
            }

        if not dir_path.is_dir():
            return {
                "success": False,
                "error": f"路径不是目录: {path}",
            }

        try:
            total_size = 0
            file_count = 0
            dir_count = 0

            for item in dir_path.rglob("*"):
                if item.is_file():
                    try:
                        total_size += item.stat().st_size
                        file_count += 1
                    except Exception:
                        pass
                elif item.is_dir():
                    dir_count += 1

            return {
                "success": True,
                "path": str(dir_path),
                "total_size": total_size,
                "file_count": file_count,
                "dir_count": dir_count,
                "size_formatted": self._format_size(total_size),
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"计算目录大小失败: {str(e)}",
            }

    async def empty(
        self,
        path: str,
        keep_structure: bool = True,
    ) -> DirectoryResult:
        dir_path = Path(path)

        if not dir_path.exists():
            return DirectoryResult(
                success=False,
                path=path,
                error=f"目录不存在: {path}",
            )

        if not dir_path.is_dir():
            return DirectoryResult(
                success=False,
                path=path,
                error=f"路径不是目录: {path}",
            )

        try:
            if self.progress_callback:
                await self.progress_callback(
                    path,
                    0.0,
                    f"开始清空目录: {dir_path.name}",
                )

            if keep_structure:
                for item in dir_path.iterdir():
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
            else:
                for item in dir_path.iterdir():
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)

            if self.progress_callback:
                await self.progress_callback(
                    path,
                    1.0,
                    f"目录清空完成: {dir_path.name}",
                )

            return DirectoryResult(
                success=True,
                path=str(dir_path),
            )

        except Exception as e:
            return DirectoryResult(
                success=False,
                path=path,
                error=f"清空目录失败: {str(e)}",
            )

    async def copy_structure(
        self,
        source: str,
        destination: str,
    ) -> DirectoryResult:
        source_path = Path(source)
        dest_path = Path(destination)

        if not source_path.exists():
            return DirectoryResult(
                success=False,
                path=source,
                error=f"源目录不存在: {source}",
            )

        if not source_path.is_dir():
            return DirectoryResult(
                success=False,
                path=source,
                error=f"源路径不是目录: {source}",
            )

        try:
            if self.progress_callback:
                await self.progress_callback(
                    source,
                    0.0,
                    f"开始复制目录结构: {source_path.name}",
                )

            def copy_dir_structure(src: Path, dst: Path):
                dst.mkdir(parents=True, exist_ok=True)
                for item in src.iterdir():
                    if item.is_dir():
                        copy_dir_structure(item, dst / item.name)

            await asyncio.to_thread(copy_dir_structure, source_path, dest_path)

            if self.progress_callback:
                await self.progress_callback(
                    source,
                    1.0,
                    "目录结构复制完成",
                )

            return DirectoryResult(
                success=True,
                path=str(dest_path),
            )

        except Exception as e:
            return DirectoryResult(
                success=False,
                path=destination,
                error=f"复制目录结构失败: {str(e)}",
            )

    def _format_size(self, size: int) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"

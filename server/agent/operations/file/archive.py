import asyncio
import tarfile
import zipfile
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ArchiveResult(BaseModel):
    success: bool = Field(default=True)
    source: str = ""
    destination: str = ""
    files_count: int = 0
    bytes_processed: int = 0
    error: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class ArchiveExecutor:
    def __init__(
        self,
        progress_callback: Callable[[str, float, str], Awaitable[None]] | None = None,
        chunk_size: int = 1024 * 1024,
    ):
        self.progress_callback = progress_callback
        self.chunk_size = chunk_size

    async def create_zip(
        self,
        source: str,
        destination: str,
        compression: int = zipfile.ZIP_DEFLATED,
        include_root: bool = True,
        ignore_patterns: list[str] | None = None,
    ) -> ArchiveResult:
        source_path = Path(source)
        dest_path = Path(destination)

        if not source_path.exists():
            return ArchiveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"源路径不存在: {source}",
            )

        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if self.progress_callback:
                await self.progress_callback(
                    source,
                    0.0,
                    f"开始创建 ZIP: {dest_path.name}",
                )

            files_to_archive: list[Path] = []

            if source_path.is_file():
                files_to_archive = [source_path]
                base_dir = source_path.parent
            else:
                base_dir = source_path
                for item in source_path.rglob("*"):
                    if item.is_file():
                        if ignore_patterns:
                            should_ignore = False
                            for pattern in ignore_patterns:
                                if item.match(pattern):
                                    should_ignore = True
                                    break
                            if should_ignore:
                                continue
                        files_to_archive.append(item)

            total_files = len(files_to_archive)
            bytes_processed = 0

            def create_zip_sync():
                nonlocal bytes_processed
                with zipfile.ZipFile(dest_path, "w", compression) as zf:
                    for idx, file_path in enumerate(files_to_archive):
                        if include_root:
                            arcname = file_path.relative_to(base_dir.parent)
                        else:
                            arcname = file_path.relative_to(base_dir)

                        zf.write(file_path, arcname)
                        bytes_processed += file_path.stat().st_size

            await asyncio.to_thread(create_zip_sync)

            if self.progress_callback:
                await self.progress_callback(
                    source,
                    1.0,
                    f"ZIP 创建完成: {total_files} 个文件",
                )

            return ArchiveResult(
                success=True,
                source=source,
                destination=destination,
                files_count=total_files,
                bytes_processed=bytes_processed,
            )

        except Exception as e:
            if dest_path.exists():
                dest_path.unlink()
            return ArchiveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"创建 ZIP 失败: {str(e)}",
            )

    async def extract_zip(
        self,
        source: str,
        destination: str,
        overwrite: bool = False,
        password: str | None = None,
    ) -> ArchiveResult:
        source_path = Path(source)
        dest_path = Path(destination)

        if not source_path.exists():
            return ArchiveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"源文件不存在: {source}",
            )

        if not zipfile.is_zipfile(source_path):
            return ArchiveResult(
                success=False,
                source=source,
                destination=destination,
                error="不是有效的 ZIP 文件",
            )

        try:
            if self.progress_callback:
                await self.progress_callback(
                    source,
                    0.0,
                    f"开始解压 ZIP: {source_path.name}",
                )

            dest_path.mkdir(parents=True, exist_ok=True)

            def extract_zip_sync():
                with zipfile.ZipFile(source_path, "r") as zf:
                    if password:
                        zf.setpassword(password.encode())

                    members = zf.namelist()
                    total = len(members)

                    for idx, member in enumerate(members):
                        if not overwrite:
                            target_path = dest_path / member
                            if target_path.exists():
                                continue

                        zf.extract(member, dest_path)

                    return total

            files_count = await asyncio.to_thread(extract_zip_sync)

            if self.progress_callback:
                await self.progress_callback(
                    source,
                    1.0,
                    f"ZIP 解压完成: {files_count} 个文件",
                )

            return ArchiveResult(
                success=True,
                source=source,
                destination=destination,
                files_count=files_count,
            )

        except RuntimeError as e:
            if "password" in str(e).lower():
                return ArchiveResult(
                    success=False,
                    source=source,
                    destination=destination,
                    error="ZIP 文件需要密码或密码错误",
                )
            raise
        except Exception as e:
            return ArchiveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"解压 ZIP 失败: {str(e)}",
            )

    async def create_tar(
        self,
        source: str,
        destination: str,
        mode: str = "gz",
        include_root: bool = True,
        ignore_patterns: list[str] | None = None,
    ) -> ArchiveResult:
        source_path = Path(source)
        dest_path = Path(destination)

        if not source_path.exists():
            return ArchiveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"源路径不存在: {source}",
            )

        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if self.progress_callback:
                await self.progress_callback(
                    source,
                    0.0,
                    f"开始创建 TAR: {dest_path.name}",
                )

            files_to_archive: list[Path] = []

            if source_path.is_file():
                files_to_archive = [source_path]
                base_dir = source_path.parent
            else:
                base_dir = source_path
                for item in source_path.rglob("*"):
                    if item.is_file():
                        if ignore_patterns:
                            should_ignore = False
                            for pattern in ignore_patterns:
                                if item.match(pattern):
                                    should_ignore = True
                                    break
                            if should_ignore:
                                continue
                        files_to_archive.append(item)

            total_files = len(files_to_archive)
            bytes_processed = 0

            mode_map = {
                "gz": "w:gz",
                "bz2": "w:bz2",
                "xz": "w:xz",
                "tar": "w",
            }
            tar_mode = mode_map.get(mode, "w:gz")

            def create_tar_sync():
                nonlocal bytes_processed
                with tarfile.open(dest_path, tar_mode) as tf:
                    for file_path in files_to_archive:
                        if include_root:
                            arcname = file_path.relative_to(base_dir.parent)
                        else:
                            arcname = file_path.relative_to(base_dir)

                        tf.add(file_path, arcname)
                        bytes_processed += file_path.stat().st_size

            await asyncio.to_thread(create_tar_sync)

            if self.progress_callback:
                await self.progress_callback(
                    source,
                    1.0,
                    f"TAR 创建完成: {total_files} 个文件",
                )

            return ArchiveResult(
                success=True,
                source=source,
                destination=destination,
                files_count=total_files,
                bytes_processed=bytes_processed,
            )

        except Exception as e:
            if dest_path.exists():
                dest_path.unlink()
            return ArchiveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"创建 TAR 失败: {str(e)}",
            )

    async def extract_tar(
        self,
        source: str,
        destination: str,
        overwrite: bool = False,
    ) -> ArchiveResult:
        source_path = Path(source)
        dest_path = Path(destination)

        if not source_path.exists():
            return ArchiveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"源文件不存在: {source}",
            )

        if not tarfile.is_tarfile(source_path):
            return ArchiveResult(
                success=False,
                source=source,
                destination=destination,
                error="不是有效的 TAR 文件",
            )

        try:
            if self.progress_callback:
                await self.progress_callback(
                    source,
                    0.0,
                    f"开始解压 TAR: {source_path.name}",
                )

            dest_path.mkdir(parents=True, exist_ok=True)

            def extract_tar_sync():
                with tarfile.open(source_path, "r:*") as tf:
                    members = tf.getmembers()
                    total = len(members)

                    for idx, member in enumerate(members):
                        if not overwrite:
                            target_path = dest_path / member.name
                            if target_path.exists():
                                continue

                        tf.extract(member, dest_path)

                    return total

            files_count = await asyncio.to_thread(extract_tar_sync)

            if self.progress_callback:
                await self.progress_callback(
                    source,
                    1.0,
                    f"TAR 解压完成: {files_count} 个文件",
                )

            return ArchiveResult(
                success=True,
                source=source,
                destination=destination,
                files_count=files_count,
            )

        except Exception as e:
            return ArchiveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"解压 TAR 失败: {str(e)}",
            )

    async def create_archive(
        self,
        source: str,
        destination: str,
        archive_type: str = "zip",
        **kwargs,
    ) -> ArchiveResult:
        archive_type = archive_type.lower()

        if archive_type == "zip":
            return await self.create_zip(source, destination, **kwargs)
        elif archive_type in ("tar", "gz", "bz2", "xz"):
            mode = archive_type if archive_type != "tar" else "tar"
            return await self.create_tar(source, destination, mode=mode, **kwargs)
        else:
            return ArchiveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"不支持的归档类型: {archive_type}",
            )

    async def extract_archive(
        self,
        source: str,
        destination: str,
        **kwargs,
    ) -> ArchiveResult:
        source_path = Path(source)
        suffix = source_path.suffix.lower()

        if suffix == ".zip":
            return await self.extract_zip(source, destination, **kwargs)
        elif suffix in (".tar", ".gz", ".bz2", ".xz", ".tgz", ".tbz2"):
            return await self.extract_tar(source, destination, **kwargs)
        else:
            return ArchiveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"无法识别的归档类型: {suffix}",
            )

    async def list_archive_contents(
        self,
        source: str,
    ) -> list[dict[str, Any]]:
        source_path = Path(source)

        if not source_path.exists():
            return []

        try:
            contents: list[dict[str, Any]] = []
            suffix = source_path.suffix.lower()

            if suffix == ".zip":
                with zipfile.ZipFile(source_path, "r") as zf:
                    for info in zf.infolist():
                        contents.append({
                            "name": info.filename,
                            "size": info.file_size,
                            "compressed_size": info.compress_size,
                            "is_dir": info.is_dir(),
                            "modified": datetime(*info.date_time).isoformat(),
                        })

            elif suffix in (".tar", ".gz", ".bz2", ".xz", ".tgz", ".tbz2"):
                with tarfile.open(source_path, "r:*") as tf:
                    for member in tf.getmembers():
                        contents.append({
                            "name": member.name,
                            "size": member.size,
                            "is_dir": member.isdir(),
                            "modified": datetime.fromtimestamp(member.mtime).isoformat() if member.mtime else "",
                        })

            return contents

        except Exception:
            return []

    async def add_to_archive(
        self,
        archive_path: str,
        files_to_add: list[str],
    ) -> ArchiveResult:
        archive = Path(archive_path)

        if not archive.exists():
            return ArchiveResult(
                success=False,
                source="",
                destination=archive_path,
                error=f"归档文件不存在: {archive_path}",
            )

        suffix = archive.suffix.lower()

        if suffix != ".zip":
            return ArchiveResult(
                success=False,
                source="",
                destination=archive_path,
                error="只支持向 ZIP 归档添加文件",
            )

        try:
            if self.progress_callback:
                await self.progress_callback(
                    archive_path,
                    0.0,
                    "开始添加文件到 ZIP",
                )

            def add_to_zip_sync():
                with zipfile.ZipFile(archive, "a") as zf:
                    for file_path in files_to_add:
                        path = Path(file_path)
                        if path.exists():
                            zf.write(path, path.name)

            await asyncio.to_thread(add_to_zip_sync)

            if self.progress_callback:
                await self.progress_callback(
                    archive_path,
                    1.0,
                    "文件添加完成",
                )

            return ArchiveResult(
                success=True,
                source="",
                destination=archive_path,
                files_count=len(files_to_add),
            )

        except Exception as e:
            return ArchiveResult(
                success=False,
                source="",
                destination=archive_path,
                error=f"添加文件失败: {str(e)}",
            )

    async def extract_single_file(
        self,
        archive_path: str,
        file_name: str,
        destination: str,
    ) -> ArchiveResult:
        archive = Path(archive_path)
        dest_path = Path(destination)

        if not archive.exists():
            return ArchiveResult(
                success=False,
                source=archive_path,
                destination=destination,
                error=f"归档文件不存在: {archive_path}",
            )

        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            suffix = archive.suffix.lower()

            if suffix == ".zip":
                with zipfile.ZipFile(archive, "r") as zf:
                    zf.extract(file_name, dest_path.parent)

            elif suffix in (".tar", ".gz", ".bz2", ".xz", ".tgz", ".tbz2"):
                with tarfile.open(archive, "r:*") as tf:
                    member = tf.getmember(file_name)
                    tf.extract(member, dest_path.parent)

            return ArchiveResult(
                success=True,
                source=archive_path,
                destination=destination,
                files_count=1,
            )

        except KeyError:
            return ArchiveResult(
                success=False,
                source=archive_path,
                destination=destination,
                error=f"归档中不存在文件: {file_name}",
            )
        except Exception as e:
            return ArchiveResult(
                success=False,
                source=archive_path,
                destination=destination,
                error=f"提取文件失败: {str(e)}",
            )

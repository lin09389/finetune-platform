import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from .copy import FileCopyExecutor
from .move import FileMoveExecutor


class BatchItemResult(BaseModel):
    source: str = ""
    destination: str = ""
    success: bool = Field(default=True)
    error: str | None = None
    bytes_processed: int = 0


class BatchResult(BaseModel):
    success: bool = Field(default=True)
    operation: str = ""
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    total_bytes: int = 0
    results: list[BatchItemResult] = Field(default_factory=list)
    error: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class BatchFileExecutor:
    def __init__(
        self,
        progress_callback: Callable[[str, float, str], Awaitable[None]] | None = None,
    ):
        self.progress_callback = progress_callback
        self.copy_executor = FileCopyExecutor(progress_callback)
        self.move_executor = FileMoveExecutor(progress_callback)

    async def batch_copy(
        self,
        sources: list[str],
        destination_dir: str,
        overwrite: bool = False,
    ) -> BatchResult:
        dest_dir = Path(destination_dir)

        if not dest_dir.exists():
            dest_dir.mkdir(parents=True, exist_ok=True)

        if not dest_dir.is_dir():
            return BatchResult(
                success=False,
                operation="batch_copy",
                error=f"目标路径不是目录: {destination_dir}",
            )

        results: list[BatchItemResult] = []
        succeeded = 0
        failed = 0
        total_bytes = 0
        total = len(sources)

        for idx, source in enumerate(sources):
            source_path = Path(source)
            dest_path = dest_dir / source_path.name

            result = await self.copy_executor.copy(
                str(source_path),
                str(dest_path),
                overwrite=overwrite,
            )

            item_result = BatchItemResult(
                source=source,
                destination=str(dest_path),
                success=result.success,
                error=result.error,
                bytes_processed=result.bytes_copied,
            )
            results.append(item_result)

            if result.success:
                succeeded += 1
                total_bytes += result.bytes_copied
            else:
                failed += 1

            if self.progress_callback:
                progress = (idx + 1) / total if total > 0 else 1.0
                await self.progress_callback(
                    "batch_copy",
                    progress,
                    f"批量复制进度: {idx + 1}/{total}",
                )

        return BatchResult(
            success=failed == 0,
            operation="batch_copy",
            total=total,
            succeeded=succeeded,
            failed=failed,
            total_bytes=total_bytes,
            results=results,
        )

    async def batch_move(
        self,
        sources: list[str],
        destination_dir: str,
        overwrite: bool = False,
    ) -> BatchResult:
        dest_dir = Path(destination_dir)

        if not dest_dir.exists():
            dest_dir.mkdir(parents=True, exist_ok=True)

        if not dest_dir.is_dir():
            return BatchResult(
                success=False,
                operation="batch_move",
                error=f"目标路径不是目录: {destination_dir}",
            )

        results: list[BatchItemResult] = []
        succeeded = 0
        failed = 0
        total = len(sources)

        for idx, source in enumerate(sources):
            source_path = Path(source)
            dest_path = dest_dir / source_path.name

            result = await self.move_executor.move(
                str(source_path),
                str(dest_path),
                overwrite=overwrite,
            )

            item_result = BatchItemResult(
                source=source,
                destination=str(dest_path),
                success=result.success,
                error=result.error,
            )
            results.append(item_result)

            if result.success:
                succeeded += 1
            else:
                failed += 1

            if self.progress_callback:
                progress = (idx + 1) / total if total > 0 else 1.0
                await self.progress_callback(
                    "batch_move",
                    progress,
                    f"批量移动进度: {idx + 1}/{total}",
                )

        return BatchResult(
            success=failed == 0,
            operation="batch_move",
            total=total,
            succeeded=succeeded,
            failed=failed,
            results=results,
        )

    async def batch_delete(
        self,
        paths: list[str],
        skip_missing: bool = True,
    ) -> BatchResult:
        results: list[BatchItemResult] = []
        succeeded = 0
        failed = 0
        total = len(paths)

        for idx, path in enumerate(paths):
            item_path = Path(path)

            try:
                if not item_path.exists():
                    if skip_missing:
                        item_result = BatchItemResult(
                            source=path,
                            destination="",
                            success=True,
                            error="文件不存在（已跳过）",
                        )
                        results.append(item_result)
                        succeeded += 1
                        continue
                    else:
                        raise FileNotFoundError(f"文件不存在: {path}")

                if self.progress_callback:
                    await self.progress_callback(
                        "batch_delete",
                        idx / total if total > 0 else 0.0,
                        f"删除中: {item_path.name}",
                    )

                if item_path.is_file():
                    await asyncio.to_thread(item_path.unlink)
                elif item_path.is_dir():
                    await asyncio.to_thread(
                        lambda p: __import__("shutil").rmtree(p), item_path
                    )

                item_result = BatchItemResult(
                    source=path,
                    destination="",
                    success=True,
                )
                results.append(item_result)
                succeeded += 1

            except Exception as e:
                item_result = BatchItemResult(
                    source=path,
                    destination="",
                    success=False,
                    error=str(e),
                )
                results.append(item_result)
                failed += 1

            if self.progress_callback:
                progress = (idx + 1) / total if total > 0 else 1.0
                await self.progress_callback(
                    "batch_delete",
                    progress,
                    f"批量删除进度: {idx + 1}/{total}",
                )

        return BatchResult(
            success=failed == 0,
            operation="batch_delete",
            total=total,
            succeeded=succeeded,
            failed=failed,
            results=results,
        )

    async def batch_rename(
        self,
        paths: list[str],
        new_names: list[str],
        overwrite: bool = False,
    ) -> BatchResult:
        if len(paths) != len(new_names):
            return BatchResult(
                success=False,
                operation="batch_rename",
                error="路径列表和新名称列表长度不匹配",
            )

        results: list[BatchItemResult] = []
        succeeded = 0
        failed = 0
        total = len(paths)

        for idx, (old_path, new_name) in enumerate(
            zip(paths, new_names, strict=False)
        ):
            source_path = Path(old_path)

            try:
                if not source_path.exists():
                    raise FileNotFoundError(f"文件不存在: {old_path}")

                dest_path = source_path.parent / new_name

                if dest_path.exists() and not overwrite:
                    raise FileExistsError(f"目标名称已存在: {new_name}")

                if dest_path.exists():
                    if dest_path.is_dir():
                        await asyncio.to_thread(
                            lambda p: __import__("shutil").rmtree(p), dest_path
                        )
                    else:
                        dest_path.unlink()

                await asyncio.to_thread(source_path.rename, dest_path)

                item_result = BatchItemResult(
                    source=old_path,
                    destination=str(dest_path),
                    success=True,
                )
                results.append(item_result)
                succeeded += 1

            except Exception as e:
                item_result = BatchItemResult(
                    source=old_path,
                    destination="",
                    success=False,
                    error=str(e),
                )
                results.append(item_result)
                failed += 1

            if self.progress_callback:
                progress = (idx + 1) / total if total > 0 else 1.0
                await self.progress_callback(
                    "batch_rename",
                    progress,
                    f"批量重命名进度: {idx + 1}/{total}",
                )

        return BatchResult(
            success=failed == 0,
            operation="batch_rename",
            total=total,
            succeeded=succeeded,
            failed=failed,
            results=results,
        )

    async def batch_create_directories(
        self,
        paths: list[str],
        parents: bool = True,
    ) -> BatchResult:
        results: list[BatchItemResult] = []
        succeeded = 0
        failed = 0
        total = len(paths)

        for idx, path in enumerate(paths):
            dir_path = Path(path)

            try:
                if parents:
                    dir_path.mkdir(parents=True, exist_ok=True)
                else:
                    dir_path.mkdir(exist_ok=True)

                item_result = BatchItemResult(
                    source=path,
                    destination=str(dir_path),
                    success=True,
                )
                results.append(item_result)
                succeeded += 1

            except Exception as e:
                item_result = BatchItemResult(
                    source=path,
                    destination="",
                    success=False,
                    error=str(e),
                )
                results.append(item_result)
                failed += 1

            if self.progress_callback:
                progress = (idx + 1) / total if total > 0 else 1.0
                await self.progress_callback(
                    "batch_create_directories",
                    progress,
                    f"批量创建目录进度: {idx + 1}/{total}",
                )

        return BatchResult(
            success=failed == 0,
            operation="batch_create_directories",
            total=total,
            succeeded=succeeded,
            failed=failed,
            results=results,
        )

    async def batch_copy_with_pattern(
        self,
        source_dir: str,
        destination_dir: str,
        pattern: str = "*",
        recursive: bool = False,
        overwrite: bool = False,
    ) -> BatchResult:
        source_path = Path(source_dir)

        if not source_path.exists():
            return BatchResult(
                success=False,
                operation="batch_copy_with_pattern",
                error=f"源目录不存在: {source_dir}",
            )

        if not source_path.is_dir():
            return BatchResult(
                success=False,
                operation="batch_copy_with_pattern",
                error=f"源路径不是目录: {source_dir}",
            )

        if recursive:
            files = list(source_path.rglob(pattern))
        else:
            files = list(source_path.glob(pattern))

        files = [f for f in files if f.is_file()]

        sources = [str(f) for f in files]
        return await self.batch_copy(sources, destination_dir, overwrite)

    async def batch_move_with_pattern(
        self,
        source_dir: str,
        destination_dir: str,
        pattern: str = "*",
        recursive: bool = False,
        overwrite: bool = False,
    ) -> BatchResult:
        source_path = Path(source_dir)

        if not source_path.exists():
            return BatchResult(
                success=False,
                operation="batch_move_with_pattern",
                error=f"源目录不存在: {source_dir}",
            )

        if not source_path.is_dir():
            return BatchResult(
                success=False,
                operation="batch_move_with_pattern",
                error=f"源路径不是目录: {source_dir}",
            )

        if recursive:
            files = list(source_path.rglob(pattern))
        else:
            files = list(source_path.glob(pattern))

        files = [f for f in files if f.is_file()]

        sources = [str(f) for f in files]
        return await self.batch_move(sources, destination_dir, overwrite)

    async def batch_delete_with_pattern(
        self,
        directory: str,
        pattern: str = "*",
        recursive: bool = False,
        skip_missing: bool = True,
    ) -> BatchResult:
        dir_path = Path(directory)

        if not dir_path.exists():
            return BatchResult(
                success=False,
                operation="batch_delete_with_pattern",
                error=f"目录不存在: {directory}",
            )

        if not dir_path.is_dir():
            return BatchResult(
                success=False,
                operation="batch_delete_with_pattern",
                error=f"路径不是目录: {directory}",
            )

        if recursive:
            items = list(dir_path.rglob(pattern))
        else:
            items = list(dir_path.glob(pattern))

        paths = [str(item) for item in items]
        return await self.batch_delete(paths, skip_missing)

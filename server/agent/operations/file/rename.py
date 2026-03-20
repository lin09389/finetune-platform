import asyncio
import re
from pathlib import Path
from typing import Optional, Callable, Awaitable, List
from pydantic import BaseModel, Field
from datetime import datetime


class RenameResult(BaseModel):
    success: bool = Field(default=True)
    old_path: str = ""
    new_path: str = ""
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class BatchRenameResult(BaseModel):
    success: bool = Field(default=True)
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: List[RenameResult] = Field(default_factory=list)
    error: Optional[str] = None


class FileRenameExecutor:
    def __init__(
        self,
        progress_callback: Optional[Callable[[str, float, str], Awaitable[None]]] = None,
    ):
        self.progress_callback = progress_callback

    async def rename(
        self,
        source: str,
        new_name: str,
        overwrite: bool = False,
    ) -> RenameResult:
        source_path = Path(source)

        if not source_path.exists():
            return RenameResult(
                success=False,
                old_path=source,
                new_path="",
                error=f"æºæä»?ç®å½ä¸å­å? {source}",
            )

        new_path = source_path.parent / new_name

        if new_path.exists() and not overwrite:
            return RenameResult(
                success=False,
                old_path=source,
                new_path=str(new_path),
                error=f"ç®æ åç§°å·²å­å? {new_name}",
            )

        try:
            if self.progress_callback:
                await self.progress_callback(
                    source,
                    0.0,
                    f"å¼å§éå½å: {source_path.name} -> {new_name}",
                )

            if new_path.exists():
                if new_path.is_dir():
                    await asyncio.to_thread(
                        lambda p: __import__("shutil").rmtree(p), new_path
                    )
                else:
                    new_path.unlink()

            await asyncio.to_thread(source_path.rename, new_path)

            if self.progress_callback:
                await self.progress_callback(
                    source,
                    1.0,
                    f"éå½åå®æ? {new_name}",
                )

            return RenameResult(
                success=True,
                old_path=source,
                new_path=str(new_path),
            )

        except Exception as e:
            return RenameResult(
                success=False,
                old_path=source,
                new_path=str(new_path),
                error=f"éå½åå¤±è´? {str(e)}",
            )

    async def batch_rename(
        self,
        directory: str,
        pattern: str,
        replacement: str,
        recursive: bool = False,
        include_dirs: bool = False,
    ) -> BatchRenameResult:
        dir_path = Path(directory)

        if not dir_path.exists():
            return BatchRenameResult(
                success=False,
                error=f"ç®å½ä¸å­å? {directory}",
            )

        if not dir_path.is_dir():
            return BatchRenameResult(
                success=False,
                error=f"è·¯å¾ä¸æ¯ç®å½: {directory}",
            )

        try:
            if recursive:
                items = list(dir_path.rglob("*"))
            else:
                items = list(dir_path.iterdir())

            if not include_dirs:
                items = [item for item in items if item.is_file()]

            items = sorted(items, key=lambda x: len(str(x)), reverse=True)

            results: List[RenameResult] = []
            succeeded = 0
            failed = 0

            total = len(items)
            for idx, item in enumerate(items):
                old_name = item.name
                try:
                    new_name = re.sub(pattern, replacement, old_name)

                    if new_name == old_name:
                        continue

                    result = await self.rename(str(item), new_name, overwrite=False)
                    results.append(result)

                    if result.success:
                        succeeded += 1
                    else:
                        failed += 1

                except re.error as e:
                    results.append(
                        RenameResult(
                            success=False,
                            old_path=str(item),
                            new_path="",
                            error=f"æ­£åè¡¨è¾¾å¼éè¯? {str(e)}",
                        )
                    )
                    failed += 1

                if self.progress_callback:
                    progress = (idx + 1) / total if total > 0 else 1.0
                    await self.progress_callback(
                        directory,
                        progress,
                        f"æ¹ééå½åè¿åº? {idx + 1}/{total}",
                    )

            return BatchRenameResult(
                success=failed == 0,
                total=len(results),
                succeeded=succeeded,
                failed=failed,
                results=results,
            )

        except Exception as e:
            return BatchRenameResult(
                success=False,
                error=f"æ¹ééå½åå¤±è´? {str(e)}",
            )

    async def add_prefix(
        self,
        directory: str,
        prefix: str,
        recursive: bool = False,
        include_dirs: bool = False,
    ) -> BatchRenameResult:
        return await self.batch_rename(
            directory,
            r"^(.*)$",
            f"{prefix}\\1",
            recursive,
            include_dirs,
        )

    async def add_suffix(
        self,
        directory: str,
        suffix: str,
        before_ext: bool = True,
        recursive: bool = False,
        include_dirs: bool = False,
    ) -> BatchRenameResult:
        if before_ext:
            pattern = r"^(.*?)(\.[^.]+)$"
            replacement = f"\\1{suffix}\\2"
        else:
            pattern = r"^(.*)$"
            replacement = f"\\1{suffix}"

        return await self.batch_rename(
            directory,
            pattern,
            replacement,
            recursive,
            include_dirs,
        )

    async def remove_prefix(
        self,
        directory: str,
        prefix: str,
        recursive: bool = False,
        include_dirs: bool = False,
    ) -> BatchRenameResult:
        escaped_prefix = re.escape(prefix)
        pattern = f"^{escaped_prefix}(.*)$"
        return await self.batch_rename(
            directory,
            pattern,
            "\\1",
            recursive,
            include_dirs,
        )

    async def remove_suffix(
        self,
        directory: str,
        suffix: str,
        before_ext: bool = True,
        recursive: bool = False,
        include_dirs: bool = False,
    ) -> BatchRenameResult:
        escaped_suffix = re.escape(suffix)
        if before_ext:
            pattern = f"^(.*?){escaped_suffix}(\\.[^.]+)$"
            replacement = "\\1\\2"
        else:
            pattern = f"^(.*){escaped_suffix}$"
            replacement = "\\1"

        return await self.batch_rename(
            directory,
            pattern,
            replacement,
            recursive,
            include_dirs,
        )

    async def replace_text(
        self,
        directory: str,
        old_text: str,
        new_text: str,
        recursive: bool = False,
        include_dirs: bool = False,
    ) -> BatchRenameResult:
        escaped_old = re.escape(old_text)
        return await self.batch_rename(
            directory,
            escaped_old,
            new_text,
            recursive,
            include_dirs,
        )

    async def change_extension(
        self,
        directory: str,
        old_ext: str,
        new_ext: str,
        recursive: bool = False,
    ) -> BatchRenameResult:
        if not old_ext.startswith("."):
            old_ext = "." + old_ext
        if not new_ext.startswith("."):
            new_ext = "." + new_ext

        escaped_old_ext = re.escape(old_ext)
        pattern = f"^(.*){escaped_old_ext}$"
        replacement = f"\\1{new_ext}"

        return await self.batch_rename(
            directory,
            pattern,
            replacement,
            recursive,
            include_dirs=False,
        )

    async def sequence_numbering(
        self,
        directory: str,
        prefix: str = "",
        start: int = 1,
        padding: int = 3,
        recursive: bool = False,
    ) -> BatchRenameResult:
        dir_path = Path(directory)

        if not dir_path.exists() or not dir_path.is_dir():
            return BatchRenameResult(
                success=False,
                error=f"ç®å½ä¸å­å? {directory}",
            )

        try:
            if recursive:
                items = sorted([f for f in dir_path.rglob("*") if f.is_file()])
            else:
                items = sorted([f for f in dir_path.iterdir() if f.is_file()])

            results: List[RenameResult] = []
            succeeded = 0
            failed = 0

            total = len(items)
            for idx, item in enumerate(items):
                ext = item.suffix
                number = start + idx
                number_str = str(number).zfill(padding)
                new_name = f"{prefix}{number_str}{ext}"

                result = await self.rename(str(item), new_name, overwrite=False)
                results.append(result)

                if result.success:
                    succeeded += 1
                else:
                    failed += 1

                if self.progress_callback:
                    progress = (idx + 1) / total if total > 0 else 1.0
                    await self.progress_callback(
                        directory,
                        progress,
                        f"åºå·éå½åè¿åº? {idx + 1}/{total}",
                    )

            return BatchRenameResult(
                success=failed == 0,
                total=len(results),
                succeeded=succeeded,
                failed=failed,
                results=results,
            )

        except Exception as e:
            return BatchRenameResult(
                success=False,
                error=f"åºå·éå½åå¤±è´? {str(e)}",
            )

import asyncio
import shutil
from pathlib import Path
from typing import Optional, Callable, Awaitable
from pydantic import BaseModel, Field
from datetime import datetime


class CopyResult(BaseModel):
    success: bool = Field(default=True)
    source: str = ""
    destination: str = ""
    bytes_copied: int = 0
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class FileCopyExecutor:
    def __init__(
        self,
        progress_callback: Optional[Callable[[str, float, str], Awaitable[None]]] = None,
        chunk_size: int = 1024 * 1024,
    ):
        self.progress_callback = progress_callback
        self.chunk_size = chunk_size

    async def copy_file(
        self,
        source: str,
        destination: str,
        overwrite: bool = False,
    ) -> CopyResult:
        source_path = Path(source)
        dest_path = Path(destination)

        if not source_path.exists():
            return CopyResult(
                success=False,
                source=source,
                destination=destination,
                error=f"æºæä»¶ä¸å­å¨: {source}",
            )

        if not source_path.is_file():
            return CopyResult(
                success=False,
                source=source,
                destination=destination,
                error=f"æºè·¯å¾ä¸æ¯æä»? {source}",
            )

        if dest_path.exists() and not overwrite:
            return CopyResult(
                success=False,
                source=source,
                destination=destination,
                error=f"ç®æ æä»¶å·²å­å? {destination}",
            )

        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            file_size = source_path.stat().st_size
            bytes_copied = 0

            if self.progress_callback:
                await self.progress_callback(
                    source,
                    0.0,
                    f"å¼å§å¤å? {source_path.name}",
                )

            with open(source_path, "rb") as src_file:
                with open(dest_path, "wb") as dest_file:
                    while True:
                        chunk = await asyncio.to_thread(src_file.read, self.chunk_size)
                        if not chunk:
                            break
                        await asyncio.to_thread(dest_file.write, chunk)
                        bytes_copied += len(chunk)

                        if self.progress_callback and file_size > 0:
                            progress = bytes_copied / file_size
                            await self.progress_callback(
                                source,
                                progress,
                                f"å¤å¶ä¸? {bytes_copied}/{file_size} å­è",
                            )

            shutil.copystat(source_path, dest_path)

            if self.progress_callback:
                await self.progress_callback(
                    source,
                    1.0,
                    f"å¤å¶å®æ: {source_path.name}",
                )

            return CopyResult(
                success=True,
                source=source,
                destination=destination,
                bytes_copied=bytes_copied,
            )

        except Exception as e:
            if dest_path.exists():
                dest_path.unlink()
            return CopyResult(
                success=False,
                source=source,
                destination=destination,
                error=f"å¤å¶å¤±è´¥: {str(e)}",
            )

    async def copy_directory(
        self,
        source: str,
        destination: str,
        overwrite: bool = False,
        ignore_patterns: Optional[list[str]] = None,
    ) -> CopyResult:
        source_path = Path(source)
        dest_path = Path(destination)

        if not source_path.exists():
            return CopyResult(
                success=False,
                source=source,
                destination=destination,
                error=f"æºç®å½ä¸å­å¨: {source}",
            )

        if not source_path.is_dir():
            return CopyResult(
                success=False,
                source=source,
                destination=destination,
                error=f"æºè·¯å¾ä¸æ¯ç®å½? {source}",
            )

        if dest_path.exists() and not overwrite:
            return CopyResult(
                success=False,
                source=source,
                destination=destination,
                error=f"ç®æ ç®å½å·²å­å? {destination}",
            )

        try:
            ignore = None
            if ignore_patterns:
                ignore = shutil.ignore_patterns(*ignore_patterns)

            if self.progress_callback:
                await self.progress_callback(
                    source,
                    0.0,
                    f"å¼å§å¤å¶ç®å½? {source_path.name}",
                )

            def sync_copy():
                if dest_path.exists():
                    shutil.rmtree(dest_path)
                shutil.copytree(source_path, dest_path, ignore=ignore)

            await asyncio.to_thread(sync_copy)

            total_size = sum(
                f.stat().st_size for f in dest_path.rglob("*") if f.is_file()
            )

            if self.progress_callback:
                await self.progress_callback(
                    source,
                    1.0,
                    f"ç®å½å¤å¶å®æ: {source_path.name}",
                )

            return CopyResult(
                success=True,
                source=source,
                destination=destination,
                bytes_copied=total_size,
            )

        except Exception as e:
            return CopyResult(
                success=False,
                source=source,
                destination=destination,
                error=f"ç®å½å¤å¶å¤±è´¥: {str(e)}",
            )

    async def copy(
        self,
        source: str,
        destination: str,
        overwrite: bool = False,
        ignore_patterns: Optional[list[str]] = None,
    ) -> CopyResult:
        source_path = Path(source)

        if source_path.is_file():
            return await self.copy_file(source, destination, overwrite)
        elif source_path.is_dir():
            return await self.copy_directory(
                source, destination, overwrite, ignore_patterns
            )
        else:
            return CopyResult(
                success=False,
                source=source,
                destination=destination,
                error=f"æºè·¯å¾ä¸å­å¨: {source}",
            )

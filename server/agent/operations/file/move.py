import asyncio
import shutil
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class MoveResult(BaseModel):
    success: bool = Field(default=True)
    source: str = ""
    destination: str = ""
    error: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class FileMoveExecutor:
    def __init__(
        self,
        progress_callback: Callable[[str, float, str], Awaitable[None]] | None = None,
    ):
        self.progress_callback = progress_callback

    async def move_file(
        self,
        source: str,
        destination: str,
        overwrite: bool = False,
    ) -> MoveResult:
        source_path = Path(source)
        dest_path = Path(destination)

        if not source_path.exists():
            return MoveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"源文件不存在: {source}",
            )

        if not source_path.is_file():
            return MoveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"源路径不是文件: {source}",
            )

        if dest_path.exists() and not overwrite:
            return MoveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"目标文件已存在: {destination}",
            )

        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            if self.progress_callback:
                await self.progress_callback(
                    source,
                    0.0,
                    f"开始移动: {source_path.name}",
                )

            if dest_path.exists():
                dest_path.unlink()

            await asyncio.to_thread(shutil.move, str(source_path), str(dest_path))

            if self.progress_callback:
                await self.progress_callback(
                    source,
                    1.0,
                    f"移动完成: {source_path.name}",
                )

            return MoveResult(
                success=True,
                source=source,
                destination=destination,
            )

        except Exception as e:
            return MoveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"移动失败: {str(e)}",
            )

    async def move_directory(
        self,
        source: str,
        destination: str,
        overwrite: bool = False,
    ) -> MoveResult:
        source_path = Path(source)
        dest_path = Path(destination)

        if not source_path.exists():
            return MoveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"源目录不存在: {source}",
            )

        if not source_path.is_dir():
            return MoveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"源路径不是目录: {source}",
            )

        if dest_path.exists() and not overwrite:
            return MoveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"目标目录已存在: {destination}",
            )

        try:
            if self.progress_callback:
                await self.progress_callback(
                    source,
                    0.0,
                    f"开始移动目录: {source_path.name}",
                )

            if dest_path.exists():
                await asyncio.to_thread(shutil.rmtree, dest_path)

            await asyncio.to_thread(shutil.move, str(source_path), str(dest_path))

            if self.progress_callback:
                await self.progress_callback(
                    source,
                    1.0,
                    f"目录移动完成: {source_path.name}",
                )

            return MoveResult(
                success=True,
                source=source,
                destination=destination,
            )

        except Exception as e:
            return MoveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"目录移动失败: {str(e)}",
            )

    async def move(
        self,
        source: str,
        destination: str,
        overwrite: bool = False,
    ) -> MoveResult:
        source_path = Path(source)

        if source_path.is_file():
            return await self.move_file(source, destination, overwrite)
        elif source_path.is_dir():
            return await self.move_directory(source, destination, overwrite)
        else:
            return MoveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"源路径不存在: {source}",
            )

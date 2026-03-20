import asyncio
import shutil
from pathlib import Path
from typing import Optional, Callable, Awaitable
from pydantic import BaseModel, Field
from datetime import datetime


class MoveResult(BaseModel):
    success: bool = Field(default=True)
    source: str = ""
    destination: str = ""
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class FileMoveExecutor:
    def __init__(
        self,
        progress_callback: Optional[Callable[[str, float, str], Awaitable[None]]] = None,
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
                error=f"æºæä»¶ä¸å­å¨: {source}",
            )

        if not source_path.is_file():
            return MoveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"æºè·¯å¾ä¸æ¯æä»? {source}",
            )

        if dest_path.exists() and not overwrite:
            return MoveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"ç®æ æä»¶å·²å­å? {destination}",
            )

        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            if self.progress_callback:
                await self.progress_callback(
                    source,
                    0.0,
                    f"å¼å§ç§»å? {source_path.name}",
                )

            if dest_path.exists():
                dest_path.unlink()

            await asyncio.to_thread(shutil.move, str(source_path), str(dest_path))

            if self.progress_callback:
                await self.progress_callback(
                    source,
                    1.0,
                    f"ç§»å¨å®æ: {source_path.name}",
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
                error=f"ç§»å¨å¤±è´¥: {str(e)}",
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
                error=f"æºç®å½ä¸å­å¨: {source}",
            )

        if not source_path.is_dir():
            return MoveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"æºè·¯å¾ä¸æ¯ç®å½? {source}",
            )

        if dest_path.exists() and not overwrite:
            return MoveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"ç®æ ç®å½å·²å­å? {destination}",
            )

        try:
            if self.progress_callback:
                await self.progress_callback(
                    source,
                    0.0,
                    f"å¼å§ç§»å¨ç®å½? {source_path.name}",
                )

            if dest_path.exists():
                await asyncio.to_thread(shutil.rmtree, dest_path)

            await asyncio.to_thread(shutil.move, str(source_path), str(dest_path))

            if self.progress_callback:
                await self.progress_callback(
                    source,
                    1.0,
                    f"ç®å½ç§»å¨å®æ: {source_path.name}",
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
                error=f"ç®å½ç§»å¨å¤±è´¥: {str(e)}",
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
                error=f"æºè·¯å¾ä¸å­å¨: {source}",
            )

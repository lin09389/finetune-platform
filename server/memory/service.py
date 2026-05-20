"""Public facade for the long-term memory subsystem."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .memory_extractor import MemoryExtractor
from .memory_service import MemoryService, get_memory_service, reset_memory_service
from .models import MEMORY_IMPORTANCE, MEMORY_TYPE_LABELS, Memory, MemoryType

logger = logging.getLogger(__name__)


async def extract_and_store_memory(
    message: str,
    role: str,
    user_id: str = "default",
) -> dict[str, Any]:
    """Extract and store long-term memories from one message."""
    try:
        service = get_memory_service()
        stored = await asyncio.to_thread(
            service.extract_and_store,
            message=message,
            role=role,
            user_id=user_id,
        )
        return {"extracted": len(stored), "memories": stored}
    except Exception as exc:
        logger.warning("记忆提取失败: %s", exc)
        return {"extracted": 0, "error": str(exc)}


__all__ = [
    "MEMORY_IMPORTANCE",
    "MEMORY_TYPE_LABELS",
    "Memory",
    "MemoryExtractor",
    "MemoryService",
    "MemoryType",
    "extract_and_store_memory",
    "get_memory_service",
    "reset_memory_service",
]

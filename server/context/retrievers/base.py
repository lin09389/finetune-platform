"""Base retriever contracts for the Context Engine."""
from __future__ import annotations

from dataclasses import dataclass, field

from context.budget import ContextBuildOptions
from context.pack import ContextSource


@dataclass
class RetrievalResult:
    sources: list[ContextSource] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duration: float = 0.0


class BaseContextRetriever:
    kind = "base"

    async def retrieve(
        self,
        query: str,
        user_id: str,
        session_id: str | None,
        options: ContextBuildOptions,
    ) -> RetrievalResult:
        raise NotImplementedError

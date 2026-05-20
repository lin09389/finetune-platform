"""Token budget helpers for the Context Engine."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from context.pack import ContextBudget, ContextSource


_EN_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def estimate_tokens(text: str) -> int:
    """Estimate tokens without adding tokenizer dependencies."""
    if not text:
        return 0

    english_words = _EN_WORD_RE.findall(text)
    english_chars = sum(len(word) for word in english_words)
    chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    other_chars = max(0, len(text) - english_chars - chinese_chars)

    estimated = chinese_chars * 2 + len(english_words) * 1.3 + other_chars * 0.5
    return max(1, int(round(estimated)))


@dataclass
class ContextBuildOptions:
    """Options for building a ContextPack."""

    use_memory: bool = True
    use_knowledge: bool = False
    use_project_context: bool = False

    max_context_tokens: int = 4000
    reserved_output_tokens: int = 1024
    max_total_sources: int = 10

    memory_top_k: int = 3
    memory_include_types: list[str] | None = None

    knowledge_collection_id: str | None = None
    knowledge_top_k: int = 5
    knowledge_auto_retrieve: bool = True

    project_path: str | None = None
    project_max_tokens: int = 1500

    metadata: dict[str, object] = field(default_factory=dict)


class TokenBudget:
    """Select sources that fit into a context budget."""

    def __init__(self, max_tokens: int, reserved_tokens: int = 0):
        self.budget = ContextBudget(
            max_tokens=max(0, int(max_tokens)),
            reserved_tokens=max(0, int(reserved_tokens)),
        )

    def select(self, sources: list[ContextSource]) -> tuple[list[ContextSource], ContextBudget]:
        selected: list[ContextSource] = []
        for source in sources:
            if source.tokens <= 0:
                source.tokens = estimate_tokens(source.content)

            if self.budget.used_tokens + source.tokens <= self.budget.max_tokens:
                selected.append(source)
                self.budget.used_tokens += source.tokens
                continue

            self.budget.dropped_sources.append(source.id)
            self.budget.dropped_tokens += source.tokens

        return selected, self.budget

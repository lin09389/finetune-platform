"""Context Engine data contracts."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextTiming:
    """Timing information for one retriever or build phase."""

    name: str
    duration: float = 0.0


@dataclass
class ContextSource:
    """Raw context source returned by a retriever."""

    id: str
    kind: str
    content: str
    score: float = 0.0
    tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def importance(self) -> float:
        return float(self.metadata.get("importance", 0.5) or 0.5)

    @property
    def source(self) -> str:
        return str(self.metadata.get("source") or self.metadata.get("title") or self.kind)

    @property
    def source_type(self) -> str:
        return str(self.metadata.get("source_type") or self.kind)

    @property
    def memory_type(self) -> str | None:
        value = self.metadata.get("memory_type") or self.metadata.get("type")
        return str(value) if value is not None else None

    @property
    def relevance(self) -> float:
        return self.score

    @property
    def path(self) -> str | None:
        value = self.metadata.get("path")
        return str(value) if value is not None else None


@dataclass
class ContextSection:
    """Formatted context section that is safe to inject into prompts."""

    kind: str
    title: str
    text: str
    tokens: int = 0
    source_ids: list[str] = field(default_factory=list)


@dataclass
class ContextBudget:
    """Token budget accounting for a context build."""

    max_tokens: int
    reserved_tokens: int = 0
    used_tokens: int = 0
    dropped_tokens: int = 0
    dropped_sources: list[str] = field(default_factory=list)

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.max_tokens - self.used_tokens)


@dataclass
class ContextBuildResult:
    """Retriever result used internally by the builder."""

    sources: list[ContextSource] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)


@dataclass
class ContextDecision:
    """Why a source was selected, dropped, or kept with caveats."""

    source_id: str
    kind: str
    selected: bool
    reason: str
    score: float = 0.0
    importance: float = 0.0
    tokens: int = 0
    rank: int | None = None
    dropped_reason: str | None = None
    conflict_ids: list[str] = field(default_factory=list)


@dataclass
class ContextConflict:
    """Conflict or duplication detected between context sources."""

    id: str
    source_ids: list[str]
    conflict_type: str
    description: str
    resolution: str


@dataclass
class PromptArtifact:
    """The exact prompt artifact produced from a ContextPack."""

    system_prompt: str
    context_text: str
    prompt_hash: str
    token_count: int
    section_ids: list[str] = field(default_factory=list)


@dataclass
class ContextTrace:
    """Audit trail for a context build."""

    decisions: list[ContextDecision] = field(default_factory=list)
    conflicts: list[ContextConflict] = field(default_factory=list)
    prompt_artifact: PromptArtifact | None = None


@dataclass
class ContextPack:
    """Final context package consumed by chat, inference, and future orchestration."""

    query: str = ""
    user_id: str = "default"
    session_id: str = "default"
    sources: list[ContextSource] = field(default_factory=list)
    sections: list[ContextSection] = field(default_factory=list)
    context_text: str = ""
    budget: ContextBudget = field(default_factory=lambda: ContextBudget(max_tokens=0))
    timings: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    trace: ContextTrace = field(default_factory=ContextTrace)
    retrieval_time: float = 0.0

    def build_system_prompt(self, base_prompt: str = "") -> str:
        """Build a system prompt from the formatted sections."""
        return self.build_prompt_artifact(base_prompt).system_prompt

    def build_prompt_artifact(self, base_prompt: str = "") -> PromptArtifact:
        """Build and store the exact prompt artifact injected into the model."""
        parts: list[str] = []
        if base_prompt:
            parts.append(base_prompt)

        if self.sections:
            rendered = "\n\n".join(f"【{section.title}】\n{section.text}" for section in self.sections)
            parts.append(f"\n\n{rendered}")
            parts.append("\n\n请根据以上上下文信息回答用户问题。如果引用具体内容，请标注来源。")

        system_prompt = "\n".join(parts)
        prompt_hash = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
        token_count = sum(section.tokens for section in self.sections)
        artifact = PromptArtifact(
            system_prompt=system_prompt,
            context_text=self.context_text,
            prompt_hash=prompt_hash,
            token_count=token_count,
            section_ids=[section.kind for section in self.sections],
        )
        self.trace.prompt_artifact = artifact
        return artifact

    @property
    def memory_sources(self) -> list[ContextSource]:
        return [source for source in self.sources if source.kind == "memory"]

    @property
    def knowledge_sources(self) -> list[ContextSource]:
        return [source for source in self.sources if source.kind == "knowledge"]

    @property
    def project_contexts(self) -> list[ContextSource]:
        return [source for source in self.sources if source.kind == "project"]

    @property
    def total_sources(self) -> int:
        return len(self.sources)

    @property
    def memory_count(self) -> int:
        return len(self.memory_sources)

    @property
    def knowledge_count(self) -> int:
        return len(self.knowledge_sources)

    @property
    def project_count(self) -> int:
        return len(self.project_contexts)

    @property
    def memory_retrieval_time(self) -> float:
        return float(self.timings.get("memory", 0.0))

    @property
    def knowledge_retrieval_time(self) -> float:
        return float(self.timings.get("knowledge", 0.0))

    @property
    def project_retrieval_time(self) -> float:
        return float(self.timings.get("project", 0.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": [
                {
                    "id": source.id,
                    "kind": source.kind,
                    "content_preview": source.content[:100] + "..." if len(source.content) > 100 else source.content,
                    "score": source.score,
                    "tokens": source.tokens,
                    "metadata": source.metadata,
                }
                for source in self.sources
            ],
            "sections": [
                {
                    "kind": section.kind,
                    "title": section.title,
                    "tokens": section.tokens,
                    "source_ids": section.source_ids,
                }
                for section in self.sections
            ],
            "budget": {
                "max_tokens": self.budget.max_tokens,
                "reserved_tokens": self.budget.reserved_tokens,
                "used_tokens": self.budget.used_tokens,
                "dropped_tokens": self.budget.dropped_tokens,
                "dropped_sources": self.budget.dropped_sources,
            },
            "warnings": self.warnings,
            "timings": self.timings,
            "trace": {
                "decisions": [
                    {
                        "source_id": decision.source_id,
                        "kind": decision.kind,
                        "selected": decision.selected,
                        "reason": decision.reason,
                        "score": decision.score,
                        "importance": decision.importance,
                        "tokens": decision.tokens,
                        "rank": decision.rank,
                        "dropped_reason": decision.dropped_reason,
                        "conflict_ids": decision.conflict_ids,
                    }
                    for decision in self.trace.decisions
                ],
                "conflicts": [
                    {
                        "id": conflict.id,
                        "source_ids": conflict.source_ids,
                        "conflict_type": conflict.conflict_type,
                        "description": conflict.description,
                        "resolution": conflict.resolution,
                    }
                    for conflict in self.trace.conflicts
                ],
                "prompt_artifact": {
                    "system_prompt": self.trace.prompt_artifact.system_prompt,
                    "prompt_hash": self.trace.prompt_artifact.prompt_hash,
                    "token_count": self.trace.prompt_artifact.token_count,
                    "context_text": self.trace.prompt_artifact.context_text,
                    "section_ids": self.trace.prompt_artifact.section_ids,
                }
                if self.trace.prompt_artifact
                else None,
            },
            "retrieval_time": self.retrieval_time,
            "total_sources": self.total_sources,
            "memory_count": self.memory_count,
            "knowledge_count": self.knowledge_count,
            "project_count": self.project_count,
        }

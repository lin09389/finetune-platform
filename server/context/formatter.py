"""Prompt formatter for ContextPack."""
from __future__ import annotations

from collections import defaultdict

from context.budget import estimate_tokens
from context.pack import ContextSection, ContextSource


class ContextFormatter:
    """Build prompt sections from selected context sources."""

    TITLES = {
        "memory": "用户记忆",
        "knowledge": "参考资料",
        "project": "项目上下文",
    }

    ORDER = ("memory", "knowledge", "project")

    def build_sections(self, sources: list[ContextSource]) -> list[ContextSection]:
        grouped: dict[str, list[ContextSource]] = defaultdict(list)
        for source in sources:
            grouped[source.kind].append(source)

        sections: list[ContextSection] = []
        for kind in self.ORDER:
            items = grouped.get(kind, [])
            if not items:
                continue
            text = self._format_group(kind, items)
            sections.append(
                ContextSection(
                    kind=kind,
                    title=self.TITLES.get(kind, kind),
                    text=text,
                    tokens=estimate_tokens(text),
                    source_ids=[source.id for source in items],
                )
            )
        return sections

    def build_context_text(self, sections: list[ContextSection]) -> str:
        return "\n\n".join(f"[{section.title}] {section.text}" for section in sections)

    def _format_group(self, kind: str, sources: list[ContextSource]) -> str:
        if kind == "memory":
            lines = []
            for index, source in enumerate(sources, 1):
                preview = self._preview(source.content, 220)
                path = source.metadata.get("memory_path") or source.path
                prefix = f"{path}: " if path else f"[{source.source_type}] "
                lines.append(f"{index}. {prefix}{preview}")
            return "\n".join(lines)

        if kind == "knowledge":
            blocks = []
            for index, source in enumerate(sources, 1):
                preview = self._preview(source.content, 360)
                blocks.append(f"[参考资料 {index}]\n来源: {source.source}\n内容: {preview}")
            return "\n\n".join(blocks)

        if kind == "project":
            lines = []
            for source in sources:
                preview = self._preview(source.content, 280)
                if source.path:
                    lines.append(f"- {source.path}: {preview}")
                else:
                    lines.append(f"- {preview}")
            return "\n".join(lines)

        return "\n\n".join(source.content for source in sources)

    @staticmethod
    def _preview(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "..."

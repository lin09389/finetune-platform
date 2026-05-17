from __future__ import annotations

from html.parser import HTMLParser


class LocalPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._title_active = False
        self._heading_tag: str | None = None
        self.title = ""
        self.headings: list[dict[str, str]] = []
        self.links: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == "title":
            self._title_active = True
        if lowered in {"h1", "h2", "h3"}:
            self._heading_tag = lowered
        if lowered == "a":
            href = dict(attrs).get("href")
            if href and len(self.links) < 12:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "title":
            self._title_active = False
        if lowered == self._heading_tag:
            self._heading_tag = None

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._title_active and not self.title:
            self.title = text[:200]
        if self._heading_tag and len(self.headings) < 8:
            self.headings.append({"tag": self._heading_tag, "text": text[:200]})
        if len(" ".join(self.text_parts)) < 4000:
            self.text_parts.append(text[:400])

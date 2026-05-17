from __future__ import annotations

import pytest

from agent_session.page_parser import LocalPageParser


def test_parses_title():
    p = LocalPageParser()
    p.feed("<html><head><title>My App</title></head><body></body></html>")
    assert p.title == "My App"


def test_parses_headings():
    p = LocalPageParser()
    p.feed("<h1>Top</h1><h2>Middle</h2><h3>Deep</h3>")
    assert p.headings == [
        {"tag": "h1", "text": "Top"},
        {"tag": "h2", "text": "Middle"},
        {"tag": "h3", "text": "Deep"},
    ]


def test_parses_links():
    p = LocalPageParser()
    p.feed('<a href="/about">About</a><a href="/contact">Contact</a>')
    assert p.links == ["/about", "/contact"]


def test_accumulates_text_parts():
    p = LocalPageParser()
    p.feed("<p>Hello</p><p>World</p>")
    joined = " ".join(p.text_parts)
    assert "Hello" in joined
    assert "World" in joined


def test_caps_links_at_12():
    p = LocalPageParser()
    html = "".join(f'<a href="/p{i}">link</a>' for i in range(20))
    p.feed(html)
    assert len(p.links) == 12


def test_caps_headings_at_8():
    p = LocalPageParser()
    html = "".join(f"<h1>H{i}</h1>" for i in range(15))
    p.feed(html)
    assert len(p.headings) == 8


def test_empty_feed_gives_defaults():
    p = LocalPageParser()
    assert p.title == ""
    assert p.headings == []
    assert p.links == []
    assert p.text_parts == []


def test_only_first_title_is_kept():
    p = LocalPageParser()
    p.feed("<title>First</title><title>Second</title>")
    assert p.title == "First"


def test_title_truncated_at_200():
    p = LocalPageParser()
    long_title = "A" * 300
    p.feed(f"<title>{long_title}</title>")
    assert len(p.title) == 200

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agent_session.browser_tools import BrowserToolsMixin
from agent_session.http_tools import HttpToolsMixin


class _Host(HttpToolsMixin, BrowserToolsMixin):
    """Concrete host: HttpToolsMixin supplies _validate_local_url."""

    def _root(self, context: dict) -> Path:
        return Path(context["project_path"])


def _ctx(path: Path) -> dict:
    return {"project_path": str(path)}


# ── guard clauses ─────────────────────────────────────────────────────────

def test_browser_validate_page_missing_url(tmp_path):
    r = _Host()._browser_validate_page({}, _ctx(tmp_path))
    assert r.status == "failed"
    assert r.error == "url is required"


def test_capture_network_errors_missing_url(tmp_path):
    r = _Host()._capture_network_errors({}, _ctx(tmp_path))
    assert r.status == "failed"
    assert r.error == "url is required"


def test_browser_click_missing_both(tmp_path):
    r = _Host()._browser_click({}, _ctx(tmp_path))
    assert r.status == "failed"


def test_browser_click_missing_selector(tmp_path):
    r = _Host()._browser_click({"url": "http://localhost:3000"}, _ctx(tmp_path))
    assert r.status == "failed"


def test_browser_fill_missing_selector(tmp_path):
    r = _Host()._browser_fill({"url": "http://localhost:3000"}, _ctx(tmp_path))
    assert r.status == "failed"


def test_browser_wait_for_missing_url(tmp_path):
    r = _Host()._browser_wait_for({}, _ctx(tmp_path))
    assert r.status == "failed"
    assert r.error == "url is required"


def test_browser_wait_for_missing_condition(tmp_path):
    r = _Host()._browser_wait_for({"url": "http://localhost:3000"}, _ctx(tmp_path))
    assert r.status == "failed"
    assert r.error == "wait_for or required_text is required"


def test_browser_validate_page_external_url_blocked(tmp_path):
    r = _Host()._browser_validate_page({"url": "http://example.com/"}, _ctx(tmp_path))
    assert r.status == "blocked"


# ── no-node graceful degradation ──────────────────────────────────────────

def test_run_browser_validation_no_node(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    payload = _Host()._run_browser_validation(
        url="http://localhost:3000",
        selectors=[],
        required_text=[],
        timeout_seconds=5,
        root=tmp_path,
    )
    assert payload["ok"] is False
    assert "node" in payload["error"]
    assert payload["engine"] == "playwright"


def test_run_browser_action_no_node(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    payload = _Host()._run_browser_action(
        root=tmp_path,
        action="click",
        url="http://localhost:3000",
        selector=".btn",
        value="",
        wait_for="",
        required_text=[],
        timeout_seconds=5,
    )
    assert payload["ok"] is False
    assert "node" in payload["error"]
    assert payload["action"] == "click"


def test_run_network_capture_no_node(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    payload = _Host()._run_network_capture(
        root=tmp_path,
        url="http://localhost:3000",
        timeout_seconds=5,
    )
    assert payload["ok"] is False
    assert "node" in payload["error"]
    assert payload["request_failures"] == []


# ── payload defaults are always set ──────────────────────────────────────

def test_run_browser_validation_no_node_sets_all_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    payload = _Host()._run_browser_validation(
        url="http://localhost:3000",
        selectors=[],
        required_text=[],
        timeout_seconds=5,
        root=tmp_path,
    )
    for key in ("url", "final_url", "ok", "status_code", "title", "headings",
                "console_errors", "page_errors", "selector_results", "text_results",
                "body_excerpt", "engine"):
        assert key in payload, f"missing key: {key}"

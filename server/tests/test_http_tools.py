from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from agent_session.http_tools import LOCAL_HTTP_HOSTS, HttpToolsMixin


class _Host(HttpToolsMixin):
    """Minimal concrete host — HttpToolsMixin needs no ToolBaseMixin."""


class _SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/json":
            body = json.dumps({"key": "value"}).encode()
            ct = "application/json"
        elif self.path == "/notfound":
            self.send_response(404)
            self.end_headers()
            return
        else:
            body = b"<html><head><title>Test Page</title></head><body>Hello Agent</body></html>"
            ct = "text/html"
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@pytest.fixture(scope="module")
def server_url():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _SimpleHandler)
    port = srv.server_address[1]
    Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


# ── LOCAL_HTTP_HOSTS constant ──────────────────────────────────────────────

def test_local_http_hosts_contains_loopback():
    assert "localhost" in LOCAL_HTTP_HOSTS
    assert "127.0.0.1" in LOCAL_HTTP_HOSTS


# ── _validate_local_url ────────────────────────────────────────────────────

def test_validate_accepts_localhost():
    h = _Host()
    assert h._validate_local_url("http://localhost:8080/path") == "http://localhost:8080/path"


def test_validate_accepts_127():
    h = _Host()
    assert h._validate_local_url("http://127.0.0.1:9000/") == "http://127.0.0.1:9000/"


def test_validate_rejects_external_host():
    h = _Host()
    with pytest.raises(ValueError, match="only localhost"):
        h._validate_local_url("http://example.com/api")


def test_validate_rejects_non_http_scheme():
    h = _Host()
    with pytest.raises(ValueError, match="only http/https"):
        h._validate_local_url("ftp://localhost/file")


# ── _extract_html_title ────────────────────────────────────────────────────

def test_extract_title_present():
    h = _Host()
    assert h._extract_html_title("<html><head><title>Hello</title></head></html>") == "Hello"


def test_extract_title_absent():
    h = _Host()
    assert h._extract_html_title("<html><body>no title</body></html>") == ""


def test_extract_title_multiline():
    h = _Host()
    assert h._extract_html_title("<title>\n  Spaced  \n</title>") == "Spaced"


# ── guard clauses (no server needed) ──────────────────────────────────────

def test_http_probe_empty_url():
    h = _Host()
    r = h._http_probe({}, {})
    assert r.status == "failed"
    assert r.error == "url is required"


def test_probe_json_endpoint_empty_url():
    h = _Host()
    r = h._probe_json_endpoint({}, {})
    assert r.status == "failed"
    assert r.error == "url is required"


def test_read_local_page_empty_url():
    h = _Host()
    r = h._read_local_page({}, {})
    assert r.status == "failed"
    assert r.error == "url is required"


def test_http_probe_external_url_blocked():
    h = _Host()
    r = h._http_probe({"url": "http://example.com/"}, {})
    assert r.status == "blocked"


# ── live server tests ─────────────────────────────────────────────────────

def test_http_probe_live_success(server_url):
    h = _Host()
    r = h._http_probe({"url": server_url}, {})
    assert r.status == "completed"
    assert r.payload["status_code"] == 200
    assert r.payload["ok"] is True
    assert r.payload["title"] == "Test Page"


def test_http_probe_live_404(server_url):
    h = _Host()
    r = h._http_probe({"url": f"{server_url}/notfound"}, {})
    assert r.status == "failed"
    assert r.payload["status_code"] == 404


def test_probe_json_endpoint_live(server_url):
    h = _Host()
    r = h._probe_json_endpoint({"url": f"{server_url}/json"}, {})
    assert r.status == "completed"
    assert r.payload["ok"] is True
    assert r.payload["json_preview"] == {"key": "value"}


def test_read_local_page_live(server_url):
    h = _Host()
    r = h._read_local_page({"url": server_url}, {})
    assert r.status == "completed"
    assert r.payload["title"] == "Test Page"
    assert "Hello Agent" in r.payload["text_excerpt"]

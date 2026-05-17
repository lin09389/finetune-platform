from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .page_parser import LocalPageParser
from .tool_types import ToolResult


LOCAL_HTTP_HOSTS = {"localhost", "127.0.0.1", "::1"}


class HttpToolsMixin:
    def _http_probe(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("server_url") or "").strip()
        if not url:
            return ToolResult("failed", "缺少页面地址", {}, "url is required")
        timeout_seconds = int(args.get("timeout_seconds") or 10)
        method = str(args.get("method") or "GET").strip().upper()
        try:
            response = self._fetch_local_url(url, timeout_seconds=timeout_seconds, method=method)
        except ValueError as exc:
            return ToolResult("blocked", "页面探测被阻断", {"url": url}, str(exc))
        status = "completed" if response["ok"] else "failed"
        summary = f"页面探测成功：{response['status_code']}" if response["ok"] else f"页面探测失败：{response['status_code']}"
        return ToolResult(
            status,
            summary,
            {
                "url": response["url"],
                "final_url": response["final_url"],
                "method": method,
                "status_code": response["status_code"],
                "ok": response["ok"],
                "content_type": response["content_type"],
                "title": self._extract_html_title(response["body"]),
                "body_excerpt": response["body"][:1200],
            },
            None if response["ok"] else f"unexpected status: {response['status_code']}",
        )

    def _probe_json_endpoint(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("server_url") or "").strip()
        if not url:
            return ToolResult("failed", "缺少接口地址", {}, "url is required")
        timeout_seconds = int(args.get("timeout_seconds") or 10)
        method = str(args.get("method") or "GET").strip().upper()
        try:
            response = self._fetch_local_url(url, timeout_seconds=timeout_seconds, method=method)
        except ValueError as exc:
            return ToolResult("blocked", "接口探测被阻断", {"url": url}, str(exc))
        try:
            parsed = json.loads(response["body"] or "null")
            parse_error = None
        except json.JSONDecodeError as exc:
            parsed = None
            parse_error = str(exc)
        ok = bool(response["ok"] and parse_error is None and isinstance(parsed, (dict, list)))
        preview = parsed if isinstance(parsed, dict) else parsed[:5] if isinstance(parsed, list) else None
        return ToolResult(
            "completed" if ok else "failed",
            "JSON 接口探测成功" if ok else f"JSON 接口探测失败：{response['status_code']}",
            {
                "url": response["url"],
                "final_url": response["final_url"],
                "method": method,
                "status_code": response["status_code"],
                "ok": ok,
                "content_type": response["content_type"],
                "json_type": type(parsed).__name__ if parsed is not None else "",
                "json_preview": preview,
                "body_excerpt": response["body"][:1200],
                "parse_error": parse_error,
            },
            None if ok else (parse_error or f"unexpected status: {response['status_code']}"),
        )

    def _read_local_page(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("server_url") or "").strip()
        if not url:
            return ToolResult("failed", "缺少页面地址", {}, "url is required")
        timeout_seconds = int(args.get("timeout_seconds") or 10)
        try:
            response = self._fetch_local_url(url, timeout_seconds=timeout_seconds, method="GET")
        except ValueError as exc:
            return ToolResult("blocked", "页面读取被阻断", {"url": url}, str(exc))
        parser = LocalPageParser()
        parser.feed(response["body"])
        text_excerpt = " ".join(parser.text_parts)[:1600]
        return ToolResult(
            "completed" if response["ok"] else "failed",
            "页面摘要读取完成" if response["ok"] else f"页面读取失败：{response['status_code']}",
            {
                "url": response["url"],
                "final_url": response["final_url"],
                "status_code": response["status_code"],
                "ok": response["ok"],
                "content_type": response["content_type"],
                "title": parser.title,
                "headings": parser.headings,
                "links": parser.links,
                "text_excerpt": text_excerpt,
            },
            None if response["ok"] else f"unexpected status: {response['status_code']}",
        )

    def _validate_local_url(self, raw_url: str) -> str:
        parsed = urlparse(raw_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("only http/https local URLs are allowed")
        if (parsed.hostname or "").lower() not in LOCAL_HTTP_HOSTS:
            raise ValueError("only localhost URLs are allowed")
        return raw_url

    def _fetch_local_url(self, raw_url: str, *, timeout_seconds: int, method: str) -> dict[str, Any]:
        url = self._validate_local_url(raw_url)
        request = Request(url, method=method, headers={"User-Agent": "finetune-platform-agent/1.0"})
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="ignore")
                status_code = int(getattr(response, "status", 200))
                final_url = str(response.geturl())
                content_type = str(response.headers.get("content-type") or "")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            status_code = int(exc.code)
            final_url = str(exc.geturl() or url)
            content_type = str(exc.headers.get("content-type") or "")
        except URLError as exc:
            return {
                "url": url,
                "final_url": url,
                "status_code": 0,
                "ok": False,
                "content_type": "",
                "body": str(exc.reason),
            }
        return {
            "url": url,
            "final_url": final_url,
            "status_code": status_code,
            "ok": 200 <= status_code < 400,
            "content_type": content_type,
            "body": body,
        }

    def _extract_html_title(self, body: str) -> str:
        match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        return " ".join(match.group(1).split())[:200]

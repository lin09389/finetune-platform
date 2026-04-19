#!/usr/bin/env python
"""Verify the Docker preview release surface.

The script intentionally uses only the Python standard library so it can run
from a fresh checkout after Docker starts the stack.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def request_json(url: str, timeout: float) -> tuple[bool, Any, str]:
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if not body:
                return True, None, f"HTTP {resp.status}"
            return True, json.loads(body), f"HTTP {resp.status}"
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        return False, None, f"HTTP {exc.code}: {body}"
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, None, str(exc)


def request_text(url: str, timeout: float) -> tuple[bool, str]:
    try:
        req = Request(url, headers={"Accept": "text/html,*/*"})
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read(300).decode("utf-8", errors="replace")
            return 200 <= resp.status < 500, f"HTTP {resp.status}, body={body[:80]!r}"
    except HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (URLError, TimeoutError) as exc:
        return False, str(exc)


def wait_for_backend(base_url: str, timeout: float, interval: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        ok, _payload, _detail = request_json(f"{base_url}/health", timeout=3)
        if ok:
            return True
        time.sleep(interval)
    return False


def check_endpoint(name: str, url: str, timeout: float) -> CheckResult:
    ok, payload, detail = request_json(url, timeout)
    if ok and isinstance(payload, dict):
        status_hint = payload.get("status") or payload.get("service_status") or payload.get("schema_version")
        if status_hint:
            detail = f"{detail}, {status_hint}"
    return CheckResult(name=name, ok=ok, detail=detail)


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 Finetune Platform Docker 体验版")
    parser.add_argument("--frontend-url", default="http://localhost:5173", help="前端地址")
    parser.add_argument("--api-url", default="http://localhost:8000", help="后端 API 地址")
    parser.add_argument("--wait", type=float, default=90, help="等待后端启动的最长秒数")
    parser.add_argument("--timeout", type=float, default=8, help="单个请求超时秒数")
    args = parser.parse_args()

    print("========================================")
    print(" Finetune Platform Docker 体验版验证")
    print("========================================")
    print(f"前端: {args.frontend_url}")
    print(f"后端: {args.api_url}")
    print()

    backend_ready = wait_for_backend(args.api_url, args.wait, interval=3)
    if not backend_ready:
        print(f"[FAIL] 后端未在 {args.wait:.0f}s 内就绪: {args.api_url}/health")
        return 1

    results: list[CheckResult] = []

    frontend_ok, frontend_detail = request_text(args.frontend_url, args.timeout)
    results.append(CheckResult("前端页面", frontend_ok, frontend_detail))

    api_checks = [
        ("后端健康检查", "/health"),
        ("运行时聚合状态", "/runtime/bootstrap"),
        ("模型列表", "/models"),
        ("数据集列表", "/datasets"),
        ("训练状态", "/training/status"),
        ("推理后端状态", "/inference/backends"),
        ("聊天会话", "/chat/sessions"),
        ("知识库集合", "/knowledge/collections"),
        ("知识库嵌入器状态", "/knowledge/embedder/status"),
    ]

    for name, path in api_checks:
        results.append(check_endpoint(name, f"{args.api_url}{path}", args.timeout))

    print("检查结果:")
    for result in results:
        prefix = "[ OK ]" if result.ok else "[FAIL]"
        print(f"{prefix} {result.name}: {result.detail}")

    failed = [result for result in results if not result.ok]
    print()
    if failed:
        print(f"验证失败: {len(failed)} 项未通过。请先查看 `docker compose logs -f api frontend`。")
        return 1

    print("验证通过: Docker 体验版核心入口和 GA API 状态可访问。")
    print("提示: GPU、Ollama、Embedding 模型缺失时，页面应显示明确的降级状态，这不等同于验证失败。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

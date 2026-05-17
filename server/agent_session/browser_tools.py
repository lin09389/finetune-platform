from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .tool_types import ToolResult


class BrowserToolsMixin:
    def _browser_validate_page(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("server_url") or "").strip()
        if not url:
            return ToolResult("failed", "缺少页面地址", {}, "url is required")
        selectors = [str(item).strip() for item in (args.get("selectors") or []) if str(item).strip()][:8]
        required_text = [str(item).strip() for item in (args.get("required_text") or []) if str(item).strip()][:8]
        timeout_seconds = int(args.get("timeout_seconds") or 15)
        try:
            payload = self._run_browser_validation(
                url=url,
                selectors=selectors,
                required_text=required_text,
                timeout_seconds=timeout_seconds,
                root=self._root(context),
            )
        except ValueError as exc:
            return ToolResult("blocked", "浏览器验证被阻断", {"url": url}, str(exc))
        ok = bool(payload.get("ok"))
        return ToolResult(
            "completed" if ok else "failed",
            "浏览器验证通过" if ok else "浏览器验证失败",
            payload,
            None if ok else str(payload.get("error") or "browser validation failed"),
        )

    def _capture_network_errors(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("server_url") or "").strip()
        if not url:
            return ToolResult("failed", "缺少页面地址", {}, "url is required")
        timeout_seconds = int(args.get("timeout_seconds") or 15)
        try:
            payload = self._run_network_capture(
                root=self._root(context),
                url=url,
                timeout_seconds=timeout_seconds,
            )
        except ValueError as exc:
            return ToolResult("blocked", "网络错误捕获被阻断", {"url": url}, str(exc))
        ok = bool(payload.get("ok"))
        return ToolResult(
            "completed" if ok else "failed",
            "网络请求检查通过" if ok else "检测到网络错误",
            payload,
            None if ok else str(payload.get("error") or "network errors detected"),
        )

    def _browser_click(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("server_url") or "").strip()
        selector = str(args.get("selector") or "").strip()
        if not url or not selector:
            return ToolResult("failed", "缺少页面地址或选择器", {}, "url and selector are required")
        timeout_seconds = int(args.get("timeout_seconds") or 15)
        try:
            payload = self._run_browser_action(
                root=self._root(context),
                action="click",
                url=url,
                selector=selector,
                value="",
                wait_for=str(args.get("wait_for") or "").strip(),
                required_text=[str(item).strip() for item in (args.get("required_text") or []) if str(item).strip()][:8],
                timeout_seconds=timeout_seconds,
            )
        except ValueError as exc:
            return ToolResult("blocked", "浏览器点击被阻断", {"url": url, "selector": selector}, str(exc))
        return ToolResult("completed" if payload.get("ok") else "failed", "浏览器点击完成" if payload.get("ok") else "浏览器点击失败", payload, None if payload.get("ok") else str(payload.get("error") or "browser click failed"))

    def _browser_fill(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("server_url") or "").strip()
        selector = str(args.get("selector") or "").strip()
        value = str(args.get("value") or "").strip()
        if not url or not selector:
            return ToolResult("failed", "缺少页面地址或选择器", {}, "url and selector are required")
        timeout_seconds = int(args.get("timeout_seconds") or 15)
        try:
            payload = self._run_browser_action(
                root=self._root(context),
                action="fill",
                url=url,
                selector=selector,
                value=value,
                wait_for=str(args.get("wait_for") or "").strip(),
                required_text=[str(item).strip() for item in (args.get("required_text") or []) if str(item).strip()][:8],
                timeout_seconds=timeout_seconds,
            )
        except ValueError as exc:
            return ToolResult("blocked", "浏览器填写被阻断", {"url": url, "selector": selector}, str(exc))
        return ToolResult("completed" if payload.get("ok") else "failed", "浏览器填写完成" if payload.get("ok") else "浏览器填写失败", payload, None if payload.get("ok") else str(payload.get("error") or "browser fill failed"))

    def _browser_wait_for(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or args.get("server_url") or "").strip()
        wait_for = str(args.get("wait_for") or args.get("selector") or "").strip()
        required_text = [str(item).strip() for item in (args.get("required_text") or []) if str(item).strip()][:8]
        if not url:
            return ToolResult("failed", "缺少页面地址", {}, "url is required")
        if not wait_for and not required_text:
            return ToolResult("failed", "缺少等待条件", {}, "wait_for or required_text is required")
        timeout_seconds = int(args.get("timeout_seconds") or 15)
        try:
            payload = self._run_browser_action(
                root=self._root(context),
                action="wait_for",
                url=url,
                selector="",
                value="",
                wait_for=wait_for,
                required_text=required_text,
                timeout_seconds=timeout_seconds,
            )
        except ValueError as exc:
            return ToolResult("blocked", "浏览器等待被阻断", {"url": url}, str(exc))
        return ToolResult("completed" if payload.get("ok") else "failed", "浏览器等待完成" if payload.get("ok") else "浏览器等待失败", payload, None if payload.get("ok") else str(payload.get("error") or "browser wait failed"))

    def _run_browser_validation(
        self,
        *,
        url: str,
        selectors: list[str],
        required_text: list[str],
        timeout_seconds: int,
        root: Path,
    ) -> dict[str, Any]:
        validated_url = self._validate_local_url(url)
        node_executable = shutil.which("node")
        if not node_executable:
            return {
                "url": validated_url,
                "final_url": validated_url,
                "ok": False,
                "status_code": 0,
                "title": "",
                "headings": [],
                "console_errors": [],
                "page_errors": [],
                "selector_results": [],
                "text_results": [],
                "body_excerpt": "",
                "error": "node executable not found",
                "engine": "playwright",
            }
        client_root = root / "client"
        script = """
const { chromium } = require('playwright');

async function main() {
  const input = JSON.parse(process.argv[1]);
  const consoleErrors = [];
  const pageErrors = [];
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('console', (msg) => {
    if (msg.type() === 'error' && consoleErrors.length < 12) {
      consoleErrors.push(msg.text());
    }
  });
  page.on('pageerror', (error) => {
    if (pageErrors.length < 12) {
      pageErrors.push(String(error));
    }
  });
  let response = null;
  try {
    response = await page.goto(input.url, { waitUntil: 'networkidle', timeout: input.timeoutMs });
    const title = await page.title();
    const headings = await page.$$eval('h1,h2,h3', (nodes) =>
      nodes.slice(0, 8).map((node) => ({
        tag: node.tagName.toLowerCase(),
        text: (node.textContent || '').trim().slice(0, 200),
      }))
    );
    const bodyText = await page.locator('body').innerText().catch(() => '');
    const selectorResults = [];
    for (const selector of input.selectors) {
      const count = await page.locator(selector).count().catch(() => 0);
      selectorResults.push({ selector, found: count > 0, count });
    }
    const textResults = [];
    for (const text of input.requiredText) {
      const found = await page.locator('body').evaluate((node, value) => (node.innerText || '').includes(value), text).catch(() => false);
      textResults.push({ text, found });
    }
    const statusCode = response ? response.status() : 0;
    const ok =
      statusCode >= 200 &&
      statusCode < 400 &&
      consoleErrors.length === 0 &&
      pageErrors.length === 0 &&
      selectorResults.every((item) => item.found) &&
      textResults.every((item) => item.found);
    const payload = {
      url: input.url,
      final_url: page.url(),
      ok,
      status_code: statusCode,
      title,
      headings,
      console_errors: consoleErrors,
      page_errors: pageErrors,
      selector_results: selectorResults,
      text_results: textResults,
      body_excerpt: bodyText.slice(0, 1600),
      engine: 'playwright',
    };
    console.log(JSON.stringify(payload));
  } catch (error) {
    const payload = {
      url: input.url,
      final_url: page.url() || input.url,
      ok: false,
      status_code: response ? response.status() : 0,
      title: '',
      headings: [],
      console_errors: consoleErrors,
      page_errors: pageErrors,
      selector_results: [],
      text_results: [],
      body_excerpt: '',
      error: String(error),
      engine: 'playwright',
    };
    console.log(JSON.stringify(payload));
  } finally {
    await browser.close().catch(() => {});
  }
}

main().catch((error) => {
  console.log(JSON.stringify({
    url: '',
    final_url: '',
    ok: false,
    status_code: 0,
    title: '',
    headings: [],
    console_errors: [],
    page_errors: [String(error)],
    selector_results: [],
    text_results: [],
    body_excerpt: '',
    error: String(error),
    engine: 'playwright',
  }));
  process.exit(0);
});
"""
        input_payload = json.dumps(
            {
                "url": validated_url,
                "selectors": selectors,
                "requiredText": required_text,
                "timeoutMs": timeout_seconds * 1000,
            },
            ensure_ascii=False,
        )
        completed = subprocess.run(
            [node_executable, "-e", script, input_payload],
            cwd=str(client_root if client_root.exists() else root),
            text=True,
            capture_output=True,
            timeout=max(timeout_seconds + 10, 20),
            shell=False,
        )
        output = (completed.stdout or "").strip().splitlines()
        raw = output[-1] if output else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {
                "url": validated_url,
                "final_url": validated_url,
                "ok": False,
                "status_code": 0,
                "title": "",
                "headings": [],
                "console_errors": [],
                "page_errors": [],
                "selector_results": [],
                "text_results": [],
                "body_excerpt": "",
                "error": completed.stderr.strip() or raw or "invalid browser validation output",
                "engine": "playwright",
            }
        payload.setdefault("url", validated_url)
        payload.setdefault("final_url", validated_url)
        payload.setdefault("engine", "playwright")
        payload.setdefault("console_errors", [])
        payload.setdefault("page_errors", [])
        payload.setdefault("selector_results", [])
        payload.setdefault("text_results", [])
        payload.setdefault("headings", [])
        payload.setdefault("title", "")
        payload.setdefault("body_excerpt", "")
        payload.setdefault("status_code", 0)
        payload.setdefault("ok", False)
        if completed.returncode != 0 and not payload.get("error"):
            payload["error"] = completed.stderr.strip() or "browser validation command failed"
        return payload

    def _run_browser_action(
        self,
        *,
        root: Path,
        action: str,
        url: str,
        selector: str,
        value: str,
        wait_for: str,
        required_text: list[str],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        validated_url = self._validate_local_url(url)
        node_executable = shutil.which("node")
        if not node_executable:
            return {
                "url": validated_url,
                "final_url": validated_url,
                "ok": False,
                "status_code": 0,
                "title": "",
                "headings": [],
                "console_errors": [],
                "page_errors": [],
                "selector_results": [],
                "text_results": [],
                "body_excerpt": "",
                "error": "node executable not found",
                "engine": "playwright",
                "action": action,
            }
        client_root = root / "client"
        script = """
const { chromium } = require('playwright');
async function main() {
  const input = JSON.parse(process.argv[1]);
  const consoleErrors = [];
  const pageErrors = [];
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('console', (msg) => {
    if (msg.type() === 'error' && consoleErrors.length < 12) consoleErrors.push(msg.text());
  });
  page.on('pageerror', (error) => {
    if (pageErrors.length < 12) pageErrors.push(String(error));
  });
  let response = null;
  try {
    response = await page.goto(input.url, { waitUntil: 'networkidle', timeout: input.timeoutMs });
    if (input.action === 'click') {
      await page.locator(input.selector).click({ timeout: input.timeoutMs });
    } else if (input.action === 'fill') {
      await page.locator(input.selector).fill(input.value, { timeout: input.timeoutMs });
    }
    if (input.waitFor) {
      if (input.waitFor.startsWith('text=')) {
        await page.getByText(input.waitFor.slice(5), { exact: false }).waitFor({ timeout: input.timeoutMs });
      } else {
        await page.locator(input.waitFor).waitFor({ timeout: input.timeoutMs });
      }
    }
    const selectorResults = [];
    if (input.selector) {
      const count = await page.locator(input.selector).count().catch(() => 0);
      selectorResults.push({ selector: input.selector, found: count > 0, count });
    }
    const textResults = [];
    for (const text of input.requiredText) {
      const found = await page.locator('body').evaluate((node, value) => (node.innerText || '').includes(value), text).catch(() => false);
      textResults.push({ text, found });
    }
    const title = await page.title();
    const headings = await page.$$eval('h1,h2,h3', (nodes) =>
      nodes.slice(0, 8).map((node) => ({ tag: node.tagName.toLowerCase(), text: (node.textContent || '').trim().slice(0, 200) }))
    );
    const bodyText = await page.locator('body').innerText().catch(() => '');
    const statusCode = response ? response.status() : 0;
    const ok = statusCode >= 200 && statusCode < 400 && consoleErrors.length === 0 && pageErrors.length === 0 && textResults.every((item) => item.found);
    console.log(JSON.stringify({
      url: input.url,
      final_url: page.url(),
      ok,
      status_code: statusCode,
      title,
      headings,
      console_errors: consoleErrors,
      page_errors: pageErrors,
      selector_results: selectorResults,
      text_results: textResults,
      body_excerpt: bodyText.slice(0, 1600),
      engine: 'playwright',
      action: input.action,
    }));
  } catch (error) {
    console.log(JSON.stringify({
      url: input.url,
      final_url: page.url() || input.url,
      ok: false,
      status_code: response ? response.status() : 0,
      title: '',
      headings: [],
      console_errors: consoleErrors,
      page_errors: pageErrors,
      selector_results: input.selector ? [{ selector: input.selector, found: false, count: 0 }] : [],
      text_results: input.requiredText.map((text) => ({ text, found: false })),
      body_excerpt: '',
      error: String(error),
      engine: 'playwright',
      action: input.action,
    }));
  } finally {
    await browser.close().catch(() => {});
  }
}
main().catch((error) => {
  console.log(JSON.stringify({
    url: '',
    final_url: '',
    ok: false,
    status_code: 0,
    title: '',
    headings: [],
    console_errors: [],
    page_errors: [String(error)],
    selector_results: [],
    text_results: [],
    body_excerpt: '',
    error: String(error),
    engine: 'playwright',
    action: 'unknown',
  }));
  process.exit(0);
});
"""
        input_payload = json.dumps(
            {
                "url": validated_url,
                "action": action,
                "selector": selector,
                "value": value,
                "waitFor": wait_for,
                "requiredText": required_text,
                "timeoutMs": timeout_seconds * 1000,
            },
            ensure_ascii=False,
        )
        completed = subprocess.run(
            [node_executable, "-e", script, input_payload],
            cwd=str(client_root if client_root.exists() else root),
            text=True,
            capture_output=True,
            timeout=max(timeout_seconds + 10, 20),
            shell=False,
        )
        output = (completed.stdout or "").strip().splitlines()
        raw = output[-1] if output else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {
                "url": validated_url,
                "final_url": validated_url,
                "ok": False,
                "status_code": 0,
                "title": "",
                "headings": [],
                "console_errors": [],
                "page_errors": [],
                "selector_results": [],
                "text_results": [],
                "body_excerpt": "",
                "error": completed.stderr.strip() or raw or "invalid browser action output",
                "engine": "playwright",
                "action": action,
            }
        payload.setdefault("url", validated_url)
        payload.setdefault("final_url", validated_url)
        payload.setdefault("engine", "playwright")
        payload.setdefault("action", action)
        payload.setdefault("console_errors", [])
        payload.setdefault("page_errors", [])
        payload.setdefault("selector_results", [])
        payload.setdefault("text_results", [])
        payload.setdefault("headings", [])
        payload.setdefault("title", "")
        payload.setdefault("body_excerpt", "")
        payload.setdefault("status_code", 0)
        payload.setdefault("ok", False)
        if completed.returncode != 0 and not payload.get("error"):
            payload["error"] = completed.stderr.strip() or "browser action command failed"
        return payload

    def _run_network_capture(
        self,
        *,
        root: Path,
        url: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        validated_url = self._validate_local_url(url)
        node_executable = shutil.which("node")
        if not node_executable:
            return {
                "url": validated_url,
                "final_url": validated_url,
                "ok": False,
                "request_failures": [],
                "error_responses": [],
                "console_errors": [],
                "page_errors": [],
                "engine": "playwright",
                "error": "node executable not found",
            }
        client_root = root / "client"
        script = """
const { chromium } = require('playwright');
async function main() {
  const input = JSON.parse(process.argv[1]);
  const requestFailures = [];
  const errorResponses = [];
  const consoleErrors = [];
  const pageErrors = [];
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('console', (msg) => {
    if (msg.type() === 'error' && consoleErrors.length < 12) consoleErrors.push(msg.text());
  });
  page.on('pageerror', (error) => {
    if (pageErrors.length < 12) pageErrors.push(String(error));
  });
  page.on('requestfailed', (request) => {
    if (requestFailures.length < 12) {
      requestFailures.push({
        url: request.url(),
        method: request.method(),
        failure: request.failure() ? request.failure().errorText : 'requestfailed',
      });
    }
  });
  page.on('response', async (response) => {
    if (response.status() >= 400 && errorResponses.length < 12) {
      errorResponses.push({
        url: response.url(),
        status: response.status(),
        method: response.request().method(),
      });
    }
  });
  try {
    const response = await page.goto(input.url, { waitUntil: 'networkidle', timeout: input.timeoutMs });
    console.log(JSON.stringify({
      url: input.url,
      final_url: page.url(),
      ok: requestFailures.length === 0 && errorResponses.length === 0 && consoleErrors.length === 0 && pageErrors.length === 0 && !!response && response.status() < 400,
      status_code: response ? response.status() : 0,
      request_failures: requestFailures,
      error_responses: errorResponses,
      console_errors: consoleErrors,
      page_errors: pageErrors,
      engine: 'playwright',
    }));
  } catch (error) {
    console.log(JSON.stringify({
      url: input.url,
      final_url: page.url() || input.url,
      ok: false,
      status_code: 0,
      request_failures: requestFailures,
      error_responses: errorResponses,
      console_errors: consoleErrors,
      page_errors: [...pageErrors, String(error)].slice(0, 12),
      engine: 'playwright',
      error: String(error),
    }));
  } finally {
    await browser.close().catch(() => {});
  }
}
main().catch((error) => {
  console.log(JSON.stringify({
    url: '',
    final_url: '',
    ok: false,
    status_code: 0,
    request_failures: [],
    error_responses: [],
    console_errors: [],
    page_errors: [String(error)],
    engine: 'playwright',
    error: String(error),
  }));
  process.exit(0);
});
"""
        input_payload = json.dumps({"url": validated_url, "timeoutMs": timeout_seconds * 1000}, ensure_ascii=False)
        completed = subprocess.run(
            [node_executable, "-e", script, input_payload],
            cwd=str(client_root if client_root.exists() else root),
            text=True,
            capture_output=True,
            timeout=max(timeout_seconds + 10, 20),
            shell=False,
        )
        output = (completed.stdout or "").strip().splitlines()
        raw = output[-1] if output else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {
                "url": validated_url,
                "final_url": validated_url,
                "ok": False,
                "status_code": 0,
                "request_failures": [],
                "error_responses": [],
                "console_errors": [],
                "page_errors": [],
                "engine": "playwright",
                "error": completed.stderr.strip() or raw or "invalid network capture output",
            }
        payload.setdefault("url", validated_url)
        payload.setdefault("final_url", validated_url)
        payload.setdefault("status_code", 0)
        payload.setdefault("ok", False)
        payload.setdefault("request_failures", [])
        payload.setdefault("error_responses", [])
        payload.setdefault("console_errors", [])
        payload.setdefault("page_errors", [])
        payload.setdefault("engine", "playwright")
        if completed.returncode != 0 and not payload.get("error"):
            payload["error"] = completed.stderr.strip() or "network capture command failed"
        return payload

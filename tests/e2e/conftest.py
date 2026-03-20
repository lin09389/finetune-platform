"""
E2E 测试配置
"""
import pytest
import asyncio
from typing import Generator
from playwright.sync_api import Page, Browser, BrowserContext
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:5173"
API_URL = "http://localhost:8000"


@pytest.fixture(scope="session")
def browser() -> Generator[Browser, None, None]:
    """创建浏览器实例"""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        yield browser
        browser.close()


@pytest.fixture
def context(browser: Browser) -> Generator[BrowserContext, None, None]:
    """创建浏览器上下文"""
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        locale="zh-CN",
    )
    yield context
    context.close()


@pytest.fixture
def page(context: BrowserContext) -> Generator[Page, None, None]:
    """创建页面"""
    page = context.new_page()
    page.set_default_timeout(30000)
    yield page
    page.close()


@pytest.fixture
def api_client():
    """API 客户端"""
    import requests
    return requests.Session()


def skip_if_no_backend(api_client):
    """检查后端是否可用"""
    try:
        response = api_client.get(f"{API_URL}/health", timeout=5)
        return response.status_code == 200
    except Exception:
        return False

"""
代理配置管理 - 支持国内环境代理透传
"""
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """
    代理配置

    支持从环境变量读取和应用代理设置
    """
    http_proxy: str | None = None
    https_proxy: str | None = None
    no_proxy: str | None = None
    socks_proxy: str | None = None

    def __post_init__(self):
        if not self.http_proxy and not self.https_proxy:
            env_config = ProxyConfig.from_env()
            self.http_proxy = self.http_proxy or env_config.http_proxy
            self.https_proxy = self.https_proxy or env_config.https_proxy
            self.no_proxy = self.no_proxy or env_config.no_proxy
            self.socks_proxy = self.socks_proxy or env_config.socks_proxy

    @classmethod
    def from_env(cls) -> 'ProxyConfig':
        """从环境变量读取代理配置"""
        return cls(
            http_proxy=os.getenv("HTTP_PROXY") or os.getenv("http_proxy"),
            https_proxy=os.getenv("HTTPS_PROXY") or os.getenv("https_proxy"),
            no_proxy=os.getenv("NO_PROXY") or os.getenv("no_proxy"),
            socks_proxy=os.getenv("ALL_PROXY"),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ProxyConfig':
        """从字典创建配置"""
        return cls(
            http_proxy=data.get("http_proxy"),
            https_proxy=data.get("https_proxy"),
            no_proxy=data.get("no_proxy"),
            socks_proxy=data.get("socks_proxy"),
        )

    def apply(self) -> None:
        """应用代理配置到环境变量"""
        if self.http_proxy:
            os.environ["HTTP_PROXY"] = self.http_proxy
            os.environ["http_proxy"] = self.http_proxy

        if self.https_proxy:
            os.environ["HTTPS_PROXY"] = self.https_proxy
            os.environ["https_proxy"] = self.https_proxy

        if self.no_proxy:
            os.environ["NO_PROXY"] = self.no_proxy
            os.environ["no_proxy"] = self.no_proxy

        if self.socks_proxy:
            os.environ["ALL_PROXY"] = self.socks_proxy

        logger.info(f"代理配置已应用: HTTP={self.http_proxy}, HTTPS={self.https_proxy}")

    def clear(self) -> None:
        """清除代理环境变量"""
        for key in [
            "HTTP_PROXY",
            "http_proxy",
            "HTTPS_PROXY",
            "https_proxy",
            "NO_PROXY",
            "no_proxy",
            "ALL_PROXY",
        ]:
            os.environ.pop(key, None)

        logger.info("代理配置已清除")

    def get_requests_proxies(self) -> dict[str, str]:
        """获取 requests 库使用的代理配置"""
        proxies = {}
        if self.http_proxy:
            proxies["http"] = self.http_proxy
        if self.https_proxy:
            proxies["https"] = self.https_proxy
        return proxies

    def get_openai_proxy(self) -> str | None:
        """获取 OpenAI SDK 使用的代理"""
        return self.https_proxy or self.http_proxy

    def get_aiohttp_proxy(self) -> str | None:
        """获取 aiohttp 使用的代理"""
        return self.http_proxy or self.https_proxy

    def get_httpx_proxy(self) -> dict[str, str]:
        """获取 httpx 使用的代理配置"""
        return self.get_requests_proxies()

    def is_configured(self) -> bool:
        """检查是否配置了代理"""
        return bool(self.http_proxy or self.https_proxy or self.socks_proxy)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "http_proxy": self.http_proxy,
            "https_proxy": self.https_proxy,
            "no_proxy": self.no_proxy,
            "socks_proxy": self.socks_proxy,
            "is_configured": self.is_configured(),
        }

    def __str__(self) -> str:
        if not self.is_configured():
            return "ProxyConfig(not configured)"

        parts = []
        if self.http_proxy:
            parts.append(f"http={self.http_proxy}")
        if self.https_proxy:
            parts.append(f"https={self.https_proxy}")
        if self.socks_proxy:
            parts.append(f"socks={self.socks_proxy}")

        return f"ProxyConfig({', '.join(parts)})"


class ProxyManager:
    """
    代理管理器

    提供统一的代理配置管理，支持多种 HTTP 客户端
    """

    def __init__(self, config: ProxyConfig | None = None):
        self.config = config or ProxyConfig.from_env()
        self._original_env: dict[str, str] = {}

    def apply(self) -> None:
        """应用代理配置"""
        self._backup_env()
        self.config.apply()

    def _backup_env(self) -> None:
        """备份原始环境变量"""
        for key in ["HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy",
                    "NO_PROXY", "no_proxy", "ALL_PROXY", "all_proxy"]:
            if key in os.environ:
                self._original_env[key] = os.environ[key]

    def restore(self) -> None:
        """恢复原始环境变量"""
        for key in ["HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy",
                    "NO_PROXY", "no_proxy", "ALL_PROXY", "all_proxy"]:
            os.environ.pop(key, None)

        for key, value in self._original_env.items():
            os.environ[key] = value

        self._original_env.clear()
        logger.info("代理配置已恢复")

    def get_proxies_for(self, url: str) -> dict[str, str]:
        """
        根据URL获取代理配置

        Args:
            url: 目标URL

        Returns:
            代理配置字典
        """
        if self.config.no_proxy:
            no_proxy_list = [h.strip() for h in self.config.no_proxy.split(",")]

            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.hostname or ""

            for no_proxy_host in no_proxy_list:
                if no_proxy_host in host or host.endswith(no_proxy_host):
                    return {}

        return self.config.get_requests_proxies()

    def configure_openai(self) -> None:
        """配置 OpenAI SDK 代理"""
        if not self.config.is_configured():
            return

        proxy = self.config.get_openai_proxy()
        if proxy:
            os.environ["OPENAI_PROXY"] = proxy
            logger.info(f"OpenAI SDK 代理已配置: {proxy}")

    def configure_httpx(self) -> dict[str, str]:
        """获取 httpx 客户端代理配置"""
        return self.config.get_httpx_proxy()

    def configure_aiohttp(self) -> str | None:
        """获取 aiohttp 客户端代理配置"""
        return self.config.get_aiohttp_proxy()

    @staticmethod
    def test_proxy(proxy_url: str, test_url: str = "https://www.google.com") -> bool:
        """
        测试代理是否可用

        Args:
            proxy_url: 代理地址
            test_url: 测试URL

        Returns:
            是否可用
        """
        import requests

        try:
            response = requests.get(
                test_url,
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"代理测试失败: {proxy_url} - {e}")
            return False


_proxy_manager: ProxyManager | None = None


def get_proxy_manager(config: ProxyConfig | None = None) -> ProxyManager:
    """获取代理管理器单例"""
    global _proxy_manager

    if _proxy_manager is None:
        _proxy_manager = ProxyManager(config)

    return _proxy_manager


def reset_proxy_manager() -> ProxyManager:
    """重置代理管理器"""
    global _proxy_manager
    _proxy_manager = None
    return get_proxy_manager()


def with_proxy(func):
    """
    代理装饰器

    自动为函数应用代理配置
    """
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        manager = get_proxy_manager()
        manager.apply()
        try:
            return func(*args, **kwargs)
        finally:
            manager.restore()

    return wrapper

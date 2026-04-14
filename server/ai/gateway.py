"""
AI 网关 - 统一云端 AI 接口

支持的服务商：
- Minimax（国产，推荐）
- Minimax Coding（编程专用）
- GLM/智谱 AI（国产）

性能优化：
- 连接池复用
- 流式传输优化
- 智能超时设置
"""
import asyncio
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_http_clients: dict[str, httpx.AsyncClient] = {}


def get_http_client(timeout: float = 60.0) -> httpx.AsyncClient:
    """
    获取或创建 HTTP 客户端（复用连接池）

    Args:
        timeout: 超时时间（秒）

    Returns:
        HTTP 客户端实例
    """
    timeout_key = f"timeout_{int(timeout)}"

    if timeout_key not in _http_clients:
        _http_clients[timeout_key] = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=timeout,
                write=30.0,
                pool=5.0
            ),
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=50,
                keepalive_expiry=30.0
            ),
            follow_redirects=True
        )

    return _http_clients[timeout_key]


async def close_http_clients():
    """关闭所有 HTTP 客户端（应用关闭时调用）"""
    for client in _http_clients.values():
        await client.aclose()
    _http_clients.clear()


class AIProvider(ABC):
    """AI 服务商抽象基类"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        model: str,
        api_key: str,
        **kwargs
    ) -> dict[str, Any]:
        """非流式聊天"""
        pass

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        model: str,
        api_key: str,
        **kwargs
    ) -> AsyncGenerator[dict[str, Any], None]:
        """流式聊天"""
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        """获取默认模型"""
        pass

    @abstractmethod
    def list_models(self) -> list[str]:
        """获取可用模型列表"""
        pass

    async def test_connection(self) -> dict[str, Any]:
        """测试连接"""
        try:
            await self.chat(
                messages=[{"role": "user", "content": "Hi"}],
                model=self.get_default_model(),
                api_key="",
                max_tokens=10
            )
            return {"success": True, "message": "连接成功"}
        except Exception as e:
            return {"success": False, "message": str(e)}


class MinimaxProvider(AIProvider):
    """Minimax 适配器"""

    def __init__(
        self,
        coding_mode: bool = False,
        group_id: str = "",
        base_url: str = ""
    ):
        """
        初始化 Minimax 适配器

        Args:
            coding_mode: 是否启用编程模式
            group_id: Group ID（可选）
            base_url: 自定义 Base URL（可选）
        """
        self.base_url = base_url or "https://api.minimaxi.com/v1"
        self.coding_mode = coding_mode
        self.group_id = group_id
        self._api_key = ""

    def set_api_key(self, api_key: str):
        """设置 API Key"""
        self._api_key = api_key

    def get_default_model(self) -> str:
        """获取默认模型"""
        return "MiniMax-M2.5"

    def list_models(self) -> list[str]:
        """获取可用模型列表"""
        return [
            "MiniMax-M2.5",
            "MiniMax-M2.5-highspeed",
            "MiniMax-Text-01",
            "abab6.5s-chat",
            "abab6.5g-chat"
        ]

    async def chat(
        self,
        messages: list[dict],
        model: str = None,
        api_key: str = "",
        **kwargs
    ) -> dict[str, Any]:
        """
        非流式聊天

        Args:
            messages: 消息列表
            model: 模型名称
            api_key: API Key
            kwargs: 其他参数

        Returns:
            响应结果
        """
        if model is None:
            model = self.get_default_model()

        api_key = api_key or self._api_key

        client = get_http_client(timeout=60.0)

        default_params = {
            "temperature": 0.7,
            "max_tokens": 2048,
            "top_p": 0.9,
        }
        params = {**default_params, **kwargs}

        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = await client.post(
                    f"{self.base_url}/text/chatcompletion_v2",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        **params
                    },
                )
                response.raise_for_status()
                data = response.json()
                base_resp = data.get("base_resp") if isinstance(data, dict) else None
                if isinstance(base_resp, dict):
                    status_code = int(base_resp.get("status_code", 0) or 0)
                    if status_code != 0:
                        raise ValueError(base_resp.get("status_msg", "Minimax returned an error"))

                content = ""
                choices = data.get("choices")
                if isinstance(choices, list) and choices:
                    first_choice = choices[0] if isinstance(choices[0], dict) else {}
                    message = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
                    if isinstance(message, dict):
                        content = message.get("content", "") or message.get("reasoning_content", "")
                    if not content:
                        delta = first_choice.get("delta", {}) if isinstance(first_choice, dict) else {}
                        if isinstance(delta, dict):
                            content = delta.get("content", "") or delta.get("reasoning_content", "")

                if not content:
                    # Backward/variant response compatibility.
                    content = (
                        data.get("content")
                        or data.get("reply")
                        or data.get("output_text")
                        or data.get("text")
                        or ""
                    )

                if not content:
                    error_msg = data.get("message", data.get("error", "未知错误"))
                    raise ValueError(f"API 返回格式异常: {error_msg}")

                return {
                    "content": content,
                    "model": model,
                    "usage": data.get("usage", {})
                }

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue

                error_detail = self._parse_error_response(e.response)

                if e.response.status_code == 401:
                    raise ValueError(f"API Key 认证失败：{error_detail}")
                elif e.response.status_code == 403:
                    raise ValueError(f"权限不足：{error_detail}")
                elif e.response.status_code == 429:
                    raise ValueError(f"请求过于频繁：{error_detail}")
                else:
                    raise ValueError(f"API 调用失败 ({e.response.status_code}): {error_detail}")

            except httpx.RequestError as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                raise ValueError(f"网络连接失败：{str(e)}")

        raise ValueError("请求重试失败")

    async def chat_stream(
        self,
        messages: list[dict],
        model: str = None,
        api_key: str = "",
        **kwargs
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        流式聊天

        Args:
            messages: 消息列表
            model: 模型名称
            api_key: API Key
            kwargs: 其他参数

        Yields:
            响应片段
        """
        if model is None:
            model = self.get_default_model()

        api_key = api_key or self._api_key

        client = get_http_client(timeout=120.0)

        default_params = {
            "temperature": 0.7,
            "max_tokens": 2048,
            "top_p": 0.9,
        }
        params = {**default_params, **kwargs}

        try:
            yielded = 0
            async with client.stream(
                "POST",
                f"{self.base_url}/text/chatcompletion_v2",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    **params
                },
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    payload = line
                    if line.startswith("data:"):
                        payload = line.split(":", 1)[1].strip()

                    if payload == "[DONE]":
                        break

                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    base_resp = chunk.get("base_resp") if isinstance(chunk, dict) else None
                    if isinstance(base_resp, dict):
                        status_code = int(base_resp.get("status_code", 0) or 0)
                        if status_code != 0:
                            raise ValueError(base_resp.get("status_msg", "Minimax stream returned an error"))

                    content = ""
                    choices = chunk.get("choices")
                    if isinstance(choices, list) and choices:
                        first_choice = choices[0] if isinstance(choices[0], dict) else {}
                        delta = first_choice.get("delta", {}) if isinstance(first_choice, dict) else {}
                        if isinstance(delta, dict):
                            content = delta.get("content", "") or delta.get("reasoning_content", "")
                        if not content:
                            message = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
                            if isinstance(message, dict):
                                content = message.get("content", "") or message.get("reasoning_content", "")

                    if not content:
                        content = (
                            chunk.get("content")
                            or chunk.get("text")
                            or chunk.get("output_text")
                            or ""
                        )

                    if content:
                        yield {"content": content, "delta": True}
                        yielded += 1

                if yielded == 0:
                    raise ValueError("云端流式响应为空，请检查 API Key、模型权限或供应商返回格式")

        except httpx.HTTPStatusError as e:
            error_detail = self._parse_error_response(e.response)
            raise ValueError(f"流式调用失败 ({e.response.status_code}): {error_detail}")
        except httpx.RequestError as e:
            raise ValueError(f"网络连接失败：{str(e)}")

    def _parse_error_response(self, response) -> str:
        """解析错误响应"""
        try:
            error_body = response.json()
            base_resp = error_body.get("base_resp") if isinstance(error_body, dict) else None
            if isinstance(base_resp, dict):
                status_msg = base_resp.get("status_msg")
                if status_msg:
                    return str(status_msg)
            return error_body.get("message", error_body.get("error", str(error_body)))
        except Exception:
            return response.text or f"HTTP {response.status_code}"


class GLMProvider(AIProvider):
    """智谱 GLM 适配器"""

    def __init__(self, base_url: str = ""):
        self.base_url = base_url or "https://open.bigmodel.cn/api/paas/v4"
        self._api_key = ""

    def set_api_key(self, api_key: str):
        """设置 API Key"""
        self._api_key = api_key

    def get_default_model(self) -> str:
        """获取默认模型"""
        return "glm-4"

    def list_models(self) -> list[str]:
        """获取可用模型列表"""
        return ["glm-4", "glm-3-turbo", "glm-4v"]

    async def chat(
        self,
        messages: list[dict],
        model: str = None,
        api_key: str = "",
        **kwargs
    ) -> dict[str, Any]:
        """非流式聊天"""
        if model is None:
            model = self.get_default_model()

        api_key = api_key or self._api_key

        client = get_http_client(timeout=60.0)

        default_params = {
            "temperature": 0.7,
            "max_tokens": 2048,
        }
        params = {**default_params, **kwargs}

        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        **params
                    },
                )
                response.raise_for_status()
                data = response.json()

                return {
                    "content": data["choices"][0]["message"]["content"],
                    "model": model,
                    "usage": data.get("usage", {})
                }

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue

                error_detail = self._parse_error_response(e.response)

                if e.response.status_code == 401:
                    raise ValueError(f"API Key 认证失败：{error_detail}")
                elif e.response.status_code == 403:
                    raise ValueError(f"权限不足：{error_detail}")
                elif e.response.status_code == 429:
                    raise ValueError(f"请求过于频繁：{error_detail}")
                else:
                    raise ValueError(f"API 调用失败 ({e.response.status_code}): {error_detail}")

            except httpx.RequestError as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                raise ValueError(f"网络连接失败：{str(e)}")

        raise ValueError("请求重试失败")

    async def chat_stream(
        self,
        messages: list[dict],
        model: str = None,
        api_key: str = "",
        **kwargs
    ) -> AsyncGenerator[dict[str, Any], None]:
        """流式聊天"""
        if model is None:
            model = self.get_default_model()

        api_key = api_key or self._api_key

        client = get_http_client(timeout=120.0)

        default_params = {
            "temperature": 0.7,
            "max_tokens": 2048,
        }
        params = {**default_params, **kwargs}

        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    **params
                },
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    payload = line
                    if line.startswith("data:"):
                        payload = line.split(":", 1)[1].strip()

                    if payload == "[DONE]":
                        break

                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    content = ""
                    choices = chunk.get("choices")
                    if isinstance(choices, list) and choices:
                        first_choice = choices[0] if isinstance(choices[0], dict) else {}
                        delta = first_choice.get("delta", {}) if isinstance(first_choice, dict) else {}
                        if isinstance(delta, dict):
                            content = delta.get("content", "")
                        if not content:
                            message = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
                            if isinstance(message, dict):
                                content = message.get("content", "")

                    if not content:
                        content = chunk.get("content") or chunk.get("text") or ""

                    if content:
                        yield {"content": content, "delta": True}

        except httpx.HTTPStatusError as e:
            error_detail = self._parse_error_response(e.response)
            raise ValueError(f"流式调用失败 ({e.response.status_code}): {error_detail}")
        except httpx.RequestError as e:
            raise ValueError(f"网络连接失败：{str(e)}")

    def _parse_error_response(self, response) -> str:
        """解析错误响应"""
        try:
            error_body = response.json()
            return error_body.get("message", error_body.get("error", str(error_body)))
        except Exception:
            return response.text or f"HTTP {response.status_code}"


PROVIDERS: dict[str, AIProvider] = {
    "minimax": MinimaxProvider(coding_mode=False),
    "minimax-coding": MinimaxProvider(coding_mode=True),
    "glm": GLMProvider(),
}


def get_provider(provider: str, group_id: str = "", base_url: str = "", version: str = "") -> AIProvider | None:
    """
    获取服务商实例，支持灰度分流

    Args:
        provider: 服务商名称 (minimax/minimax-coding/glm)
        group_id: Group ID（可选，用于 Minimax）
        base_url: 自定义 Base URL（可选）
        version: 版本标签（用于灰度分流）

    Returns:
        服务商实例
    """
    # 灰度分流逻辑：如果版本为 canary，强制使用高性能模型或灰度端点
    if version == "canary" and provider == "minimax":
        return MinimaxProvider(coding_mode=False, base_url="https://api-canary.minimaxi.com/v1")

    if provider not in PROVIDERS:
        return None

    if provider.startswith("minimax") and (group_id or base_url):
        if provider == "minimax":
            return MinimaxProvider(coding_mode=False, group_id=group_id, base_url=base_url)
        elif provider == "minimax-coding":
            return MinimaxProvider(coding_mode=True, group_id=group_id, base_url=base_url)

    return PROVIDERS[provider]


def list_providers() -> list[dict]:
    """
    列出所有可用的服务商

    Returns:
        服务商信息列表
    """
    return [
        {
            "id": "minimax",
            "name": "Minimax",
            "description": "国产 AI，中文优化好",
            "models": ["MiniMax-M2.5", "MiniMax-M2.5-highspeed", "MiniMax-Text-01", "abab6.5s-chat", "abab6.5g-chat"],
        },
        {
            "id": "minimax-coding",
            "name": "Minimax Coding",
            "description": "编程专用，代码生成优化",
            "models": ["MiniMax-M2.5", "MiniMax-M2.5-highspeed", "MiniMax-Text-01", "abab6.5s-chat"],
        },
        {
            "id": "glm",
            "name": "智谱 GLM",
            "description": "智谱 AI，中文能力强",
            "models": ["glm-4", "glm-3-turbo", "glm-4v"],
        },
    ]

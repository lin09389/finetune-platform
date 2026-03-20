"""
AI 网关 - 统一云端 AI 接口

支持的服务商�?- Minimax（国产，推荐�?- Minimax Coding（编程专用）
- GLM/智谱 AI（国产）

性能优化�?- 连接池复�?- 流式传输优化
- 智能超时设置
"""
from typing import Dict, List, AsyncGenerator, Optional
from abc import ABC, abstractmethod
import httpx
import json
import logging
import asyncio

logger = logging.getLogger(__name__)


# 全局 HTTP 客户端（连接池复用）
_http_clients: Dict[str, httpx.AsyncClient] = {}


def get_http_client(timeout: float = 60.0) -> httpx.AsyncClient:
    """
    获取或创�?HTTP 客户端（复用连接池）
    
    Args:
        timeout: 超时时间（秒�?    
    Returns:
        HTTP 客户端实�?    """
    timeout_key = f"timeout_{int(timeout)}"
    
    if timeout_key not in _http_clients:
        _http_clients[timeout_key] = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,      # 连接超时 10s
                read=timeout,      # 读取超时
                write=30.0,        # 写入超时 30s
                pool=5.0           # 连接池超�?5s
            ),
            limits=httpx.Limits(
                max_keepalive_connections=20,  # 最大保持连接数
                max_connections=50,            # 最大连接数
                keepalive_expiry=30.0          # 连接保持时间 30s
            ),
            follow_redirects=True
        )
    
    return _http_clients[timeout_key]


async def close_http_clients():
    """关闭所�?HTTP 客户端（应用关闭时调用）"""
    for client in _http_clients.values():
        await client.aclose()
    _http_clients.clear()


class AIProvider(ABC):
    """AI 服务商抽象基�?""

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict],
        model: str,
        api_key: str,
        **kwargs
    ) -> str:
        """非流式聊�?""
        pass

    @abstractmethod
    async def stream(
        self,
        messages: List[Dict],
        model: str,
        api_key: str,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """流式聊天"""
        pass

    async def models(self, api_key: str) -> List[str]:
        """获取可用模型列表"""
        return []
    
    async def test_connection(self, api_key: str, **kwargs) -> bool:
        """测试 API Key 连接是否有效"""
        try:
            await self.chat(
                messages=[{"role": "user", "content": "Hi"}],
                model=self._get_default_model() if hasattr(self, '_get_default_model') else "",
                api_key=api_key,
                max_tokens=10,
                **kwargs
            )
            return True
        except Exception:
            raise


class MinimaxProvider(AIProvider):
    """Minimax 适配器（�?Coding Plan 支持�?""

    def __init__(self, coding_mode: bool = False, group_id: str = "", base_url: str = ""):
        """
        初始�?Minimax 适配�?
        Args:
            coding_mode: 是否启用编程模式（使�?Coding Plan�?            group_id: Group ID（可选，用于鉴权�?            base_url: 自定�?Base URL（可选，默认使用官方 API�?        """
        self.base_url = base_url or "https://api.minimaxi.com/v1"
        self.coding_mode = coding_mode
        self.group_id = group_id

    def _get_default_params(self) -> Dict:
        """获取默认参数"""
        if self.coding_mode:
            # Coding Plan 专用参数 - 编程优化
            return {
                "temperature": 0.7,
                "max_tokens": 4096,
                "top_p": 0.95,
                "presence_penalty": 0.1,  # 鼓励多样�?            }
        else:
            # 通用参数
            return {
                "temperature": 0.7,
                "max_tokens": 2048,
                "top_p": 0.9,
            }

    def _get_default_model(self) -> str:
        """获取默认模型"""
        if self.coding_mode:
            return "MiniMax-M2.5"
        else:
            return "MiniMax-M2.5"

    async def chat(
        self,
        messages: List[Dict],
        model: str = None,
        api_key: str = "",
        group_id: str = "",
        base_url: str = "",
        **kwargs
    ) -> str:
        """
        非流式聊�?
        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            model: 模型名称
            api_key: API Key
            group_id: Group ID（可选）
            base_url: 自定�?Base URL（可选）
            kwargs: 其他参数

        Returns:
            AI 回复内容
        """
        # 设置默认模型
        if model is None:
            model = self._get_default_model()

        # 使用传入�?base_url 或实例的 base_url
        base_url = base_url or self.base_url
        # 使用传入�?group_id 或实例的 group_id
        group_id = group_id or self.group_id

        # Coding Plan 使用专用模型和参�?        if self.coding_mode:
            default_params = self._get_default_params()
            kwargs = {**default_params, **kwargs}

        client = get_http_client(timeout=60.0)

        # 重试逻辑
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = await client.post(
                    f"{base_url}/text/chatcompletion_v2",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        **kwargs
                    },
                )
                response.raise_for_status()
                data = response.json()

                if "choices" not in data or not data["choices"]:
                    error_msg = data.get("message", data.get("error", "未知错误"))
                    logger.error(f"Minimax API 返回格式异常: {data}")
                    raise ValueError(f"API 返回格式异常: {error_msg}。请检�?API Key 是否有效�?)

                message = data["choices"][0]["message"]
                # MiniMax-M2.5 等推理模型返�?reasoning_content
                content = message.get("content", "") or message.get("reasoning_content", "")
                return content

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                error_detail = "Unknown error"
                try:
                    error_body = e.response.json()
                    error_detail = error_body.get("message", error_body.get("error", str(error_body)))
                except Exception:
                    error_detail = e.response.text or f"HTTP {e.response.status_code}"
                
                logger.error(f"Minimax API 错误 ({e.response.status_code}): {error_detail}")
                
                if e.response.status_code == 401:
                    raise ValueError(f"API Key 认证失败：请检�?API Key �?Group ID 是否正确。详情：{error_detail}")
                elif e.response.status_code == 403:
                    raise ValueError(f"权限不足：{error_detail}。请检�?API Key 权限或套餐是否有效�?)
                elif e.response.status_code == 429:
                    raise ValueError(f"请求过于频繁，请稍后重试。详情：{error_detail}")
                else:
                    raise ValueError(f"API 调用失败 ({e.response.status_code}): {error_detail}")
            except httpx.RequestError as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                logger.error(f"请求错误：{e}")
                raise ValueError(f"网络连接失败：{str(e)}")
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                logger.error(f"未知错误：{e}")
                raise ValueError(f"调用失败：{str(e)}")

        raise ValueError("请求重试失败")

    async def stream(
        self,
        messages: List[Dict],
        model: str = None,
        api_key: str = "",
        group_id: str = "",
        base_url: str = "",
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天

        Args:
            messages: 消息列表
            model: 模型名称
            api_key: API Key
            group_id: Group ID（可选）
            base_url: 自定�?Base URL（可选）
            kwargs: 其他参数

        Yields:
            AI 回复内容片段
        """
        # 设置默认模型
        if model is None:
            model = self._get_default_model()

        # 使用传入�?base_url 或实例的 base_url
        base_url = base_url or self.base_url
        # 使用传入�?group_id 或实例的 group_id
        group_id = group_id or self.group_id

        if self.coding_mode:
            default_params = self._get_default_params()
            kwargs = {**default_params, **kwargs}

        client = get_http_client(timeout=120.0)

        try:
            async with client.stream(
                "POST",
                f"{base_url}/text/chatcompletion_v2",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    **kwargs
                },
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0]["delta"]
                            # MiniMax-M2.5 等推理模型返�?reasoning_content
                            content = delta.get("content", "") or delta.get("reasoning_content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

        except httpx.HTTPStatusError as e:
            error_detail = "Unknown error"
            try:
                error_body = e.response.json()
                error_detail = error_body.get("message", error_body.get("error", str(error_body)))
            except Exception:
                error_detail = e.response.text or f"HTTP {e.response.status_code}"
            
            logger.error(f"Minimax 流式调用失败 ({e.response.status_code}): {error_detail}")
            
            if e.response.status_code == 401:
                raise ValueError(f"API Key 认证失败：请检�?API Key �?Group ID 是否正确。详情：{error_detail}")
            elif e.response.status_code == 403:
                raise ValueError(f"权限不足：{error_detail}。请检�?API Key 权限或套餐是否有效�?)
            elif e.response.status_code == 429:
                raise ValueError(f"请求过于频繁，请稍后重试。详情：{error_detail}")
            else:
                raise ValueError(f"Minimax 流式调用失败 ({e.response.status_code}): {error_detail}")
        except httpx.RequestError as e:
            logger.error(f"Minimax 网络连接失败：{e}")
            raise ValueError(f"网络连接失败：{str(e)}。请检查网络连接或代理设置�?)
        except Exception as e:
            logger.error(f"Minimax 流式调用失败：{e}")
            raise

    async def models(self, api_key: str) -> List[str]:
        """获取可用模型列表"""
        return ["MiniMax-Text-01", "MiniMax-M2.5", "MiniMax-M2.5-highspeed", "abab6.5s-chat", "abab6.5g-chat"]
    
    async def test_connection(self, api_key: str, group_id: str = "", base_url: str = "") -> bool:
        """测试 API Key 连接是否有效"""
        try:
            await self.chat(
                messages=[{"role": "user", "content": "Hi"}],
                model=self._get_default_model(),
                api_key=api_key,
                group_id=group_id or self.group_id,
                base_url=base_url or self.base_url,
                max_tokens=10
            )
            return True
        except Exception:
            raise


class GLMProvider(AIProvider):
    """智谱 GLM 适配�?""

    def __init__(self):
        self.base_url = "https://open.bigmodel.cn/api/paas/v4"

    async def chat(
        self,
        messages: List[Dict],
        model: str = "glm-4",
        api_key: str = "",
        **kwargs
    ) -> str:
        client = get_http_client(timeout=60.0)
        
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
                        **kwargs
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                error_detail = "Unknown error"
                try:
                    error_body = e.response.json()
                    error_detail = error_body.get("message", error_body.get("error", str(error_body)))
                except Exception:
                    error_detail = e.response.text or f"HTTP {e.response.status_code}"
                
                logger.error(f"GLM API 错误 ({e.response.status_code}): {error_detail}")
                
                if e.response.status_code == 401:
                    raise ValueError(f"API Key 认证失败：请检查智�?GLM API Key 是否正确。详情：{error_detail}")
                elif e.response.status_code == 403:
                    raise ValueError(f"权限不足：{error_detail}。请检�?API Key 权限或账户余额�?)
                elif e.response.status_code == 429:
                    raise ValueError(f"请求过于频繁，请稍后重试。详情：{error_detail}")
                else:
                    raise ValueError(f"GLM API 调用失败 ({e.response.status_code}): {error_detail}")
            except httpx.RequestError as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                raise
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                raise
        
        raise ValueError("请求重试失败")

    async def stream(
        self,
        messages: List[Dict],
        model: str = "glm-4",
        api_key: str = "",
        **kwargs
    ) -> AsyncGenerator[str, None]:
        client = get_http_client(timeout=120.0)
        
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
                    **kwargs
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            content = chunk["choices"][0]["delta"].get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError) as e:
                            logger.debug(f"解析响应失败：{e}")
                            continue
        except httpx.HTTPStatusError as e:
            error_detail = "Unknown error"
            try:
                error_body = e.response.json()
                error_detail = error_body.get("message", error_body.get("error", str(error_body)))
            except Exception:
                error_detail = e.response.text or f"HTTP {e.response.status_code}"
            
            logger.error(f"GLM 流式调用失败 ({e.response.status_code}): {error_detail}")
            
            if e.response.status_code == 401:
                raise ValueError(f"API Key 认证失败：请检查智�?GLM API Key 是否正确。详情：{error_detail}")
            elif e.response.status_code == 403:
                raise ValueError(f"权限不足：{error_detail}。请检�?API Key 权限或账户余额�?)
            elif e.response.status_code == 429:
                raise ValueError(f"请求过于频繁，请稍后重试。详情：{error_detail}")
            else:
                raise ValueError(f"GLM 流式调用失败 ({e.response.status_code}): {error_detail}")
        except httpx.RequestError as e:
            logger.error(f"GLM 网络连接失败：{e}")
            raise ValueError(f"网络连接失败：{str(e)}。请检查网络连接或代理设置�?)
        except Exception as e:
            logger.error(f"GLM 流式调用失败：{e}")
            raise

    async def models(self, api_key: str) -> List[str]:
        return ["glm-4", "glm-3-turbo", "glm-4v"]
    
    async def test_connection(self, api_key: str) -> bool:
        """测试 API Key 连接是否有效"""
        try:
            await self.chat(
                messages=[{"role": "user", "content": "Hi"}],
                model="glm-3-turbo",
                api_key=api_key,
                max_tokens=10
            )
            return True
        except Exception:
            raise


# 服务商注册表（静态实例，用于无配置场景）
PROVIDERS: Dict[str, AIProvider] = {
    "minimax": MinimaxProvider(coding_mode=False),
    "minimax-coding": MinimaxProvider(coding_mode=True),
    "glm": GLMProvider(),
}


async def get_provider(provider: str, group_id: str = "", base_url: str = "") -> AIProvider:
    """
    获取服务商实�?
    Args:
        provider: 服务商名�?(minimax/minimax-coding/glm)
        group_id: Group ID（可选，用于 Minimax�?        base_url: 自定�?Base URL（可选）

    Returns:
        服务商实�?
    Raises:
        ValueError: 不支持的服务�?    """
    if provider not in PROVIDERS:
        available = ", ".join(PROVIDERS.keys())
        raise ValueError(f"不支持的服务商：{provider}，可选：{available}")

    # 如果�?Minimax 且提供了 group_id �?base_url，创建新实例
    if provider.startswith("minimax") and (group_id or base_url):
        if provider == "minimax":
            return MinimaxProvider(coding_mode=False, group_id=group_id, base_url=base_url)
        elif provider == "minimax-coding":
            return MinimaxProvider(coding_mode=True, group_id=group_id, base_url=base_url)

    return PROVIDERS[provider]


def list_providers() -> List[Dict]:
    """
    列出所有可用的服务�?
    Returns:
        服务商信息列�?    """
    return [
        {
            "id": "minimax",
            "name": "Minimax",
            "description": "国产 AI，中文优化好",
            "models": ["MiniMax-M2.5", "MiniMax-M2.5-highspeed", "MiniMax-Text-01", "abab6.5s-chat", "abab6.5g-chat"],
            "coding_models": ["MiniMax-M2.5", "MiniMax-M2.5-highspeed"]
        },
        {
            "id": "minimax-coding",
            "name": "Minimax Coding",
            "description": "编程专用，代码生�?优化",
            "models": ["MiniMax-M2.5", "MiniMax-M2.5-highspeed", "MiniMax-Text-01", "abab6.5s-chat"],
        },
        {
            "id": "glm",
            "name": "智谱 GLM",
            "description": "智谱 AI，中文能力强",
            "models": ["glm-4", "glm-3-turbo", "glm-4v"],
        },
    ]

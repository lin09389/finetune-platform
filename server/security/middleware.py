"""
安全中间�?- 过滤响应中的敏感数据

功能�?- 响应体脱�?- 请求体日志脱�?- 错误信息脱敏
- 敏感 Header 过滤
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import json
import logging
from typing import List, Set

from .data_masking import data_masker

logger = logging.getLogger(__name__)


class SecurityMiddleware(BaseHTTPMiddleware):
    """安全中间�?""

    # 需要脱敏的响应字段
    SENSITIVE_FIELDS: Set[str] = {
        'api_key', 'apikey', 'api-key', 'token', 'secret', 'credential',
        'password', 'passwd', 'pwd', 'private_key', 'access_token',
        'refresh_token', 'auth_token', 'session_id', 'encrypted'
    }

    # 需要脱敏的 Header
    SENSITIVE_HEADERS: Set[str] = {
        'authorization', 'cookie', 'set-cookie', 'x-api-key',
        'x-auth-token', 'x-access-token'
    }

    # 需要脱敏的 URL 参数
    SENSITIVE_PARAMS: Set[str] = {
        'api_key', 'apikey', 'token', 'secret', 'password', 'key'
    }

    def __init__(self, app: ASGIApp, enabled: bool = True):
        """
        初始化安全中间件

        Args:
            app: FastAPI 应用
            enabled: 是否启用中间�?        """
        super().__init__(app)
        self.enabled = enabled
        logger.info(f"安全中间件已{'启用' if self.enabled else '禁用'}")

    async def dispatch(self, request: Request, call_next):
        """处理请求"""
        # 记录请求（脱敏后�?        self._log_request(request)

        # 处理请求
        try:
            response = await call_next(request)
        except Exception as e:
            # 错误信息脱敏
            error_msg = self._mask_error(str(e))
            logger.error(f"请求处理错误：{error_msg}")
            raise

        # 记录响应（脱敏后�?        self._log_response(request, response)

        return response

    def _log_request(self, request: Request):
        """记录请求日志（脱敏）"""
        # 脱敏 URL 参数
        query_params = dict(request.query_params)
        masked_params = data_masker.mask_dict(query_params)

        # 脱敏 Headers
        headers = dict(request.headers)
        masked_headers = self._mask_headers(headers)

        logger.info(
            f"请求：{request.method} {request.url.path} "
            f"params={json.dumps(masked_params, ensure_ascii=False)} "
            f"headers={json.dumps(masked_headers, ensure_ascii=False)}"
        )

    def _log_response(self, request: Request, response: Response):
        """记录响应日志（脱敏）"""
        # 脱敏响应 Headers
        headers = dict(response.headers)
        masked_headers = self._mask_headers(headers)

        logger.info(
            f"响应：{request.method} {request.url.path} "
            f"status={response.status_code} "
            f"headers={json.dumps(masked_headers, ensure_ascii=False)}"
        )

    def _mask_headers(self, headers: dict) -> dict:
        """脱敏 Headers"""
        masked = {}
        for key, value in headers.items():
            key_lower = key.lower()
            if key_lower in self.SENSITIVE_HEADERS:
                # 完全隐藏敏感 Header
                masked[key] = '[MASKED]'
            else:
                # 检查值中是否包含敏感信息
                masked_value = data_masker.mask_text(value)
                masked[key] = masked_value if masked_value != value else value
        return masked

    def _mask_error(self, error_msg: str) -> str:
        """脱敏错误信息"""
        return data_masker.mask_text(error_msg)

    def mask_response_data(self, data: dict) -> dict:
        """
        脱敏响应数据

        Args:
            data: 响应数据

        Returns:
            脱敏后的数据
        """
        if not self.enabled:
            return data

        return data_masker.mask_dict(data)


class ResponseMaskingMiddleware(BaseHTTPMiddleware):
    """
    响应脱敏中间�?
    专门用于处理 JSON 响应体的脱敏
    """

    def __init__(self, app: ASGIApp, sensitive_fields: Set[str] = None):
        """
        初始化响应脱敏中间件

        Args:
            app: FastAPI 应用
            sensitive_fields: 额外需要脱敏的字段
        """
        super().__init__(app)
        self.sensitive_fields = sensitive_fields or set()
        logger.info("响应脱敏中间件已初始�?)

    async def dispatch(self, request: Request, call_next):
        """处理请求"""
        response = await call_next(request)

        # 只处�?JSON 响应
        content_type = response.headers.get('content-type', '')
        if 'application/json' not in content_type:
            return response

        # 读取响应�?        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        # 脱敏处理
        try:
            if body:
                data = json.loads(body.decode('utf-8'))
                masked_data = self._mask_data(data)

                # 重新构建响应�?                new_body = json.dumps(masked_data, ensure_ascii=False).encode('utf-8')

                # 更新内容长度
                response.headers['content-length'] = str(len(new_body))

                # 重新设置响应体迭代器
                response.body_iterator = self._async_iter([new_body])
        except json.JSONDecodeError:
            # 不是有效 JSON，跳�?            pass
        except Exception as e:
            logger.warning(f"响应脱敏失败：{e}")

        return response

    def _mask_data(self, data):
        """递归脱敏数据"""
        if isinstance(data, dict):
            return self._mask_dict(data)
        elif isinstance(data, list):
            return [self._mask_data(item) for item in data]
        elif isinstance(data, str):
            return data_masker.mask_text(data)
        return data

    def _mask_dict(self, data: dict) -> dict:
        """脱敏字典"""
        result = {}
        for key, value in data.items():
            key_lower = key.lower()

            # 检查是否是敏感字段
            if key_lower in self.SENSITIVE_FIELDS or key_lower in self.sensitive_fields:
                if isinstance(value, str) and value:
                    result[key] = data_masker.mask_api_key(value)
                else:
                    result[key] = '[MASKED]'
            elif isinstance(value, dict):
                result[key] = self._mask_dict(value)
            elif isinstance(value, list):
                result[key] = [self._mask_data(item) for item in value]
            else:
                result[key] = value

        return result

    async def _async_iter(self, items):
        """异步迭代�?""
        for item in items:
            yield item


def create_security_middleware(app: ASGIApp, enabled: bool = True) -> SecurityMiddleware:
    """创建安全中间�?""
    return SecurityMiddleware(app, enabled=enabled)


def create_response_masking_middleware(
    app: ASGIApp,
    additional_fields: Set[str] = None
) -> ResponseMaskingMiddleware:
    """创建响应脱敏中间�?""
    return ResponseMaskingMiddleware(app, sensitive_fields=additional_fields)

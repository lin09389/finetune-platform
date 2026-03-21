# -*- coding: utf-8 -*-
"""
安全中间件 - 过滤响应中的敏感数据

功能：
- 响应体脱敏
- 请求体日志脱敏
- 错误信息脱敏
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
    """安全中间件"""

    SENSITIVE_FIELDS: Set[str] = {
        'api_key', 'apikey', 'api-key', 'token', 'secret', 'credential',
        'password', 'passwd', 'pwd', 'private_key', 'access_token',
        'refresh_token', 'auth_token', 'session_id', 'encrypted'
    }

    SENSITIVE_HEADERS: Set[str] = {
        'authorization', 'cookie', 'set-cookie', 'x-api-key',
        'x-auth-token', 'x-access-token'
    }

    SENSITIVE_PARAMS: Set[str] = {
        'api_key', 'apikey', 'token', 'secret', 'password', 'key'
    }

    def __init__(self, app: ASGIApp, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        logger.info(f"安全中间件已{'启用' if self.enabled else '禁用'}")

    async def dispatch(self, request: Request, call_next):
        self._log_request(request)

        try:
            response = await call_next(request)
        except Exception as e:
            error_msg = self._mask_error(str(e))
            logger.error(f"请求处理错误：{error_msg}")
            raise

        self._log_response(request, response)

        return response

    def _log_request(self, request: Request):
        query_params = dict(request.query_params)
        masked_params = data_masker.mask_dict(query_params)

        headers = dict(request.headers)
        masked_headers = self._mask_headers(headers)

        logger.info(
            f"请求：{request.method} {request.url.path} "
            f"params={json.dumps(masked_params, ensure_ascii=False)} "
            f"headers={json.dumps(masked_headers, ensure_ascii=False)}"
        )

    def _log_response(self, request: Request, response: Response):
        headers = dict(response.headers)
        masked_headers = self._mask_headers(headers)

        logger.info(
            f"响应：{request.method} {request.url.path} "
            f"status={response.status_code} "
            f"headers={json.dumps(masked_headers, ensure_ascii=False)}"
        )

    def _mask_headers(self, headers: dict) -> dict:
        masked = {}
        for key, value in headers.items():
            key_lower = key.lower()
            if key_lower in self.SENSITIVE_HEADERS:
                masked[key] = '[MASKED]'
            else:
                masked_value = data_masker.mask_text(value)
                masked[key] = masked_value if masked_value != value else value
        return masked

    def _mask_error(self, error_msg: str) -> str:
        return data_masker.mask_text(error_msg)

    def mask_response_data(self, data: dict) -> dict:
        if not self.enabled:
            return data

        return data_masker.mask_dict(data)


class ResponseMaskingMiddleware(BaseHTTPMiddleware):
    """响应脱敏中间件"""

    def __init__(self, app: ASGIApp, sensitive_fields: Set[str] = None):
        super().__init__(app)
        self.sensitive_fields = sensitive_fields or set()
        logger.info("响应脱敏中间件已初始化")

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        content_type = response.headers.get('content-type', '')
        if 'application/json' not in content_type:
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        try:
            if body:
                data = json.loads(body.decode('utf-8'))
                masked_data = self._mask_data(data)

                new_body = json.dumps(masked_data, ensure_ascii=False).encode('utf-8')

                response.headers['content-length'] = str(len(new_body))

                response.body_iterator = self._async_iter([new_body])
        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.warning(f"响应脱敏失败：{e}")

        return response

    def _mask_data(self, data):
        if isinstance(data, dict):
            return self._mask_dict(data)
        elif isinstance(data, list):
            return [self._mask_data(item) for item in data]
        elif isinstance(data, str):
            return data_masker.mask_text(data)
        return data

    def _mask_dict(self, data: dict) -> dict:
        result = {}
        for key, value in data.items():
            key_lower = key.lower()

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
        for item in items:
            yield item


def create_security_middleware(app: ASGIApp, enabled: bool = True) -> SecurityMiddleware:
    return SecurityMiddleware(app, enabled=enabled)


def create_response_masking_middleware(
    app: ASGIApp,
    additional_fields: Set[str] = None
) -> ResponseMaskingMiddleware:
    return ResponseMaskingMiddleware(app, sensitive_fields=additional_fields)

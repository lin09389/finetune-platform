# -*- coding: utf-8 -*-
"""
数据脱敏模块 - 保护敏感信息

功能：
- API Key 脱敏（保留首尾字符）
- 密码脱敏（固定长度星号）
- 邮箱脱敏（保留前后缀）
- 手机号脱敏（保留前后 3 位）
- IP 地址脱敏（保留前两段）
- 自定义正则脱敏
- 递归字典/列表脱敏

脱敏规则：
- 生产环境：严格脱敏
- 开发环境：可选择性脱敏
"""
import re
import os
from typing import Any, Dict, List, Optional, Set, Union
from functools import lru_cache


class DataMasker:
    """数据脱敏器"""

    MASK_FULL = 'full'
    MASK_PARTIAL = 'partial'
    MASK_NONE = 'none'

    def __init__(self, mode: str = None):
        if mode is None:
            mode = os.environ.get('SECURITY_MASK_MODE', 'auto')

        if mode == 'auto':
            is_prod = os.environ.get('ENVIRONMENT', 'development') == 'production'
            self.mode = self.MASK_FULL if is_prod else self.MASK_PARTIAL
        elif mode == 'strict':
            self.mode = self.MASK_FULL
        elif mode == 'permissive':
            self.mode = self.MASK_PARTIAL
        else:
            self.mode = mode

        self.mask_char = '*'
        self._compile_patterns()

    def _compile_patterns(self):
        self.api_key_patterns = [
            re.compile(r'(group_id["\s:=]+)([a-zA-Z0-9]{10,})(:[a-zA-Z0-9]{20,})', re.IGNORECASE),
            re.compile(r'(api[_-]?key|apikey)["\s:=]+([a-zA-Z0-9\-_]{20,})', re.IGNORECASE),
            re.compile(r'\b(sk-[a-zA-Z0-9]{20,})\b', re.IGNORECASE),
            re.compile(r'(bearer|token)["\s:=]+([a-zA-Z0-9\-_\.]{20,})', re.IGNORECASE),
            re.compile(r'(authorization["\s:=]+)(bearer\s+)?([a-zA-Z0-9\-_\.]{20,})', re.IGNORECASE),
        ]

        self.password_patterns = [
            re.compile(r'(password|passwd|pwd|secret)["\s:=]+([^\s,}\]"]{4,})', re.IGNORECASE),
        ]

        self.email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        self.phone_pattern = re.compile(r'1[3-9]\d{9}')
        self.ip_pattern = re.compile(r'\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b')

        self.secret_patterns = [
            re.compile(r'(-----BEGIN\s+(?:RSA\s+)?(?:PRIVATE\s+)?KEY-----)', re.IGNORECASE),
            re.compile(r'(ghp_[a-zA-Z0-9]{36})', re.IGNORECASE),
        ]

    def mask_api_key(self, api_key: str, keep_chars: int = 4) -> str:
        if not api_key or len(api_key) <= keep_chars * 2:
            return self.mask_char * 8

        if ':' in api_key:
            parts = api_key.split(':')
            if len(parts) == 2:
                group_id, key = parts
                masked_key = key[:keep_chars] + self.mask_char * (len(key) - keep_chars * 2) + key[-keep_chars:]
                return self.mask_char * len(group_id) + ':' + masked_key

        return api_key[:keep_chars] + self.mask_char * (len(api_key) - keep_chars * 2) + api_key[-keep_chars:]

    def mask_password(self, password: str) -> str:
        if not password:
            return self.mask_char * 8
        return self.mask_char * len(password)

    def mask_email(self, email: str) -> str:
        if not email or '@' not in email:
            return self.mask_char * 8

        parts = email.split('@')
        if len(parts) != 2:
            return self.mask_char * 8

        local, domain = parts
        if len(local) <= 2:
            masked_local = self.mask_char * len(local)
        else:
            masked_local = local[:2] + self.mask_char * (len(local) - 2)

        return f"{masked_local}@{domain}"

    def mask_phone(self, phone: str) -> str:
        if not phone or len(phone) < 7:
            return self.mask_char * 11

        return phone[:3] + self.mask_char * 4 + phone[-4:]

    def mask_ip(self, ip: str) -> str:
        if not ip:
            return self.mask_char * 8

        parts = ip.split('.')
        if len(parts) != 4:
            return self.mask_char * 8

        return f"{parts[0]}.{parts[1]}.*.*"

    def mask_text(self, text: str) -> str:
        if not text:
            return text

        result = text

        for pattern in self.api_key_patterns:
            def replace_api_key(match):
                groups = match.groups()
                if len(groups) == 1:
                    return self.mask_api_key(groups[0])
                if len(groups) >= 2:
                    prefix = groups[0]
                    key = groups[-1] if groups[-1] else groups[1]
                    return prefix + self.mask_api_key(key.lstrip(':').lstrip())
                return match.group(0)
            result = pattern.sub(replace_api_key, result)

        for pattern in self.password_patterns:
            def replace_password(match):
                groups = match.groups()
                if len(groups) >= 2:
                    return groups[0] + self.mask_password(groups[1])
                return match.group(0)
            result = pattern.sub(replace_password, result)

        result = self.email_pattern.sub(lambda m: self.mask_email(m.group(0)), result)
        result = self.phone_pattern.sub(lambda m: self.mask_phone(m.group(0)), result)
        result = self.ip_pattern.sub(lambda m: self.mask_ip(m.group(0)), result)

        for pattern in self.secret_patterns:
            def replace_secret(match):
                secret = match.group(0)
                if secret.startswith('-----'):
                    return '[CERTIFICATE_MASKED]'
                return self.mask_api_key(secret)
            result = pattern.sub(replace_secret, result)

        return result

    def mask_value(self, value: Any, key_name: str = "") -> Any:
        key_lower = key_name.lower() if key_name else ""

        if any(k in key_lower for k in ['api_key', 'apikey', 'api-key', 'token', 'secret', 'credential']):
            return self.mask_api_key(str(value)) if value else value

        if any(k in key_lower for k in ['password', 'passwd', 'pwd', 'secret']):
            return self.mask_password(str(value)) if value else value

        if 'email' in key_lower and isinstance(value, str):
            return self.mask_email(value)

        if any(k in key_lower for k in ['phone', 'mobile', 'tel']) and isinstance(value, str):
            return self.mask_phone(value)

        if any(k in key_lower for k in ['ip', 'address']) and isinstance(value, str):
            return self.mask_ip(value)

        return value

    def mask_dict(self, data: Dict[str, Any], sensitive_keys: Optional[Set[str]] = None) -> Dict[str, Any]:
        if not data:
            return data

        default_sensitive = {
            'api_key', 'apikey', 'api-key', 'token', 'secret', 'credential',
            'password', 'passwd', 'pwd', 'private_key', 'access_token',
            'refresh_token', 'auth_token', 'session_id'
        }

        if sensitive_keys:
            default_sensitive.update(sensitive_keys)

        result = {}
        for key, value in data.items():
            key_lower = key.lower()

            if isinstance(value, dict):
                result[key] = self.mask_dict(value, sensitive_keys)
            elif isinstance(value, list):
                result[key] = self.mask_list(value, key, sensitive_keys)
            elif key_lower in default_sensitive or any(k in key_lower for k in default_sensitive):
                result[key] = self.mask_value(value, key)
            elif isinstance(value, str) and len(value) > 20:
                masked = self.mask_text(value)
                result[key] = masked if masked != value else value
            else:
                result[key] = value

        return result

    def mask_list(self, data: List[Any], parent_key: str = "", sensitive_keys: Optional[Set[str]] = None) -> List[Any]:
        if not data:
            return data

        result = []
        for item in data:
            if isinstance(item, dict):
                result.append(self.mask_dict(item, sensitive_keys))
            elif isinstance(item, list):
                result.append(self.mask_list(item, parent_key, sensitive_keys))
            elif isinstance(item, str):
                masked = self.mask_text(item)
                result.append(masked if masked != item else item)
            else:
                result.append(item)

        return result

    def mask(self, data: Any) -> Any:
        if data is None:
            return None

        if isinstance(data, dict):
            return self.mask_dict(data)
        elif isinstance(data, list):
            return self.mask_list(data)
        elif isinstance(data, str):
            return self.mask_text(data)
        else:
            return data

    @lru_cache(maxsize=100)
    def is_sensitive_key(self, key: str) -> bool:
        key_lower = key.lower()
        sensitive_keywords = {
            'api_key', 'apikey', 'token', 'secret', 'password', 'passwd',
            'credential', 'private', 'auth', 'session', 'cookie'
        }
        return any(k in key_lower for k in sensitive_keywords)


data_masker = DataMasker()


def mask(data: Any) -> Any:
    return data_masker.mask(data)


def mask_text(text: str) -> str:
    return data_masker.mask_text(text)


def mask_api_key(api_key: str) -> str:
    return data_masker.mask_api_key(api_key)


def mask_password(password: str) -> str:
    return data_masker.mask_password(password)

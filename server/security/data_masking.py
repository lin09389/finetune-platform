"""
数据脱敏模块 - 保护敏感信息

功能�?- API Key 脱敏（保留首尾字符）
- 密码脱敏（固定长度星号）
- 邮箱脱敏（保留前后缀�?- 手机号脱敏（保留前后 3 位）
- IP 地址脱敏（保留前两段�?- 自定义正则脱�?- 递归字典/列表脱敏

脱敏规则�?- 生产环境：严格脱�?- 开发环境：可选择性脱�?"""
import re
import os
from typing import Any, Dict, List, Optional, Set, Union
from functools import lru_cache


class DataMasker:
    """数据脱敏�?""

    # 脱敏模式
    MASK_FULL = 'full'  # 完全隐藏
    MASK_PARTIAL = 'partial'  # 部分隐藏（保留首尾）
    MASK_NONE = 'none'  # 不脱敏（仅开�?调试模式�?
    def __init__(self, mode: str = None):
        """
        初始化脱敏器

        Args:
            mode: 脱敏模式（auto/strict/permissive�?                  auto: 根据环境变量自动选择
                  strict: 严格脱敏（生产环境）
                  permissive: 宽松模式（开发环境，仅日志脱敏）
        """
        if mode is None:
            mode = os.environ.get('SECURITY_MASK_MODE', 'auto')

        if mode == 'auto':
            # 根据环境变量判断
            is_prod = os.environ.get('ENVIRONMENT', 'development') == 'production'
            self.mode = self.MASK_FULL if is_prod else self.MASK_PARTIAL
        elif mode == 'strict':
            self.mode = self.MASK_FULL
        elif mode == 'permissive':
            self.mode = self.MASK_PARTIAL
        else:
            self.mode = mode

        # 脱敏字符
        self.mask_char = '*'

        # 预编译正则表达式（提高性能�?        self._compile_patterns()

    def _compile_patterns(self):
        """预编译正则表达式"""
        # API Key 模式（各种格式）
        self.api_key_patterns = [
            # MiniMax 格式：group_id:api_key
            re.compile(r'(group_id["\s:=]+)([a-zA-Z0-9]{10,})(:[a-zA-Z0-9]{20,})', re.IGNORECASE),
            # 通用 API Key（包�?sk-前缀�?            re.compile(r'(api[_-]?key|apikey)["\s:=]+([a-zA-Z0-9\-_]{20,})', re.IGNORECASE),
            # OpenAI 风格 sk-xxx
            re.compile(r'\b(sk-[a-zA-Z0-9]{20,})\b', re.IGNORECASE),
            # Bearer Token
            re.compile(r'(bearer|token)["\s:=]+([a-zA-Z0-9\-_\.]{20,})', re.IGNORECASE),
            # Authorization Header
            re.compile(r'(authorization["\s:=]+)(bearer\s+)?([a-zA-Z0-9\-_\.]{20,})', re.IGNORECASE),
        ]

        # 密码模式
        self.password_patterns = [
            re.compile(r'(password|passwd|pwd|secret)["\s:=]+([^\s,}\]"]{4,})', re.IGNORECASE),
        ]

        # 邮箱模式
        self.email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

        # 手机号模式（中国�?        self.phone_pattern = re.compile(r'1[3-9]\d{9}')

        # IP 地址模式
        self.ip_pattern = re.compile(r'\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b')

        # 密钥/证书模式
        self.secret_patterns = [
            re.compile(r'(-----BEGIN\s+(?:RSA\s+)?(?:PRIVATE\s+)?KEY-----)', re.IGNORECASE),
            re.compile(r'(ghp_[a-zA-Z0-9]{36})', re.IGNORECASE),  # GitHub Token
        ]

    def mask_api_key(self, api_key: str, keep_chars: int = 4) -> str:
        """
        脱敏 API Key

        Args:
            api_key: API Key 原文
            keep_chars: 保留的首尾字符数

        Returns:
            脱敏后的 API Key
        """
        if not api_key or len(api_key) <= keep_chars * 2:
            return self.mask_char * 8

        # 处理 group_id:api_key 格式
        if ':' in api_key:
            parts = api_key.split(':')
            if len(parts) == 2:
                group_id, key = parts
                # group_id 完全隐藏，key 部分隐藏
                masked_key = key[:keep_chars] + self.mask_char * (len(key) - keep_chars * 2) + key[-keep_chars:]
                return self.mask_char * len(group_id) + ':' + masked_key

        # 普�?API Key
        return api_key[:keep_chars] + self.mask_char * (len(api_key) - keep_chars * 2) + api_key[-keep_chars:]

    def mask_password(self, password: str) -> str:
        """脱敏密码"""
        if not password:
            return self.mask_char * 8
        return self.mask_char * len(password)

    def mask_email(self, email: str) -> str:
        """
        脱敏邮箱

        规则：保留前 2 位和后缀
        例：user@example.com �?us**@example.com
        """
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
        """
        脱敏手机�?
        规则：保留前 3 位和�?4 �?        例：13812345678 �?138****5678
        """
        if not phone or len(phone) < 7:
            return self.mask_char * 11

        return phone[:3] + self.mask_char * 4 + phone[-4:]

    def mask_ip(self, ip: str) -> str:
        """
        脱敏 IP 地址

        规则：保留前两段
        例：192.168.1.100 �?192.168.*.*
        """
        if not ip:
            return self.mask_char * 8

        parts = ip.split('.')
        if len(parts) != 4:
            return self.mask_char * 8

        return f"{parts[0]}.{parts[1]}.*.*"

    def mask_text(self, text: str) -> str:
        """
        脱敏文本中的所有敏感信�?
        Args:
            text: 原始文本

        Returns:
            脱敏后的文本
        """
        if not text:
            return text

        result = text

        # 脱敏 API Key
        for pattern in self.api_key_patterns:
            def replace_api_key(match):
                groups = match.groups()
                # 处理 sk-xxx 格式（只�?1 组）
                if len(groups) == 1:
                    return self.mask_api_key(groups[0])
                # 处理其他格式（多组）
                if len(groups) >= 2:
                    prefix = groups[0]
                    key = groups[-1] if groups[-1] else groups[1]
                    return prefix + self.mask_api_key(key.lstrip(':').lstrip())
                return match.group(0)
            result = pattern.sub(replace_api_key, result)

        # 脱敏密码
        for pattern in self.password_patterns:
            def replace_password(match):
                groups = match.groups()
                if len(groups) >= 2:
                    return groups[0] + self.mask_password(groups[1])
                return match.group(0)
            result = pattern.sub(replace_password, result)

        # 脱敏邮箱
        result = self.email_pattern.sub(lambda m: self.mask_email(m.group(0)), result)

        # 脱敏手机�?        result = self.phone_pattern.sub(lambda m: self.mask_phone(m.group(0)), result)

        # 脱敏 IP
        result = self.ip_pattern.sub(lambda m: self.mask_ip(m.group(0)), result)

        # 脱敏密钥/证书
        for pattern in self.secret_patterns:
            def replace_secret(match):
                secret = match.group(0)
                if secret.startswith('-----'):
                    return '[CERTIFICATE_MASKED]'
                return self.mask_api_key(secret)
            result = pattern.sub(replace_secret, result)

        return result

    def mask_value(self, value: Any, key_name: str = "") -> Any:
        """
        根据键名脱敏�?
        Args:
            value: �?            key_name: 键名（用于判断脱敏类型）

        Returns:
            脱敏后的�?        """
        key_lower = key_name.lower() if key_name else ""

        # 判断脱敏类型
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
        """
        递归脱敏字典

        Args:
            data: 原始字典
            sensitive_keys: 额外需要脱敏的键名集合

        Returns:
            脱敏后的字典
        """
        if not data:
            return data

        # 默认敏感�?        default_sensitive = {
            'api_key', 'apikey', 'api-key', 'token', 'secret', 'credential',
            'password', 'passwd', 'pwd', 'private_key', 'access_token',
            'refresh_token', 'auth_token', 'session_id'
        }

        if sensitive_keys:
            default_sensitive.update(sensitive_keys)

        result = {}
        for key, value in data.items():
            key_lower = key.lower()

            # 递归处理嵌套字典
            if isinstance(value, dict):
                result[key] = self.mask_dict(value, sensitive_keys)
            # 递归处理列表
            elif isinstance(value, list):
                result[key] = self.mask_list(value, key, sensitive_keys)
            # 检查是否是敏感�?            elif key_lower in default_sensitive or any(k in key_lower for k in default_sensitive):
                result[key] = self.mask_value(value, key)
            # 检查值是否是敏感文本
            elif isinstance(value, str) and len(value) > 20:
                # 长字符串可能包含敏感信息，检查并脱敏
                masked = self.mask_text(value)
                result[key] = masked if masked != value else value
            else:
                result[key] = value

        return result

    def mask_list(self, data: List[Any], parent_key: str = "", sensitive_keys: Optional[Set[str]] = None) -> List[Any]:
        """递归脱敏列表"""
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
        """
        智能脱敏任意数据

        Args:
            data: 任意数据

        Returns:
            脱敏后的数据
        """
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
        """判断键名是否敏感"""
        key_lower = key.lower()
        sensitive_keywords = {
            'api_key', 'apikey', 'token', 'secret', 'password', 'passwd',
            'credential', 'private', 'auth', 'session', 'cookie'
        }
        return any(k in key_lower for k in sensitive_keywords)


# 全局单例
data_masker = DataMasker()


# 便捷函数
def mask(data: Any) -> Any:
    """脱敏数据"""
    return data_masker.mask(data)


def mask_text(text: str) -> str:
    """脱敏文本"""
    return data_masker.mask_text(text)


def mask_api_key(api_key: str) -> str:
    """脱敏 API Key"""
    return data_masker.mask_api_key(api_key)


def mask_password(password: str) -> str:
    """脱敏密码"""
    return data_masker.mask_password(password)

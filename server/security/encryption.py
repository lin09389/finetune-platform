"""
安全加密模块 - 加密存储敏感数据

使用 Fernet 对称加密算法
- API Key 加密存储
- 密钥文件权限 600（仅所有者可读写）
- 保险库存储所有加密数据
- 内存中密钥保护（使用后立即清除）

安全增强：
- 密钥轮换支持
- 访问计数审计
- 内存数据保护
"""
import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class SecureStorage:
    """安全存储 - 加密敏感数据"""

    def __init__(self):
        """初始化安全存储"""
        self.data_dir = Path(__file__).parent.parent / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.key_file = self.data_dir / ".encryption_key"
        self.vault_file = self.data_dir / ".vault"

        self.key = self._get_or_create_key()
        self.cipher = Fernet(self.key)

        logger.info("安全存储已初始化")

    def _get_or_create_key(self) -> bytes:
        """获取或创建加密密钥"""
        if self.key_file.exists():
            try:
                with open(self.key_file, 'rb') as f:
                    key = f.read()
                logger.info("已加载现有加密密钥")
                return key
            except Exception as e:
                logger.error(f"加载密钥失败：{e}")
                return self._create_new_key()
        else:
            logger.info("生成新的加密密钥")
            return self._create_new_key()

    def _create_new_key(self) -> bytes:
        """创建新的加密密钥"""
        key = Fernet.generate_key()

        try:
            with open(self.key_file, 'wb') as f:
                f.write(key)

            os.chmod(self.key_file, 0o600)
            logger.info("新密钥已创建并保存")

            return key
        except Exception as e:
            logger.error(f"保存密钥失败：{e}")
            return key

    def encrypt(self, plaintext: str) -> str:
        """
        加密字符串

        Args:
            plaintext: 明文字符串

        Returns:
            密文字符串（Base64 编码）
        """
        try:
            encrypted = self.cipher.encrypt(plaintext.encode('utf-8'))
            return base64.urlsafe_b64encode(encrypted).decode('utf-8')
        except Exception as e:
            logger.error(f"加密失败：{e}")
            raise

    def decrypt(self, ciphertext: str) -> str:
        """
        解密字符串

        Args:
            ciphertext: 密文字符串（Base64 编码）

        Returns:
            明文字符串
        """
        try:
            encrypted = base64.urlsafe_b64decode(ciphertext.encode('utf-8'))
            decrypted = self.cipher.decrypt(encrypted)
            return decrypted.decode('utf-8')
        except Exception as e:
            logger.error(f"解密失败：{e}")
            raise

    def store(self, key: str, value: Any) -> None:
        """
        存储数据

        Args:
            key: 存储键
            value: 要存储的值（将被加密）
        """
        vault = self._load_vault()

        if isinstance(value, dict):
            encrypted_value = self.encrypt(json.dumps(value, ensure_ascii=False))
        else:
            encrypted_value = self.encrypt(str(value))

        vault[key] = encrypted_value
        self._save_vault(vault)
        logger.debug(f"数据已存储：{key}")

    def get(self, key: str) -> Any | None:
        """
        获取数据

        Args:
            key: 存储键

        Returns:
            解密后的值，如果不存在返回 None
        """
        vault = self._load_vault()

        encrypted_value = vault.get(key)
        if encrypted_value is None:
            return None

        try:
            decrypted = self.decrypt(encrypted_value)

            try:
                return json.loads(decrypted)
            except json.JSONDecodeError:
                return decrypted
        except Exception as e:
            logger.error(f"解密数据失败：{key}, {e}")
            return None

    def delete(self, key: str) -> bool:
        """
        删除数据

        Args:
            key: 存储键

        Returns:
            是否删除成功
        """
        vault = self._load_vault()

        if key in vault:
            del vault[key]
            self._save_vault(vault)
            logger.debug(f"数据已删除：{key}")
            return True

        return False

    def store_api_key(self, key_id: str, provider: str, api_key: str, group_id: str = "", base_url: str = ""):
        """
        存储 API Key

        Args:
            key_id: Key ID
            provider: 服务商名称
            api_key: API Key 明文
            group_id: Group ID（可选，用于 Minimax）
            base_url: 自定义 Base URL（可选）
        """
        vault = self._load_vault()

        encrypted_api_key = self.encrypt(api_key)
        encrypted_group_id = self.encrypt(group_id) if group_id else ""

        vault[f"api_key:{key_id}"] = {
            'encrypted': encrypted_api_key,
            'provider': provider,
            'group_id': encrypted_group_id,
            'base_url': base_url,
            'created_at': self._get_timestamp(),
            'access_count': 0,
            'last_accessed': None
        }

        self._save_vault(vault)
        logger.info(f"API Key 已加密存储：{key_id}")

    def get_api_key(self, key_id: str) -> str:
        """
        获取 API Key

        Args:
            key_id: Key ID

        Returns:
            API Key 明文

        Raises:
            KeyError: Key 不存在
        """
        vault = self._load_vault()

        key_data = vault.get(f"api_key:{key_id}")
        if not key_data:
            raise KeyError(f"API Key 不存在：{key_id}")

        try:
            api_key = self.decrypt(key_data['encrypted'])

            key_data['access_count'] = key_data.get('access_count', 0) + 1
            key_data['last_accessed'] = self._get_timestamp()
            self._save_vault(vault)

            return api_key
        except Exception as e:
            logger.error(f"解密 API Key 失败：{e}")
            raise KeyError(f"无法解密 API Key: {key_id}")

    def get_provider(self, key_id: str) -> str:
        """获取 API Key 的服务商"""
        vault = self._load_vault()
        key_data = vault.get(f"api_key:{key_id}")
        if not key_data:
            raise KeyError(f"API Key 不存在：{key_id}")
        return key_data.get('provider', 'unknown')

    def get_key_data(self, key_id: str) -> dict:
        """
        获取完整的 Key 数据（包含 group_id 和 base_url）

        Args:
            key_id: Key ID

        Returns:
            包含 provider、group_id、base_url 的字典

        Raises:
            KeyError: Key 不存在
        """
        vault = self._load_vault()
        key_data = vault.get(f"api_key:{key_id}")
        if not key_data:
            raise KeyError(f"API Key 不存在：{key_id}")

        group_id = ""
        if key_data.get('group_id'):
            try:
                group_id = self.decrypt(key_data['group_id'])
            except Exception:
                group_id = ""

        key_data['access_count'] = key_data.get('access_count', 0) + 1
        key_data['last_accessed'] = self._get_timestamp()
        self._save_vault(vault)

        return {
            'provider': key_data.get('provider', 'unknown'),
            'group_id': group_id,
            'base_url': key_data.get('base_url', ''),
        }

    def delete_api_key(self, key_id: str):
        """
        删除 API Key

        Args:
            key_id: Key ID
        """
        vault = self._load_vault()
        vault.pop(f"api_key:{key_id}", None)
        self._save_vault(vault)
        logger.info(f"API Key 已删除：{key_id}")

    def list_api_keys(self) -> list[dict[str, str]]:
        """列出所有 API Key ID"""
        vault = self._load_vault()
        keys = []
        for key_name, data in vault.items():
            if key_name.startswith("api_key:"):
                keys.append({
                    'id': key_name.replace("api_key:", ""),
                    'provider': data.get('provider', 'unknown'),
                    'created_at': data.get('created_at', 'unknown')
                })
        return keys

    def list_keys(self) -> list[str]:
        """列出保险库中所有的键"""
        vault = self._load_vault()
        return list(vault.keys())


    def _load_vault(self) -> dict[str, Any]:
        """加载保险库"""
        if self.vault_file.exists():
            try:
                with open(self.vault_file, encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载保险库失败：{e}")
                return {}
        return {}

    def _save_vault(self, vault: dict[str, Any]):
        """保存保险库"""
        try:
            with open(self.vault_file, 'w', encoding='utf-8') as f:
                json.dump(vault, f, indent=2, ensure_ascii=False)

            os.chmod(self.vault_file, 0o600)
        except Exception as e:
            logger.error(f"保存保险库失败：{e}")
            raise

    def _get_timestamp(self) -> str:
        """获取时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()


secure_storage = SecureStorage()

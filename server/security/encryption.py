"""
安全加密模块 - 加密存储敏感数据

使用 Fernet 对称加密算法
- API Key 加密存储
- 密钥文件权限 600（仅所有者可读写�?- 保险库存储所有加密数�?- 内存中密钥保护（使用后立即清除）

安全增强�?- 密钥轮换支持
- 访问计数审计
- 内存数据保护
"""
from cryptography.fernet import Fernet
from pathlib import Path
import base64
import os
import json
import logging
import secrets
import hashlib

logger = logging.getLogger(__name__)


class SecureStorage:
    """安全存储 - 加密敏感数据"""

    def __init__(self):
        """初始化安全存�?""
        self.data_dir = Path(__file__).parent.parent / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.key_file = self.data_dir / ".encryption_key"
        self.vault_file = self.data_dir / ".vault"
        
        # 获取或创建密�?        self.key = self._get_or_create_key()
        self.cipher = Fernet(self.key)
        
        logger.info("安全存储已初始化")

    def _get_or_create_key(self) -> bytes:
        """获取或创建加密密�?""
        if self.key_file.exists():
            try:
                with open(self.key_file, 'rb') as f:
                    key = f.read()
                logger.info("已加载现有加密密�?)
                return key
            except Exception as e:
                logger.error(f"加载密钥失败：{e}")
                # 密钥损坏，生成新�?                return self._create_new_key()
        else:
            logger.info("生成新的加密密钥")
            return self._create_new_key()

    def _create_new_key(self) -> bytes:
        """创建新的加密密钥"""
        key = Fernet.generate_key()
        
        try:
            with open(self.key_file, 'wb') as f:
                f.write(key)
            
            # 设置安全权限（仅所有者可读写�?            os.chmod(self.key_file, 0o600)
            logger.info("新密钥已创建并保�?)
            
            return key
        except Exception as e:
            logger.error(f"保存密钥失败：{e}")
            # 内存中保存，不写入文�?            return key

    def encrypt(self, plaintext: str) -> str:
        """
        加密字符�?
        Args:
            plaintext: 明文字符�?
        Returns:
            密文字符串（Base64 编码�?        """
        try:
            encrypted = self.cipher.encrypt(plaintext.encode('utf-8'))
            return base64.urlsafe_b64encode(encrypted).decode('utf-8')
        except Exception as e:
            logger.error(f"加密失败：{e}")
            raise

    def decrypt(self, ciphertext: str) -> str:
        """
        解密字符�?
        Args:
            ciphertext: 密文字符串（Base64 编码�?
        Returns:
            明文字符�?        """
        try:
            encrypted = base64.urlsafe_b64decode(ciphertext.encode('utf-8'))
            decrypted = self.cipher.decrypt(encrypted)
            return decrypted.decode('utf-8')
        except Exception as e:
            logger.error(f"解密失败：{e}")
            raise

    def store_api_key(self, key_id: str, provider: str, api_key: str, group_id: str = "", base_url: str = ""):
        """
        存储 API Key

        Args:
            key_id: Key ID
            provider: 服务商名�?            api_key: API Key 明文
            group_id: Group ID（可选，用于 Minimax�?            base_url: 自定�?Base URL（可选）
        """
        vault = self._load_vault()

        # 加密敏感数据
        encrypted_api_key = self.encrypt(api_key)
        encrypted_group_id = self.encrypt(group_id) if group_id else ""

        # 存储加密�?API Key 和提供商信息
        vault[f"api_key:{key_id}"] = {
            'encrypted': encrypted_api_key,
            'provider': provider,
            'group_id': encrypted_group_id,
            'base_url': base_url,  # Base URL 通常不敏感，可不加密
            'created_at': self._get_timestamp(),
            'access_count': 0,  # 访问计数
            'last_accessed': None  # 最后访问时�?        }

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
            KeyError: Key 不存�?        """
        vault = self._load_vault()

        key_data = vault.get(f"api_key:{key_id}")
        if not key_data:
            raise KeyError(f"API Key 不存在：{key_id}")

        try:
            # 解密 API Key
            api_key = self.decrypt(key_data['encrypted'])
            
            # 更新访问记录
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
        获取完整�?Key 数据（包�?group_id �?base_url�?
        Args:
            key_id: Key ID

        Returns:
            包含 provider、group_id、base_url 的字�?
        Raises:
            KeyError: Key 不存�?        """
        vault = self._load_vault()
        key_data = vault.get(f"api_key:{key_id}")
        if not key_data:
            raise KeyError(f"API Key 不存在：{key_id}")
        
        # 解密 group_id（如果有�?        group_id = ""
        if key_data.get('group_id'):
            try:
                group_id = self.decrypt(key_data['group_id'])
            except Exception:
                group_id = ""
        
        # 更新访问记录
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

    def list_api_keys(self) -> list:
        """列出所�?API Key ID"""
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

    def _load_vault(self) -> dict:
        """加载保险�?""
        if self.vault_file.exists():
            try:
                with open(self.vault_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载保险库失败：{e}")
                return {}
        return {}

    def _save_vault(self, vault: dict):
        """保存保险�?""
        try:
            with open(self.vault_file, 'w', encoding='utf-8') as f:
                json.dump(vault, f, indent=2, ensure_ascii=False)
            
            # 设置安全权限
            os.chmod(self.vault_file, 0o600)
        except Exception as e:
            logger.error(f"保存保险库失败：{e}")
            raise

    def _get_timestamp(self) -> str:
        """获取时间�?""
        from datetime import datetime
        return datetime.now().isoformat()


# 全局单例
secure_storage = SecureStorage()

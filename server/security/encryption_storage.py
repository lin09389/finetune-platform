"""
加密存储模块
使用 Fernet 对称加密保护敏感数据
"""
import base64
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    logger.warning("cryptography 库未安装，凭证将使用 Base64 编码存储（不安全）")


@dataclass
class EncryptedData:
    """加密数据结构"""
    ciphertext: str
    salt: str
    iterations: int
    created_at: datetime
    algorithm: str = "Fernet"


class EncryptionManager:
    """
    加密管理器
    
    使用 Fernet 对称加密保护敏感数据
    """

    KEY_FILE_NAME = ".encryption_key"
    MIN_ITERATIONS = 100000

    def __init__(self, storage_path: Path = None, password: str = None):
        """
        初始化加密管理器
        
        Args:
            storage_path: 密钥存储路径
            password: 主密码（可选，不提供则自动生成）
        """
        self.storage_path = storage_path or Path.home() / ".finetune" / "security"
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._fernet: Any | None = None
        self._key: bytes | None = None
        self._password = password

        self._initialize_encryption()

    def _initialize_encryption(self):
        """初始化加密"""
        key_file = self.storage_path / self.KEY_FILE_NAME

        if key_file.exists():
            try:
                self._load_key(key_file)
                return
            except Exception as e:
                logger.warning(f"加载密钥失败，将生成新密钥: {e}")

        self._generate_key(key_file)

    def _generate_key(self, key_file: Path):
        """生成新密钥"""
        if CRYPTO_AVAILABLE:
            self._key = Fernet.generate_key()
            self._fernet = Fernet(self._key)

            with open(key_file, "wb") as f:
                f.write(self._key)

            os.chmod(key_file, 0o600)
            logger.info("已生成新的加密密钥")
        else:
            self._key = base64.urlsafe_b64encode(os.urandom(32))
            self._fernet = None
            logger.warning("使用不安全的 Base64 编码")

    def _load_key(self, key_file: Path):
        """加载密钥"""
        with open(key_file, "rb") as f:
            self._key = f.read()

        if CRYPTO_AVAILABLE:
            self._fernet = Fernet(self._key)
        else:
            self._fernet = None

        logger.info("已加载加密密钥")

    def _derive_key_from_password(self, password: str, salt: bytes = None) -> tuple:
        """从密码派生密钥"""
        if salt is None:
            salt = os.urandom(16)

        if CRYPTO_AVAILABLE:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=self.MIN_ITERATIONS,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
            return key, salt
        else:
            key = base64.urlsafe_b64encode(
                hashlib.pbkdf2_hmac('sha256', password.encode(), salt, self.MIN_ITERATIONS)
            )
            return key, salt

    def encrypt(self, plaintext: str) -> str:
        """
        加密数据
        
        Args:
            plaintext: 明文
            
        Returns:
            str: 加密后的数据（Base64编码）
        """
        if not plaintext:
            return ""

        try:
            if CRYPTO_AVAILABLE and self._fernet:
                ciphertext = self._fernet.encrypt(plaintext.encode())
                return base64.urlsafe_b64encode(ciphertext).decode()
            else:
                encoded = base64.urlsafe_b64encode(plaintext.encode())
                return f"plain:{encoded.decode()}"
        except Exception as e:
            logger.error(f"加密失败: {e}")
            raise

    def decrypt(self, ciphertext: str) -> str:
        """
        解密数据
        
        Args:
            ciphertext: 密文
            
        Returns:
            str: 解密后的明文
        """
        if not ciphertext:
            return ""

        try:
            if ciphertext.startswith("plain:"):
                return base64.urlsafe_b64decode(ciphertext[6:]).decode()

            if CRYPTO_AVAILABLE and self._fernet:
                decoded = base64.urlsafe_b64decode(ciphertext.encode())
                plaintext = self._fernet.decrypt(decoded)
                return plaintext.decode()
            else:
                return base64.urlsafe_b64decode(ciphertext).decode()
        except Exception as e:
            logger.error(f"解密失败: {e}")
            raise

    def encrypt_dict(self, data: dict[str, Any]) -> str:
        """加密字典"""
        json_str = json.dumps(data, ensure_ascii=False)
        return self.encrypt(json_str)

    def decrypt_dict(self, ciphertext: str) -> dict[str, Any]:
        """解密字典"""
        json_str = self.decrypt(ciphertext)
        return json.loads(json_str)

    def is_encrypted(self, value: str) -> bool:
        """检查值是否已加密"""
        if not value:
            return False

        if value.startswith("plain:"):
            return True

        try:
            decoded = base64.urlsafe_b64decode(value.encode())
            if CRYPTO_AVAILABLE:
                return len(decoded) > 0
            return True
        except Exception:
            return False

    def rotate_key(self) -> bool:
        """
        轮换密钥
        
        Returns:
            bool: 是否成功
        """
        key_file = self.storage_path / self.KEY_FILE_NAME
        backup_file = self.storage_path / f"{self.KEY_FILE_NAME}.bak"

        try:
            if key_file.exists():
                with open(key_file, "rb") as f:
                    old_key = f.read()
                with open(backup_file, "wb") as f:
                    f.write(old_key)

            self._generate_key(key_file)
            logger.info("密钥轮换成功")
            return True
        except Exception as e:
            logger.error(f"密钥轮换失败: {e}")
            return False


class SecureCredentialStorage:
    """
    安全凭证存储
    
    使用加密存储敏感凭证
    """

    CREDENTIALS_FILE = "credentials.enc"

    def __init__(self, storage_path: Path = None):
        """
        初始化安全凭证存储
        
        Args:
            storage_path: 存储路径
        """
        self.storage_path = storage_path or Path.home() / ".finetune" / "credentials"
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.encryption = EncryptionManager(self.storage_path)
        self._credentials: dict[str, dict[str, Any]] = {}

        self._load_credentials()

    def _load_credentials(self):
        """加载凭证"""
        cred_file = self.storage_path / self.CREDENTIALS_FILE

        if not cred_file.exists():
            return

        try:
            with open(cred_file, encoding="utf-8") as f:
                encrypted_data = f.read()

            if encrypted_data:
                self._credentials = self.encryption.decrypt_dict(encrypted_data)
                logger.info(f"已加载 {len(self._credentials)} 个凭证")
        except Exception as e:
            logger.error(f"加载凭证失败: {e}")
            self._credentials = {}

    def _save_credentials(self):
        """保存凭证"""
        cred_file = self.storage_path / self.CREDENTIALS_FILE

        try:
            encrypted_data = self.encryption.encrypt_dict(self._credentials)

            with open(cred_file, "w", encoding="utf-8") as f:
                f.write(encrypted_data)

            os.chmod(cred_file, 0o600)
        except Exception as e:
            logger.error(f"保存凭证失败: {e}")

    def store(self, key: str, value: str, metadata: dict[str, Any] = None) -> bool:
        """
        存储凭证
        
        Args:
            key: 凭证键
            value: 凭证值
            metadata: 元数据
            
        Returns:
            bool: 是否成功
        """
        try:
            encrypted_value = self.encryption.encrypt(value)

            self._credentials[key] = {
                "value": encrypted_value,
                "metadata": metadata or {},
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

            self._save_credentials()
            logger.info(f"已存储凭证: {key}")
            return True
        except Exception as e:
            logger.error(f"存储凭证失败: {e}")
            return False

    def retrieve(self, key: str) -> str | None:
        """
        获取凭证
        
        Args:
            key: 凭证键
            
        Returns:
            Optional[str]: 凭证值
        """
        cred = self._credentials.get(key)
        if not cred:
            return None

        try:
            return self.encryption.decrypt(cred["value"])
        except Exception as e:
            logger.error(f"解密凭证失败: {e}")
            return None

    def delete(self, key: str) -> bool:
        """删除凭证"""
        if key in self._credentials:
            del self._credentials[key]
            self._save_credentials()
            return True
        return False

    def list_keys(self) -> list:
        """列出所有凭证键"""
        return list(self._credentials.keys())

    def exists(self, key: str) -> bool:
        """检查凭证是否存在"""
        return key in self._credentials


_encryption_manager: EncryptionManager | None = None
_credential_storage: SecureCredentialStorage | None = None


def get_encryption_manager() -> EncryptionManager:
    """获取加密管理器单例"""
    global _encryption_manager
    if _encryption_manager is None:
        _encryption_manager = EncryptionManager()
    return _encryption_manager


def get_credential_storage() -> SecureCredentialStorage:
    """获取凭证存储单例"""
    global _credential_storage
    if _credential_storage is None:
        _credential_storage = SecureCredentialStorage()
    return _credential_storage

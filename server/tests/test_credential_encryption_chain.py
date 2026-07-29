"""
凭证加密链聚焦测试

覆盖：
- EncryptionManager 未初始化时 encrypt/decrypt 抛 RuntimeError
- CredentialManager 加密初始化失败降级明文，且降级日志含稳定关联标识
- 降级模式下明文持久化日志与触发条件可通过同一事件标识关联
- production/staging 下加密初始化失败 fail-closed，拒绝明文持久化
"""
import json
import logging
from types import SimpleNamespace

import pytest

import security.encryption_storage as encryption_storage
from security.encryption_storage import EncryptionManager
from security.sandbox import (
    CREDENTIAL_ENCRYPTION_FALLBACK_EVENT,
    CredentialManager,
)


@pytest.fixture
def broken_encryption(monkeypatch):
    """使 EncryptionManager 构造失败，触发降级"""

    class _BrokenEncryptionManager:
        def __init__(self, *args, **kwargs):
            raise OSError("key file unreadable")

    monkeypatch.setattr(
        encryption_storage, "EncryptionManager", _BrokenEncryptionManager
    )


class TestEncryptionManagerUninitialized:
    """EncryptionManager 未初始化路径"""

    @pytest.fixture
    def manager(self, tmp_path):
        manager = EncryptionManager(storage_path=tmp_path)
        # 模拟加密器未初始化状态
        manager._fernet = None
        return manager

    def test_encrypt_raises_runtime_error(self, manager):
        """EC-001: 未初始化时 encrypt 抛 RuntimeError"""
        with pytest.raises(RuntimeError, match="加密器未初始化"):
            manager.encrypt("secret-value")

    def test_decrypt_raises_runtime_error(self, manager):
        """EC-002: 未初始化时 decrypt 抛 RuntimeError"""
        with pytest.raises(RuntimeError, match="加密器未初始化"):
            manager.decrypt("ZmFrZS1jaXBoZXJ0ZXh0")

    def test_empty_input_short_circuits(self, manager):
        """EC-003: 空输入短路返回，不触发未初始化异常"""
        assert manager.encrypt("") == ""
        assert manager.decrypt("") == ""


class TestCredentialManagerEncryptionFallback:
    """CredentialManager 加密初始化失败降级明文路径（开发环境）"""

    def test_init_failure_falls_back_to_plaintext(
        self, tmp_path, broken_encryption, caplog
    ):
        """EC-004: 加密初始化失败后 _encryption 为 None 且明文持久化"""
        with caplog.at_level(logging.WARNING, logger="security.sandbox"):
            manager = CredentialManager(storage_path=tmp_path)

        assert manager._encryption is None

        manager.store_credential(
            name="fallback_key",
            credential_type="api_key",
            value="sk-plain-123",
        )

        persisted = json.loads(
            (tmp_path / "fallback_key.json").read_text(encoding="utf-8")
        )
        assert persisted["value"] == "sk-plain-123"
        assert "_encrypted" not in persisted

    def test_fallback_log_contains_stable_event_id(
        self, tmp_path, broken_encryption, caplog
    ):
        """EC-005: 降级触发日志含稳定关联标识与触发原因"""
        with caplog.at_level(logging.WARNING, logger="security.sandbox"):
            CredentialManager(storage_path=tmp_path)

        fallback_records = [
            r for r in caplog.records
            if CREDENTIAL_ENCRYPTION_FALLBACK_EVENT in r.getMessage()
        ]
        assert len(fallback_records) == 1
        # 触发条件（构造异常信息）与事件标识出现在同一条日志中
        assert "key file unreadable" in fallback_records[0].getMessage()

    def test_plaintext_persist_log_correlates_with_trigger(
        self, tmp_path, broken_encryption, caplog
    ):
        """EC-006: 明文持久化日志携带同一事件标识与凭证 ID，可与触发条件关联"""
        with caplog.at_level(logging.WARNING, logger="security.sandbox"):
            manager = CredentialManager(storage_path=tmp_path)
            manager.store_credential(
                name="correlated_key",
                credential_type="api_key",
                value="sk-plain-456",
            )

        fallback_messages = [
            r.getMessage() for r in caplog.records
            if CREDENTIAL_ENCRYPTION_FALLBACK_EVENT in r.getMessage()
        ]
        # 一条来自初始化降级触发，一条来自明文持久化
        assert len(fallback_messages) == 2
        assert any("correlated_key" in m for m in fallback_messages)


class TestCredentialManagerProductionFailClosed:
    """production/staging 加密初始化失败 fail-closed 路径"""

    @pytest.mark.parametrize("environment", ["production", "staging"])
    def test_init_failure_raises_and_skips_fallback(
        self, tmp_path, broken_encryption, caplog, environment
    ):
        """EC-008: 生产/预发下初始化失败直接 RuntimeError，不进入明文降级"""
        settings = SimpleNamespace(environment=environment)
        with caplog.at_level(logging.WARNING, logger="security.sandbox"):
            with pytest.raises(RuntimeError, match="refusing plaintext"):
                CredentialManager(storage_path=tmp_path, settings=settings)

        # fail-closed 路径不应再记录降级事件日志
        assert not any(
            CREDENTIAL_ENCRYPTION_FALLBACK_EVENT in r.getMessage()
            for r in caplog.records
        )

    def test_persist_refuses_plaintext_in_production(self, tmp_path):
        """EC-009: 生产环境下加密缺失时持久化前 fail-closed，不落盘明文"""
        settings = SimpleNamespace(environment="production")
        manager = CredentialManager(storage_path=tmp_path, settings=settings)
        assert manager._encryption is not None
        # 模拟运行期加密器丢失（防御性写盘前拦截）
        manager._encryption = None

        with pytest.raises(RuntimeError, match="refusing plaintext"):
            manager.store_credential(
                name="prod_key",
                credential_type="api_key",
                value="sk-prod-000",
            )

        assert not (tmp_path / "prod_key.json").exists()

    def test_development_fallback_unchanged(self, tmp_path, broken_encryption):
        """EC-010: 开发环境降级容错行为不变（显式 settings 对照）"""
        settings = SimpleNamespace(environment="development")
        manager = CredentialManager(storage_path=tmp_path, settings=settings)
        assert manager._encryption is None

        manager.store_credential(
            name="dev_key",
            credential_type="api_key",
            value="sk-dev-111",
        )

        persisted = json.loads(
            (tmp_path / "dev_key.json").read_text(encoding="utf-8")
        )
        assert persisted["value"] == "sk-dev-111"


class TestCredentialManagerEncryptedPersist:
    """加密可用时的对照路径"""

    def test_persisted_value_is_encrypted(self, tmp_path, caplog):
        """EC-007: 加密可用时持久化值为密文且标记 _encrypted"""
        with caplog.at_level(logging.WARNING, logger="security.sandbox"):
            manager = CredentialManager(storage_path=tmp_path)
            assert manager._encryption is not None
            manager.store_credential(
                name="encrypted_key",
                credential_type="api_key",
                value="sk-secret-789",
            )

        persisted = json.loads(
            (tmp_path / "encrypted_key.json").read_text(encoding="utf-8")
        )
        assert persisted["_encrypted"] is True
        assert persisted["value"] != "sk-secret-789"
        # 密文可由同一加密管理器解密还原
        assert manager._encryption.decrypt(persisted["value"]) == "sk-secret-789"
        # 正常路径不应出现降级事件标识
        assert not any(
            CREDENTIAL_ENCRYPTION_FALLBACK_EVENT in r.getMessage()
            for r in caplog.records
        )

"""Focused regression: EncryptionManager fails closed when uninitialized.

`encrypt` / `decrypt` must raise RuntimeError instead of AttributeError when
`_fernet` was never initialized (e.g. key load failure), and must never return
plaintext-ish output. Normal initialized round-trip stays intact.
"""

from __future__ import annotations

import pytest

from security.encryption_storage import EncryptionManager


@pytest.fixture()
def uninitialized_manager(tmp_path):
    manager = EncryptionManager(storage_path=tmp_path / "sec")
    # Simulate a manager whose encryption never came up (fail-closed path).
    manager._fernet = None
    return manager


def test_encrypt_without_fernet_raises_runtime_error(uninitialized_manager):
    with pytest.raises(RuntimeError, match="加密器未初始化"):
        uninitialized_manager.encrypt("secret-value")


def test_decrypt_without_fernet_raises_runtime_error(uninitialized_manager):
    with pytest.raises(RuntimeError, match="加密器未初始化"):
        uninitialized_manager.decrypt("Zm9vYmFy")


def test_empty_input_short_circuits_before_guard(uninitialized_manager):
    # Empty payloads keep returning "" without touching the cipher.
    assert uninitialized_manager.encrypt("") == ""
    assert uninitialized_manager.decrypt("") == ""


def test_initialized_round_trip_still_works(tmp_path):
    manager = EncryptionManager(storage_path=tmp_path / "sec-ok")
    ciphertext = manager.encrypt("secret-value")
    assert ciphertext and ciphertext != "secret-value"
    assert manager.decrypt(ciphertext) == "secret-value"

from __future__ import annotations

from cloud_models.repository import CloudProviderRepository


class MemoryStorage:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get(self, key: str):
        return self.values.get(key)

    def store(self, key: str, value: object) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)

    def list_keys(self) -> list[str]:
        return list(self.values)


def test_save_preserves_existing_secret_when_edit_payload_omits_it():
    storage = MemoryStorage()
    repository = CloudProviderRepository(storage)
    repository.save("custom", {"api_key": "secret", "models": ["first"]}, custom=True)

    saved = repository.save("custom", {"name": "Renamed", "models": ["second"]}, custom=True)

    assert saved["api_key"] == "secret"
    assert saved["default_model"] == "second"
    assert repository.custom_provider_ids() == ["custom"]


def test_delete_removes_credential_and_custom_index_entry():
    storage = MemoryStorage()
    repository = CloudProviderRepository(storage)
    repository.save("custom", {"api_key": "secret"}, custom=True)

    repository.delete("custom")

    assert repository.get("custom") == {}
    assert repository.custom_provider_ids() == []


def test_redacted_never_returns_api_key():
    storage = MemoryStorage()
    repository = CloudProviderRepository(storage)
    repository.save("deepseek", {"api_key": "secret", "base_url": "https://example.test/v1"}, custom=False)

    assert repository.redacted("deepseek") == {
        "base_url": "https://example.test/v1",
        "created_at": repository.get("deepseek")["created_at"],
        "updated_at": repository.get("deepseek")["updated_at"],
        "models": [],
        "default_model": "",
    }


def test_configured_provider_ids_includes_legacy_builtins_and_custom_records():
    storage = MemoryStorage()
    repository = CloudProviderRepository(storage)
    repository.save("openai", {"api_key": "openai-key"}, custom=False)
    repository.save("custom", {"api_key": "custom-key"}, custom=True)

    assert repository.configured_provider_ids() == ["custom", "openai"]

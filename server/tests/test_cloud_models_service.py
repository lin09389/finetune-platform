from __future__ import annotations

import pytest
from cloud_models.repository import CloudProviderRepository
from cloud_models.service import CloudModelService


class MemoryStorage:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get(self, key: str):
        return self.values.get(key)

    def store(self, key: str, value: object) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


class Provider:
    def get_default_model(self) -> str:
        return "fallback-model"


def test_service_resolves_saved_key_model_and_normalized_base_url(monkeypatch):
    repository = CloudProviderRepository(MemoryStorage())
    repository.save(
        "deepseek",
        {"api_key": "secret", "default_model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com/anthropic/v1"},
        custom=False,
    )
    monkeypatch.setattr("cloud_models.service.resolve_provider", lambda *_args, **_kwargs: Provider())

    resolved = CloudModelService(repository).resolve("deepseek")

    assert resolved.api_key == "secret"
    assert resolved.model == "deepseek-v4-flash"
    assert resolved.base_url == "https://api.deepseek.com/v1"


def test_service_rejects_missing_key_before_provider_call(monkeypatch):
    repository = CloudProviderRepository(MemoryStorage())
    service = CloudModelService(repository)
    monkeypatch.setattr("cloud_models.service.resolve_provider", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))

    with pytest.raises(ValueError, match="未配置 openai 的 API Key"):
        service.resolve("openai")

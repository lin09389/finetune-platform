"""Persistence boundary for cloud provider credentials and metadata."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any


class CloudProviderRepository:
    """Owns the secure-storage representation of a cloud provider.

    The payload shape deliberately remains compatible with legacy
    ``cloud_<provider>_key`` records while preventing callers from duplicating
    custom-provider index management.
    """

    INDEX_KEY = "cloud_custom_provider_index"

    def __init__(self, storage: Any) -> None:
        self._storage = storage

    @staticmethod
    def _key(provider_id: str) -> str:
        provider_id = provider_id.strip()
        if not provider_id:
            raise ValueError("provider id is required")
        return f"cloud_{provider_id}_key"

    def get(self, provider_id: str) -> dict[str, Any]:
        value = self._storage.get(self._key(provider_id)) or {}
        return dict(value) if isinstance(value, dict) else {}

    def custom_provider_ids(self) -> list[str]:
        index = self._storage.get(self.INDEX_KEY) or {}
        values = index.get("providers", []) if isinstance(index, dict) else []
        return sorted({str(value).strip() for value in values if str(value).strip()})

    def configured_provider_ids(self) -> list[str]:
        """Return providers with persisted records, including legacy built-ins."""
        list_keys = getattr(self._storage, "list_keys", None)
        if not callable(list_keys):
            return self.custom_provider_ids()
        return sorted(
            key.removeprefix("cloud_").removesuffix("_key")
            for key in list_keys()
            if isinstance(key, str) and key.startswith("cloud_") and key.endswith("_key")
        )

    def add_custom_provider_id(self, provider_id: str) -> None:
        provider_id = provider_id.strip()
        if not provider_id:
            raise ValueError("provider id is required")
        self._storage.store(self.INDEX_KEY, {"providers": sorted({*self.custom_provider_ids(), provider_id})})

    def remove_custom_provider_id(self, provider_id: str) -> None:
        self._storage.store(self.INDEX_KEY, {"providers": [item for item in self.custom_provider_ids() if item != provider_id]})

    def save(self, provider_id: str, payload: dict[str, Any], *, custom: bool) -> dict[str, Any]:
        existing = self.get(provider_id)
        api_key = str(payload.get("api_key") or "").strip() or str(existing.get("api_key") or "")
        if not api_key:
            raise ValueError("新增供应商时必须填写 API Key")
        models = [str(model).strip() for model in payload.get("models", []) if str(model).strip()]
        stored = {
            **existing,
            **payload,
            "api_key": api_key,
            "created_at": existing.get("created_at") or datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "models": models,
            "default_model": str(payload.get("default_model") or (models[0] if models else existing.get("default_model") or "")),
        }
        self._storage.store(self._key(provider_id), stored)
        if custom:
            self.add_custom_provider_id(provider_id)
        return stored

    def update(self, provider_id: str, **changes: Any) -> dict[str, Any]:
        current = self.get(provider_id)
        if not current:
            raise ValueError(f"未配置 {provider_id} 的 API Key")
        current.update(changes)
        current["updated_at"] = datetime.now().isoformat()
        self._storage.store(self._key(provider_id), current)
        return current

    def delete(self, provider_id: str) -> None:
        self._storage.delete(self._key(provider_id))
        self.remove_custom_provider_id(provider_id)

    def redacted(self, provider_id: str) -> dict[str, Any]:
        value = self.get(provider_id)
        if not value:
            return {}
        return {key: item for key, item in value.items() if key != "api_key"}

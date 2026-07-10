"""Application service for resolving a ready-to-call cloud model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .repository import CloudProviderRepository
from .resolver import normalize_base_url, resolve_provider


@dataclass(frozen=True)
class ResolvedCloudModel:
    provider_id: str
    provider: Any
    api_key: str
    model: str
    base_url: str
    config: dict[str, Any]


class CloudModelService:
    def __init__(self, repository: CloudProviderRepository) -> None:
        self.repository = repository

    def resolve(self, provider_id: str, *, model: str | None = None, api_key: str | None = None, group_id: str = "", base_url: str = "", version: str = "") -> ResolvedCloudModel:
        config = self.repository.get(provider_id)
        effective_key = str(api_key or config.get("api_key") or "").strip()
        if not effective_key:
            raise ValueError(f"未配置 {provider_id} 的 API Key")
        provider = resolve_provider(provider_id, config, group_id=group_id, base_url=base_url, version=version)
        if provider is None:
            raise ValueError(f"不支持的服务商：{provider_id}")
        resolved_model = str(model or config.get("default_model") or provider.get_default_model() or "").strip()
        if not resolved_model:
            raise ValueError(f"未配置 {provider_id} 的默认模型")
        return ResolvedCloudModel(provider_id, provider, effective_key, resolved_model, normalize_base_url(base_url or config.get("base_url")), config)

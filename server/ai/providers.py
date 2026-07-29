"""Shared provider resolution helpers for agent runtimes."""

from __future__ import annotations

from typing import Any


def resolve_saved_provider(provider_name: str, key_data: dict[str, Any]):
    """Backward-compatible alias for the cloud-model domain resolver."""
    # Deferred to avoid a package-init cycle when cloud_models imports
    # ai.gateway and ai.__init__ re-exports this compatibility helper.
    from cloud_models.resolver import resolve_provider

    return resolve_provider(provider_name, key_data)


__all__ = ["resolve_saved_provider"]

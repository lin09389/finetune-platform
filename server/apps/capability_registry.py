"""Single source of truth for GA / beta / experimental capability tiers.

Registration (`apps.routers`), `/api/info`, and frontend tier badges must all
read from this catalog so labels cannot drift from mounts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

CapabilityTier = Literal["ga", "beta", "experimental"]


@dataclass(frozen=True)
class CapabilitySpec:
    """One product capability with tier + mount metadata."""

    id: str
    tier: CapabilityTier
    label: str
    # Canonical HTTP mount(s) as advertised in /api/info (without host).
    mounts: tuple[str, ...]
    # When True, capability is experimental high-risk (auth still route-level).
    high_risk: bool = False
    # Router registration group key used by apps.routers (empty = not a router group).
    router_group: str = ""


# Authoritative catalog — keep in sync with GA product surfaces.
CAPABILITY_CATALOG: tuple[CapabilitySpec, ...] = (
    # GA
    CapabilitySpec("device", "ga", "Device", ("/device",), router_group="finetune"),
    CapabilitySpec("models", "ga", "Models", ("/models",), router_group="finetune"),
    CapabilitySpec("datasets", "ga", "Datasets", ("/datasets",), router_group="finetune"),
    CapabilitySpec("training", "ga", "Training", ("/training",), router_group="finetune"),
    CapabilitySpec("inference", "ga", "Inference", ("/inference",), router_group="inference"),
    CapabilitySpec("chat_sessions", "ga", "Chat sessions", ("/chat/sessions",), router_group="agent"),
    CapabilitySpec("knowledge_base", "ga", "Knowledge", ("/knowledge",), router_group="agent"),
    # Beta
    CapabilitySpec("project_context", "beta", "Project context", ("/context",), router_group="agent_aux"),
    CapabilitySpec("memory", "beta", "Memory", ("/memory",), router_group="agent_aux"),
    CapabilitySpec("model_center", "beta", "Model center", ("/model-center",), router_group="finetune"),
    CapabilitySpec("workspace", "beta", "Workspace", ("/workspace",), router_group="agent"),
    CapabilitySpec("agent_eval", "beta", "Agent evaluation", ("/agent-eval",), router_group="agent_aux"),
    # Always-on auxiliary (not gated by ENABLE_EXPERIMENTAL_CAPABILITIES)
    CapabilitySpec("cloud_chat", "beta", "Cloud chat / API keys", ("/cloud",), router_group="agent_aux"),
    # Experimental
    CapabilitySpec(
        "cua",
        "experimental",
        "CUA",
        ("/cua", "/experimental/cua"),
        high_risk=True,
        router_group="experimental",
    ),
    CapabilitySpec(
        "heartbeat",
        "experimental",
        "Heartbeat",
        ("/heartbeat", "/experimental/heartbeat"),
        router_group="experimental",
    ),
    CapabilitySpec(
        "mcp",
        "experimental",
        "MCP",
        ("/mcp", "/experimental/mcp"),
        router_group="experimental",
    ),
    CapabilitySpec(
        "gateway",
        "experimental",
        "Gateway",
        ("/gateway", "/experimental/gateway"),
        router_group="experimental",
    ),
    CapabilitySpec(
        "ocr_fallbacks",
        "experimental",
        "OCR",
        ("/ocr", "/experimental/ocr"),
        router_group="experimental",
    ),
    CapabilitySpec(
        "action_recorder",
        "experimental",
        "Action recorder",
        ("/cua", "/experimental/cua"),  # shares CUA control plane routes
        high_risk=True,
        router_group="experimental",
    ),
)

# Experimental router modules registered under isolation mount + legacy aliases.
EXPERIMENTAL_ROUTER_SPECS: tuple[tuple[str, str, str], ...] = (
    # (module, attribute, legacy_tag)
    ("api.cua", "router", "CUA"),
    ("api.mcp", "router", "MCP"),
    ("api.gateway_api.routes", "router", "Gateway"),
    ("api.heartbeat", "router", "Heartbeat"),
    ("api.ocr", "router", "OCR"),
)

EXPERIMENTAL_MOUNT_PREFIX = "/experimental"


def list_capabilities(*, tier: CapabilityTier | None = None) -> list[CapabilitySpec]:
    if tier is None:
        return list(CAPABILITY_CATALOG)
    return [c for c in CAPABILITY_CATALOG if c.tier == tier]


def capability_ids_by_tier() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"ga": [], "beta": [], "experimental": []}
    for cap in CAPABILITY_CATALOG:
        out[cap.tier].append(cap.id)
    return out


def experimental_enabled(settings: Any | None = None) -> bool:
    """Whether experimental routers should be registered."""
    if settings is None:
        from core.config import get_settings

        settings = get_settings()
    return bool(getattr(settings, "enable_experimental_capabilities", True))


def build_info_capability_payload(settings: Any | None = None) -> dict[str, Any]:
    """Machine-checkable tier payload for GET /api/info."""
    enabled = experimental_enabled(settings)
    tiers = capability_ids_by_tier()
    experimental_detail = []
    for cap in list_capabilities(tier="experimental"):
        experimental_detail.append(
            {
                "id": cap.id,
                "label": cap.label,
                "enabled": enabled,
                "high_risk": cap.high_risk,
                "mounts": list(cap.mounts),
                "canonical_mount": f"{EXPERIMENTAL_MOUNT_PREFIX}/{cap.id.split('_')[0]}"
                if cap.id != "ocr_fallbacks"
                else f"{EXPERIMENTAL_MOUNT_PREFIX}/ocr",
            }
        )
    # Normalize canonical experimental mounts to known routers
    mount_map = {
        "cua": f"{EXPERIMENTAL_MOUNT_PREFIX}/cua",
        "heartbeat": f"{EXPERIMENTAL_MOUNT_PREFIX}/heartbeat",
        "mcp": f"{EXPERIMENTAL_MOUNT_PREFIX}/mcp",
        "gateway": f"{EXPERIMENTAL_MOUNT_PREFIX}/gateway",
        "ocr_fallbacks": f"{EXPERIMENTAL_MOUNT_PREFIX}/ocr",
        "action_recorder": f"{EXPERIMENTAL_MOUNT_PREFIX}/cua",
    }
    for item in experimental_detail:
        item["canonical_mount"] = mount_map.get(item["id"], item["mounts"][0])

    return {
        "capability_tiers": tiers,
        "experimental_enabled": enabled,
        "experimental_capabilities": experimental_detail,
        "endpoints": {
            "device": "/device",
            "models": "/models",
            "datasets": "/datasets",
            "training": "/training",
            "inference": "/inference",
            "chat": "/chat/sessions",
            "knowledge": "/knowledge",
            "runtime": "/runtime/bootstrap",
            "memory": "/memory",
            "workspace": "/workspace",
            "context": "/context",
            "model_center": "/model-center",
            "agent_eval": "/agent-eval",
            "experimental_status": f"{EXPERIMENTAL_MOUNT_PREFIX}/status",
            "experimental": {
                "cua": mount_map["cua"] if enabled else None,
                "mcp": mount_map["mcp"] if enabled else None,
                "gateway": mount_map["gateway"] if enabled else None,
                "heartbeat": mount_map["heartbeat"] if enabled else None,
                "ocr": mount_map["ocr_fallbacks"] if enabled else None,
                # Legacy aliases remain when experimental is enabled
                "legacy_aliases": {
                    "cua": "/cua",
                    "mcp": "/mcp",
                    "gateway": "/gateway",
                    "heartbeat": "/heartbeat",
                    "ocr": "/ocr",
                }
                if enabled
                else {},
            },
        },
    }


def experimental_status_payload(settings: Any | None = None) -> dict[str, Any]:
    """Dedicated experimental readiness signal (does not fail core /health)."""
    enabled = experimental_enabled(settings)
    return {
        "tier": "experimental",
        "enabled": enabled,
        "runtime_status": "ready" if enabled else "disabled",
        "mount_prefix": EXPERIMENTAL_MOUNT_PREFIX,
        "message": (
            "Experimental capabilities are registered under /experimental/* "
            "(legacy aliases remain for compatibility)."
            if enabled
            else "Experimental capabilities are disabled by policy "
            "(ENABLE_EXPERIMENTAL_CAPABILITIES)."
        ),
        "capabilities": [
            {
                "id": c.id,
                "enabled": enabled,
                "high_risk": c.high_risk,
            }
            for c in list_capabilities(tier="experimental")
        ],
    }

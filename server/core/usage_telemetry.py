"""Safe aggregate usage recording facade for future runtime integrations."""

from __future__ import annotations

from core.telemetry import LocalTelemetryRegistry, get_telemetry_registry

_COMPONENTS = frozenset({"agent", "inference", "provider", "training"})
_PROVIDERS = frozenset({"anthropic", "huggingface", "local", "modelscope", "ollama", "openai"})
_OUTCOMES = frozenset({"cancelled", "error", "success"})


def _bounded(value: str, allowed: frozenset[str]) -> str:
    return value if value in allowed else "other"


class UsageTelemetry:
    """Record aggregate usage only; never prompt, session, request, or path data."""

    def __init__(self, registry: LocalTelemetryRegistry | None = None) -> None:
        self._registry = registry

    @property
    def _active_registry(self) -> LocalTelemetryRegistry:
        return self._registry or get_telemetry_registry()

    def record_usage(
        self,
        *,
        component: str,
        provider: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        outcome: str = "success",
    ) -> None:
        """Record token totals by fixed dimensions without retaining event data."""

        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("token totals must be non-negative")
        labels = {
            "component": _bounded(component, _COMPONENTS),
            "provider": _bounded(provider, _PROVIDERS),
            "outcome": _bounded(outcome, _OUTCOMES),
        }
        registry = self._active_registry
        registry.record_counter("finetune_usage_events_total", labels)
        registry.record_counter("finetune_usage_input_tokens_total", labels, input_tokens)
        registry.record_counter("finetune_usage_output_tokens_total", labels, output_tokens)


_usage_telemetry = UsageTelemetry()


def record_usage(**kwargs) -> None:
    """Record aggregate usage through the process-local default facade."""

    _usage_telemetry.record_usage(**kwargs)


def get_usage_telemetry() -> UsageTelemetry:
    return _usage_telemetry


__all__ = ["UsageTelemetry", "get_usage_telemetry", "record_usage"]

"""Thread-safe, bounded, process-local Prometheus telemetry.

This module is deliberately dependency-free: it neither exports data nor
retains request/event payloads.  Only aggregate counters and sums keyed by
small, allowlisted label values are kept in memory.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from threading import RLock
from typing import Final

PROMETHEUS_CONTENT_TYPE: Final = "text/plain; version=0.0.4; charset=utf-8"
_FORBIDDEN_LABELS: Final = frozenset(
    {
        "authorization",
        "correlation_id",
        "path",
        "prompt",
        "prompts",
        "request_id",
        "session_id",
        "token",
        "tokens",
        "user_id",
    }
)
_HTTP_METHODS: Final = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"})
_PROFILES: Final = frozenset({"agent", "combined", "finetune"})


class LocalTelemetryRegistry:
    """A bounded registry for counters and summary sum/count pairs.

    ``max_series`` is a global cap across all stored metric names, so an
    unexpected label value cannot grow process memory without bound.  New
    series beyond the cap are discarded and counted by the fixed, unlabeled
    ``finetune_telemetry_dropped_series_total`` metric.
    """

    def __init__(self, max_series: int = 256) -> None:
        if max_series < 1:
            raise ValueError("max_series must be positive")
        self._max_series = max_series
        self._counters: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(dict)
        self._summaries: dict[str, dict[tuple[tuple[str, str], ...], list[float]]] = defaultdict(dict)
        self._series: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
        self._dropped_series = 0
        self._lock = RLock()

    @staticmethod
    def _labels_key(labels: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
        normalized: list[tuple[str, str]] = []
        for raw_key, raw_value in labels.items():
            key = str(raw_key)
            if key in _FORBIDDEN_LABELS:
                raise ValueError(f"sensitive telemetry label is forbidden: {key}")
            normalized.append((key, str(raw_value)))
        return tuple(sorted(normalized))

    def _allows_series(self, metric_name: str, labels: tuple[tuple[str, str], ...]) -> bool:
        identity = (metric_name, labels)
        if identity in self._series:
            return True
        if len(self._series) >= self._max_series:
            self._dropped_series += 1
            return False
        self._series.add(identity)
        return True

    def record_counter(self, name: str, labels: Mapping[str, object], value: float = 1) -> None:
        """Increase a counter using caller-supplied, non-sensitive labels."""

        if value < 0:
            raise ValueError("counter value must be non-negative")
        label_key = self._labels_key(labels)
        with self._lock:
            if self._allows_series(name, label_key):
                self._counters[name][label_key] = self._counters[name].get(label_key, 0) + value

    def record_summary(self, name: str, labels: Mapping[str, object], value: float) -> None:
        """Record one value as Prometheus summary ``_sum`` and ``_count``."""

        if value < 0:
            raise ValueError("summary value must be non-negative")
        label_key = self._labels_key(labels)
        with self._lock:
            if self._allows_series(name, label_key):
                state = self._summaries[name].setdefault(label_key, [0.0, 0.0])
                state[0] += value
                state[1] += 1

    def record_http_request(
        self,
        *,
        method: str,
        status_code: int,
        duration_seconds: float,
        profile: str,
    ) -> None:
        """Record one HTTP request using only bounded operational dimensions."""

        labels = {
            "method": method.upper() if method.upper() in _HTTP_METHODS else "OTHER",
            "profile": profile if profile in _PROFILES else "other",
            "status_code": str(status_code) if 100 <= int(status_code) <= 599 else "other",
        }
        self.record_counter("finetune_http_requests_total", labels)
        self.record_summary("finetune_http_request_duration_seconds", labels, duration_seconds)

    @staticmethod
    def _format_value(value: float) -> str:
        numeric = float(value)
        return str(int(numeric)) if numeric.is_integer() else format(numeric, ".12g")

    @staticmethod
    def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
        if not labels:
            return ""
        escaped = [f'{key}="{LocalTelemetryRegistry._escape_label_value(value)}"' for key, value in labels]
        return "{" + ",".join(escaped) + "}"

    @staticmethod
    def _escape_label_value(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    def render_prometheus(self) -> str:
        """Render a Prometheus 0.0.4 text exposition snapshot."""

        with self._lock:
            counters = {name: values.copy() for name, values in self._counters.items()}
            summaries = {
                name: {labels: values.copy() for labels, values in grouped.items()}
                for name, grouped in self._summaries.items()
            }
            dropped_series = self._dropped_series

        lines = [
            "# HELP finetune_http_requests_total Total HTTP responses observed by the local process.",
            "# TYPE finetune_http_requests_total counter",
        ]
        for name in sorted(counters):
            if name != "finetune_http_requests_total":
                lines.extend((f"# TYPE {name} counter",))
            for labels, value in sorted(counters[name].items()):
                lines.append(f"{name}{self._format_labels(labels)} {self._format_value(value)}")
        for name in sorted(summaries):
            lines.append(f"# TYPE {name} summary")
            for labels, (total, count) in sorted(summaries[name].items()):
                rendered = self._format_labels(labels)
                lines.append(f"{name}_sum{rendered} {self._format_value(total)}")
                lines.append(f"{name}_count{rendered} {self._format_value(count)}")
        lines.extend(
            (
                "# HELP finetune_telemetry_dropped_series_total New metric series discarded because the local cap was reached.",
                "# TYPE finetune_telemetry_dropped_series_total counter",
                f"finetune_telemetry_dropped_series_total {dropped_series}",
            )
        )
        return "\n".join(lines) + "\n"


_registry = LocalTelemetryRegistry()


def get_telemetry_registry() -> LocalTelemetryRegistry:
    """Return the process-local aggregate telemetry registry."""

    return _registry


def configure_telemetry(max_series: int) -> LocalTelemetryRegistry:
    """Replace an untouched registry when configuration changes at startup."""

    global _registry
    with _registry._lock:
        if _registry._series or _registry._dropped_series:
            return _registry
        if _registry._max_series != max_series:
            _registry = LocalTelemetryRegistry(max_series=max_series)
        return _registry


def reset_telemetry_for_tests(max_series: int = 256) -> None:
    """Reset global state for isolated tests; not an application endpoint."""

    global _registry
    _registry = LocalTelemetryRegistry(max_series=max_series)


__all__ = [
    "LocalTelemetryRegistry",
    "PROMETHEUS_CONTENT_TYPE",
    "configure_telemetry",
    "get_telemetry_registry",
    "reset_telemetry_for_tests",
]

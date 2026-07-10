"""Request-scoped tracing context kept entirely inside this process."""

from contextvars import ContextVar

# ``trace_id_var`` remains available for legacy callers.  New code should use
# ``correlation_id_var`` so HTTP, Agent, training, and provider work can share
# one neutral request correlation primitive.
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")


def get_correlation_id() -> str:
    """Return the current request correlation ID, if one is active."""

    return correlation_id_var.get()


__all__ = [
    "correlation_id_var",
    "get_correlation_id",
    "trace_id_var",
    "user_id_var",
]

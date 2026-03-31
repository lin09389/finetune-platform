from contextvars import ContextVar

# 全局 Trace ID 上下文
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")

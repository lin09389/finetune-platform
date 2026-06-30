"""Backward-compatible Finetune Platform backend entrypoint.

The application assembly now lives in :mod:`apps`. Existing commands and tests
may continue importing ``main:app`` or launching ``server.main:app``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from apps.combined import app  # noqa: E402
from apps.factory import (  # noqa: E402
    UnicodeJSONResponse,
    api_info,
    check_rate_limit,
    health_check,
    logger,
    root,
    settings,
)

__all__ = [
    "UnicodeJSONResponse",
    "api_info",
    "app",
    "check_rate_limit",
    "health_check",
    "logger",
    "root",
    "settings",
]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=os.getenv("DEBUG", "false").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )

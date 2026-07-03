from __future__ import annotations

import os
import sys
import inspect
from pathlib import Path

# Ensure tests run with predictable local defaults before app imports settings.
os.environ.setdefault("ENABLE_AUTH", "false")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALLOWED_ORIGINS", "*")
# Legacy API tests exercise the explicit compatibility path. Worker-mode tests
# opt in with a Settings override and an isolated temporary database.
os.environ.setdefault("TRAINING_EXECUTION_MODE", "in_process")
os.environ.setdefault("INFERENCE_EXECUTION_MODE", "in_process")

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))


def _patch_starlette_testclient_for_httpx_028() -> None:
    """Allow Starlette 0.35 TestClient to run with httpx 0.28 in this test env."""

    try:
        import httpx
    except Exception:
        return
    if "app" in inspect.signature(httpx.Client.__init__).parameters:
        return
    if getattr(httpx.Client.__init__, "_finetune_platform_patched", False):
        return

    original_init = httpx.Client.__init__

    def patched_init(self, *args, **kwargs):
        kwargs.pop("app", None)
        return original_init(self, *args, **kwargs)

    patched_init._finetune_platform_patched = True
    httpx.Client.__init__ = patched_init


_patch_starlette_testclient_for_httpx_028()

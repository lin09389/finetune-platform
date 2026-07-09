from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

# Ensure tests run with predictable local defaults before app imports settings.
os.environ.setdefault("ENABLE_AUTH", "false")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALLOWED_ORIGINS", "*")
# Explicit local agent auth opt-in for optional-auth desktop tests (not production).
os.environ.setdefault("ALLOW_LOCAL_AGENT_AUTH", "true")
# Stable non-default key for service-mode inference tests.
os.environ.setdefault("INFERENCE_INTERNAL_API_KEY", "test-internal-inference-key")
# Development tests expect experimental routes (CUA/MCP/…) registered.
os.environ.setdefault("ENABLE_EXPERIMENTAL_CAPABILITIES", "true")
# Align default test execution mode with production defaults.
# Tests now run against the worker/service boundary by default, using
# Test Doubles for the GPU worker and the inference service process.
os.environ.setdefault("TRAINING_EXECUTION_MODE", "worker")
os.environ.setdefault("INFERENCE_EXECUTION_MODE", "service")
# Use an isolated test database by default.
os.environ.setdefault("FINETUNE_PLATFORM_DB_PATH", "data/app_test.db")

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


# Import pytest late so that the environment variables above are set before
# any application code imports settings.
import pytest as _pytest  # noqa: E402

# Register shared fixture modules so they are available to all tests without
# relying on implicit discovery (which does not happen under ``server/``).
pytest_plugins = ["tests.fixtures.execution_mode"]


@_pytest.fixture(autouse=True)
def _reset_global_singletons():
    """Reset process-wide singletons before and after each test.

    This keeps the default worker/service test mode from leaking state
    between tests that touch training/inference singletons.
    """
    from training_worker.repository import reset_training_job_repositories_for_tests

    from core.state import StateManager
    from core.training_context import reset_training_context

    reset_training_job_repositories_for_tests()
    reset_training_context()
    StateManager._instance = None
    yield
    reset_training_job_repositories_for_tests()
    reset_training_context()
    StateManager._instance = None


@_pytest.fixture(autouse=True)
def _close_deepagents_runners():
    """Close compat checkpointer contexts created by DeepAgentsSessionRunner.

    Tests that build a runner directly and reach ``_get_checkpointer`` (the
    compatibility helper) would otherwise leak aiosqlite connections. This runs
    after every test, drains the live-runner WeakSet, and closes any pending
    contexts on a fresh event loop (safe whether or not the test used asyncio).
    """
    yield
    import asyncio as _asyncio

    try:
        from agent_session.deepagents_runtime import _RUNNER_INSTANCES
    except Exception:
        return
    runners = list(_RUNNER_INSTANCES)
    if not runners:
        return
    loop = _asyncio.new_event_loop()
    try:
        for runner in runners:
            try:
                loop.run_until_complete(runner.aclose())
            except Exception:
                pass
    finally:
        loop.close()


@_pytest.fixture
def inference_in_process(monkeypatch):
    """Temporarily switch to the in-process inference path for a test."""
    from core.config import settings

    monkeypatch.setattr(settings, "inference_execution_mode", "in_process")


@_pytest.fixture
def training_in_process(monkeypatch):
    """Temporarily switch to the in-process training path for a test."""
    from core.config import settings

    monkeypatch.setattr(settings, "training_execution_mode", "in_process")

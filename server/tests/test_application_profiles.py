from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from typing import Any

import pytest


def _paths(app) -> set[str]:
    """Collect registered HTTP + WebSocket paths across FastAPI route layouts.

    FastAPI 0.137+ wraps ``include_router`` entries as ``_IncludedRouter``
    objects without a top-level ``.path``. OpenAPI covers HTTP routes; WebSocket
    routes (e.g. ``/gateway/ws``) are recovered from route contexts /
    ``original_route.path``.
    """
    paths: set[str] = set()
    try:
        paths.update((app.openapi() or {}).get("paths", {}) or {})
    except Exception:
        pass

    for route in app.routes:
        path = getattr(route, "path", None)
        if isinstance(path, str) and path:
            paths.add(path)
        contexts = getattr(route, "effective_route_contexts", None)
        if not callable(contexts):
            continue
        for ctx in contexts():
            original = getattr(ctx, "original_route", None)
            for candidate in (
                getattr(ctx, "path", None),
                getattr(ctx, "path_format", None),
                getattr(original, "path", None),
                getattr(original, "path_format", None),
            ):
                if isinstance(candidate, str) and candidate:
                    paths.add(candidate)
    return paths


def _endpoint_for_path(app, path: str) -> Callable[..., Any]:
    for route in app.routes:
        if getattr(route, "path", None) == path and hasattr(route, "endpoint"):
            return route.endpoint
        contexts = getattr(route, "effective_route_contexts", None)
        if callable(contexts):
            for ctx in contexts():
                if getattr(ctx, "path", None) == path and getattr(ctx, "endpoint", None):
                    return ctx.endpoint
    raise LookupError(f"No endpoint registered for path {path!r}")


def test_combined_profile_preserves_legacy_application_contract():
    import main
    from apps.combined import app as combined_app

    paths = _paths(combined_app)

    assert main.app is combined_app
    assert combined_app.state.profile == "combined"
    # Route registrations evolve as capabilities are added; the compatibility
    # contract is the required public route set below, not a brittle count.
    assert combined_app.routes
    assert {
        "/device/info",
        "/models",
        "/datasets",
        "/training/history",
        "/inference/models",
        "/v1/chat/completions",
        "/chat/sessions",
        "/agent-sessions",
        "/agent-eval/overview",
        "/knowledge/collections",
        "/workspace/workspaces",
        "/runtime/bootstrap",
        "/gateway/ws",
        "/api/info",
        "/model-runtime/overview",
        "/model-runtime/selection",
    } <= paths


def test_agent_profile_owns_workspace_and_agent_routes_only():
    from apps.agent import app

    paths = _paths(app)

    assert app.state.profile == "agent"
    assert {
        "/agents",
        "/agent-sessions",
        "/agent-eval/overview",
        "/chat/sessions",
        "/knowledge/collections",
        "/workspace/workspaces",
        "/memory/files",
    } <= paths
    assert "/training/history" not in paths
    assert "/inference/models" not in paths
    assert "/v1/models" not in paths


def test_finetune_profile_owns_gpu_and_model_lifecycle_routes_only():
    from apps.finetune import app

    paths = _paths(app)

    assert app.state.profile == "finetune"
    assert {
        "/device/info",
        "/models",
        "/datasets",
        "/training/history",
        "/evaluation/runs",
        "/deployment/packages",
        "/inference/models",
        "/v1/models",
        "/model-runtime/overview",
        "/model-runtime/selection",
    } <= paths
    assert "/agent-sessions" not in paths
    assert "/agent-eval/overview" not in paths
    assert "/chat/sessions" not in paths
    assert "/workspace/workspaces" not in paths


@pytest.mark.asyncio
@pytest.mark.parametrize("module", ("apps.agent", "apps.finetune"))
async def test_api_info_exposes_agent_model_capability_for_each_profile(module):
    app = __import__(module, fromlist=["app"]).app
    endpoint = _endpoint_for_path(app, "/api/info")

    payload = await endpoint()

    assert "agent_model_runtime" in payload
    assert payload["agent_model_runtime"]["local_tool_calling_supported"] is False
    assert "backends" in payload["agent_model_runtime"]
    assert "recommended_agent_providers" in payload["agent_model_runtime"]
    assert payload["agent_model_runtime"]["backends"]["ollama"]["tool_calling"] is True
    assert payload["agent_model_runtime"]["backends"]["llama-cpp"]["tool_calling"] is False
    assert "llamacpp" not in payload["agent_model_runtime"]["backends"]


@pytest.mark.parametrize(
    ("module", "forbidden_modules"),
    [
        ("apps.agent", ("api.training", "api.inference")),
        ("apps.finetune", ("api.agent_sessions", "agent_session.service")),
    ],
)
def test_profile_import_does_not_eagerly_load_other_domain(module, forbidden_modules):
    expression = (
        f"import sys, {module}; "
        f"assert not any(name in sys.modules for name in {forbidden_modules!r})"
    )

    import pathlib
    server_dir = str(pathlib.Path(__file__).resolve().parent.parent)
    completed = subprocess.run(
        [sys.executable, "-c", expression],
        check=False,
        capture_output=True,
        text=True,
        cwd=server_dir,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.asyncio
async def test_main_keeps_api_info_compatibility_export():
    import main

    payload = await main.api_info()

    assert payload["endpoints"]["runtime"] == "/runtime/bootstrap"


@pytest.mark.asyncio
async def test_agent_lifespan_does_not_initialize_or_shutdown_finetune(monkeypatch):
    from apps import lifespan as lifecycle
    from apps.profiles import ApplicationProfile

    events: list[str] = []

    monkeypatch.setattr(lifecycle, "_warn_about_auth_configuration", lambda: events.append("auth"))
    monkeypatch.setattr(lifecycle, "_initialize_storage", lambda: events.append("storage"))

    async def init_agent():
        events.append("agent:init")

    async def init_finetune():
        events.append("finetune:init")
        return object()

    async def stop_agent():
        events.append("agent:stop")

    async def stop_finetune(_server):
        events.append("finetune:stop")

    async def stop_shared():
        events.append("shared:stop")

    monkeypatch.setattr(lifecycle, "_initialize_agent_services", init_agent)
    monkeypatch.setattr(lifecycle, "_initialize_finetune_services", init_finetune)
    monkeypatch.setattr(lifecycle, "_shutdown_agent_services", stop_agent)
    monkeypatch.setattr(lifecycle, "_shutdown_finetune_services", stop_finetune)
    monkeypatch.setattr(lifecycle, "_shutdown_shared_services", stop_shared)

    async with lifecycle.create_lifespan(ApplicationProfile.AGENT)(object()):
        events.append("running")

    assert events == ["auth", "storage", "agent:init", "running", "agent:stop", "shared:stop"]


@pytest.mark.asyncio
async def test_finetune_lifespan_does_not_initialize_or_shutdown_agent(monkeypatch):
    from apps import lifespan as lifecycle
    from apps.profiles import ApplicationProfile

    events: list[str] = []
    grpc_server = object()

    monkeypatch.setattr(lifecycle, "_warn_about_auth_configuration", lambda: events.append("auth"))
    monkeypatch.setattr(lifecycle, "_initialize_storage", lambda: events.append("storage"))

    async def init_agent():
        events.append("agent:init")

    async def init_finetune():
        events.append("finetune:init")
        return grpc_server

    async def stop_agent():
        events.append("agent:stop")

    async def stop_finetune(server):
        assert server is grpc_server
        events.append("finetune:stop")

    async def stop_shared():
        events.append("shared:stop")

    monkeypatch.setattr(lifecycle, "_initialize_agent_services", init_agent)
    monkeypatch.setattr(lifecycle, "_initialize_finetune_services", init_finetune)
    monkeypatch.setattr(lifecycle, "_shutdown_agent_services", stop_agent)
    monkeypatch.setattr(lifecycle, "_shutdown_finetune_services", stop_finetune)
    monkeypatch.setattr(lifecycle, "_shutdown_shared_services", stop_shared)

    async with lifecycle.create_lifespan(ApplicationProfile.FINETUNE)(object()):
        events.append("running")

    assert events == [
        "auth",
        "storage",
        "finetune:init",
        "running",
        "finetune:stop",
        "shared:stop",
    ]

"""Gateway API signature contract tests.

These tests lock API-route-to-manager method contracts to prevent
future interface drift.
"""

from __future__ import annotations

import inspect

from gateway import (
    get_binding_manager,
    get_gateway_server,
    get_gateway_session_manager,
    get_message_router,
)
from gateway.agent_isolation import get_isolation_manager
from gateway.cross_agent import get_cross_agent_communicator
from gateway.device_auth import get_device_auth_manager


def _assert_has_params(obj, method_name: str, expected_params: list[str]) -> None:
    assert hasattr(obj, method_name), f"{obj.__class__.__name__}.{method_name} is missing"
    method = getattr(obj, method_name)
    assert callable(method), f"{obj.__class__.__name__}.{method_name} is not callable"

    sig = inspect.signature(method)
    params = list(sig.parameters.keys())
    for expected in expected_params:
        assert expected in params, (
            f"{obj.__class__.__name__}.{method_name} missing param '{expected}', got {params}"
        )


def test_gateway_core_status_contract():
    gateway = get_gateway_server()
    router = get_message_router()
    sessions = get_gateway_session_manager()
    binding = get_binding_manager()
    isolation = get_isolation_manager()
    auth = get_device_auth_manager()
    comm = get_cross_agent_communicator()

    for obj, method in [
        (gateway, "get_stats"),
        (gateway, "handle_websocket"),
        (router, "get_routing_stats"),
        (sessions, "get_stats"),
        (binding, "get_stats"),
        (isolation, "get_all_workspaces"),
        (auth, "get_stats"),
        (comm, "get_channel_stats"),
    ]:
        assert hasattr(obj, method), f"{obj.__class__.__name__}.{method} is missing"
        assert callable(getattr(obj, method)), f"{obj.__class__.__name__}.{method} is not callable"


def test_gateway_device_auth_contract():
    auth = get_device_auth_manager()

    _assert_has_params(auth, "register_device", ["device_id", "device_type", "device_name", "metadata"])
    _assert_has_params(auth, "authenticate_device", ["device_id", "token"])
    _assert_has_params(auth, "create_challenge", ["device_id"])
    _assert_has_params(auth, "verify_challenge", ["device_id", "challenge_id", "signed_response"])
    _assert_has_params(auth, "get_devices_by_type", ["device_type"])
    _assert_has_params(auth, "get_devices_by_status", ["status"])
    _assert_has_params(auth, "get_all_devices", [])
    _assert_has_params(auth, "get_device_info", ["device_id"])
    _assert_has_params(auth, "unregister_device", ["device_id"])
    _assert_has_params(
        auth,
        "set_permissions",
        ["device_id", "level", "allowed_actions", "denied_actions", "rate_limit"],
    )


def test_gateway_binding_contract():
    binding = get_binding_manager()

    _assert_has_params(binding, "register_agent", ["agent"])
    _assert_has_params(binding, "add_binding", ["rule"])
    _assert_has_params(binding, "get_agent_bindings", ["agent_id"])
    _assert_has_params(binding, "get_all_bindings", [])
    _assert_has_params(binding, "remove_binding", ["rule_id"])


def test_gateway_cross_agent_contract():
    comm = get_cross_agent_communicator()

    _assert_has_params(
        comm,
        "send_message",
        ["source_agent", "target_agent", "payload", "message_type", "priority", "correlation_id", "timeout"],
    )
    _assert_has_params(comm, "send_and_wait", ["source_agent", "target_agent", "payload", "timeout"])
    _assert_has_params(comm, "broadcast", ["source_agent", "payload", "exclude"])
    _assert_has_params(comm, "spawn_agent", ["parent_agent", "task_type", "config"])
    _assert_has_params(comm, "get_spawned_agents", ["parent_agent"])
    _assert_has_params(comm, "terminate_agent", ["agent_id"])
    _assert_has_params(comm, "collect_results", ["agent_ids", "timeout"])
    _assert_has_params(comm, "merge_results", ["results", "strategy"])

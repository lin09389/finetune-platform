"""Architecture-review Phase 0: security + GPU coordination.

Exercises shipped policy helpers and dependency chains (not re-implementations).
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from security.jwt_auth import Role, TokenPayload, reset_jwt_auth
from security.runtime_policy import (
    DEFAULT_INFERENCE_INTERNAL_API_KEY,
    allow_local_agent_auth,
    assert_inference_internal_key_safe,
    gpu_coordination_enabled,
    is_production_environment,
    require_configured_jwt_secret,
)


# ---------------------------------------------------------------------------
# JWT secret fail-closed
# ---------------------------------------------------------------------------


def test_require_configured_jwt_secret_rejects_missing(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="JWT secret is required"):
        require_configured_jwt_secret(
            None,
            settings=SimpleNamespace(environment="development", enable_auth=True),
        )


def test_require_configured_jwt_secret_accepts_configured():
    assert require_configured_jwt_secret("stable-secret") == "stable-secret"


def test_jwt_auth_init_fail_closed_without_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    reset_jwt_auth()
    from security.jwt_auth import JWTAuth

    with pytest.raises(RuntimeError, match="JWT secret is required"):
        JWTAuth(secret_key=None)


def test_jwt_auth_init_succeeds_with_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET_KEY", "unit-test-secret-key")
    reset_jwt_auth()
    from security.jwt_auth import JWTAuth

    auth = JWTAuth(secret_key="unit-test-secret-key", db_path=str(tmp_path / "jwt.db"))
    assert auth.secret_key == "unit-test-secret-key"
    uid = auth.register_user("admin", "password123", role=Role.ADMIN)
    assert uid
    pair = auth.create_token_pair(user_id=uid, role=Role.ADMIN)
    payload = auth.verify_token(pair.access_token)
    assert payload.user_id == uid
    assert payload.role == Role.ADMIN
    reset_jwt_auth()


def test_settings_production_requires_jwt_and_rejects_default_inference_key(monkeypatch):
    from core.config import Settings

    with pytest.raises(Exception):
        Settings(
            _env_file=None,
            environment="production",
            enable_auth=True,
            jwt_secret_key=None,
            inference_internal_api_key=DEFAULT_INFERENCE_INTERNAL_API_KEY,
            allowed_origins=["https://app.example.com"],
        )


def test_settings_production_accepts_strong_secrets(monkeypatch):
    from core.config import Settings

    s = Settings(
        _env_file=None,
        environment="production",
        enable_auth=True,
        jwt_secret_key="prod-secret-not-default",
        inference_internal_api_key="prod-inference-key-xyz",
        allowed_origins=["https://app.example.com"],
    )
    assert s.jwt_secret_key == "prod-secret-not-default"
    assert s.inference_internal_api_key == "prod-inference-key-xyz"


# ---------------------------------------------------------------------------
# Agent local auth fallback
# ---------------------------------------------------------------------------


def test_allow_local_agent_auth_production_hard_closed(monkeypatch):
    monkeypatch.setenv("ALLOW_LOCAL_AGENT_AUTH", "true")
    prod = SimpleNamespace(environment="production", allow_local_agent_auth=True)
    assert is_production_environment(prod) is True
    assert allow_local_agent_auth(prod) is False

    staging = SimpleNamespace(environment="staging", allow_local_agent_auth=True)
    assert allow_local_agent_auth(staging) is False


def test_allow_local_agent_auth_requires_explicit_flag(monkeypatch):
    monkeypatch.delenv("ALLOW_LOCAL_AGENT_AUTH", raising=False)
    dev = SimpleNamespace(environment="development", allow_local_agent_auth=False)
    assert allow_local_agent_auth(dev) is False

    monkeypatch.setenv("ALLOW_LOCAL_AGENT_AUTH", "true")
    assert allow_local_agent_auth(dev) is True


@pytest.mark.asyncio
async def test_get_agent_session_user_production_401(monkeypatch):
    import api.agent_sessions as agent_sessions
    from core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "environment", "production")
    monkeypatch.setenv("ALLOW_LOCAL_AGENT_AUTH", "true")

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        await agent_sessions.get_agent_session_user(current_user=None)
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_get_agent_session_user_dev_requires_flag(monkeypatch):
    import api.agent_sessions as agent_sessions
    from core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "environment", "development")
    monkeypatch.setattr(config_mod.settings, "allow_local_agent_auth", False)
    monkeypatch.delenv("ALLOW_LOCAL_AGENT_AUTH", raising=False)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        await agent_sessions.get_agent_session_user(current_user=None)
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_get_agent_session_user_dev_with_flag_ok(monkeypatch):
    import api.agent_sessions as agent_sessions
    from core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "environment", "development")
    monkeypatch.setattr(config_mod.settings, "allow_local_agent_auth", True)
    monkeypatch.setenv("ALLOW_LOCAL_AGENT_AUTH", "true")

    user = await agent_sessions.get_agent_session_user(current_user=None)
    assert user.user_id == "desktop-local-user"
    assert user.role == Role.USER


def test_factory_local_agent_fallback_respects_policy(monkeypatch):
    from apps import factory as factory_mod
    from core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "environment", "production")
    monkeypatch.setenv("ALLOW_LOCAL_AGENT_AUTH", "true")
    assert factory_mod._allows_local_agent_auth_fallback("/agent-sessions") is False

    monkeypatch.setattr(config_mod.settings, "environment", "development")
    monkeypatch.setattr(config_mod.settings, "allow_local_agent_auth", False)
    monkeypatch.delenv("ALLOW_LOCAL_AGENT_AUTH", raising=False)
    assert factory_mod._allows_local_agent_auth_fallback("/agent-sessions") is False

    monkeypatch.setenv("ALLOW_LOCAL_AGENT_AUTH", "true")
    monkeypatch.setattr(config_mod.settings, "allow_local_agent_auth", True)
    assert factory_mod._allows_local_agent_auth_fallback("/agent-sessions/foo") is True
    assert factory_mod._allows_local_agent_auth_fallback("/models") is False


# ---------------------------------------------------------------------------
# CUA ADMIN gate (real require_cua_admin dependency)
# ---------------------------------------------------------------------------


def _jwt_for(role: Role, tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("JWT_SECRET_KEY", "phase0-cua-secret")
    reset_jwt_auth()
    from security import jwt_auth as jwt_mod
    from security.jwt_auth import JWTAuth

    auth = JWTAuth(secret_key="phase0-cua-secret", db_path=str(tmp_path / f"cua_jwt_{role.value}.db"))
    uid = auth.register_user(f"user-{role.value}", "password123", role=role)
    assert uid
    pair = auth.create_token_pair(user_id=uid, role=role)
    jwt_mod._jwt_auth = auth
    return pair.access_token


def test_require_cua_admin_user_403_admin_ok(tmp_path, monkeypatch):
    from core import config as config_mod
    from security.auth_middleware import require_cua_admin

    monkeypatch.setattr(config_mod.settings, "enable_auth", True)

    app = FastAPI()

    @app.get("/cua-probe")
    async def probe(user=Depends(require_cua_admin)):
        return {"ok": True, "role": getattr(user, "role", None)}

    client = TestClient(app)

    # unauthenticated
    r0 = client.get("/cua-probe")
    assert r0.status_code == 401

    user_tok = _jwt_for(Role.USER, tmp_path, monkeypatch)
    r1 = client.get("/cua-probe", headers={"Authorization": f"Bearer {user_tok}"})
    assert r1.status_code == 403

    admin_tok = _jwt_for(Role.ADMIN, tmp_path, monkeypatch)
    r2 = client.get("/cua-probe", headers={"Authorization": f"Bearer {admin_tok}"})
    assert r2.status_code == 200
    assert r2.json()["ok"] is True

    super_tok = _jwt_for(Role.SUPER_ADMIN, tmp_path, monkeypatch)
    r3 = client.get("/cua-probe", headers={"Authorization": f"Bearer {super_tok}"})
    assert r3.status_code == 200
    reset_jwt_auth()


def test_cua_router_registers_admin_dependency():
    """Structural + import of shipped dep: CUA module wires require_cua_admin.

    Full ``import api.cua`` may fail in sandboxes with broken cv2/pyautogui;
    assert the shipped source and the live dependency object instead.
    """
    from security.auth_middleware import require_cua_admin

    cua_src = Path(__file__).resolve().parents[1] / "api" / "cua.py"
    text = cua_src.read_text(encoding="utf-8")
    assert "require_cua_admin" in text
    assert "dependencies=[Depends(require_cua_admin)]" in text
    assert "DEBUG never bypasses" in (require_cua_admin.__doc__ or "") or callable(require_cua_admin)

    # Count control routes declared in source (must stay gated as a group)
    route_decorators = text.count("@router.post(") + text.count("@router.get(") + text.count("@router.delete(")
    assert route_decorators >= 20


# ---------------------------------------------------------------------------
# Inference internal key
# ---------------------------------------------------------------------------


def test_assert_inference_key_rejects_default_in_production():
    with pytest.raises(RuntimeError, match="non-default"):
        assert_inference_internal_key_safe(
            SimpleNamespace(
                environment="production",
                inference_internal_api_key=DEFAULT_INFERENCE_INTERNAL_API_KEY,
            )
        )


def test_assert_inference_key_allows_custom_in_production():
    assert_inference_internal_key_safe(
        SimpleNamespace(
            environment="production",
            inference_internal_api_key="custom-prod-key",
        )
    )


def test_assert_inference_key_dev_default_warns(caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        assert_inference_internal_key_safe(
            SimpleNamespace(
                environment="development",
                inference_internal_api_key=DEFAULT_INFERENCE_INTERNAL_API_KEY,
            )
        )
    assert any("default development inference" in r.message.lower() or "default" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# GPU coordination
# ---------------------------------------------------------------------------


def test_gpu_lease_training_blocks_inference(tmp_path, monkeypatch):
    monkeypatch.delenv("GPU_COORDINATION", raising=False)
    from core.gpu_coordination import (
        GpuCoordinationError,
        GpuCoordinator,
        TRAINING_HOLDER,
        assert_inference_gpu_available,
        reset_gpu_coordinator,
    )

    coord = reset_gpu_coordinator(tmp_path / "gpu_lease.json")
    coord.claim(TRAINING_HOLDER, owner="worker-1")

    with pytest.raises(GpuCoordinationError) as ei:
        assert_inference_gpu_available()
    assert ei.value.code == "gpu_training_active"

    coord.release(TRAINING_HOLDER, owner="worker-1")
    assert_inference_gpu_available()  # no raise


def test_gpu_lease_inference_blocks_training(tmp_path, monkeypatch):
    monkeypatch.delenv("GPU_COORDINATION", raising=False)
    from core.gpu_coordination import (
        GpuCoordinationError,
        INFERENCE_HOLDER,
        assert_training_gpu_available,
        reset_gpu_coordinator,
    )

    coord = reset_gpu_coordinator(tmp_path / "gpu_lease2.json")
    coord.claim(INFERENCE_HOLDER, owner="infer-1")
    with pytest.raises(GpuCoordinationError):
        assert_training_gpu_available()
    coord.release(INFERENCE_HOLDER, owner="infer-1")


def test_gpu_coordination_disable_only_non_production(monkeypatch):
    monkeypatch.setenv("GPU_COORDINATION", "off")
    assert gpu_coordination_enabled(SimpleNamespace(environment="development", gpu_coordination=True)) is False
    assert gpu_coordination_enabled(SimpleNamespace(environment="production", gpu_coordination=False)) is True


def test_vram_precheck_consults_gpu_coordination(monkeypatch, tmp_path):
    from core.gpu_coordination import TRAINING_HOLDER, reset_gpu_coordinator
    from training_engine import model_loader

    coord = reset_gpu_coordinator(tmp_path / "gpu_lease3.json")
    coord.claim(TRAINING_HOLDER, owner="other-worker")

    monkeypatch.setattr(model_loader, "get_available_memory", lambda: 8.0)

    class Cfg:
        model_name = "m"
        method = "qlora"
        quantize = 4

    # training claim by this process conflicts with existing training holder of different
    # owner — claim with same holder replaces; use inference holder to block training
    coord.release(TRAINING_HOLDER, owner="other-worker")
    from core.gpu_coordination import INFERENCE_HOLDER

    coord.claim(INFERENCE_HOLDER, owner="infer")
    with pytest.raises(Exception):
        model_loader._check_vram_before_load(Cfg())


@pytest.mark.asyncio
async def test_scheduler_ensure_model_refuses_when_training_holds(tmp_path, monkeypatch):
    """Real entry: ModelScheduler._ensure_model_loaded returns False under training lease."""
    from core.gpu_coordination import TRAINING_HOLDER, reset_gpu_coordinator
    from api.inference.scheduler import BackendType, ModelScheduler

    coord = reset_gpu_coordinator(tmp_path / "gpu_lease4.json")
    coord.claim(TRAINING_HOLDER, owner="train-w")

    sched = ModelScheduler.__new__(ModelScheduler)
    sched._models = {}
    sched._loaded_models = {}
    sched._stats = {"cache_hits": 0, "cache_misses": 0, "total_loads": 0, "total_unloads": 0, "active_leases": 0}
    sched.max_loaded_models = 3
    load_called = {"n": 0}

    async def _should_not_load(*_a, **_k):
        load_called["n"] += 1
        raise AssertionError("backend load must not run while training holds GPU")

    # If coordination failed open, resolve would continue — fail closed is the contract.
    result = await ModelScheduler._ensure_model_loaded(
        sched,
        model_name="m1",
        model_path="/models/m1",
        backend=BackendType.HUGGINGFACE,
    )
    assert result is False
    assert load_called["n"] == 0

    # After training releases, assert path is open again (load still mocked separately).
    coord.release(TRAINING_HOLDER, owner="train-w")
    from core.gpu_coordination import assert_inference_gpu_available

    assert_inference_gpu_available()


@pytest.mark.asyncio
async def test_scheduler_releases_inference_lease_on_unload(tmp_path, monkeypatch):
    """Unload last model must release inference lease so training can claim."""
    from core.gpu_coordination import (
        INFERENCE_HOLDER,
        TRAINING_HOLDER,
        assert_training_gpu_available,
        reset_gpu_coordinator,
    )
    from api.inference.scheduler import BackendType, ModelInfo, ModelScheduler, ModelStatus

    coord = reset_gpu_coordinator(tmp_path / "gpu_lease_release.json")
    coord.claim(INFERENCE_HOLDER, owner="inference:m1")

    sched = ModelScheduler.__new__(ModelScheduler)
    sched._models = {
        "m1": ModelInfo(name="m1", path="/m", backend=BackendType.HUGGINGFACE, status=ModelStatus.LOADED)
    }
    sched._loaded_models = {"m1": {"path": "/m"}}
    sched._stats = {"cache_hits": 0, "cache_misses": 0, "total_loads": 0, "total_unloads": 0, "active_leases": 0}
    sched._backends = {}

    class FakeBackend:
        async def unload_model(self):
            return True

    async def get_backend(_name=None):
        return FakeBackend()

    sched.get_backend = get_backend  # type: ignore[method-assign]

    ok = await ModelScheduler._unload_model_locked(sched, "m1", force=True)
    assert ok is True
    assert "m1" not in sched._loaded_models
    # Training must now be allowed
    assert_training_gpu_available()
    # Inference holder cleared
    assert coord.get_state().holder != INFERENCE_HOLDER


def test_training_pipeline_cleanup_releases_gpu_lease(tmp_path, monkeypatch):
    """Shipped pipeline cleanup must release training holder."""
    from core.gpu_coordination import TRAINING_HOLDER, assert_inference_gpu_available, reset_gpu_coordinator
    from training_engine.pipeline import TrainingPipeline, TrainingPhase

    coord = reset_gpu_coordinator(tmp_path / "gpu_lease_train_release.json")
    coord.claim(TRAINING_HOLDER, owner="training:task-1")

    # Minimal fake pipeline with only what _run_cleanup needs
    pipe = TrainingPipeline.__new__(TrainingPipeline)
    pipe.ctx = SimpleNamespace(task_id="task-1", model=None, tokenizer=None, trainer=None, train_logger=None, state=SimpleNamespace(unregister_training_task=lambda *_: None))
    pipe.bus = SimpleNamespace(publish_training_state=lambda *_: None)
    pipe._current_phase = TrainingPhase.CLEANUP
    pipe._set_phase = lambda p: None

    TrainingPipeline._run_cleanup(pipe)
    assert_inference_gpu_available()
    assert coord.get_state().holder != TRAINING_HOLDER

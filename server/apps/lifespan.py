"""Composable startup and shutdown ownership for backend app profiles."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI

from core.config import settings

from .profiles import ApplicationProfile

logger = logging.getLogger("finetune-platform")
_TRAINING_RECONCILER: Any | None = None
# P1-7: API-side recover loop — periodically checks Worker liveness and
# hard-recovers expired leases only when no alive Worker is observed.
_TRAINING_RECOVER_TASK: Any | None = None
# Populated during Agent profile startup; consumed by /api/info (agent_ready).
_AGENT_READINESS: dict[str, Any] = {
    "ready": False,
    "session_service": False,
    "context_service": False,
    "memory_service": False,
    "issues": ["not_initialized"],
}


def get_agent_readiness() -> dict[str, Any]:
    """Return a shallow copy of the latest Agent service readiness snapshot."""
    return {
        "ready": bool(_AGENT_READINESS.get("ready")),
        "session_service": bool(_AGENT_READINESS.get("session_service")),
        "context_service": bool(_AGENT_READINESS.get("context_service")),
        "memory_service": bool(_AGENT_READINESS.get("memory_service")),
        "issues": list(_AGENT_READINESS.get("issues") or []),
    }


def _warn_about_auth_configuration() -> None:
    from security.runtime_policy import (
        assert_inference_internal_key_safe,
        is_production_environment,
        require_configured_jwt_secret,
    )

    if not settings.enable_auth:
        if is_production_environment(settings):
            raise RuntimeError(
                "SECURITY: Authentication cannot be disabled in production/staging "
                "(ENABLE_AUTH=false is forbidden)."
            )
        logger.warning(
            "SECURITY: Authentication is DISABLED (enable_auth=false). "
            "This should NEVER be used in production. "
            "Set ENABLE_AUTH=true and JWT_SECRET_KEY for production deployments."
        )
    if settings.enable_auth:
        # Fail-closed: align JWTAuth init with settings (no silent random secret).
        require_configured_jwt_secret(
            settings.jwt_secret_key or __import__("os").environ.get("JWT_SECRET_KEY"),
            settings=settings,
            source="lifespan",
        )
    try:
        assert_inference_internal_key_safe(settings)
    except RuntimeError:
        raise


def _warn_about_agent_runtime_environment() -> None:
    """Phase 4: surface venv / agent dependency gaps without failing startup."""
    try:
        from core.runtime_env import log_agent_runtime_environment

        log_agent_runtime_environment(logger)
    except Exception as exc:
        logger.debug("Agent runtime environment probe skipped: %s", exc)


def _initialize_storage() -> None:
    from core.storage import init_storage, migrate_json_state, storage_json_migrate_on_startup

    init_storage()
    if storage_json_migrate_on_startup():
        migrated = migrate_json_state()
        logger.info("SQLite storage initialized, migrated=%s", migrated)
    else:
        logger.info("SQLite storage initialized, JSON data migration skipped on startup")


def _cleanup_expired_langgraph_checkpoints() -> None:
    """Optionally prune only expired checkpoints from terminal Agent sessions."""
    if not settings.langgraph_checkpoint_cleanup_on_startup:
        return
    from core.storage import cleanup_langgraph_checkpoints

    try:
        result = cleanup_langgraph_checkpoints(
            max_age_days=settings.langgraph_checkpoint_retention_days,
            vacuum=settings.langgraph_checkpoint_vacuum_on_cleanup,
        )
        logger.info("LangGraph checkpoint cleanup complete: %s", result)
    except Exception as exc:
        # Retention is hygiene, never a prerequisite for serving requests.
        logger.warning("LangGraph checkpoint cleanup skipped: %s", exc)


def _cleanup_tmp_residue() -> None:
    """启动时清理中断上传留下的临时目录残留。

    只清理已知安全的命名前缀（multipart-finalize / compact-finalize），
    避免误删活跃的 dev server 或诊断目录。启动时不会有活跃上传，可安全删除。
    """
    import shutil

    tmp_dir = settings.base_dir / "tmp"
    if not tmp_dir.is_dir():
        return
    prefixes = ("agent-multipart-finalize-", "compact-finalize-")
    removed = 0
    for entry in tmp_dir.iterdir():
        if not entry.is_dir():
            continue
        name = entry.name
        if name == "agent-multipart-finalize" or any(name.startswith(p) for p in prefixes):
            try:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
            except Exception as exc:
                logger.debug("Failed to clean tmp entry %s: %s", name, exc)
    if removed:
        logger.info("Cleaned %d stale tmp residue directories", removed)


async def _initialize_agent_services() -> None:
    issues: list[str] = []
    session_ok = False
    context_ok = False
    memory_ok = False

    try:
        from api.agent_sessions import get_agent_session_service

        service = get_agent_session_service()
        recovered = await service.recover_async_subtasks()
        if recovered.get("scheduled") or recovered.get("synchronized"):
            logger.info("Async subagent recovery complete: %s", recovered)
        recovered_sessions = service.recover_active_sessions_after_restart()
        if (
            recovered_sessions.get("recovered")
            or recovered_sessions.get("preserved")
            or recovered_sessions.get("failed")
        ):
            logger.info("Agent session restart recovery complete: %s", recovered_sessions)
        session_ok = True
    except Exception as exc:
        issues.append(f"session_service:{exc}")
        logger.warning("Agent session recovery failed: %s", exc)

    await _initialize_training_reconciler()

    try:
        from api.chat.session import get_session_manager

        get_session_manager()
        logger.info("Chat session manager initialized")
    except Exception as exc:
        logger.warning("Session manager init failed: %s", exc)

    try:
        from context.service import get_context_service
        from rag.embedder import get_embedder
        from rag.vector_store import get_vector_store

        embedder = get_embedder()
        vector_store = get_vector_store()
        get_context_service(embedder=embedder, vector_store=vector_store)
        logger.info("Project context service initialized")
        context_ok = True
    except Exception as exc:
        issues.append(f"context_service:{exc}")
        logger.warning("Context service init failed: %s", exc)

    try:
        from memory.memory_service import get_memory_service

        get_memory_service()
        logger.info("Memory service initialized")
        memory_ok = True
    except Exception as exc:
        issues.append(f"memory_service:{exc}")
        logger.warning("Memory service init failed: %s", exc)

    # Core Agent path requires the session service. Context/memory are beta assist
    # layers: degrade agent_ready when missing, but do not hard-fail startup.
    ready = session_ok
    if not session_ok:
        issues = issues or ["session_service_unavailable"]
    _AGENT_READINESS.update(
        {
            "ready": ready,
            "session_service": session_ok,
            "context_service": context_ok,
            "memory_service": memory_ok,
            "issues": issues,
        }
    )
    if ready and issues:
        logger.warning("Agent services started in degraded mode: %s", issues)
    elif not ready:
        logger.error("Agent session service is not ready: %s", issues)


async def _training_recover_loop() -> None:
    """P1-7: API 进程周期性检查 Worker 存活状态。

    策略:
    - 有活 Worker 时,不调用 recover_expired(让 Worker 自愈,避免与 Worker 冲突)
    - 无活 Worker 时,硬清理过期 lease(防止 Worker 永不重启导致任务卡死)
    """
    while True:
        try:
            await asyncio.sleep(60)
            from training_worker.repository import get_training_job_repository

            repository = get_training_job_repository()
            # 用 2x lease_seconds 作为 stale 阈值,避免误判
            stale_after = max(60, int(settings.training_worker_lease_seconds) * 2)
            workers = repository.worker_status(stale_after_seconds=stale_after)
            alive_workers = [w for w in workers if w.get("status") == "online"]

            if not alive_workers:
                recovered = repository.recover_expired()
                requeued = recovered.get("requeued", 0)
                interrupted = recovered.get("interrupted", 0)
                cancelled = recovered.get("cancelled", 0)
                if requeued or interrupted or cancelled:
                    logger.warning(
                        "No alive workers (stale_after=%ds); recovered expired jobs: "
                        "requeued=%d, interrupted=%d, cancelled=%d",
                        stale_after,
                        requeued,
                        interrupted,
                        cancelled,
                    )
        except asyncio.CancelledError:
            logger.info("Training recover loop cancelled")
            raise
        except Exception as exc:
            logger.debug("Training recover loop iteration skipped: %s", exc)


async def _initialize_finetune_services():
    if settings.training_execution_mode == "worker":
        from training_worker.repository import (
            TrainingEventRepositoryHub,
            get_training_job_repository,
        )

        from core.training_events_v2 import configure_training_event_hub_v2

        repository = get_training_job_repository()
        repository.recover_expired()
        try:
            pruned = repository.prune_events()
            if pruned.get("deleted_by_age") or pruned.get("deleted_by_cap"):
                logger.info("Training events pruned on startup: %s", pruned)
        except Exception as prune_exc:
            logger.debug("Training events prune skipped: %s", prune_exc)
        configure_training_event_hub_v2(TrainingEventRepositoryHub(repository))
        logger.info("Durable training control plane initialized (execution=worker)")

    try:
        from api.evaluation import recover_evaluation_runs_after_restart

        recovered = await recover_evaluation_runs_after_restart()
        if recovered.get("scheduled") or recovered.get("failed"):
            logger.info("Evaluation restart recovery complete: %s", recovered)
    except Exception as exc:
        logger.warning("Evaluation restart recovery failed: %s", exc)

    logger.info("Models directory: %s", settings.models_dir_resolved)
    logger.info("Datasets directory: %s", settings.datasets_dir_resolved)
    logger.info("Outputs directory: %s", settings.outputs_dir_resolved)
    settings.models_dir_resolved.mkdir(parents=True, exist_ok=True)
    settings.datasets_dir_resolved.mkdir(parents=True, exist_ok=True)
    settings.outputs_dir_resolved.mkdir(parents=True, exist_ok=True)

    if settings.training_execution_mode == "in_process":
        from core.training_context import init_training_context

        init_training_context(
            settings=settings,
            max_concurrent_training=settings.max_concurrent_training,
            max_queue_size=10,
        )
        logger.info(
            "TrainingContext initialized, max_concurrent=%s",
            settings.max_concurrent_training,
        )

    grpc_server = None
    if settings.inference_execution_mode == "in_process" and settings.enable_inference_grpc:
        try:
            from api.inference.grpc_server import get_inference_grpc_server

            grpc_server = get_inference_grpc_server(
                settings.inference_grpc_host,
                settings.inference_grpc_port,
            )
            await grpc_server.start()
        except Exception as exc:
            logger.warning("Inference gRPC startup failed: %s", exc)

    # P1-7: 启动 API 侧 recover loop — 仅在 worker 模式下需要
    global _TRAINING_RECOVER_TASK
    if _TRAINING_RECOVER_TASK is None and settings.training_execution_mode == "worker":
        _TRAINING_RECOVER_TASK = asyncio.create_task(_training_recover_loop())
        logger.info("Training recover loop started (interval=60s, stale_after=%ds)",
                    max(60, int(settings.training_worker_lease_seconds) * 2))

    return grpc_server


async def _auto_backup_loop() -> None:
    interval = int(os.environ.get("BACKUP_INTERVAL_HOURS", "6")) * 3600
    retention = int(os.environ.get("BACKUP_RETENTION_DAYS", "7"))
    await asyncio.sleep(300)
    while True:
        try:
            from core.storage import backup_all, cleanup_old_backups

            backup_all()
            cleanup_old_backups(keep_days=retention)
            logger.info("Automatic backup complete")
        except Exception as exc:
            logger.warning("Automatic backup failed: %s", exc)
        await asyncio.sleep(interval)


async def _shutdown_finetune_services(grpc_server) -> None:
    # P1-7: 取消 API 侧 recover loop,避免 "Task was destroyed but it is pending" 警告
    global _TRAINING_RECOVER_TASK
    if _TRAINING_RECOVER_TASK is not None:
        _TRAINING_RECOVER_TASK.cancel()
        try:
            await _TRAINING_RECOVER_TASK
        except asyncio.CancelledError:
            pass
        _TRAINING_RECOVER_TASK = None
        logger.info("Training recover loop stopped")

    if grpc_server:
        try:
            await grpc_server.stop()
            logger.info("Inference gRPC shutdown complete")
        except Exception as exc:
            logger.warning("Inference gRPC shutdown failed: %s", exc)

    if settings.inference_execution_mode == "in_process":
        try:
            from api.inference.pipeline import get_local_inference_pipeline
            from api.inference.routes import get_scheduler

            await get_local_inference_pipeline().shutdown()
            await get_scheduler().shutdown()
            logger.info("Inference scheduler shutdown complete")
        except Exception as exc:
            logger.warning("Inference scheduler shutdown failed: %s", exc)

    try:
        from core.training_context import shutdown_training_context

        shutdown_training_context()
        logger.info("TrainingContext shutdown complete")
    except Exception as exc:
        logger.warning("TrainingContext shutdown failed: %s", exc)

    if settings.training_execution_mode == "worker":
        from core.training_events_v2 import reset_training_event_hub_v2

        reset_training_event_hub_v2()


async def _shutdown_agent_services() -> None:
    await _shutdown_training_reconciler()

    try:
        from api.agent_sessions import get_agent_session_service

        await get_agent_session_service().shutdown_async_subtasks()
        logger.info("Async subagent tasks shutdown complete")
    except Exception as exc:
        logger.warning("Async subagent shutdown failed: %s", exc)

    try:
        from api.chat.session import close_session_manager

        close_session_manager()
        logger.info("Chat session manager shutdown complete")
    except Exception as exc:
        logger.warning("Chat session manager shutdown failed: %s", exc)

    try:
        from context.service import close_context_service

        close_context_service()
        logger.info("Project context service shutdown complete")
    except Exception as exc:
        logger.warning("Project context service shutdown failed: %s", exc)

    try:
        from rag.embedder import close_embedder

        close_embedder()
        logger.info("RAG embedder shutdown complete")
    except Exception as exc:
        logger.warning("RAG embedder shutdown failed: %s", exc)

    try:
        from rag.vector_store import close_vector_store

        close_vector_store()
        logger.info("RAG vector store shutdown complete")
    except Exception as exc:
        logger.warning("RAG vector store shutdown failed: %s", exc)

    try:
        from memory.memory_service import close_memory_service

        close_memory_service()
        logger.info("Memory service shutdown complete")
    except Exception as exc:
        logger.warning("Memory service shutdown failed: %s", exc)


async def _initialize_training_reconciler() -> None:
    """Start the optional Agent control-plane bridge without making startup fatal."""
    global _TRAINING_RECONCILER
    if _TRAINING_RECONCILER is not None:
        return
    try:
        from api.agent_sessions import get_agent_session_service
        from agent_session.training_run_sync import LocalSQLiteTrainingEventSource, TrainingRunReconciler
        from training_worker.repository import get_training_job_repository

        service = get_agent_session_service()

        def publish(session_id: str, part: dict[str, Any]) -> None:
            payload = part.get("payload") if isinstance(part.get("payload"), dict) else {}
            activity = payload.get("training_activity") if isinstance(payload.get("training_activity"), dict) else {}
            service._event(
                session_id,
                "training_progress",
                str(activity.get("summary") or "Training progress updated."),
                {
                    "part_id": part.get("id"),
                    "part_type": part.get("type"),
                    "part": part,
                    "task_id": activity.get("task_id"),
                    "training_sync": True,
                },
            )

        _TRAINING_RECONCILER = TrainingRunReconciler(
            repository=service.repository,
            event_source=LocalSQLiteTrainingEventSource(get_training_job_repository()),
            publish=publish,
        )
        _TRAINING_RECONCILER.start()
        logger.info("Agent training reconciler started")
    except Exception as exc:
        # Agent-only and combined deployments may run before a Worker database
        # is present. The persisted card remains recoverable once it is back.
        _TRAINING_RECONCILER = None
        logger.warning("Agent training reconciler unavailable; live training sync is degraded: %s", exc)


async def _shutdown_training_reconciler() -> None:
    global _TRAINING_RECONCILER
    reconciler, _TRAINING_RECONCILER = _TRAINING_RECONCILER, None
    if reconciler is None:
        return
    try:
        await reconciler.close()
        logger.info("Agent training reconciler shutdown complete")
    except Exception as exc:
        logger.warning("Agent training reconciler shutdown failed: %s", exc)


async def _shutdown_shared_services() -> None:
    try:
        from inference_provider import close_inference_service_client

        await close_inference_service_client()
        logger.info("Inference provider HTTP client closed")
    except Exception as exc:
        logger.warning("Inference provider HTTP client shutdown failed: %s", exc)

    try:
        from ai.gateway import close_http_clients

        await close_http_clients()
        logger.info("AI gateway HTTP clients closed")
    except Exception as exc:
        logger.warning("AI gateway HTTP client shutdown failed: %s", exc)

    try:
        from core.db_manager import close_all_pools

        close_all_pools()
        logger.info("SQLite connection pools closed")
    except Exception as exc:
        logger.warning("SQLite pool shutdown failed: %s", exc)


def create_lifespan(profile: ApplicationProfile) -> Callable:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("Initializing %s application...", profile.value)
        _warn_about_auth_configuration()
        _warn_about_agent_runtime_environment()
        _initialize_storage()
        _cleanup_expired_langgraph_checkpoints()
        _cleanup_tmp_residue()

        grpc_server = None
        if profile.includes_finetune:
            grpc_server = await _initialize_finetune_services()
        if profile.includes_agent:
            await _initialize_agent_services()

        # Until data ownership is split, only the backward-compatible combined
        # process owns automatic backups. This avoids duplicate backup loops if
        # both profile apps are evaluated side by side.
        backup_task = (
            asyncio.create_task(_auto_backup_loop())
            if profile is ApplicationProfile.COMBINED
            else None
        )

        try:
            yield
        finally:
            logger.info("Shutting down %s application...", profile.value)
            if backup_task is not None:
                backup_task.cancel()
                with suppress(asyncio.CancelledError):
                    await backup_task
            if profile.includes_finetune:
                await _shutdown_finetune_services(grpc_server)
            if profile.includes_agent:
                await _shutdown_agent_services()
            await _shutdown_shared_services()

    return lifespan


__all__ = ["create_lifespan", "get_agent_readiness"]

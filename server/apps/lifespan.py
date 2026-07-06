"""Composable startup and shutdown ownership for backend app profiles."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from core.config import settings

from .profiles import ApplicationProfile

logger = logging.getLogger("finetune-platform")


def _warn_about_auth_configuration() -> None:
    if not settings.enable_auth:
        logger.warning(
            "SECURITY: Authentication is DISABLED (enable_auth=false). "
            "This should NEVER be used in production. "
            "Set ENABLE_AUTH=true and JWT_SECRET_KEY for production deployments."
        )
    if not settings.jwt_secret_key and settings.enable_auth:
        logger.warning(
            "SECURITY: JWT secret key is auto-generated. "
            "Tokens will be invalidated on restart. "
            "Set JWT_SECRET_KEY environment variable for persistent authentication."
        )


def _initialize_storage() -> None:
    from core.storage import init_storage, migrate_json_state, storage_json_migrate_on_startup

    init_storage()
    if storage_json_migrate_on_startup():
        migrated = migrate_json_state()
        logger.info("SQLite storage initialized, migrated=%s", migrated)
    else:
        logger.info("SQLite storage initialized, JSON data migration skipped on startup")


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
    try:
        from api.agent_sessions import get_agent_session_service

        service = get_agent_session_service()
        recovered_sessions = service.recover_active_sessions_after_restart()
        if recovered_sessions.get("recovered") or recovered_sessions.get("failed"):
            logger.info("Agent session restart recovery complete: %s", recovered_sessions)
        recovered = await service.recover_async_subtasks()
        if recovered.get("scheduled") or recovered.get("synchronized"):
            logger.info("Async subagent recovery complete: %s", recovered)
    except Exception as exc:
        logger.warning("Agent session recovery failed: %s", exc)

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
    except Exception as exc:
        logger.warning("Context service init failed: %s", exc)

    try:
        from memory.memory_service import get_memory_service

        get_memory_service()
        logger.info("Memory service initialized")
    except Exception as exc:
        logger.warning("Memory service init failed: %s", exc)


async def _initialize_finetune_services():
    if settings.training_execution_mode == "worker":
        from training_worker.repository import (
            TrainingEventRepositoryHub,
            get_training_job_repository,
        )

        from core.training_events_v2 import configure_training_event_hub_v2

        repository = get_training_job_repository()
        repository.recover_expired()
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
    try:
        from api.agent_sessions import get_agent_session_service

        await get_agent_session_service().shutdown_async_subtasks()
        logger.info("Async subagent tasks shutdown complete")
    except Exception as exc:
        logger.warning("Async subagent shutdown failed: %s", exc)


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
        _initialize_storage()
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


__all__ = ["create_lifespan"]

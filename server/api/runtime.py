"""Runtime bootstrap API.

This module exposes a single aggregated contract for the frontend runtime
foundation. It intentionally reuses existing route-level status functions so
the bootstrap endpoint stays a thin composition layer instead of a second
implementation of subsystem probes.
"""

from __future__ import annotations

import inspect
import importlib
from datetime import datetime
from typing import Any, Awaitable, Callable

from fastapi import APIRouter

from api.inference import routes as inference_routes
from api.knowledge import routes as knowledge_routes
from core.storage import (
    backup_storage,
    check_storage,
    checkpoint_storage,
    get_storage_status,
    migrate_json_state,
    process_storage_outbox,
)
from core.db_manager import run_sync
from memory.memory_service import get_memory_service

training_routes = importlib.import_module("api.training")

router = APIRouter()


async def _resolve(value_or_awaitable: Any) -> Any:
    if inspect.isawaitable(value_or_awaitable):
        return await value_or_awaitable
    return value_or_awaitable


def _to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if isinstance(value, tuple):
        return [_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    return value


async def _collect(
    label: str,
    collector: Callable[[], Awaitable[Any] | Any],
    fallback: Any,
    warnings: list[str],
) -> Any:
    try:
        return _to_plain(await _resolve(collector()))
    except Exception as exc:  # pragma: no cover - exercised through endpoint-level tests
        warnings.append(f"{label}: {exc}")
        return fallback


def _normalise_models(raw_models: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_models, list):
        return []

    normalised: list[dict[str, Any]] = []
    for model in raw_models:
        if not isinstance(model, dict):
            continue
        model_id = model.get("id") or model.get("name") or model.get("model")
        if not model_id:
            continue
        normalised.append({
            "id": model_id,
            "name": model.get("name") or model_id,
            "size": model.get("size"),
            "source": model.get("source") or model.get("backend"),
        })
    return normalised


def _normalise_collections(raw_payload: Any) -> list[dict[str, Any]]:
    collections = raw_payload.get("collections", []) if isinstance(raw_payload, dict) else []
    normalised: list[dict[str, Any]] = []
    for collection in collections:
        if not isinstance(collection, dict):
            continue
        name = collection.get("id") or collection.get("name")
        if not name:
            continue
        normalised.append({
            "id": name,
            "name": collection.get("name") or name,
            "count": collection.get("count") or collection.get("document_count") or 0,
        })
    return normalised


def _derive_runtime_status(observed: dict[str, Any], warnings: list[str]) -> str:
    if warnings:
        return "degraded"

    embedder = observed["knowledge"].get("embedder_status") or {}
    if embedder.get("loaded") is False:
        return "degraded"

    return "ready"


def _derive_storage_status(storage: Any) -> str:
    if not isinstance(storage, dict):
        return "unknown"
    if storage.get("schema_health") == "failed":
        return "failed"
    outbox = storage.get("outbox") if isinstance(storage.get("outbox"), dict) else {}
    if int(outbox.get("failed", 0) or 0) > 0:
        return "degraded"
    return "ready"


@router.get("/bootstrap")
async def get_runtime_bootstrap():
    """Return an aggregated runtime bootstrap payload for the frontend shell."""
    warnings: list[str] = []

    backends_payload = await _collect(
        "inference.backends",
        inference_routes.list_backends,
        {"current": "huggingface", "backends": []},
        warnings,
    )
    hf_models_payload = await _collect(
        "inference.huggingface_models",
        lambda: inference_routes.list_models("huggingface"),
        [],
        warnings,
    )
    ollama_payload = await _collect(
        "inference.ollama",
        inference_routes.get_ollama_status,
        {"running": False, "models": []},
        warnings,
    )
    collections_payload = await _collect(
        "knowledge.collections",
        knowledge_routes.list_collections,
        {"collections": []},
        warnings,
    )
    embedder_payload = await _collect(
        "knowledge.embedder",
        knowledge_routes.get_embedder_status,
        {"loaded": False, "error": "unavailable"},
        warnings,
    )
    training_payload = await _collect(
        "training.status",
        training_routes.get_status,
        {"is_training": False, "progress": None},
        warnings,
    )

    backends = backends_payload.get("backends", []) if isinstance(backends_payload, dict) else []
    current_backend = backends_payload.get("current", "huggingface") if isinstance(backends_payload, dict) else "huggingface"
    ollama_models = _normalise_models(ollama_payload.get("models", []) if isinstance(ollama_payload, dict) else [])

    observed = {
        "backend_status": "connected",
        "inference": {
            "backends": backends,
            "current_backend": current_backend,
            "huggingface_models": _normalise_models(hf_models_payload),
            "ollama": {
                "available": bool(ollama_payload.get("running")) if isinstance(ollama_payload, dict) else False,
                "running": bool(ollama_payload.get("running")) if isinstance(ollama_payload, dict) else False,
                "base_url": ollama_payload.get("base_url") if isinstance(ollama_payload, dict) else None,
                "models": ollama_models,
            },
        },
        "knowledge": {
            "collections": _normalise_collections(collections_payload),
            "embedder_status": embedder_payload,
        },
        "training": training_payload,
        "storage": get_storage_status(),
    }

    runtime_status = _derive_runtime_status(observed, warnings)

    return {
        "schema_version": "runtime.bootstrap.v1",
        "generated_at": datetime.now().isoformat(),
        "observed": observed,
        "derived": {
            "runtime_status": runtime_status,
            "warnings": warnings,
            "available_model_count": len(observed["inference"]["huggingface_models"])
            if current_backend != "ollama"
            else len(ollama_models),
            "storage_status": _derive_storage_status(observed["storage"]),
        },
    }


@router.get("/storage/status")
async def get_runtime_storage_status():
    """Return storage convergence status for SQLite/JSON/vector transition."""
    return {
        "schema_version": "runtime.storage.status.v1",
        "generated_at": datetime.now().isoformat(),
        "storage": await run_sync(get_storage_status),
    }


@router.post("/storage/reconcile")
async def reconcile_runtime_storage(limit: int = 100):
    """Trigger one memory vector reconciliation pass."""
    result = await run_sync(get_memory_service().reconcile_vectors, limit=limit)
    return {
        "schema_version": "runtime.storage.reconcile.v1",
        "generated_at": datetime.now().isoformat(),
        "result": result,
    }


@router.post("/storage/outbox/process")
async def process_runtime_storage_outbox(limit: int = 100):
    """Process pending JSON shadow-write and vector outbox tasks once."""
    result = await run_sync(process_storage_outbox, limit=limit)
    return {
        "schema_version": "runtime.storage.outbox.process.v1",
        "generated_at": datetime.now().isoformat(),
        "result": result,
    }


@router.post("/storage/checkpoint")
async def checkpoint_runtime_storage():
    """Run a WAL checkpoint for the SQLite application database."""
    return {
        "schema_version": "runtime.storage.checkpoint.v1",
        "generated_at": datetime.now().isoformat(),
        "result": await run_sync(checkpoint_storage),
    }


@router.post("/storage/migrate-json")
async def migrate_runtime_storage_json():
    """Import legacy JSON sessions and shares into SQLite once."""
    return {
        "schema_version": "runtime.storage.migrate_json.v1",
        "generated_at": datetime.now().isoformat(),
        "result": await run_sync(migrate_json_state),
    }


@router.post("/storage/check")
async def check_runtime_storage():
    """Run SQLite integrity and foreign key checks."""
    return {
        "schema_version": "runtime.storage.check.v1",
        "generated_at": datetime.now().isoformat(),
        "result": await run_sync(check_storage),
    }


@router.post("/storage/backup")
async def backup_runtime_storage():
    """Checkpoint and copy the SQLite application database to data/backups."""
    return {
        "schema_version": "runtime.storage.backup.v1",
        "generated_at": datetime.now().isoformat(),
        "result": await run_sync(backup_storage),
    }

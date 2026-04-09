"""Skills API."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from skills.models import SkillCategory
from skills.registry import SkillRegistry

router = APIRouter(prefix="/skills", tags=["skills"])

SKILL_MEMORY_STATE_FILE = Path("data/skills/memory_state.json")


class SkillExecuteRequest(BaseModel):
    skill_name: str
    parameters: dict[str, Any] = {}
    execution_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    priority: str = "normal"


class SkillResponse(BaseModel):
    name: str
    display_name: str
    description: str
    category: str
    version: str
    tags: list[str]
    parameters: list[dict[str, Any]]
    enabled: bool = True


class ExecutionResponse(BaseModel):
    execution_id: str
    skill_name: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float | None = None


class StatsResponse(BaseModel):
    total_skills: int
    total_executions: int
    categories: dict[str, int]
    tags: dict[str, int]


def get_registry() -> SkillRegistry:
    return SkillRegistry.get_instance()


def category_to_str(cat: Any) -> str:
    if isinstance(cat, str):
        return cat
    if hasattr(cat, "value"):
        return cat.value
    return str(cat)


def param_type_to_str(param_type: Any) -> str:
    if isinstance(param_type, str):
        return param_type
    if hasattr(param_type, "value"):
        return param_type.value
    return str(param_type)


def _default_skill_memory_state() -> dict[str, Any]:
    return {
        "configs": {},
        "preferences": {},
        "history": [],
    }


def _load_skill_memory_state() -> dict[str, Any]:
    if not SKILL_MEMORY_STATE_FILE.exists():
        return _default_skill_memory_state()

    try:
        with open(SKILL_MEMORY_STATE_FILE, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _default_skill_memory_state()

    state = _default_skill_memory_state()
    state["configs"] = payload.get("configs", {}) or {}
    state["preferences"] = payload.get("preferences", {}) or {}
    state["history"] = payload.get("history", []) or []
    return state


def _persist_skill_memory_state() -> None:
    SKILL_MEMORY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SKILL_MEMORY_STATE_FILE, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "configs": _memory_configs,
                "preferences": _user_preferences,
                "history": _operation_history[-200:],
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )


def _build_default_memory_config(skill_name: str) -> dict[str, Any]:
    return {
        "skill_name": skill_name,
        "memory_enabled": True,
        "context_injection": True,
        "result_storage": True,
        "preference_learning": True,
        "max_memories": 50,
        "relevance_threshold": 0.7,
    }


def _append_operation_history(entry: dict[str, Any]) -> None:
    _operation_history.append(entry)
    if len(_operation_history) > 200:
        del _operation_history[:-200]
    _persist_skill_memory_state()


_skill_memory_state = _load_skill_memory_state()
_memory_configs: dict[str, dict[str, Any]] = _skill_memory_state["configs"]
_user_preferences: dict[str, dict[str, Any]] = _skill_memory_state["preferences"]
_operation_history: list[dict[str, Any]] = _skill_memory_state["history"]


@router.get("", response_model=dict[str, Any])
async def list_skills(
    category: str | None = Query(None, description="Filter by category"),
    tag: str | None = Query(None, description="Filter by tag"),
):
    registry = get_registry()

    if category:
        try:
            category_enum = SkillCategory(category.lower())
            names = registry.list_skills_by_category(category_enum)
        except ValueError:
            names = []
    elif tag:
        names = registry.list_skills_by_tag(tag)
    else:
        names = registry.list_skills()

    skills = []
    for name in names:
        metadata = registry.get_metadata(name)
        if not metadata:
            continue

        params = []
        for parameter in metadata.parameters:
            params.append(
                {
                    "name": parameter.name,
                    "type": param_type_to_str(parameter.type),
                    "description": parameter.description,
                    "required": parameter.required,
                    "default": parameter.default,
                }
            )

        skills.append(
            SkillResponse(
                name=metadata.name,
                display_name=metadata.display_name,
                description=metadata.description,
                category=category_to_str(metadata.category),
                version=metadata.version,
                tags=list(metadata.tags),
                parameters=params,
                enabled=metadata.enabled,
            ).model_dump()
        )

    return {"skills": skills}


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    registry = get_registry()
    stats = registry.get_stats()

    return StatsResponse(
        total_skills=stats.get("total_skills", 0),
        total_executions=stats.get("total_executions", 0),
        categories=stats.get("categories", {}),
        tags=stats.get("tags", {}),
    )


@router.get("/categories", response_model=list[str])
async def list_categories():
    return [category.value for category in SkillCategory]


@router.get("/{skill_name}", response_model=SkillResponse)
async def get_skill(skill_name: str):
    registry = get_registry()
    metadata = registry.get_metadata(skill_name)

    if not metadata:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")

    params = []
    for parameter in metadata.parameters:
        params.append(
            {
                "name": parameter.name,
                "type": param_type_to_str(parameter.type),
                "description": parameter.description,
                "required": parameter.required,
                "default": parameter.default,
            }
        )

    return SkillResponse(
        name=metadata.name,
        display_name=metadata.display_name,
        description=metadata.description,
        category=category_to_str(metadata.category),
        version=metadata.version,
        tags=list(metadata.tags),
        parameters=params,
        enabled=metadata.enabled,
    )


@router.post("/execute", response_model=ExecutionResponse)
async def execute_skill(request: SkillExecuteRequest):
    registry = get_registry()

    if not registry.has_skill(request.skill_name):
        raise HTTPException(status_code=404, detail=f"Skill not found: {request.skill_name}")

    try:
        execution = await registry.execute(
            name=request.skill_name,
            parameters=request.parameters,
            execution_id=request.execution_id,
            user_id=request.user_id,
            session_id=request.session_id,
        )

        result_data = None
        error_msg = None
        if execution.result:
            if execution.result.success:
                result_data = execution.result.data
            else:
                error_msg = execution.result.error

        _append_operation_history(
            {
                "skill_name": execution.skill_name,
                "timestamp": (
                    execution.completed_at or execution.started_at or datetime.now()
                ).isoformat(),
                "success": bool(execution.result and execution.result.success),
                "duration": float((execution.duration_ms or 0) / 1000),
                "params": execution.parameters,
                "status": execution.status.value if hasattr(execution.status, "value") else str(execution.status),
            }
        )

        return ExecutionResponse(
            execution_id=execution.execution_id,
            skill_name=execution.skill_name,
            status=execution.status.value if hasattr(execution.status, "value") else str(execution.status),
            result=result_data,
            error=error_msg,
            started_at=execution.started_at.isoformat() if execution.started_at else None,
            completed_at=execution.completed_at.isoformat() if execution.completed_at else None,
            duration_ms=execution.duration_ms,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Execution failed: {exc}") from exc


@router.get("/execution/{execution_id}", response_model=ExecutionResponse)
async def get_execution(execution_id: str):
    registry = get_registry()
    execution = registry.get_execution(execution_id)

    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution not found: {execution_id}")

    result_data = None
    error_msg = None
    if execution.result:
        if execution.result.success:
            result_data = execution.result.data
        else:
            error_msg = execution.result.error

    return ExecutionResponse(
        execution_id=execution.execution_id,
        skill_name=execution.skill_name,
        status=execution.status.value if hasattr(execution.status, "value") else str(execution.status),
        result=result_data,
        error=error_msg,
        started_at=execution.started_at.isoformat() if execution.started_at else None,
        completed_at=execution.completed_at.isoformat() if execution.completed_at else None,
        duration_ms=execution.duration_ms,
    )


@router.post("/scan")
async def scan_skills():
    registry = get_registry()

    try:
        from skills.scanner import SkillScanner

        scanner = SkillScanner()
        discovered = scanner.scan()
        registered = []

        for skill_class in discovered:
            if registry.register(skill_class):
                registered.append(skill_class.get_metadata().name)

        return {"success": True, "discovered": len(discovered), "registered": registered}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.get("/memory/configs")
async def get_memory_configs():
    registry = get_registry()
    skill_names = set(registry.list_skills()) | set(_memory_configs.keys())
    configs = []

    for skill_name in sorted(skill_names):
        config = _build_default_memory_config(skill_name)
        config.update(_memory_configs.get(skill_name, {}))
        config["skill_name"] = skill_name
        _memory_configs.setdefault(skill_name, config)
        configs.append(config)

    if skill_names:
        _persist_skill_memory_state()

    return {"configs": configs}


@router.post("/memory/configs")
async def update_memory_config(request: dict[str, Any]):
    skill_name = request.get("skill_name")
    if not skill_name:
        raise HTTPException(status_code=400, detail="skill_name is required")

    config = _build_default_memory_config(skill_name)
    config.update(request)
    config["skill_name"] = skill_name
    _memory_configs[skill_name] = config
    _persist_skill_memory_state()
    return {"success": True, "config": config}


@router.put("/memory/configs/{skill_name}")
async def replace_memory_config(skill_name: str, request: dict[str, Any]):
    config = _build_default_memory_config(skill_name)
    config.update(_memory_configs.get(skill_name, {}))
    config.update(request)
    config["skill_name"] = skill_name
    _memory_configs[skill_name] = config
    _persist_skill_memory_state()
    return {"success": True, "config": config}


@router.get("/memory/preferences")
async def get_memory_preferences():
    return {"preferences": list(_user_preferences.values())}


@router.delete("/memory/preferences/{key}")
async def delete_memory_preference(key: str):
    if key in _user_preferences:
        del _user_preferences[key]
        _persist_skill_memory_state()
    return {"success": True}


@router.get("/memory/history")
async def get_memory_history(limit: int = 50):
    history = list(reversed(_operation_history[-limit:]))
    return {"history": history, "total": len(_operation_history)}


@router.delete("/memory/history")
async def delete_memory_history():
    _operation_history.clear()
    _persist_skill_memory_state()
    return {"success": True}


@router.post("/memory/history/clear")
async def clear_memory_history():
    _operation_history.clear()
    _persist_skill_memory_state()
    return {"success": True}

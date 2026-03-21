# -*- coding: utf-8 -*-
"""
技能管理 API
"""
import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from skills.registry import SkillRegistry
from skills.models import SkillCategory, SkillStatus

router = APIRouter(prefix="/skills", tags=["skills"])


class SkillExecuteRequest(BaseModel):
    skill_name: str
    parameters: Dict[str, Any] = {}
    execution_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    priority: str = "normal"


class SkillResponse(BaseModel):
    name: str
    display_name: str
    description: str
    category: str
    version: str
    tags: List[str]
    parameters: List[Dict[str, Any]]
    enabled: bool = True


class ExecutionResponse(BaseModel):
    execution_id: str
    skill_name: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None


class StatsResponse(BaseModel):
    total_skills: int
    total_executions: int
    categories: Dict[str, int]
    tags: Dict[str, int]


def get_registry() -> SkillRegistry:
    return SkillRegistry.get_instance()


def category_to_str(cat) -> str:
    if isinstance(cat, str):
        return cat
    if hasattr(cat, 'value'):
        return cat.value
    return str(cat)


def param_type_to_str(pt) -> str:
    if isinstance(pt, str):
        return pt
    if hasattr(pt, 'value'):
        return pt.value
    return str(pt)


@router.get("", response_model=Dict[str, Any])
async def list_skills(
    category: Optional[str] = Query(None, description="Filter by category"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
):
    registry = get_registry()

    if category:
        try:
            cat_enum = SkillCategory(category.lower())
            names = registry.list_skills_by_category(cat_enum)
        except ValueError:
            names = []
    elif tag:
        names = registry.list_skills_by_tag(tag)
    else:
        names = registry.list_skills()

    skills = []
    for name in names:
        metadata = registry.get_metadata(name)
        if metadata:
            params = []
            for p in metadata.parameters:
                params.append({
                    "name": p.name,
                    "type": param_type_to_str(p.type),
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                })

            skills.append(SkillResponse(
                name=metadata.name,
                display_name=metadata.display_name,
                description=metadata.description,
                category=category_to_str(metadata.category),
                version=metadata.version,
                tags=list(metadata.tags),
                parameters=params,
                enabled=metadata.enabled,
            ).model_dump())

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


@router.get("/categories", response_model=List[str])
async def list_categories():
    return [c.value for c in SkillCategory]


@router.get("/{skill_name}", response_model=SkillResponse)
async def get_skill(skill_name: str):
    registry = get_registry()
    metadata = registry.get_metadata(skill_name)

    if not metadata:
        raise HTTPException(status_code=404, detail=f"技能不存在: {skill_name}")

    params = []
    for p in metadata.parameters:
        params.append({
            "name": p.name,
            "type": param_type_to_str(p.type),
            "description": p.description,
            "required": p.required,
            "default": p.default,
        })

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
        raise HTTPException(status_code=404, detail=f"技能不存在: {request.skill_name}")

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

        return ExecutionResponse(
            execution_id=execution.execution_id,
            skill_name=execution.skill_name,
            status=execution.status.value if hasattr(execution.status, 'value') else str(execution.status),
            result=result_data,
            error=error_msg,
            started_at=execution.started_at.isoformat() if execution.started_at else None,
            completed_at=execution.completed_at.isoformat() if execution.completed_at else None,
            duration_ms=execution.duration_ms,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"执行失败: {str(e)}")


@router.get("/execution/{execution_id}", response_model=ExecutionResponse)
async def get_execution(execution_id: str):
    registry = get_registry()
    execution = registry.get_execution(execution_id)

    if not execution:
        raise HTTPException(status_code=404, detail=f"执行记录不存在: {execution_id}")

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
        status=execution.status.value if hasattr(execution.status, 'value') else str(execution.status),
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

        return {
            "success": True,
            "discovered": len(discovered),
            "registered": registered,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


_memory_configs: Dict[str, Dict[str, Any]] = {}
_user_preferences: Dict[str, Dict[str, Any]] = {}
_operation_history: List[Dict[str, Any]] = []


@router.get("/memory/configs")
async def get_memory_configs():
    """获取技能记忆配置"""
    configs = []
    for skill_name in ["ScreenshotSkill", "CodeAnalysisSkill", "FileOperationSkill"]:
        config = _memory_configs.get(skill_name, {
            "skill_name": skill_name,
            "memory_enabled": True,
            "context_injection": True,
            "result_storage": True,
            "preference_learning": True,
            "max_memories": 50,
            "relevance_threshold": 0.7,
        })
        configs.append(config)
    return {"configs": configs}


@router.post("/memory/configs")
async def update_memory_config(request: Dict[str, Any]):
    """更新技能记忆配置"""
    skill_name = request.get("skill_name")
    if not skill_name:
        raise HTTPException(status_code=400, detail="skill_name is required")
    _memory_configs[skill_name] = request
    return {"success": True, "config": request}


@router.get("/memory/preferences")
async def get_memory_preference():
    """获取用户偏好"""
    return {"preferences": list(_user_preferences.values()) if _user_preferences else [
        {"key": "preferred_language", "value": "python", "confidence": 0.9, "source": "learned"},
        {"key": "code_style", "value": "pep8", "confidence": 0.85, "source": "learned"},
    ]}


@router.delete("/memory/preferences/{key}")
async def delete_memory_preference(key: str):
    """删除用户偏好"""
    if key in _user_preferences:
        del _user_preferences[key]
    return {"success": True}


@router.get("/memory/history")
async def get_memory_history(limit: int = 50):
    """获取操作历史"""
    history = _operation_history[-limit:] if _operation_history else [
        {"id": "1", "skill": "ScreenshotSkill", "action": "capture", "timestamp": "2024-01-15T10:00:00Z", "success": True},
        {"id": "2", "skill": "CodeAnalysisSkill", "action": "analyze", "timestamp": "2024-01-15T10:05:00Z", "success": True},
    ]
    return {"history": history, "total": len(history)}


@router.post("/memory/history/clear")
async def clear_memory_history():
    """清除操作历史"""
    _operation_history.clear()
    return {"success": True}

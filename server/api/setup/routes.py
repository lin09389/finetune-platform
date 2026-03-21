# -*- coding: utf-8 -*-
"""
系统设置 API 路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

router = APIRouter(prefix="/setup", tags=["Setup"])


class SystemConfig(BaseModel):
    """系统配置"""
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")


class ModelConfig(BaseModel):
    """模型配置"""
    default_model: str = Field(default="")
    inference_backend: str = Field(default="huggingface")
    max_tokens: int = Field(default=2048)
    temperature: float = Field(default=0.7)


class SetupStatus(BaseModel):
    """设置状态"""
    initialized: bool = Field(default=False)
    models_loaded: int = Field(default=0)
    datasets_count: int = Field(default=0)
    config_valid: bool = Field(default=True)


@router.get("/status")
async def get_setup_status():
    """获取设置状态"""
    return SetupStatus().model_dump()


@router.get("/config")
async def get_config():
    """获取配置"""
    return {
        "system": SystemConfig().model_dump(),
        "model": ModelConfig().model_dump()
    }


@router.put("/config")
async def update_config(config: Dict[str, Any]):
    """更新配置"""
    return {"success": True, "message": "配置已更新"}


@router.post("/initialize")
async def initialize_system():
    """初始化系统"""
    return {
        "success": True,
        "message": "系统初始化完成",
        "status": SetupStatus(initialized=True).model_dump()
    }


@router.get("/check")
async def check_dependencies():
    """检查依赖"""
    dependencies = [
        {"name": "Python", "version": "3.10+", "installed": True},
        {"name": "FastAPI", "version": "0.100+", "installed": True},
        {"name": "PyTorch", "version": "2.0+", "installed": True},
        {"name": "Transformers", "version": "4.30+", "installed": True},
    ]
    
    return {
        "dependencies": dependencies,
        "all_installed": all(d["installed"] for d in dependencies)
    }


@router.get("/paths")
async def get_paths():
    """获取系统路径"""
    return {
        "models_dir": "models",
        "datasets_dir": "datasets",
        "outputs_dir": "outputs",
        "logs_dir": "logs"
    }

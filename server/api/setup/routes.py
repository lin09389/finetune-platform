"""
配置向导 API 路由

功能�?- 系统环境检�?- 自动配置建议
- 一键配�?- 配置向导流程
"""
import logging
import uuid
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...core.user_experience import (
    EnvironmentDetector,
    ConfigAdvisor,
    QuickSetup,
    ConfigWizard,
    ConfigSuggestion,
    SystemInfo,
    get_quick_setup,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/setup", tags=["Setup"])


class AutoConfigRequest(BaseModel):
    """自动配置请求"""
    preferences: Dict[str, Any] = Field(default_factory=dict)


class ApplySuggestionRequest(BaseModel):
    """应用建议请求"""
    category: str
    name: str
    value: Any


class WizardStepRequest(BaseModel):
    """向导步骤请求"""
    action: str
    key: Optional[str] = None
    value: Optional[Any] = None


_wizards: Dict[str, ConfigWizard] = {}


@router.get("/system-info")
async def get_system_info():
    """获取系统信息"""
    info = EnvironmentDetector.detect_system()
    return info.to_dict()


@router.get("/libraries")
async def get_installed_libraries():
    """获取已安装的�?""
    return EnvironmentDetector.get_installed_libraries()


@router.get("/suggestions")
async def get_config_suggestions(current_config: Dict[str, Any] = None):
    """获取配置建议"""
    system_info = EnvironmentDetector.detect_system()
    advisor = ConfigAdvisor(system_info)
    suggestions = advisor.generate_suggestions(current_config or {})
    return {
        "suggestions": [s.to_dict() for s in suggestions],
        "total": len(suggestions),
    }


@router.post("/auto-configure")
async def auto_configure(request: AutoConfigRequest = None):
    """自动配置"""
    setup = get_quick_setup()
    config = setup.auto_configure()
    
    if request and request.preferences:
        config.update(request.preferences)
    
    return {
        "success": True,
        "config": config,
    }


@router.get("/report")
async def get_setup_report():
    """获取设置报告"""
    setup = get_quick_setup()
    return setup.get_setup_report()


@router.post("/wizard/start")
async def start_wizard():
    """开始配置向�?""
    wizard_id = str(uuid.uuid4())
    wizard = ConfigWizard()
    wizard.current_step_name = wizard.steps[0]
    _wizards[wizard_id] = wizard
    
    return {
        "wizard_id": wizard_id,
        **wizard.to_dict(),
    }


@router.post("/wizard/{wizard_id}/step")
async def wizard_step(wizard_id: str, request: WizardStepRequest):
    """向导步骤操作"""
    wizard = _wizards.get(wizard_id)
    
    if not wizard:
        raise HTTPException(status_code=404, detail="Wizard not found")
    
    if request.action == "next":
        step_name = wizard.next_step()
    elif request.action == "previous":
        step_name = wizard.previous_step()
    elif request.action == "set":
        if request.key and request.value is not None:
            wizard.set_config(request.key, request.value)
        step_name = wizard.current_step_name
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
    
    return {
        "wizard_id": wizard_id,
        **wizard.to_dict(),
    }


@router.get("/wizard/{wizard_id}")
async def get_wizard(wizard_id: str):
    """获取向导状�?""
    wizard = _wizards.get(wizard_id)
    
    if not wizard:
        raise HTTPException(status_code=404, detail="Wizard not found")
    
    return {
        "wizard_id": wizard_id,
        **wizard.to_dict(),
    }


@router.delete("/wizard/{wizard_id}")
async def delete_wizard(wizard_id: str):
    """删除向导"""
    if wizard_id in _wizards:
        del _wizards[wizard_id]
        return {"success": True}
    raise HTTPException(status_code=404, detail="Wizard not found")


@router.post("/apply-suggestion")
async def apply_suggestion(request: ApplySuggestionRequest):
    """应用配置建议"""
    return {
        "success": True,
        "applied": {
            "category": request.category,
            "name": request.name,
            "value": request.value,
        },
    }


@router.get("/quick-start")
async def quick_start():
    """快速开�?- 返回所有初始化信息"""
    setup = get_quick_setup()
    system_info = setup.system_info
    libraries = EnvironmentDetector.get_installed_libraries()
    config = setup.auto_configure()
    
    return {
        "system_info": system_info.to_dict(),
        "libraries": libraries,
        "recommended_config": config,
        "ready": system_info.gpu_available or system_info.total_memory_gb >= 8,
        "messages": _generate_startup_messages(system_info, libraries),
    }


def _generate_startup_messages(system_info: SystemInfo, libraries: Dict[str, bool]) -> List[Dict[str, str]]:
    """生成启动消息"""
    messages = []
    
    if system_info.gpu_available:
        messages.append({
            "type": "success",
            "message": f"检测到 GPU: {', '.join(system_info.gpu_names)}",
        })
    else:
        messages.append({
            "type": "warning",
            "message": "未检测到 GPU，将使用 CPU 模式（性能较低�?,
        })
    
    if not libraries.get("torch", False):
        messages.append({
            "type": "error",
            "message": "PyTorch 未安装，请运�? pip install torch",
        })
    
    if not libraries.get("transformers", False):
        messages.append({
            "type": "error",
            "message": "Transformers 未安装，请运�? pip install transformers",
        })
    
    if system_info.gpu_available and not libraries.get("vllm", False):
        messages.append({
            "type": "info",
            "message": "建议安装 vLLM 以获得更好的推理性能: pip install vllm",
        })
    
    if system_info.available_memory_gb < 4:
        messages.append({
            "type": "warning",
            "message": f"可用内存较低 ({system_info.available_memory_gb:.1f}GB)，建议关闭其他应�?,
        })
    
    return messages

"""
系统信息技能 - 获取系统信息
"""
import platform
from typing import Dict, Any

from skills.base import SkillBase
from skills.models import SkillMetadata, SkillParameter, SkillResult, SkillCategory

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class SystemInfoSkill(SkillBase):
    """系统信息技能"""
    
    metadata = SkillMetadata(
        name="system_info",
        display_name="系统信息",
        description="获取系统信息",
        version="1.0.0",
        category=SkillCategory.UTILITY,
        parameters=[],
        tags=["system", "info", "utility"],
    )
    
    async def execute(self, **kwargs) -> SkillResult:
        try:
            info = {
                "platform": {
                    "system": platform.system(),
                    "release": platform.release(),
                    "version": platform.version(),
                    "machine": platform.machine(),
                    "processor": platform.processor(),
                },
            }
            
            if HAS_PSUTIL:
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                
                info["cpu"] = {
                    "count": psutil.cpu_count(),
                    "percent": cpu_percent,
                }
                info["memory"] = {
                    "total": memory.total,
                    "available": memory.available,
                    "used": memory.used,
                    "percent": memory.percent,
                }
                info["disk"] = {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": disk.percent,
                }
            
            return SkillResult(
                success=True,
                data=info,
                message="系统信息获取成功",
            )
            
        except Exception as e:
            return SkillResult(
                success=False,
                error=str(e),
                error_code="SYSTEM_INFO_ERROR",
            )


def get_skill():
    return SystemInfoSkill()

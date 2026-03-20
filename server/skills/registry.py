"""
技能注册表
"""
import asyncio
import importlib
import inspect
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

from .base import SkillBase
from .models import (
    SkillCategory,
    SkillExecution,
    SkillMetadata,
    SkillPriority,
    SkillResult,
    SkillStatus,
)


class SkillRegistry:
    """技能注册表"""
    
    _instance: Optional["SkillRegistry"] = None
    _skills: Dict[str, Type[SkillBase]]
    _instances: Dict[str, SkillBase]
    _executions: Dict[str, SkillExecution]
    _execution_tasks: Dict[str, asyncio.Task]
    _on_skill_registered: Optional[Callable[[str], None]]
    _on_skill_unregistered: Optional[Callable[[str], None]]
    
    def __new__(cls) -> "SkillRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._skills = {}
            cls._instance._instances = {}
            cls._instance._executions = {}
            cls._instance._execution_tasks = {}
            cls._instance._on_skill_registered = None
            cls._instance._on_skill_unregistered = None
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "SkillRegistry":
        """获取单例实例"""
        return cls()
    
    def register(self, skill_class: Type[SkillBase]) -> bool:
        """注册技�?""
        try:
            metadata = skill_class.get_metadata()
            name = metadata.name
            
            if name in self._skills:
                return False
            
            self._skills[name] = skill_class
            self._instances[name] = skill_class()
            
            if self._on_skill_registered:
                self._on_skill_registered(name)
            
            return True
        
        except Exception as e:
            print(f"注册技能失�? {e}")
            return False
    
    def unregister(self, name: str) -> bool:
        """注销技�?""
        if name not in self._skills:
            return False
        
        if name in self._execution_tasks:
            for task in self._execution_tasks[name].values():
                task.cancel()
        
        del self._skills[name]
        del self._instances[name]
        
        if self._on_skill_unregistered:
            self._on_skill_unregistered(name)
        
        return True
    
    def get_skill(self, name: str) -> Optional[SkillBase]:
        """获取技能实�?""
        return self._instances.get(name)
    
    def get_skill_class(self, name: str) -> Optional[Type[SkillBase]]:
        """获取技能类"""
        return self._skills.get(name)
    
    def get_metadata(self, name: str) -> Optional[SkillMetadata]:
        """获取技能元数据"""
        skill = self.get_skill(name)
        if skill:
            return skill.get_metadata()
        return None
    
    def list_skills(self) -> List[str]:
        """列出所有已注册技能名�?""
        return list(self._skills.keys())
    
    def list_skills_by_category(self, category: SkillCategory) -> List[str]:
        """按类别列出技�?""
        result = []
        for name, skill_class in self._skills.items():
            metadata = skill_class.get_metadata()
            if metadata.category == category:
                result.append(name)
        return result
    
    def list_skills_by_tag(self, tag: str) -> List[str]:
        """按标签列出技�?""
        result = []
        for name, skill_class in self._skills.items():
            metadata = skill_class.get_metadata()
            if tag in metadata.tags:
                result.append(name)
        return result
    
    def get_all_metadata(self) -> Dict[str, SkillMetadata]:
        """获取所有技能元数据"""
        return {
            name: skill_class.get_metadata()
            for name, skill_class in self._skills.items()
        }
    
    def has_skill(self, name: str) -> bool:
        """检查技能是否存�?""
        return name in self._skills
    
    async def execute(
        self,
        name: str,
        parameters: Dict[str, Any],
        execution_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        priority: SkillPriority = SkillPriority.NORMAL,
    ) -> SkillExecution:
        """执行技�?""
        skill = self.get_skill(name)
        if not skill:
            import uuid
            return SkillExecution(
                execution_id=execution_id or str(uuid.uuid4()),
                skill_name=name,
                parameters=parameters,
                status=SkillStatus.FAILED,
                result=SkillResult(
                    success=False,
                    error=f"技能不存在: {name}",
                    error_code="SKILL_NOT_FOUND",
                ),
            )
        
        execution = await skill.run(
            parameters=parameters,
            execution_id=execution_id,
            user_id=user_id,
            session_id=session_id,
            priority=priority,
        )
        
        self._executions[execution.execution_id] = execution
        
        return execution
    
    async def execute_async(
        self,
        name: str,
        parameters: Dict[str, Any],
        execution_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        priority: SkillPriority = SkillPriority.NORMAL,
        on_complete: Optional[Callable[[SkillExecution], None]] = None,
    ) -> str:
        """异步执行技能（返回执行ID�?""
        import uuid
        
        exec_id = execution_id or str(uuid.uuid4())
        
        async def run_task():
            execution = await self.execute(
                name=name,
                parameters=parameters,
                execution_id=exec_id,
                user_id=user_id,
                session_id=session_id,
                priority=priority,
            )
            if on_complete:
                on_complete(execution)
        
        task = asyncio.create_task(run_task())
        
        if name not in self._execution_tasks:
            self._execution_tasks[name] = {}
        self._execution_tasks[name][exec_id] = task
        
        return exec_id
    
    def get_execution(self, execution_id: str) -> Optional[SkillExecution]:
        """获取执行记录"""
        return self._executions.get(execution_id)
    
    def cancel_execution(self, execution_id: str) -> bool:
        """取消执行"""
        for name, tasks in self._execution_tasks.items():
            if execution_id in tasks:
                tasks[execution_id].cancel()
                return True
        return False
    
    def list_executions(
        self,
        skill_name: Optional[str] = None,
        status: Optional[SkillStatus] = None,
        user_id: Optional[str] = None,
    ) -> List[SkillExecution]:
        """列出执行记录"""
        result = []
        for execution in self._executions.values():
            if skill_name and execution.skill_name != skill_name:
                continue
            if status and execution.status != status:
                continue
            if user_id and execution.user_id != user_id:
                continue
            result.append(execution)
        return result
    
    def clear_executions(self, keep_count: int = 100):
        """清理执行记录"""
        if len(self._executions) <= keep_count:
            return
        
        sorted_executions = sorted(
            self._executions.items(),
            key=lambda x: x[1].created_at,
            reverse=True
        )
        
        self._executions = dict(sorted_executions[:keep_count])
    
    def set_on_skill_registered(self, callback: Callable[[str], None]):
        """设置技能注册回�?""
        self._on_skill_registered = callback
    
    def set_on_skill_unregistered(self, callback: Callable[[str], None]):
        """设置技能注销回调"""
        self._on_skill_unregistered = callback
    
    def auto_discover(self, package_path: str = "server.skills.implemented"):
        """自动发现并注册技�?""
        try:
            package = importlib.import_module(package_path)
            package_dir = Path(package.__file__).parent
            
            if not package_dir.exists():
                return
            
            for file_path in package_dir.glob("*.py"):
                if file_path.name.startswith("_"):
                    continue
                
                module_name = f"{package_path}.{file_path.stem}"
                try:
                    module = importlib.import_module(module_name)
                    
                    for name, obj in inspect.getmembers(module):
                        if (
                            inspect.isclass(obj)
                            and issubclass(obj, SkillBase)
                            and obj is not SkillBase
                        ):
                            self.register(obj)
                
                except Exception as e:
                    print(f"加载技能模�?{module_name} 失败: {e}")
        
        except Exception as e:
            print(f"自动发现技能失�? {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取注册表统计信�?""
        total_executions = len(self._executions)
        status_counts = {}
        
        for execution in self._executions.values():
            status = execution.status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "total_skills": len(self._skills),
            "total_executions": total_executions,
            "status_counts": status_counts,
            "categories": {
                cat.value: len(self.list_skills_by_category(cat))
                for cat in SkillCategory
            },
        }


def register_skill(skill_class: Type[SkillBase]) -> Type[SkillBase]:
    """装饰器：自动注册技�?""
    registry = SkillRegistry.get_instance()
    registry.register(skill_class)
    return skill_class


def get_registry() -> SkillRegistry:
    """获取技能注册表实例"""
    return SkillRegistry.get_instance()

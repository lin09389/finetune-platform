"""
技能注册表
"""
import asyncio
import importlib
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

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
    _skills: dict[str, type[SkillBase]]
    _instances: dict[str, SkillBase]
    _executions: dict[str, SkillExecution]
    _execution_tasks: dict[str, asyncio.Task]
    _on_skill_registered: Callable[[str], None] | None
    _on_skill_unregistered: Callable[[str], None] | None

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
        return cls()

    def register(self, skill_class: type[SkillBase]) -> bool:
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
            print(f"注册技能失败: {e}")
            return False

    def unregister(self, name: str) -> bool:
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

    def get_skill(self, name: str) -> SkillBase | None:
        return self._instances.get(name)

    def get_skill_class(self, name: str) -> type[SkillBase] | None:
        return self._skills.get(name)

    def get_metadata(self, name: str) -> SkillMetadata | None:
        skill = self.get_skill(name)
        if skill:
            return skill.get_metadata()
        return None

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())

    def list_skills_by_category(self, category: SkillCategory) -> list[str]:
        result = []
        for name, skill_class in self._skills.items():
            metadata = skill_class.get_metadata()
            if metadata.category == category:
                result.append(name)
        return result

    def list_skills_by_tag(self, tag: str) -> list[str]:
        result = []
        for name, skill_class in self._skills.items():
            metadata = skill_class.get_metadata()
            if tag in metadata.tags:
                result.append(name)
        return result

    def get_all_metadata(self) -> dict[str, SkillMetadata]:
        return {
            name: skill_class.get_metadata()
            for name, skill_class in self._skills.items()
        }

    def has_skill(self, name: str) -> bool:
        return name in self._skills

    async def execute(
        self,
        name: str,
        parameters: dict[str, Any],
        execution_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        priority: SkillPriority = SkillPriority.NORMAL,
    ) -> SkillExecution:
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
        parameters: dict[str, Any],
        execution_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        priority: SkillPriority = SkillPriority.NORMAL,
        on_complete: Callable[[SkillExecution], None] | None = None,
    ) -> str:
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

    def get_execution(self, execution_id: str) -> SkillExecution | None:
        return self._executions.get(execution_id)

    def cancel_execution(self, execution_id: str) -> bool:
        for name, tasks in self._execution_tasks.items():
            if execution_id in tasks:
                tasks[execution_id].cancel()
                return True
        return False

    def list_executions(
        self,
        skill_name: str | None = None,
        status: SkillStatus | None = None,
        user_id: str | None = None,
    ) -> list[SkillExecution]:
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
        if len(self._executions) <= keep_count:
            return

        sorted_executions = sorted(
            self._executions.items(),
            key=lambda x: x[1].created_at,
            reverse=True
        )

        self._executions = dict(sorted_executions[:keep_count])

    def set_on_skill_registered(self, callback: Callable[[str], None]):
        self._on_skill_registered = callback

    def set_on_skill_unregistered(self, callback: Callable[[str], None]):
        self._on_skill_unregistered = callback

    def auto_discover(self, package_path: str = "server.skills.implemented"):
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
                    print(f"加载技能模块 {module_name} 失败: {e}")

        except Exception as e:
            print(f"自动发现技能失败: {e}")

    def get_stats(self) -> dict[str, Any]:
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


def register_skill(skill_class: type[SkillBase]) -> type[SkillBase]:
    registry = SkillRegistry.get_instance()
    registry.register(skill_class)
    return skill_class


def get_registry() -> SkillRegistry:
    return SkillRegistry.get_instance()

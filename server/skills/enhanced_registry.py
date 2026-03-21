# -*- coding: utf-8 -*-
"""
增强版技能注册表

提供技能注册、依赖管理、状态监控、版本控制等功能。
支持：
- 技能注册与注销
- 依赖解析与管理
- 技能状态监控
- 版本控制
- 技能查找与过滤
"""
import asyncio
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

from .base import SkillBase
from .models import (
    SkillCategory,
    SkillExecution,
    SkillMetadata,
    SkillPriority,
    SkillResult,
    SkillStatus,
)
from .scanner import SkillLoadStatus, SkillScanResult


class SkillRegistrationStatus(str, Enum):
    """技能注册状态"""
    REGISTERED = "registered"
    UNREGISTERED = "unregistered"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class SkillRegistration:
    """技能注册信息"""
    skill_class: Type[SkillBase]
    instance: Optional[SkillBase] = None
    metadata: Optional[SkillMetadata] = None
    status: SkillRegistrationStatus = SkillRegistrationStatus.REGISTERED
    load_status: SkillLoadStatus = SkillLoadStatus.PENDING
    registered_at: datetime = field(default_factory=datetime.now)
    last_used_at: Optional[datetime] = None
    use_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    file_path: Optional[str] = None
    file_hash: Optional[str] = None
    version: str = "1.0.0"


@dataclass
class DependencyNode:
    """依赖节点"""
    skill_name: str
    dependencies: Set[str] = field(default_factory=set)
    dependents: Set[str] = field(default_factory=set)


class EnhancedSkillRegistry:
    """增强版技能注册表"""

    _instance: Optional["EnhancedSkillRegistry"] = None
    _lock: threading.RLock

    def __new__(cls) -> "EnhancedSkillRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._lock = threading.RLock()
            cls._instance._registrations: Dict[str, SkillRegistration] = {}
            cls._instance._dependency_graph: Dict[str, DependencyNode] = {}
            cls._instance._executions: Dict[str, SkillExecution] = {}
            cls._instance._execution_tasks: Dict[str, asyncio.Task] = {}
            cls._instance._status_callbacks: List[Callable[[str, SkillRegistrationStatus], None]] = []
            cls._instance._execution_callbacks: List[Callable[[SkillExecution], None]] = []
            cls._instance._category_index: Dict[SkillCategory, Set[str]] = defaultdict(set)
            cls._instance._tag_index: Dict[str, Set[str]] = defaultdict(set)
            cls._instance._author_index: Dict[str, Set[str]] = defaultdict(set)
        return cls._instance

    @classmethod
    def get_instance(cls) -> "EnhancedSkillRegistry":
        """获取单例实例"""
        return cls()

    def register(
        self,
        skill_class: Type[SkillBase],
        file_path: Optional[str] = None,
        file_hash: Optional[str] = None,
        scan_result: Optional[SkillScanResult] = None,
    ) -> bool:
        """注册技能"""
        with self._lock:
            try:
                metadata = skill_class.get_metadata()
                name = metadata.name

                if name in self._registrations:
                    existing = self._registrations[name]
                    if existing.file_hash == file_hash and file_hash is not None:
                        return True

                instance = skill_class()

                registration = SkillRegistration(
                    skill_class=skill_class,
                    instance=instance,
                    metadata=metadata,
                    status=SkillRegistrationStatus.REGISTERED,
                    load_status=SkillLoadStatus.LOADED,
                    file_path=file_path,
                    file_hash=file_hash,
                    version=metadata.version,
                )

                if scan_result:
                    registration.file_path = str(scan_result.file_path)
                    registration.file_hash = scan_result.file_hash

                self._registrations[name] = registration

                self._category_index[metadata.category].add(name)

                for tag in metadata.tags:
                    self._tag_index[tag].add(name)

                if metadata.author:
                    self._author_index[metadata.author].add(name)

                self._update_dependency_graph(name, metadata.dependencies)

                self._notify_status_change(name, SkillRegistrationStatus.REGISTERED)

                return True

            except Exception as e:
                return False

    def unregister(self, name: str, force: bool = False) -> bool:
        """注销技能"""
        with self._lock:
            if name not in self._registrations:
                return False

            node = self._dependency_graph.get(name)
            if node and node.dependents and not force:
                return False

            registration = self._registrations[name]
            metadata = registration.metadata

            if metadata:
                self._category_index[metadata.category].discard(name)

                for tag in metadata.tags:
                    self._tag_index[tag].discard(name)

                if metadata.author:
                    self._author_index[metadata.author].discard(name)

            self._remove_from_dependency_graph(name)

            for task in list(self._execution_tasks.values()):
                if task.get_name() == name:
                    task.cancel()

            del self._registrations[name]

            self._notify_status_change(name, SkillRegistrationStatus.UNREGISTERED)

            return True

    def reload(self, name: str, skill_class: Type[SkillBase]) -> bool:
        """重载技能"""
        with self._lock:
            if name not in self._registrations:
                return self.register(skill_class)

            old_registration = self._registrations[name]

            try:
                metadata = skill_class.get_metadata()
                instance = skill_class()

                new_registration = SkillRegistration(
                    skill_class=skill_class,
                    instance=instance,
                    metadata=metadata,
                    status=SkillRegistrationStatus.REGISTERED,
                    load_status=SkillLoadStatus.LOADED,
                    registered_at=old_registration.registered_at,
                    use_count=old_registration.use_count,
                    file_path=old_registration.file_path,
                    version=metadata.version,
                )

                self._registrations[name] = new_registration

                self._update_dependency_graph(name, metadata.dependencies)

                return True

            except Exception as e:
                old_registration.status = SkillRegistrationStatus.ERROR
                old_registration.last_error = str(e)
                return False

    def get_skill(self, name: str) -> Optional[SkillBase]:
        """获取技能实例"""
        with self._lock:
            registration = self._registrations.get(name)
            if registration and registration.instance:
                registration.last_used_at = datetime.now()
                registration.use_count += 1
                return registration.instance
            return None

    def get_skill_class(self, name: str) -> Optional[Type[SkillBase]]:
        """获取技能类"""
        with self._lock:
            registration = self._registrations.get(name)
            return registration.skill_class if registration else None

    def get_metadata(self, name: str) -> Optional[SkillMetadata]:
        """获取技能元数据"""
        with self._lock:
            registration = self._registrations.get(name)
            return registration.metadata if registration else None

    def get_registration(self, name: str) -> Optional[SkillRegistration]:
        """获取注册信息"""
        with self._lock:
            return self._registrations.get(name)

    def has_skill(self, name: str) -> bool:
        """检查技能是否存在"""
        return name in self._registrations

    def list_skills(self) -> List[str]:
        """列出所有技能名称"""
        with self._lock:
            return list(self._registrations.keys())

    def list_skills_by_category(self, category: SkillCategory) -> List[str]:
        """按类别列出技能"""
        with self._lock:
            return list(self._category_index.get(category, set()))

    def list_skills_by_tag(self, tag: str) -> List[str]:
        """按标签列出技能"""
        with self._lock:
            return list(self._tag_index.get(tag, set()))

    def list_skills_by_author(self, author: str) -> List[str]:
        """按作者列出技能"""
        with self._lock:
            return list(self._author_index.get(author, set()))

    def search_skills(
        self,
        query: Optional[str] = None,
        category: Optional[SkillCategory] = None,
        tags: Optional[List[str]] = None,
        author: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[str]:
        """搜索技能"""
        with self._lock:
            results = set(self._registrations.keys())

            if category:
                results &= self._category_index.get(category, set())

            if tags:
                for tag in tags:
                    results &= self._tag_index.get(tag, set())

            if author:
                results &= self._author_index.get(author, set())

            if query:
                query_lower = query.lower()
                matched = set()
                for name in results:
                    registration = self._registrations.get(name)
                    if registration and registration.metadata:
                        if (
                            query_lower in name.lower()
                            or query_lower in registration.metadata.display_name.lower()
                            or query_lower in registration.metadata.description.lower()
                        ):
                            matched.add(name)
                results = matched

            if enabled_only:
                enabled = set()
                for name in results:
                    registration = self._registrations.get(name)
                    if registration and registration.metadata and registration.metadata.enabled:
                        enabled.add(name)
                results = enabled

            return list(results)

    def get_all_metadata(self) -> Dict[str, SkillMetadata]:
        """获取所有技能元数据"""
        with self._lock:
            return {
                name: reg.metadata
                for name, reg in self._registrations.items()
                if reg.metadata
            }

    def _update_dependency_graph(self, skill_name: str, dependencies: List[str]):
        """更新依赖图"""
        if skill_name not in self._dependency_graph:
            self._dependency_graph[skill_name] = DependencyNode(skill_name)

        node = self._dependency_graph[skill_name]
        old_deps = node.dependencies.copy()
        node.dependencies = set(dependencies)

        for dep in old_deps - node.dependencies:
            if dep in self._dependency_graph:
                self._dependency_graph[dep].dependents.discard(skill_name)

        for dep in node.dependencies:
            if dep not in self._dependency_graph:
                self._dependency_graph[dep] = DependencyNode(dep)
            self._dependency_graph[dep].dependents.add(skill_name)

    def _remove_from_dependency_graph(self, skill_name: str):
        """从依赖图中移除"""
        if skill_name not in self._dependency_graph:
            return

        node = self._dependency_graph[skill_name]

        for dep in node.dependencies:
            if dep in self._dependency_graph:
                self._dependency_graph[dep].dependents.discard(skill_name)

        for dependent in node.dependents:
            if dependent in self._dependency_graph:
                self._dependency_graph[dependent].dependencies.discard(skill_name)

        del self._dependency_graph[skill_name]

    def get_dependencies(self, skill_name: str) -> Set[str]:
        """获取技能依赖"""
        node = self._dependency_graph.get(skill_name)
        return node.dependencies.copy() if node else set()

    def get_dependents(self, skill_name: str) -> Set[str]:
        """获取依赖此技能的其他技能"""
        node = self._dependency_graph.get(skill_name)
        return node.dependents.copy() if node else set()

    def check_dependencies(self, skill_name: str) -> Dict[str, Any]:
        """检查依赖状态"""
        dependencies = self.get_dependencies(skill_name)
        missing = []
        available = []

        for dep in dependencies:
            if dep in self._registrations:
                available.append(dep)
            else:
                missing.append(dep)

        return {
            "skill_name": skill_name,
            "valid": len(missing) == 0,
            "available": available,
            "missing": missing,
            "total": len(dependencies),
        }

    def get_load_order(self, skill_names: Optional[List[str]] = None) -> List[str]:
        """获取加载顺序（拓扑排序）"""
        if skill_names is None:
            skill_names = list(self._registrations.keys())

        visited = set()
        order = []
        temp_marks = set()

        def visit(name: str):
            if name in temp_marks:
                raise ValueError(f"检测到循环依赖: {name}")
            if name in visited:
                return

            temp_marks.add(name)

            node = self._dependency_graph.get(name)
            if node:
                for dep in node.dependencies:
                    if dep in skill_names:
                        visit(dep)

            temp_marks.remove(name)
            visited.add(name)
            order.append(name)

        for name in skill_names:
            if name not in visited:
                visit(name)

        return order

    def get_unload_order(self, skill_names: Optional[List[str]] = None) -> List[str]:
        """获取卸载顺序（反向拓扑排序）"""
        load_order = self.get_load_order(skill_names)
        return list(reversed(load_order))

    async def execute(
        self,
        name: str,
        parameters: Dict[str, Any],
        execution_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        priority: SkillPriority = SkillPriority.NORMAL,
    ) -> SkillExecution:
        """执行技能"""
        import uuid

        skill = self.get_skill(name)
        if not skill:
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

        registration = self._registrations.get(name)
        if registration and registration.metadata and not registration.metadata.enabled:
            return SkillExecution(
                execution_id=execution_id or str(uuid.uuid4()),
                skill_name=name,
                parameters=parameters,
                status=SkillStatus.FAILED,
                result=SkillResult(
                    success=False,
                    error=f"技能已禁用: {name}",
                    error_code="SKILL_DISABLED",
                ),
            )

        execution = await skill.run(
            parameters=parameters,
            execution_id=execution_id,
            user_id=user_id,
            session_id=session_id,
            priority=priority,
        )

        with self._lock:
            self._executions[execution.execution_id] = execution

            if registration:
                if execution.status == SkillStatus.FAILED:
                    registration.error_count += 1
                    registration.last_error = execution.result.error if execution.result else None

        self._notify_execution(execution)

        return execution

    def get_execution(self, execution_id: str) -> Optional[SkillExecution]:
        """获取执行记录"""
        return self._executions.get(execution_id)

    def list_executions(
        self,
        skill_name: Optional[str] = None,
        status: Optional[SkillStatus] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[SkillExecution]:
        """列出执行记录"""
        results = []
        for execution in self._executions.values():
            if skill_name and execution.skill_name != skill_name:
                continue
            if status and execution.status != status:
                continue
            if user_id and execution.user_id != user_id:
                continue
            results.append(execution)

        results.sort(key=lambda x: x.created_at, reverse=True)
        return results[:limit]

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

    def enable_skill(self, name: str) -> bool:
        """启用技能"""
        with self._lock:
            registration = self._registrations.get(name)
            if registration and registration.metadata:
                registration.metadata.enabled = True
                return True
            return False

    def disable_skill(self, name: str) -> bool:
        """禁用技能"""
        with self._lock:
            registration = self._registrations.get(name)
            if registration and registration.metadata:
                registration.metadata.enabled = False
                return True
            return False

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            total_skills = len(self._registrations)
            enabled_skills = sum(
                1 for reg in self._registrations.values()
                if reg.metadata and reg.metadata.enabled
            )

            status_counts = defaultdict(int)
            for execution in self._executions.values():
                status_counts[execution.status] += 1

            category_counts = {}
            for cat, skills in self._category_index.items():
                cat_value = cat.value if hasattr(cat, 'value') else str(cat)
                category_counts[cat_value] = len(skills)

            return {
                "total_skills": total_skills,
                "enabled_skills": enabled_skills,
                "disabled_skills": total_skills - enabled_skills,
                "total_executions": len(self._executions),
                "execution_status_counts": dict(status_counts),
                "category_counts": category_counts,
                "tag_count": len(self._tag_index),
                "author_count": len(self._author_index),
            }

    def get_skill_stats(self, name: str) -> Optional[Dict[str, Any]]:
        """获取单个技能统计"""
        with self._lock:
            registration = self._registrations.get(name)
            if not registration:
                return None

            executions = [
                e for e in self._executions.values()
                if e.skill_name == name
            ]

            success_count = sum(
                1 for e in executions
                if e.status == SkillStatus.COMPLETED
            )
            failed_count = sum(
                1 for e in executions
                if e.status == SkillStatus.FAILED
            )

            return {
                "name": name,
                "status": registration.status.value,
                "load_status": registration.load_status.value,
                "use_count": registration.use_count,
                "error_count": registration.error_count,
                "total_executions": len(executions),
                "success_count": success_count,
                "failed_count": failed_count,
                "success_rate": success_count / len(executions) if executions else 0,
                "registered_at": registration.registered_at.isoformat(),
                "last_used_at": registration.last_used_at.isoformat() if registration.last_used_at else None,
                "last_error": registration.last_error,
            }

    def add_status_callback(self, callback: Callable[[str, SkillRegistrationStatus], None]):
        """添加状态变更回调"""
        self._status_callbacks.append(callback)

    def add_execution_callback(self, callback: Callable[[SkillExecution], None]):
        """添加执行回调"""
        self._execution_callbacks.append(callback)

    def _notify_status_change(self, skill_name: str, status: SkillRegistrationStatus):
        """通知状态变更"""
        for callback in self._status_callbacks:
            try:
                callback(skill_name, status)
            except Exception:
                pass

    def _notify_execution(self, execution: SkillExecution):
        """通知执行完成"""
        for callback in self._execution_callbacks:
            try:
                callback(execution)
            except Exception:
                pass

    def clear(self):
        """清空注册表"""
        with self._lock:
            self._registrations.clear()
            self._dependency_graph.clear()
            self._executions.clear()
            self._execution_tasks.clear()
            self._category_index.clear()
            self._tag_index.clear()
            self._author_index.clear()


def get_enhanced_registry() -> EnhancedSkillRegistry:
    """获取增强版注册表实例"""
    return EnhancedSkillRegistry.get_instance()


def register_skill_enhanced(
    skill_class: Type[SkillBase],
    file_path: Optional[str] = None,
    file_hash: Optional[str] = None,
) -> Type[SkillBase]:
    """装饰器：自动注册技能到增强版注册表"""
    registry = get_enhanced_registry()
    registry.register(skill_class, file_path=file_path, file_hash=file_hash)
    return skill_class

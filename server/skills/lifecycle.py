"""
技能生命周期管理

提供技能的加载、卸载、重载、状态监控等功能。
支持：
- 技能热加载
- 技能卸载与清理
- 技能重载
- 文件变更监控
- 状态监控与事件通知
"""
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .base import SkillBase
from .enhanced_registry import EnhancedSkillRegistry
from .models import SkillMetadata
from .scanner import ScanStatus, SkillLoadStatus, SkillScanner, SkillScanResult


class LifecycleEventType(str, Enum):
    """生命周期事件类型"""
    BEFORE_LOAD = "before_load"
    AFTER_LOAD = "after_load"
    BEFORE_UNLOAD = "before_unload"
    AFTER_UNLOAD = "after_unload"
    BEFORE_RELOAD = "before_reload"
    AFTER_RELOAD = "after_reload"
    ON_ERROR = "on_error"
    ON_ENABLE = "on_enable"
    ON_DISABLE = "on_disable"


@dataclass
class LifecycleEvent:
    """生命周期事件"""
    event_type: LifecycleEventType
    skill_name: str
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadResult:
    """加载结果"""
    skill_name: str
    success: bool
    status: SkillLoadStatus
    error: str | None = None
    metadata: SkillMetadata | None = None
    load_time_ms: int = 0


@dataclass
class UnloadResult:
    """卸载结果"""
    skill_name: str
    success: bool
    error: str | None = None
    cleanup_time_ms: int = 0
    resources_freed: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReloadResult:
    """重载结果"""
    skill_name: str
    success: bool
    old_version: str | None = None
    new_version: str | None = None
    error: str | None = None
    reload_time_ms: int = 0


class SkillLifecycleManager:
    """技能生命周期管理器"""

    def __init__(
        self,
        skills_dir: Path | None = None,
        registry: EnhancedSkillRegistry | None = None,
        scanner: SkillScanner | None = None,
        auto_reload: bool = False,
        reload_interval: int = 5,
    ):
        self.skills_dir = skills_dir or Path(__file__).parent / "implemented"
        self.registry = registry or EnhancedSkillRegistry.get_instance()
        self.scanner = scanner or SkillScanner(skills_dir=self.skills_dir)
        self.auto_reload = auto_reload
        self.reload_interval = reload_interval

        self._event_handlers: dict[LifecycleEventType, list[Callable[[LifecycleEvent], None]]] = {
            event_type: [] for event_type in LifecycleEventType
        }
        self._load_history: dict[str, list[LoadResult]] = {}
        self._watch_thread: threading.Thread | None = None
        self._watch_running: bool = False
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="skill-lifecycle")
        self._loaded_modules: dict[str, str] = {}
        self._skill_states: dict[str, SkillLoadStatus] = {}

    def on(self, event_type: LifecycleEventType, handler: Callable[[LifecycleEvent], None]):
        """注册事件处理器"""
        self._event_handlers[event_type].append(handler)

    def off(self, event_type: LifecycleEventType, handler: Callable[[LifecycleEvent], None]):
        """移除事件处理器"""
        if handler in self._event_handlers[event_type]:
            self._event_handlers[event_type].remove(handler)

    def _emit(self, event: LifecycleEvent):
        """触发事件"""
        handlers = self._event_handlers.get(event.event_type, [])
        for handler in handlers:
            with suppress(Exception):
                handler(event)

    def load_skill(
        self,
        skill_class: type[SkillBase],
        file_path: Path | None = None,
        file_hash: str | None = None,
    ) -> LoadResult:
        """加载单个技能"""
        start_time = time.time()
        skill_name = ""

        try:
            metadata = skill_class.get_metadata()
            skill_name = metadata.name

            self._emit(LifecycleEvent(
                event_type=LifecycleEventType.BEFORE_LOAD,
                skill_name=skill_name,
                metadata={"file_path": str(file_path) if file_path else None},
            ))

            success = self.registry.register(
                skill_class=skill_class,
                file_path=str(file_path) if file_path else None,
                file_hash=file_hash,
            )

            if success:
                self._skill_states[skill_name] = SkillLoadStatus.LOADED

                if skill_name not in self._load_history:
                    self._load_history[skill_name] = []
                self._load_history[skill_name].append(LoadResult(
                    skill_name=skill_name,
                    success=True,
                    status=SkillLoadStatus.LOADED,
                    metadata=metadata,
                    load_time_ms=int((time.time() - start_time) * 1000),
                ))

                self._emit(LifecycleEvent(
                    event_type=LifecycleEventType.AFTER_LOAD,
                    skill_name=skill_name,
                    metadata={"load_time_ms": int((time.time() - start_time) * 1000)},
                ))

                return LoadResult(
                    skill_name=skill_name,
                    success=True,
                    status=SkillLoadStatus.LOADED,
                    metadata=metadata,
                    load_time_ms=int((time.time() - start_time) * 1000),
                )
            else:
                self._skill_states[skill_name] = SkillLoadStatus.ERROR

                self._emit(LifecycleEvent(
                    event_type=LifecycleEventType.ON_ERROR,
                    skill_name=skill_name,
                    success=False,
                    error="注册失败",
                ))

                return LoadResult(
                    skill_name=skill_name,
                    success=False,
                    status=SkillLoadStatus.ERROR,
                    error="注册失败",
                    load_time_ms=int((time.time() - start_time) * 1000),
                )

        except Exception as e:
            self._skill_states[skill_name or "unknown"] = SkillLoadStatus.ERROR

            self._emit(LifecycleEvent(
                event_type=LifecycleEventType.ON_ERROR,
                skill_name=skill_name or "unknown",
                success=False,
                error=str(e),
            ))

            return LoadResult(
                skill_name=skill_name or "unknown",
                success=False,
                status=SkillLoadStatus.ERROR,
                error=str(e),
                load_time_ms=int((time.time() - start_time) * 1000),
            )

    def load_from_scan_result(self, scan_result: SkillScanResult) -> LoadResult:
        """从扫描结果加载技能"""
        if scan_result.status != ScanStatus.SUCCESS or scan_result.skill_class is None:
            return LoadResult(
                skill_name=scan_result.skill_name,
                success=False,
                status=SkillLoadStatus.ERROR,
                error=scan_result.error or "扫描失败",
            )

        return self.load_skill(
            skill_class=scan_result.skill_class,
            file_path=scan_result.file_path,
            file_hash=scan_result.file_hash,
        )

    def load_from_file(self, file_path: Path) -> list[LoadResult]:
        """从文件加载技能"""
        results = self.scanner._scan_file(file_path)
        return [self.load_from_scan_result(r) for r in results]

    def load_all(self, directory: Path | None = None) -> dict[str, LoadResult]:
        """加载目录下所有技能"""
        target_dir = directory or self.skills_dir
        results = {}

        scan_report = self.scanner.scan_directory(target_dir)

        load_order = self.scanner.get_dependency_order([
            r.skill_name for r in scan_report.results
            if r.status == ScanStatus.SUCCESS
        ])

        result_map = {r.skill_name: r for r in scan_report.results}

        for skill_name in load_order:
            if skill_name in result_map:
                results[skill_name] = self.load_from_scan_result(result_map[skill_name])

        return results

    def unload_skill(self, skill_name: str, force: bool = False) -> UnloadResult:
        """卸载技能"""
        start_time = time.time()

        if not self.registry.has_skill(skill_name):
            return UnloadResult(
                skill_name=skill_name,
                success=False,
                error="技能不存在",
            )

        dependents = self.registry.get_dependents(skill_name)
        if dependents and not force:
            return UnloadResult(
                skill_name=skill_name,
                success=False,
                error=f"存在依赖此技能的其他技能: {', '.join(dependents)}",
            )

        self._emit(LifecycleEvent(
            event_type=LifecycleEventType.BEFORE_UNLOAD,
            skill_name=skill_name,
        ))

        registration = self.registry.get_registration(skill_name)
        resources_freed = {}

        if registration and registration.file_path:
            module_name = f"skills.implemented.{Path(registration.file_path).stem}"
            if module_name in sys.modules:
                try:
                    del sys.modules[module_name]
                    resources_freed["module_unloaded"] = module_name
                except Exception:
                    pass

        success = self.registry.unregister(skill_name, force=force)

        if success:
            self._skill_states[skill_name] = SkillLoadStatus.UNLOADED

            self._emit(LifecycleEvent(
                event_type=LifecycleEventType.AFTER_UNLOAD,
                skill_name=skill_name,
            ))

            return UnloadResult(
                skill_name=skill_name,
                success=True,
                cleanup_time_ms=int((time.time() - start_time) * 1000),
                resources_freed=resources_freed,
            )
        else:
            self._emit(LifecycleEvent(
                event_type=LifecycleEventType.ON_ERROR,
                skill_name=skill_name,
                success=False,
                error="卸载失败",
            ))

            return UnloadResult(
                skill_name=skill_name,
                success=False,
                error="卸载失败",
                cleanup_time_ms=int((time.time() - start_time) * 1000),
            )

    def unload_all(self, force: bool = False) -> dict[str, UnloadResult]:
        """卸载所有技能"""
        results = {}

        unload_order = self.registry.get_unload_order()

        for skill_name in unload_order:
            results[skill_name] = self.unload_skill(skill_name, force=force)

        return results

    def reload_skill(self, skill_name: str) -> ReloadResult:
        """重载技能"""
        start_time = time.time()

        registration = self.registry.get_registration(skill_name)
        if not registration:
            return ReloadResult(
                skill_name=skill_name,
                success=False,
                error="技能不存在",
            )

        old_version = registration.version

        self._emit(LifecycleEvent(
            event_type=LifecycleEventType.BEFORE_RELOAD,
            skill_name=skill_name,
            metadata={"old_version": old_version},
        ))

        file_path = registration.file_path

        if file_path:
            try:
                file_path = Path(file_path)
                scan_results = self.scanner._scan_file(file_path)

                success = False
                new_version = None
                error = None

                for result in scan_results:
                    if result.skill_name == skill_name and result.skill_class:
                        if result.metadata:
                            new_version = result.metadata.version

                        reload_success = self.registry.reload(skill_name, result.skill_class)

                        if reload_success:
                            success = True
                            break
                        else:
                            error = "重载注册失败"

                if success:
                    self._skill_states[skill_name] = SkillLoadStatus.LOADED

                    self._emit(LifecycleEvent(
                        event_type=LifecycleEventType.AFTER_RELOAD,
                        skill_name=skill_name,
                        metadata={
                            "old_version": old_version,
                            "new_version": new_version,
                        },
                    ))

                    return ReloadResult(
                        skill_name=skill_name,
                        success=True,
                        old_version=old_version,
                        new_version=new_version,
                        reload_time_ms=int((time.time() - start_time) * 1000),
                    )
                else:
                    self._emit(LifecycleEvent(
                        event_type=LifecycleEventType.ON_ERROR,
                        skill_name=skill_name,
                        success=False,
                        error=error or "重载失败",
                    ))

                    return ReloadResult(
                        skill_name=skill_name,
                        success=False,
                        old_version=old_version,
                        error=error or "重载失败",
                        reload_time_ms=int((time.time() - start_time) * 1000),
                    )

            except Exception as e:
                self._emit(LifecycleEvent(
                    event_type=LifecycleEventType.ON_ERROR,
                    skill_name=skill_name,
                    success=False,
                    error=str(e),
                ))

                return ReloadResult(
                    skill_name=skill_name,
                    success=False,
                    old_version=old_version,
                    error=str(e),
                    reload_time_ms=int((time.time() - start_time) * 1000),
                )
        else:
            return ReloadResult(
                skill_name=skill_name,
                success=False,
                old_version=old_version,
                error="无法找到技能文件路径",
                reload_time_ms=int((time.time() - start_time) * 1000),
            )

    def reload_all(self) -> dict[str, ReloadResult]:
        """重载所有技能"""
        results = {}

        load_order = self.registry.get_load_order()

        for skill_name in load_order:
            results[skill_name] = self.reload_skill(skill_name)

        return results

    def enable_skill(self, skill_name: str) -> bool:
        """启用技能"""
        success = self.registry.enable_skill(skill_name)

        if success:
            self._emit(LifecycleEvent(
                event_type=LifecycleEventType.ON_ENABLE,
                skill_name=skill_name,
            ))

        return success

    def disable_skill(self, skill_name: str) -> bool:
        """禁用技能"""
        success = self.registry.disable_skill(skill_name)

        if success:
            self._emit(LifecycleEvent(
                event_type=LifecycleEventType.ON_DISABLE,
                skill_name=skill_name,
            ))

        return success

    def get_skill_state(self, skill_name: str) -> SkillLoadStatus:
        """获取技能状态"""
        return self._skill_states.get(skill_name, SkillLoadStatus.UNLOADED)

    def get_all_states(self) -> dict[str, SkillLoadStatus]:
        """获取所有技能状态"""
        return self._skill_states.copy()

    def check_dependencies(self, skill_name: str) -> dict[str, Any]:
        """检查技能依赖"""
        return self.registry.check_dependencies(skill_name)

    def start_watching(self):
        """开始监控文件变更"""
        if self._watch_running:
            return

        self._watch_running = True
        self._watch_thread = threading.Thread(
            target=self._watch_loop,
            daemon=True,
            name="skill-watcher",
        )
        self._watch_thread.start()

    def stop_watching(self):
        """停止监控文件变更"""
        self._watch_running = False
        if self._watch_thread:
            self._watch_thread.join(timeout=5)
            self._watch_thread = None

    def _watch_loop(self):
        """监控循环"""
        while self._watch_running:
            try:
                updates = self.scanner.check_for_updates()

                for modified in updates.get("modified", []):
                    skill_name = modified.get("skill_name")
                    if skill_name and self.auto_reload:
                        self.reload_skill(skill_name)

                for added in updates.get("added", []):
                    file_path = Path(added.get("file_path", ""))
                    if file_path.exists():
                        self.load_from_file(file_path)

                for removed in updates.get("removed", []):
                    skill_name = removed.get("skill_name")
                    if skill_name:
                        self.unload_skill(skill_name)

            except Exception:
                pass

            time.sleep(self.reload_interval)

    def get_load_history(self, skill_name: str) -> list[LoadResult]:
        """获取加载历史"""
        return self._load_history.get(skill_name, [])

    def get_status_report(self) -> dict[str, Any]:
        """获取状态报告"""
        registry_stats = self.registry.get_stats()

        states_count = {}
        for state in self._skill_states.values():
            states_count[state.value] = states_count.get(state.value, 0) + 1

        return {
            "registry_stats": registry_stats,
            "load_states": states_count,
            "watch_running": self._watch_running,
            "auto_reload": self.auto_reload,
            "skills_dir": str(self.skills_dir),
            "total_load_history": sum(len(h) for h in self._load_history.values()),
        }

    def cleanup(self):
        """清理资源"""
        self.stop_watching()
        self._executor.shutdown(wait=True)
        self.scanner.clear_cache()


def create_lifecycle_manager(
    skills_dir: Path | None = None,
    auto_reload: bool = False,
    **kwargs
) -> SkillLifecycleManager:
    """创建生命周期管理器实例"""
    return SkillLifecycleManager(
        skills_dir=skills_dir,
        auto_reload=auto_reload,
        **kwargs
    )


_lifecycle_manager: SkillLifecycleManager | None = None


def get_lifecycle_manager() -> SkillLifecycleManager:
    """获取全局生命周期管理器实例"""
    global _lifecycle_manager
    if _lifecycle_manager is None:
        _lifecycle_manager = SkillLifecycleManager()
    return _lifecycle_manager

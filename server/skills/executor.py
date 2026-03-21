# -*- coding: utf-8 -*-
"""
技能执行器模块

功能：
- 同步/异步技能执行
- 执行超时控制
- 资源限制管理
- 执行结果缓存集成
- 执行队列和并发控制
- 执行状态监控
"""
import asyncio
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

from .base import SkillBase
from .cache import CachedSkillExecutor, SkillExecutionCache, get_skill_cache
from .models import (
    SkillExecution,
    SkillMetadata,
    SkillPriority,
    SkillResult,
    SkillStatus,
)
from .sandbox import (
    ExecutionSandbox,
    ResourceLimits,
    SandboxConfig,
    SandboxPermission,
    SandboxResult,
    SkillSandbox,
    create_sandbox,
)


class ExecutionMode(str, Enum):
    """执行模式"""
    SYNC = "sync"
    ASYNC = "async"
    BACKGROUND = "background"


@dataclass
class ExecutorConfig:
    """执行器配置"""
    default_timeout: int = 30
    max_concurrent_executions: int = 10
    max_queue_size: int = 100
    enable_cache: bool = True
    enable_sandbox: bool = True
    default_cache_ttl: int = 3600
    retry_on_failure: bool = False
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class ExecutionTask:
    """执行任务"""
    task_id: str
    skill_name: str
    parameters: Dict[str, Any]
    priority: SkillPriority
    mode: ExecutionMode
    timeout: Optional[int]
    use_cache: bool
    cache_ttl: Optional[int]
    use_sandbox: bool
    sandbox_config: Optional[SandboxConfig]
    user_id: Optional[str]
    session_id: Optional[str]
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: SkillStatus = SkillStatus.PENDING
    result: Optional[SkillResult] = None
    error: Optional[str] = None


@dataclass
class ExecutorStats:
    """执行器统计"""
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    cancelled_executions: int = 0
    timeout_executions: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    current_running: int = 0
    current_queued: int = 0
    average_execution_time: float = 0.0


class SkillExecutor:
    """技能执行器"""

    def __init__(
        self,
        config: Optional[ExecutorConfig] = None,
        cache: Optional[SkillExecutionCache] = None,
        sandbox: Optional[SkillSandbox] = None,
    ):
        self._config = config or ExecutorConfig()
        self._cache = cache
        self._sandbox = sandbox
        self._cached_executor: Optional[CachedSkillExecutor] = None

        self._tasks: Dict[str, ExecutionTask] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._task_queue: asyncio.PriorityQueue = None
        self._semaphore: Optional[asyncio.Semaphore] = None

        self._stats = ExecutorStats()
        self._lock = threading.Lock()
        self._async_lock: Optional[asyncio.Lock] = None

        self._skill_registry = None
        self._thread_pool: Optional[ThreadPoolExecutor] = None

        self._on_task_start: Optional[Callable[[ExecutionTask], None]] = None
        self._on_task_complete: Optional[Callable[[ExecutionTask], None]] = None
        self._on_task_error: Optional[Callable[[ExecutionTask, Exception], None]] = None

    def _get_cache(self) -> SkillExecutionCache:
        """获取缓存实例"""
        if self._cache is None:
            self._cache = get_skill_cache()
        return self._cache

    def _get_cached_executor(self) -> CachedSkillExecutor:
        """获取缓存执行器"""
        if self._cached_executor is None:
            self._cached_executor = CachedSkillExecutor(cache=self._get_cache())
        return self._cached_executor

    def _get_sandbox(self) -> SkillSandbox:
        """获取沙箱实例"""
        if self._sandbox is None:
            self._sandbox = create_sandbox()
        return self._sandbox

    def _get_skill_registry(self):
        """获取技能注册表"""
        if self._skill_registry is None:
            from .registry import get_registry
            self._skill_registry = get_registry()
        return self._skill_registry

    def _get_thread_pool(self) -> ThreadPoolExecutor:
        """获取线程池"""
        if self._thread_pool is None:
            self._thread_pool = ThreadPoolExecutor(
                max_workers=self._config.max_concurrent_executions,
            )
        return self._thread_pool

    def _generate_task_id(self) -> str:
        """生成任务ID"""
        return str(uuid.uuid4())

    def _update_stats(self, success: bool, cached: bool = False, timeout: bool = False):
        """更新统计"""
        with self._lock:
            self._stats.total_executions += 1

            if timeout:
                self._stats.timeout_executions += 1
            elif success:
                self._stats.successful_executions += 1
            else:
                self._stats.failed_executions += 1

            if cached:
                self._stats.cache_hits += 1
            else:
                self._stats.cache_misses += 1

    async def _initialize_async(self):
        """初始化异步资源"""
        if self._task_queue is None:
            self._task_queue = asyncio.PriorityQueue(maxsize=self._config.max_queue_size)

        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._config.max_concurrent_executions)

        if self._async_lock is None:
            self._async_lock = asyncio.Lock()

    def create_task(
        self,
        skill_name: str,
        parameters: Dict[str, Any],
        priority: SkillPriority = SkillPriority.NORMAL,
        mode: ExecutionMode = ExecutionMode.ASYNC,
        timeout: Optional[int] = None,
        use_cache: Optional[bool] = None,
        cache_ttl: Optional[int] = None,
        use_sandbox: Optional[bool] = None,
        sandbox_config: Optional[SandboxConfig] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> ExecutionTask:
        """创建执行任务"""
        task = ExecutionTask(
            task_id=self._generate_task_id(),
            skill_name=skill_name,
            parameters=parameters,
            priority=priority,
            mode=mode,
            timeout=timeout or self._config.default_timeout,
            use_cache=use_cache if use_cache is not None else self._config.enable_cache,
            cache_ttl=cache_ttl or self._config.default_cache_ttl,
            use_sandbox=use_sandbox if use_sandbox is not None else self._config.enable_sandbox,
            sandbox_config=sandbox_config,
            user_id=user_id,
            session_id=session_id,
        )

        self._tasks[task.task_id] = task
        return task

    async def execute_task(self, task: ExecutionTask) -> SkillResult:
        """执行任务"""
        await self._initialize_async()

        task.status = SkillStatus.RUNNING
        task.started_at = datetime.now()

        if self._on_task_start:
            self._on_task_start(task)

        skill = self._get_skill_registry().get_skill(task.skill_name)
        if not skill:
            task.status = SkillStatus.FAILED
            task.error = f"技能不存在: {task.skill_name}"
            task.completed_at = datetime.now()
            self._update_stats(success=False)

            return SkillResult(
                success=False,
                error=task.error,
                error_code="SKILL_NOT_FOUND",
            )

        cached = False
        result = None

        try:
            if task.use_cache:
                cached_result = self._get_cache().get(task.skill_name, task.parameters)
                if cached_result:
                    result = cached_result
                    cached = True

            if result is None:
                if task.use_sandbox:
                    result = await self._execute_in_sandbox(task, skill)
                else:
                    result = await self._execute_direct(task, skill)

                if task.use_cache and result.success:
                    self._get_cache().set(
                        task.skill_name,
                        task.parameters,
                        result,
                        task.cache_ttl,
                    )

            task.result = result
            task.status = SkillStatus.COMPLETED if result.success else SkillStatus.FAILED
            task.completed_at = datetime.now()

            self._update_stats(success=result.success, cached=cached)

            if self._on_task_complete:
                self._on_task_complete(task)

            return result

        except asyncio.TimeoutError:
            task.status = SkillStatus.FAILED
            task.error = f"执行超时（超过 {task.timeout} 秒）"
            task.completed_at = datetime.now()
            task.result = SkillResult(
                success=False,
                error=task.error,
                error_code="TIMEOUT",
            )

            self._update_stats(success=False, timeout=True)

            if self._on_task_error:
                self._on_task_error(task, asyncio.TimeoutError(task.error))

            return task.result

        except asyncio.CancelledError:
            task.status = SkillStatus.CANCELLED
            task.error = "执行被取消"
            task.completed_at = datetime.now()
            task.result = SkillResult(
                success=False,
                error=task.error,
                error_code="CANCELLED",
            )

            with self._lock:
                self._stats.cancelled_executions += 1

            return task.result

        except Exception as e:
            task.status = SkillStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now()
            task.result = SkillResult(
                success=False,
                error=task.error,
                error_code="EXECUTION_ERROR",
                metadata={"traceback": traceback.format_exc()},
            )

            self._update_stats(success=False)

            if self._on_task_error:
                self._on_task_error(task, e)

            return task.result

    async def _execute_in_sandbox(self, task: ExecutionTask, skill: SkillBase) -> SkillResult:
        """在沙箱中执行"""
        sandbox = self._get_sandbox()

        if task.sandbox_config:
            sandbox = SkillSandbox(
                working_dir=task.sandbox_config.working_directory,
                permissions=task.sandbox_config.permissions,
                resource_limits=task.sandbox_config.resource_limits,
            )

        sandbox_result = await sandbox.execute_async(
            skill.execute,
            **task.parameters,
            timeout=task.timeout,
        )

        if sandbox_result.success:
            return SkillResult(
                success=True,
                data=sandbox_result.result,
                metadata={
                    "sandbox_violations": [v.message for v in sandbox_result.violations],
                    "resource_usage": sandbox_result.resource_usage,
                },
                execution_time=sandbox_result.execution_time,
            )
        else:
            return SkillResult(
                success=False,
                error=sandbox_result.error,
                error_code=sandbox_result.error_type,
                metadata={
                    "sandbox_violations": [v.message for v in sandbox_result.violations],
                    "resource_usage": sandbox_result.resource_usage,
                },
                execution_time=sandbox_result.execution_time,
            )

    async def _execute_direct(self, task: ExecutionTask, skill: SkillBase) -> SkillResult:
        """直接执行（无沙箱）"""
        try:
            result = await asyncio.wait_for(
                skill.execute(**task.parameters),
                timeout=task.timeout,
            )
            return result

        except asyncio.TimeoutError:
            raise

        except Exception as e:
            return SkillResult(
                success=False,
                error=str(e),
                error_code="EXECUTION_ERROR",
                metadata={"traceback": traceback.format_exc()},
            )

    async def execute(
        self,
        skill_name: str,
        parameters: Dict[str, Any],
        priority: SkillPriority = SkillPriority.NORMAL,
        timeout: Optional[int] = None,
        use_cache: Optional[bool] = None,
        use_sandbox: Optional[bool] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> SkillResult:
        """执行技能"""
        task = self.create_task(
            skill_name=skill_name,
            parameters=parameters,
            priority=priority,
            mode=ExecutionMode.ASYNC,
            timeout=timeout,
            use_cache=use_cache,
            use_sandbox=use_sandbox,
            user_id=user_id,
            session_id=session_id,
        )

        return await self.execute_task(task)

    async def execute_background(
        self,
        skill_name: str,
        parameters: Dict[str, Any],
        priority: SkillPriority = SkillPriority.NORMAL,
        timeout: Optional[int] = None,
        use_cache: Optional[bool] = None,
        use_sandbox: Optional[bool] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        on_complete: Optional[Callable[[SkillResult], None]] = None,
    ) -> str:
        """后台执行技能"""
        await self._initialize_async()

        task = self.create_task(
            skill_name=skill_name,
            parameters=parameters,
            priority=priority,
            mode=ExecutionMode.BACKGROUND,
            timeout=timeout,
            use_cache=use_cache,
            use_sandbox=use_sandbox,
            user_id=user_id,
            session_id=session_id,
        )

        async def run_background():
            async with self._semaphore:
                result = await self.execute_task(task)
                if on_complete:
                    on_complete(result)

        async_task = asyncio.create_task(run_background())
        self._running_tasks[task.task_id] = async_task

        return task.task_id

    def execute_sync(
        self,
        skill_name: str,
        parameters: Dict[str, Any],
        timeout: Optional[int] = None,
        use_cache: Optional[bool] = None,
        use_sandbox: Optional[bool] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> SkillResult:
        """同步执行技能"""
        task = self.create_task(
            skill_name=skill_name,
            parameters=parameters,
            mode=ExecutionMode.SYNC,
            timeout=timeout,
            use_cache=use_cache,
            use_sandbox=use_sandbox,
            user_id=user_id,
            session_id=session_id,
        )

        skill = self._get_skill_registry().get_skill(skill_name)
        if not skill:
            return SkillResult(
                success=False,
                error=f"技能不存在: {skill_name}",
                error_code="SKILL_NOT_FOUND",
            )

        cached = False
        result = None

        if task.use_cache:
            cached_result = self._get_cache().get(skill_name, parameters)
            if cached_result:
                result = cached_result
                cached = True

        if result is None:
            if task.use_sandbox:
                sandbox = self._get_sandbox()
                sandbox_result = sandbox.execute_sync(
                    lambda: skill.execute(**parameters),
                    timeout=task.timeout,
                )

                if sandbox_result.success:
                    result = SkillResult(
                        success=True,
                        data=sandbox_result.result,
                        metadata={
                            "resource_usage": sandbox_result.resource_usage,
                        },
                        execution_time=sandbox_result.execution_time,
                    )
                else:
                    result = SkillResult(
                        success=False,
                        error=sandbox_result.error,
                        error_code=sandbox_result.error_type,
                        execution_time=sandbox_result.execution_time,
                    )
            else:
                try:
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(
                            lambda: asyncio.run(skill.execute(**parameters))
                        )
                        result = future.result(timeout=task.timeout)

                except concurrent.futures.TimeoutError:
                    result = SkillResult(
                        success=False,
                        error=f"执行超时（超过 {task.timeout} 秒）",
                        error_code="TIMEOUT",
                    )

                except Exception as e:
                    result = SkillResult(
                        success=False,
                        error=str(e),
                        error_code="EXECUTION_ERROR",
                    )

            if task.use_cache and result.success:
                self._get_cache().set(skill_name, parameters, result, task.cache_ttl)

        task.result = result
        task.status = SkillStatus.COMPLETED if result.success else SkillStatus.FAILED
        task.completed_at = datetime.now()

        self._update_stats(success=result.success, cached=cached)

        return result

    def get_task(self, task_id: str) -> Optional[ExecutionTask]:
        """获取任务"""
        return self._tasks.get(task_id)

    def get_task_status(self, task_id: str) -> Optional[SkillStatus]:
        """获取任务状态"""
        task = self._tasks.get(task_id)
        return task.status if task else None

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id in self._running_tasks:
            async_task = self._running_tasks[task_id]
            async_task.cancel()

            try:
                await async_task
            except asyncio.CancelledError:
                pass

            return True

        task = self._tasks.get(task_id)
        if task and task.status == SkillStatus.PENDING:
            task.status = SkillStatus.CANCELLED
            task.error = "任务已取消"
            task.completed_at = datetime.now()
            return True

        return False

    async def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> Optional[SkillResult]:
        """等待任务完成"""
        if task_id in self._running_tasks:
            try:
                await asyncio.wait_for(
                    self._running_tasks[task_id],
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                return None

        task = self._tasks.get(task_id)
        return task.result if task else None

    def get_stats(self) -> ExecutorStats:
        """获取执行器统计"""
        with self._lock:
            running = sum(1 for t in self._tasks.values() if t.status == SkillStatus.RUNNING)
            queued = sum(1 for t in self._tasks.values() if t.status == SkillStatus.PENDING)

            completed_tasks = [
                t for t in self._tasks.values()
                if t.status in (SkillStatus.COMPLETED, SkillStatus.FAILED)
                and t.started_at and t.completed_at
            ]

            avg_time = 0.0
            if completed_tasks:
                total_time = sum(
                    (t.completed_at - t.started_at).total_seconds()
                    for t in completed_tasks
                )
                avg_time = total_time / len(completed_tasks)

            return ExecutorStats(
                total_executions=self._stats.total_executions,
                successful_executions=self._stats.successful_executions,
                failed_executions=self._stats.failed_executions,
                cancelled_executions=self._stats.cancelled_executions,
                timeout_executions=self._stats.timeout_executions,
                cache_hits=self._stats.cache_hits,
                cache_misses=self._stats.cache_misses,
                current_running=running,
                current_queued=queued,
                average_execution_time=avg_time,
            )

    def clear_completed_tasks(self, keep_count: int = 100):
        """清理已完成任务"""
        with self._lock:
            completed = [
                (tid, t) for tid, t in self._tasks.items()
                if t.status in (SkillStatus.COMPLETED, SkillStatus.FAILED, SkillStatus.CANCELLED)
            ]

            if len(completed) <= keep_count:
                return

            completed.sort(key=lambda x: x[1].completed_at or datetime.min, reverse=True)

            to_remove = [tid for tid, _ in completed[keep_count:]]

            for tid in to_remove:
                del self._tasks[tid]

    def set_callbacks(
        self,
        on_task_start: Optional[Callable[[ExecutionTask], None]] = None,
        on_task_complete: Optional[Callable[[ExecutionTask], None]] = None,
        on_task_error: Optional[Callable[[ExecutionTask, Exception], None]] = None,
    ):
        """设置回调函数"""
        self._on_task_start = on_task_start
        self._on_task_complete = on_task_complete
        self._on_task_error = on_task_error

    async def shutdown(self, wait: bool = True):
        """关闭执行器"""
        for task_id, async_task in list(self._running_tasks.items()):
            async_task.cancel()

        if wait:
            await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)

        self._running_tasks.clear()

        if self._thread_pool:
            self._thread_pool.shutdown(wait=wait)
            self._thread_pool = None


_executor: Optional[SkillExecutor] = None


def get_executor() -> SkillExecutor:
    """获取全局执行器实例"""
    global _executor
    if _executor is None:
        _executor = SkillExecutor()
    return _executor


def create_executor(
    config: Optional[ExecutorConfig] = None,
    cache: Optional[SkillExecutionCache] = None,
    sandbox: Optional[SkillSandbox] = None,
) -> SkillExecutor:
    """创建执行器实例"""
    return SkillExecutor(config=config, cache=cache, sandbox=sandbox)


async def execute_skill(
    skill_name: str,
    parameters: Dict[str, Any],
    timeout: Optional[int] = None,
    use_cache: bool = True,
    use_sandbox: bool = True,
) -> SkillResult:
    """便捷函数：执行技能"""
    executor = get_executor()
    return await executor.execute(
        skill_name=skill_name,
        parameters=parameters,
        timeout=timeout,
        use_cache=use_cache,
        use_sandbox=use_sandbox,
    )

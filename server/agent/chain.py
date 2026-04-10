"""
操作链编排模块 - 支持多步骤操作链的 DAG 编排
"""
import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ChainStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorStrategy(str, Enum):
    STOP = "stop"
    SKIP = "skip"
    RETRY = "retry"
    CONTINUE = "continue"


@dataclass
class OperationNode:
    id: str
    name: str
    action: str
    params: dict[str, Any]
    dependencies: list[str] = field(default_factory=list)
    condition: str | None = None
    on_success: str | None = None
    on_failure: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    timeout: float = 30.0
    status: str = NodeStatus.PENDING.value
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OperationNode":
        return cls(**data)


@dataclass
class OperationChain:
    id: str
    name: str
    description: str
    nodes: dict[str, OperationNode]
    error_strategy: str = ErrorStrategy.STOP.value
    rollback_on_failure: bool = True
    parallel_execution: bool = False
    status: str = ChainStatus.PENDING.value
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    current_node: str | None = None
    progress: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OperationChain":
        nodes = {k: OperationNode.from_dict(v) for k, v in data.pop("nodes", {}).items()}
        return cls(nodes=nodes, **data)


class ChainBuilder:
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.nodes: dict[str, OperationNode] = {}
        self.error_strategy = ErrorStrategy.STOP.value
        self.rollback_on_failure = True
        self.parallel_execution = False

    def add_node(
        self,
        node_id: str,
        action: str,
        params: dict[str, Any],
        name: str = "",
        dependencies: list[str] | None = None,
        condition: str | None = None,
        max_retries: int = 3,
        timeout: float = 30.0,
    ) -> "ChainBuilder":
        self.nodes[node_id] = OperationNode(
            id=node_id,
            name=name or node_id,
            action=action,
            params=params,
            dependencies=dependencies or [],
            condition=condition,
            max_retries=max_retries,
            timeout=timeout,
        )
        return self

    def set_error_strategy(self, strategy: ErrorStrategy) -> "ChainBuilder":
        self.error_strategy = strategy.value
        return self

    def enable_rollback(self, enable: bool = True) -> "ChainBuilder":
        self.rollback_on_failure = enable
        return self

    def enable_parallel(self, enable: bool = True) -> "ChainBuilder":
        self.parallel_execution = enable
        return self

    def build(self) -> OperationChain:
        self._validate()
        return OperationChain(
            id=f"chain_{uuid.uuid4().hex[:8]}",
            name=self.name,
            description=self.description,
            nodes=self.nodes,
            error_strategy=self.error_strategy,
            rollback_on_failure=self.rollback_on_failure,
            parallel_execution=self.parallel_execution,
        )

    def _validate(self):
        for node_id, node in self.nodes.items():
            for dep in node.dependencies:
                if dep not in self.nodes:
                    raise ValueError(f"节点 {node_id} 的依赖 {dep} 不存在")

        visited = set()
        path = set()

        def check_cycle(node_id: str):
            if node_id in path:
                raise ValueError(f"检测到循环依赖: {node_id}")
            if node_id in visited:
                return
            path.add(node_id)
            for dep in self.nodes[node_id].dependencies:
                check_cycle(dep)
            path.remove(node_id)
            visited.add(node_id)

        for node_id in self.nodes:
            check_cycle(node_id)


class ChainExecutor:
    def __init__(
        self,
        executor_factory: Callable[[], Any],
        previewer_factory: Callable[[], Any] | None = None,
        rollback_manager_factory: Callable[[], Any] | None = None,
    ):
        self.executor_factory = executor_factory
        self.previewer_factory = previewer_factory
        self.rollback_manager_factory = rollback_manager_factory
        self._chains: dict[str, OperationChain] = {}
        self._callbacks: dict[str, list[Callable]] = defaultdict(list)

    def register_callback(self, event: str, callback: Callable):
        self._callbacks[event].append(callback)

    async def _emit(self, event: str, data: dict[str, Any]):
        for callback in self._callbacks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                logger.warning(f"回调执行失败: {e}")

    async def execute(self, chain: OperationChain) -> dict[str, Any]:
        chain.status = ChainStatus.RUNNING.value
        chain.started_at = datetime.now().isoformat()
        self._chains[chain.id] = chain

        await self._emit("chain_started", {"chain_id": chain.id, "chain": chain.to_dict()})

        execution_order = self._get_execution_order(chain)

        try:
            if chain.parallel_execution:
                await self._execute_parallel(chain, execution_order)
            else:
                await self._execute_sequential(chain, execution_order)

            if all(n.status == NodeStatus.SUCCESS.value for n in chain.nodes.values()):
                chain.status = ChainStatus.COMPLETED.value
            else:
                chain.status = ChainStatus.FAILED.value

        except Exception as e:
            chain.status = ChainStatus.FAILED.value
            logger.error(f"操作链执行失败: {e}")

        chain.completed_at = datetime.now().isoformat()
        chain.progress = 1.0

        await self._emit("chain_completed", {"chain_id": chain.id, "chain": chain.to_dict()})

        return chain.to_dict()

    def _get_execution_order(self, chain: OperationChain) -> list[list[str]]:
        in_degree = defaultdict(int)
        for node in chain.nodes.values():
            for _ in node.dependencies:
                in_degree[node.id] += 1

        levels = []
        remaining = set(chain.nodes.keys())

        while remaining:
            level = [n for n in remaining if in_degree[n] == 0]
            if not level:
                break

            levels.append(level)

            for node_id in level:
                remaining.remove(node_id)
                for node in chain.nodes.values():
                    if node_id in node.dependencies:
                        in_degree[node.id] -= 1

        return levels

    async def _execute_sequential(
        self, chain: OperationChain, execution_order: list[list[str]]
    ):
        executor = self.executor_factory()
        completed = 0
        total = len(chain.nodes)

        for level in execution_order:
            for node_id in level:
                node = chain.nodes[node_id]

                if not self._check_dependencies(chain, node):
                    node.status = NodeStatus.SKIPPED.value
                    continue

                chain.current_node = node_id
                await self._emit("node_started", {"chain_id": chain.id, "node_id": node_id})

                success = await self._execute_node(chain, node, executor)

                completed += 1
                chain.progress = completed / total

                await self._emit(
                    "node_completed",
                    {"chain_id": chain.id, "node_id": node_id, "success": success},
                )

                if not success and chain.error_strategy == ErrorStrategy.STOP.value:
                    if chain.rollback_on_failure:
                        await self._rollback_chain(chain)
                    raise Exception(f"节点 {node_id} 执行失败")

    async def _execute_parallel(
        self, chain: OperationChain, execution_order: list[list[str]]
    ):
        executor = self.executor_factory()

        for level in execution_order:
            tasks = []
            for node_id in level:
                node = chain.nodes[node_id]
                if self._check_dependencies(chain, node):
                    tasks.append(self._execute_node(chain, node, executor))
                else:
                    node.status = NodeStatus.SKIPPED.value

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                if chain.error_strategy == ErrorStrategy.STOP.value:
                    for result in results:
                        if isinstance(result, Exception) or result is False:
                            if chain.rollback_on_failure:
                                await self._rollback_chain(chain)
                            raise Exception("并行执行失败")

        chain.progress = 1.0

    def _check_dependencies(self, chain: OperationChain, node: OperationNode) -> bool:
        for dep_id in node.dependencies:
            dep_node = chain.nodes.get(dep_id)
            if not dep_node or dep_node.status != NodeStatus.SUCCESS.value:
                return False
        return True

    async def _execute_node(
        self, chain: OperationChain, node: OperationNode, executor: Any
    ) -> bool:
        node.status = NodeStatus.RUNNING.value
        node.started_at = datetime.now().isoformat()

        from .config import ActionType

        for attempt in range(node.max_retries + 1):
            try:
                action = ActionType(node.action)
                result = await asyncio.wait_for(
                    executor.execute(action, node.params),
                    timeout=node.timeout,
                )

                node.result = result.to_dict() if hasattr(result, "to_dict") else result
                node.status = NodeStatus.SUCCESS.value
                node.completed_at = datetime.now().isoformat()
                return True

            except asyncio.TimeoutError:
                node.error = f"执行超时 ({node.timeout}秒)"
                logger.warning(f"节点 {node.id} 超时，尝试 {attempt + 1}/{node.max_retries + 1}")

            except Exception as e:
                node.error = str(e)
                logger.error(f"节点 {node.id} 执行失败: {e}")

            if attempt < node.max_retries:
                await asyncio.sleep(1 * (attempt + 1))

        node.status = NodeStatus.FAILED.value
        node.completed_at = datetime.now().isoformat()
        return False

    async def _rollback_chain(self, chain: OperationChain):
        if not self.rollback_manager_factory:
            return

        rollback_manager = self.rollback_manager_factory()
        completed_nodes = [
            n for n in chain.nodes.values()
            if n.status == NodeStatus.SUCCESS.value and n.result
        ]

        for node in reversed(completed_nodes):
            try:
                if node.result and node.result.get("snapshot_id"):
                    await rollback_manager.rollback(node.result["snapshot_id"])
            except Exception as e:
                logger.error(f"回滚节点 {node.id} 失败: {e}")

    async def cancel(self, chain_id: str) -> bool:
        chain = self._chains.get(chain_id)
        if not chain or chain.status != ChainStatus.RUNNING.value:
            return False

        chain.status = ChainStatus.CANCELLED.value
        chain.completed_at = datetime.now().isoformat()

        for node in chain.nodes.values():
            if node.status == NodeStatus.PENDING.value:
                node.status = NodeStatus.SKIPPED.value

        await self._emit("chain_cancelled", {"chain_id": chain_id})
        return True

    def get_chain(self, chain_id: str) -> OperationChain | None:
        return self._chains.get(chain_id)

    def get_chain_status(self, chain_id: str) -> dict[str, Any] | None:
        chain = self._chains.get(chain_id)
        if chain:
            return {
                "id": chain.id,
                "name": chain.name,
                "status": chain.status,
                "progress": chain.progress,
                "current_node": chain.current_node,
                "started_at": chain.started_at,
                "completed_at": chain.completed_at,
            }
        return None


_chain_executor: ChainExecutor | None = None


def get_chain_executor() -> ChainExecutor:
    global _chain_executor
    if _chain_executor is None:
        from .executor import get_executor
        from .rollback import get_rollback_manager

        _chain_executor = ChainExecutor(
            executor_factory=get_executor,
            rollback_manager_factory=get_rollback_manager,
        )
    return _chain_executor

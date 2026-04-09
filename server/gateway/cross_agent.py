"""
跨 Agent 通信管理器
实现多 Agent 环境下的通信机制：
- 消息传递
- 子 Agent spawn
- 结果收集和合并
- 通信权限控制
"""
import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """消息类型"""
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    SPAWN = "spawn"
    TERMINATE = "terminate"
    HEARTBEAT = "heartbeat"


class MessagePriority(str, Enum):
    """消息优先级"""
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class AgentMessage:
    """Agent 消息"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_agent: str = ""
    target_agent: str = ""
    message_type: MessageType = MessageType.REQUEST
    priority: MessagePriority = MessagePriority.NORMAL
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at


@dataclass
class SpawnedAgent:
    """生成的子 Agent"""
    id: str
    parent_agent: str
    task_type: str
    status: str = "running"
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class CommunicationChannel:
    """通信通道"""
    id: str
    agent_a: str
    agent_b: str
    created_at: datetime = field(default_factory=datetime.now)
    message_count: int = 0
    last_activity: datetime = field(default_factory=datetime.now)
    permissions: dict[str, list[str]] = field(default_factory=dict)


class CrossAgentCommunicator:
    """
    跨 Agent 通信管理器

    功能:
    - 消息传递
    - 子 Agent spawn
    - 结果收集和合并
    - 通信权限控制
    """

    def __init__(self):
        self._message_queues: dict[str, asyncio.Queue] = {}
        self._channels: dict[str, CommunicationChannel] = {}
        self._spawned_agents: dict[str, SpawnedAgent] = {}
        self._agent_handlers: dict[str, Callable] = {}
        self._pending_responses: dict[str, asyncio.Future] = {}

        self._max_spawned_agents = 10
        self._message_timeout = 300
        self._max_queue_size = 1000

        self._is_running = False
        self._background_tasks: list[asyncio.Task] = []

    async def start(self):
        """启动通信管理器"""
        if self._is_running:
            return

        self._is_running = True
        logger.info("跨 Agent 通信管理器已启动")

    async def stop(self):
        """停止通信管理器"""
        self._is_running = False

        for task in self._background_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        for future in self._pending_responses.values():
            if not future.done():
                future.cancel()

        self._pending_responses.clear()
        logger.info("跨 Agent 通信管理器已停止")

    def register_agent(self, agent_id: str, handler: Callable | None = None):
        """注册 Agent"""
        if agent_id not in self._message_queues:
            self._message_queues[agent_id] = asyncio.Queue(maxsize=self._max_queue_size)

        if handler:
            self._agent_handlers[agent_id] = handler

        logger.info(f"注册 Agent: {agent_id}")

    def unregister_agent(self, agent_id: str):
        """注销 Agent"""
        if agent_id in self._message_queues:
            del self._message_queues[agent_id]

        if agent_id in self._agent_handlers:
            del self._agent_handlers[agent_id]

        channels_to_remove = [
            cid for cid, c in self._channels.items()
            if c.agent_a == agent_id or c.agent_b == agent_id
        ]
        for cid in channels_to_remove:
            del self._channels[cid]

        logger.info(f"注销 Agent: {agent_id}")

    async def send_message(
        self,
        source_agent: str,
        target_agent: str,
        payload: dict[str, Any],
        message_type: MessageType = MessageType.REQUEST,
        priority: MessagePriority = MessagePriority.NORMAL,
        correlation_id: str | None = None,
        timeout: int | None = None,
    ) -> AgentMessage | None:
        """发送消息"""
        if target_agent not in self._message_queues:
            logger.warning(f"目标 Agent 不存在: {target_agent}")
            return None

        if not self._check_permission(source_agent, target_agent, "send"):
            logger.warning(f"Agent {source_agent} 无权向 {target_agent} 发送消息")
            return None

        message = AgentMessage(
            source_agent=source_agent,
            target_agent=target_agent,
            message_type=message_type,
            priority=priority,
            payload=payload,
            correlation_id=correlation_id,
            expires_at=datetime.now() + timedelta(seconds=timeout or self._message_timeout),
        )

        try:
            await asyncio.wait_for(
                self._message_queues[target_agent].put(message),
                timeout=5.0,
            )

            channel_id = self._get_or_create_channel(source_agent, target_agent)
            self._channels[channel_id].message_count += 1
            self._channels[channel_id].last_activity = datetime.now()

            logger.debug(f"消息已发送: {source_agent} -> {target_agent}")
            return message

        except asyncio.TimeoutError:
            logger.warning(f"消息队列已满: {target_agent}")
            return None

    async def send_and_wait(
        self,
        source_agent: str,
        target_agent: str,
        payload: dict[str, Any],
        timeout: int = 60,
    ) -> dict[str, Any] | None:
        """发送消息并等待响应"""
        correlation_id = str(uuid.uuid4())

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_responses[correlation_id] = future

        try:
            message = await self.send_message(
                source_agent=source_agent,
                target_agent=target_agent,
                payload=payload,
                message_type=MessageType.REQUEST,
                correlation_id=correlation_id,
                timeout=timeout,
            )

            if not message:
                return None

            result = await asyncio.wait_for(future, timeout=timeout)
            return result

        except asyncio.TimeoutError:
            logger.warning(f"等待响应超时: {correlation_id}")
            return None

        finally:
            self._pending_responses.pop(correlation_id, None)

    async def broadcast(
        self,
        source_agent: str,
        payload: dict[str, Any],
        exclude: list[str] | None = None,
    ) -> list[str]:
        """广播消息到所有 Agent"""
        exclude = exclude or []
        if source_agent not in exclude:
            exclude.append(source_agent)

        sent_to = []
        for agent_id in self._message_queues.keys():
            if agent_id in exclude:
                continue

            message = await self.send_message(
                source_agent=source_agent,
                target_agent=agent_id,
                payload=payload,
                message_type=MessageType.BROADCAST,
            )

            if message:
                sent_to.append(agent_id)

        logger.info(f"广播消息: {source_agent} -> {len(sent_to)} 个 Agent")
        return sent_to

    async def receive_message(self, agent_id: str, timeout: float = 1.0) -> AgentMessage | None:
        """接收消息"""
        if agent_id not in self._message_queues:
            return None

        try:
            message = await asyncio.wait_for(
                self._message_queues[agent_id].get(),
                timeout=timeout,
            )
            return message
        except asyncio.TimeoutError:
            return None

    async def spawn_agent(
        self,
        parent_agent: str,
        task_type: str,
        config: dict[str, Any] | None = None,
    ) -> str | None:
        """生成子 Agent"""
        if len(self._spawned_agents) >= self._max_spawned_agents:
            logger.warning("已达到最大子 Agent 数量")
            return None

        spawned_id = f"{parent_agent}_spawn_{uuid.uuid4().hex[:8]}"

        spawned = SpawnedAgent(
            id=spawned_id,
            parent_agent=parent_agent,
            task_type=task_type,
        )

        self._spawned_agents[spawned_id] = spawned
        self.register_agent(spawned_id)

        asyncio.create_task(self._run_spawned_agent(spawned_id, config))

        logger.info(f"生成子 Agent: {spawned_id} (父: {parent_agent})")
        return spawned_id

    async def _run_spawned_agent(self, spawned_id: str, config: dict[str, Any] | None):
        """运行子 Agent"""
        spawned = self._spawned_agents.get(spawned_id)
        if not spawned:
            return

        try:
            result = await self._execute_spawned_task(spawned, config)

            spawned.status = "completed"
            spawned.result = result
            spawned.completed_at = datetime.now()

            await self.send_message(
                source_agent=spawned_id,
                target_agent=spawned.parent_agent,
                payload={"result": result, "task_type": spawned.task_type},
                message_type=MessageType.RESPONSE,
            )

        except Exception as e:
            spawned.status = "failed"
            spawned.error = str(e)
            spawned.completed_at = datetime.now()

            await self.send_message(
                source_agent=spawned_id,
                target_agent=spawned.parent_agent,
                payload={"error": str(e), "task_type": spawned.task_type},
                message_type=MessageType.RESPONSE,
            )

        finally:
            self.unregister_agent(spawned_id)

    async def _execute_spawned_task(
        self,
        spawned: SpawnedAgent,
        config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """执行子 Agent 任务"""
        await asyncio.sleep(0.1)
        return {"status": "completed", "task_type": spawned.task_type}

    async def terminate_agent(self, agent_id: str) -> bool:
        """终止子 Agent"""
        spawned = self._spawned_agents.get(agent_id)
        if not spawned:
            return False

        spawned.status = "terminated"
        spawned.completed_at = datetime.now()

        self.unregister_agent(agent_id)

        logger.info(f"终止子 Agent: {agent_id}")
        return True

    async def collect_results(
        self,
        agent_ids: list[str],
        timeout: int = 60,
    ) -> dict[str, Any]:
        """收集多个 Agent 的结果"""
        results = {}
        tasks = []

        for agent_id in agent_ids:
            spawned = self._spawned_agents.get(agent_id)
            if spawned and spawned.status == "completed":
                results[agent_id] = spawned.result
            elif agent_id in self._message_queues:
                tasks.append(self._collect_agent_result(agent_id, timeout))

        if tasks:
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
            for agent_id, result in zip(agent_ids, task_results):
                if not isinstance(result, Exception):
                    results[agent_id] = result

        return results

    async def _collect_agent_result(self, agent_id: str, timeout: int) -> dict[str, Any] | None:
        """收集单个 Agent 结果"""
        result = await self.send_and_wait(
            source_agent="system",
            target_agent=agent_id,
            payload={"action": "get_result"},
            timeout=timeout,
        )
        return result

    def merge_results(
        self,
        results: dict[str, Any],
        strategy: str = "combine",
    ) -> dict[str, Any]:
        """合并多个 Agent 的结果"""
        if not results:
            return {}

        if strategy == "combine":
            combined = {}
            for agent_id, result in results.items():
                if isinstance(result, dict):
                    combined[agent_id] = result
            return combined

        elif strategy == "best":
            best_result = None
            best_score = -1

            for agent_id, result in results.items():
                if isinstance(result, dict):
                    score = result.get("score", 0)
                    if score > best_score:
                        best_score = score
                        best_result = result

            return best_result or {}

        elif strategy == "aggregate":
            aggregated = {"count": len(results), "results": []}
            for agent_id, result in results.items():
                aggregated["results"].append({
                    "agent_id": agent_id,
                    "result": result,
                })
            return aggregated

        return results

    def _get_or_create_channel(self, agent_a: str, agent_b: str) -> str:
        """获取或创建通信通道"""
        channel_id = f"{min(agent_a, agent_b)}:{max(agent_a, agent_b)}"

        if channel_id not in self._channels:
            self._channels[channel_id] = CommunicationChannel(
                id=channel_id,
                agent_a=agent_a,
                agent_b=agent_b,
            )

        return channel_id

    def _check_permission(self, source_agent: str, target_agent: str, action: str) -> bool:
        """检查通信权限"""
        channel_id = f"{min(source_agent, target_agent)}:{max(source_agent, target_agent)}"

        channel = self._channels.get(channel_id)
        if not channel:
            return True

        permissions = channel.permissions.get(source_agent, [])
        if not permissions:
            return True

        return action in permissions or "*" in permissions

    def set_channel_permissions(
        self,
        agent_a: str,
        agent_b: str,
        permissions: dict[str, list[str]],
    ):
        """设置通道权限"""
        channel_id = self._get_or_create_channel(agent_a, agent_b)
        self._channels[channel_id].permissions.update(permissions)
        logger.info(f"设置通道权限: {channel_id}")

    def get_spawned_agents(self, parent_agent: str | None = None) -> list[SpawnedAgent]:
        """获取子 Agent 列表"""
        if parent_agent:
            return [
                a for a in self._spawned_agents.values()
                if a.parent_agent == parent_agent
            ]
        return list(self._spawned_agents.values())

    def get_channel_stats(self) -> dict[str, Any]:
        """获取通道统计"""
        return {
            "total_channels": len(self._channels),
            "total_messages": sum(c.message_count for c in self._channels.values()),
            "active_spawned_agents": sum(
                1 for a in self._spawned_agents.values()
                if a.status == "running"
            ),
            "total_spawned_agents": len(self._spawned_agents),
        }


_communicator: CrossAgentCommunicator | None = None


def get_cross_agent_communicator() -> CrossAgentCommunicator:
    """获取跨 Agent 通信管理器单例"""
    global _communicator
    if _communicator is None:
        _communicator = CrossAgentCommunicator()
    return _communicator

"""
消息路由器。

参考 OpenClaw 的 Binding Router 设计，按“最具体匹配优先”的顺序路由：
1. peer 精确匹配
2. guild + roles
3. guild
4. team
5. account
6. channel
7. 默认 agent
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .models import AgentInfo, BindingRule, GatewayMessage

logger = logging.getLogger(__name__)


@dataclass
class RoutingContext:
    """消息路由上下文。"""

    message: GatewayMessage
    source_device_id: str
    source_info: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    peer_id: str | None = None
    guild_id: str | None = None
    channel_id: str | None = None
    team_id: str | None = None
    account_id: str | None = None
    roles: list[str] = field(default_factory=list)


class MessageRouter:
    """
    消息路由器。

    功能：
    - 基于绑定规则的消息路由
    - 最具体匹配优先算法
    - Agent 隔离管理
    - 跨 Agent 通信
    """

    def __init__(self):
        self._bindings: dict[str, BindingRule] = {}
        self._agents: dict[str, AgentInfo] = {}
        self._default_agent_id: str | None = None

        self._agent_handlers: dict[str, Callable] = {}
        self._fallback_handler: Callable | None = None

    @staticmethod
    def _build_agent_info(agent_id: str, intents: list[str] | None = None) -> AgentInfo:
        """
        根据 AgentInfo 当前模型定义构造实例。

        这里兼容不同版本的 AgentInfo 字段，避免 router 与 models 演进不同步时直接报错。
        """

        field_map = getattr(AgentInfo, "model_fields", None) or getattr(AgentInfo, "__fields__", {})
        kwargs: dict[str, Any] = {
            "id": agent_id,
            "name": agent_id,
        }

        if "workspace_path" in field_map:
            kwargs["workspace_path"] = ""
        if "capabilities" in field_map:
            kwargs["capabilities"] = intents or []
        if "config" in field_map and intents:
            kwargs["config"] = {"intents": intents}

        return AgentInfo(**kwargs)

    def register_agent(self, agent_info: AgentInfo | str, intents: list[str] | None = None):
        """注册 Agent。"""
        if isinstance(agent_info, str):
            agent_info = self._build_agent_info(agent_info, intents)

        self._agents[agent_info.id] = agent_info
        logger.info("注册 Agent: %s (%s)", agent_info.id, agent_info.name)

    def unregister_agent(self, agent_id: str):
        """注销 Agent。"""
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info("注销 Agent: %s", agent_id)

        bindings_to_remove = [
            rule_id for rule_id, rule in self._bindings.items() if rule.agent_id == agent_id
        ]
        for rule_id in bindings_to_remove:
            del self._bindings[rule_id]

    def add_binding(self, rule: BindingRule):
        """添加绑定规则。"""
        self._bindings[rule.id] = rule
        logger.info("添加绑定规则: %s -> Agent %s (优先级 %s)", rule.id, rule.agent_id, rule.priority)

    def remove_binding(self, rule_id: str):
        """移除绑定规则。"""
        if rule_id in self._bindings:
            del self._bindings[rule_id]
            logger.info("移除绑定规则: %s", rule_id)

    def set_default_agent(self, agent_id: str):
        """设置默认 Agent。"""
        if agent_id in self._agents:
            self._default_agent_id = agent_id
            logger.info("设置默认 Agent: %s", agent_id)
        else:
            logger.warning("Agent 不存在: %s", agent_id)

    def register_agent_handler(self, agent_id: str, handler: Callable):
        """注册 Agent 消息处理器。"""
        self._agent_handlers[agent_id] = handler

    def set_fallback_handler(self, handler: Callable):
        """设置回退处理器。"""
        self._fallback_handler = handler

    async def _route_message(
        self, message: GatewayMessage, context: RoutingContext | None = None
    ) -> dict[str, Any]:
        """
        将消息路由到目标 Agent。

        使用“最具体匹配优先”算法。
        """
        if context is None:
            context = RoutingContext(
                message=message,
                source_device_id=message.source or "unknown",
            )

        agent_id = self._find_target_agent(context)

        if agent_id is None:
            if self._fallback_handler:
                return await self._fallback_handler(message, context)
            return {"error": "No matching agent found", "success": False}

        handler = self._agent_handlers.get(agent_id)
        if handler:
            try:
                return await handler(message, context)
            except Exception as exc:
                logger.error("Agent %s 处理消息失败: %s", agent_id, exc, exc_info=True)
                return {"error": str(exc), "success": False, "agent_id": agent_id}

        return {
            "routed": True,
            "agent_id": agent_id,
            "message": f"消息已路由到 Agent {agent_id}",
        }

    def _find_target_agent(self, context: RoutingContext) -> str | None:
        """
        查找目标 Agent。

        优先级从高到低：
        1. peer 精确匹配
        2. guild + roles
        3. guild
        4. team
        5. account
        6. channel
        7. fallback
        """
        matching_rules: list[tuple[BindingRule, int]] = []

        for rule in self._bindings.values():
            if not rule.enabled:
                continue

            score = self._calculate_match_score(rule, context)
            if score > 0:
                matching_rules.append((rule, score))

        if matching_rules:
            matching_rules.sort(key=lambda item: (item[1], item[0].priority), reverse=True)
            best_rule = matching_rules[0][0]
            logger.debug("路由匹配: 规则 %s -> Agent %s", best_rule.id, best_rule.agent_id)
            return best_rule.agent_id

        return self._default_agent_id

    def _calculate_match_score(self, rule: BindingRule, context: RoutingContext) -> int:
        """
        计算匹配分数。

        返回值越高，说明匹配越具体。
        """
        score = 0

        if rule.peer_id:
            if rule.peer_id != context.peer_id:
                return 0
            score += 1000

        if rule.guild_id:
            if rule.guild_id != context.guild_id:
                return 0
            score += 100

        if rule.roles:
            matched_roles = set(rule.roles) & set(context.roles)
            if not matched_roles:
                return 0
            score += 50 + len(matched_roles) * 10

        if rule.team_id:
            if rule.team_id != context.team_id:
                return 0
            score += 80

        if rule.account_id:
            if rule.account_id != context.account_id:
                return 0
            score += 70

        if rule.channel_id:
            if rule.channel_id != context.channel_id:
                return 0
            score += 60

        score += rule.priority
        return score

    def get_agent_info(self, agent_id: str) -> AgentInfo | None:
        """获取 Agent 信息。"""
        return self._agents.get(agent_id)

    def get_all_agents(self) -> dict[str, AgentInfo]:
        """获取所有 Agent。"""
        return self._agents.copy()

    def get_agent_bindings(self, agent_id: str) -> list[BindingRule]:
        """获取指定 Agent 的所有绑定规则。"""
        return [rule for rule in self._bindings.values() if rule.agent_id == agent_id]

    def get_routing_stats(self) -> dict[str, Any]:
        """获取路由统计信息。"""
        return {
            "total_agents": len(self._agents),
            "total_bindings": len(self._bindings),
            "default_agent": self._default_agent_id,
            "enabled_bindings": sum(1 for rule in self._bindings.values() if rule.enabled),
        }

    def route_intent(self, intent: str) -> str | None:
        for agent in self._agents.values():
            config = agent.config if isinstance(agent.config, dict) else {}
            capabilities = config.get("capabilities") or config.get("intents") or []
            if intent in capabilities:
                return agent.id
        return self._default_agent_id

    def route(self, *args, **kwargs):
        if args and isinstance(args[0], str) and len(args) == 1 and not kwargs:
            return self.route_intent(args[0])
        return self._route_message(*args, **kwargs)


_router: MessageRouter | None = None


def get_message_router() -> MessageRouter:
    """获取消息路由器单例。"""
    global _router
    if _router is None:
        _router = MessageRouter()
    return _router

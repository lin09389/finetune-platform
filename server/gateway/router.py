"""
消息路由�?- 借鉴 OpenClaw Binding Router 设计

实现最具体匹配优先算法�?1. peer 精确匹配（特�?DM/群组 ID�?2. parentPeer 继承（线程）
3. guildId + roles（Discord 角色�?4. guildId（Discord 服务器）
5. teamId（Slack�?6. accountId 匹配
7. channel 级别匹配
8. fallback 到默�?agent
"""
import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

from .models import GatewayMessage, GatewayResponse, BindingRule, AgentInfo

logger = logging.getLogger(__name__)


@dataclass
class RoutingContext:
    """路由上下�?""
    message: GatewayMessage
    source_device_id: str
    source_info: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    peer_id: Optional[str] = None
    guild_id: Optional[str] = None
    channel_id: Optional[str] = None
    team_id: Optional[str] = None
    account_id: Optional[str] = None
    roles: List[str] = field(default_factory=list)


class MessageRouter:
    """
    消息路由�?    
    功能�?    - 基于绑定规则的消息路�?    - 最具体匹配优先算法
    - Agent 隔离管理
    - �?Agent 通信
    """
    
    def __init__(self):
        self._bindings: Dict[str, BindingRule] = {}
        self._agents: Dict[str, AgentInfo] = {}
        self._default_agent_id: Optional[str] = None
        
        self._agent_handlers: Dict[str, Callable] = {}
        self._fallback_handler: Optional[Callable] = None
    
    def register_agent(self, agent_info: AgentInfo):
        """注册 Agent"""
        self._agents[agent_info.id] = agent_info
        logger.info(f"注册 Agent: {agent_info.id} ({agent_info.name})")
    
    def unregister_agent(self, agent_id: str):
        """注销 Agent"""
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info(f"注销 Agent: {agent_id}")
        
        bindings_to_remove = [
            rule_id for rule_id, rule in self._bindings.items()
            if rule.agent_id == agent_id
        ]
        for rule_id in bindings_to_remove:
            del self._bindings[rule_id]
    
    def add_binding(self, rule: BindingRule):
        """添加绑定规则"""
        self._bindings[rule.id] = rule
        logger.info(f"添加绑定规则: {rule.id} -> Agent {rule.agent_id} (优先�? {rule.priority})")
    
    def remove_binding(self, rule_id: str):
        """移除绑定规则"""
        if rule_id in self._bindings:
            del self._bindings[rule_id]
            logger.info(f"移除绑定规则: {rule_id}")
    
    def set_default_agent(self, agent_id: str):
        """设置默认 Agent"""
        if agent_id in self._agents:
            self._default_agent_id = agent_id
            logger.info(f"设置默认 Agent: {agent_id}")
        else:
            logger.warning(f"Agent 不存�? {agent_id}")
    
    def register_agent_handler(self, agent_id: str, handler: Callable):
        """注册 Agent 消息处理�?""
        self._agent_handlers[agent_id] = handler
    
    def set_fallback_handler(self, handler: Callable):
        """设置回退处理�?""
        self._fallback_handler = handler
    
    async def route(self, message: GatewayMessage, context: Optional[RoutingContext] = None) -> Dict[str, Any]:
        """
        路由消息到目�?Agent
        
        使用最具体匹配优先算法
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
                result = await handler(message, context)
                return result
            except Exception as e:
                logger.error(f"Agent {agent_id} 处理消息失败: {e}", exc_info=True)
                return {"error": str(e), "success": False, "agent_id": agent_id}
        
        return {
            "routed": True,
            "agent_id": agent_id,
            "message": f"消息已路由到 Agent {agent_id}",
        }
    
    def _find_target_agent(self, context: RoutingContext) -> Optional[str]:
        """
        查找目标 Agent
        
        优先级从高到低：
        1. peer 精确匹配
        2. parentPeer 继承
        3. guildId + roles
        4. guildId
        5. teamId
        6. accountId
        7. channel 级别
        8. fallback
        """
        matching_rules = []
        
        for rule in self._bindings.values():
            if not rule.enabled:
                continue
            
            score = self._calculate_match_score(rule, context)
            if score > 0:
                matching_rules.append((rule, score))
        
        if matching_rules:
            matching_rules.sort(key=lambda x: (x[1], x[0].priority), reverse=True)
            best_rule = matching_rules[0][0]
            logger.debug(f"路由匹配: 规则 {best_rule.id} -> Agent {best_rule.agent_id}")
            return best_rule.agent_id
        
        return self._default_agent_id
    
    def _calculate_match_score(self, rule: BindingRule, context: RoutingContext) -> int:
        """
        计算匹配分数
        
        返回值越高表示匹配越具体
        """
        score = 0
        
        if rule.peer_id and context.peer_id:
            if rule.peer_id == context.peer_id:
                score += 1000
            else:
                return 0
        
        if rule.guild_id and context.guild_id:
            if rule.guild_id == context.guild_id:
                score += 100
            else:
                return 0
        
        if rule.roles and context.roles:
            matched_roles = set(rule.roles) & set(context.roles)
            if matched_roles:
                score += 50 + len(matched_roles) * 10
            else:
                return 0
        
        if rule.team_id and context.team_id:
            if rule.team_id == context.team_id:
                score += 80
            else:
                return 0
        
        if rule.account_id and context.account_id:
            if rule.account_id == context.account_id:
                score += 70
            else:
                return 0
        
        if rule.channel_id and context.channel_id:
            if rule.channel_id == context.channel_id:
                score += 60
            else:
                return 0
        
        score += rule.priority
        
        return score
    
    def get_agent_info(self, agent_id: str) -> Optional[AgentInfo]:
        """获取 Agent 信息"""
        return self._agents.get(agent_id)
    
    def get_all_agents(self) -> Dict[str, AgentInfo]:
        """获取所�?Agent"""
        return self._agents.copy()
    
    def get_agent_bindings(self, agent_id: str) -> List[BindingRule]:
        """获取 Agent 的所有绑定规�?""
        return [rule for rule in self._bindings.values() if rule.agent_id == agent_id]
    
    def get_routing_stats(self) -> Dict[str, Any]:
        """获取路由统计"""
        return {
            "total_agents": len(self._agents),
            "total_bindings": len(self._bindings),
            "default_agent": self._default_agent_id,
            "enabled_bindings": sum(1 for r in self._bindings.values() if r.enabled),
        }


_router: Optional[MessageRouter] = None


def get_message_router() -> MessageRouter:
    """获取消息路由器单�?""
    global _router
    if _router is None:
        _router = MessageRouter()
    return _router

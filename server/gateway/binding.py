"""
Binding Router - 消息绑定路由器
支持多维度绑定：peer/guild/channel/team/account
"""
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import re

logger = logging.getLogger(__name__)


class BindingType(str, Enum):
    """绑定类型"""
    PEER = "peer"
    GUILD = "guild"
    CHANNEL = "channel"
    TEAM = "team"
    ACCOUNT = "account"


@dataclass
class Binding:
    """绑定规则"""
    binding_id: str
    binding_type: BindingType
    target_id: str
    agent_id: str
    priority: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class BindingMatch:
    """绑定匹配结果"""
    binding: Binding
    match_score: float = 1.0
    match_details: Dict[str, Any] = field(default_factory=dict)


class BindingRouter:
    """
    绑定路由器
    
    支持多维度绑定，按最具体匹配优先原则路由消息
    """
    
    PRIORITY_ORDER = [
        BindingType.PEER,
        BindingType.CHANNEL,
        BindingType.GUILD,
        BindingType.TEAM,
        BindingType.ACCOUNT,
    ]
    
    def __init__(self):
        self._bindings: Dict[str, Binding] = {}
        self._bindings_by_agent: Dict[str, List[str]] = {}
        self._bindings_by_target: Dict[str, List[str]] = {}
    
    def add_binding(self, binding: Binding) -> None:
        """添加绑定规则"""
        self._bindings[binding.binding_id] = binding
        
        if binding.agent_id not in self._bindings_by_agent:
            self._bindings_by_agent[binding.agent_id] = []
        self._bindings_by_agent[binding.agent_id].append(binding.binding_id)
        
        target_key = f"{binding.binding_type.value}:{binding.target_id}"
        if target_key not in self._bindings_by_target:
            self._bindings_by_target[target_key] = []
        self._bindings_by_target[target_key].append(binding.binding_id)
        
        logger.info(f"添加绑定: {binding.binding_id} -> {binding.agent_id}")
    
    def remove_binding(self, binding_id: str) -> bool:
        """移除绑定规则"""
        binding = self._bindings.get(binding_id)
        if not binding:
            return False
        
        del self._bindings[binding_id]
        
        if binding.agent_id in self._bindings_by_agent:
            self._bindings_by_agent[binding.agent_id].discard(binding_id)
        
        target_key = f"{binding.binding_type.value}:{binding.target_id}"
        if target_key in self._bindings_by_target:
            self._bindings_by_target[target_key].discard(binding_id)
        
        return True
    
    def get_binding(self, binding_id: str) -> Optional[Binding]:
        """获取绑定规则"""
        return self._bindings.get(binding_id)
    
    def get_agent_bindings(self, agent_id: str) -> List[Binding]:
        """获取 Agent 的所有绑定"""
        binding_ids = self._bindings_by_agent.get(agent_id, [])
        return [self._bindings[bid] for bid in binding_ids if bid in self._bindings]
    
    def route(
        self,
        peer_id: Optional[str] = None,
        guild_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        team_id: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> Optional[BindingMatch]:
        """
        路由消息到最匹配的绑定
        
        按优先级顺序匹配：peer > channel > guild > team > account
        """
        matches: List[BindingMatch] = []
        
        if peer_id:
            match = self._find_binding(BindingType.PEER, peer_id)
            if match:
                matches.append(match)
        
        if channel_id:
            match = self._find_binding(BindingType.CHANNEL, channel_id)
            if match:
                matches.append(match)
        
        if guild_id:
            match = self._find_binding(BindingType.GUILD, guild_id)
            if match:
                matches.append(match)
        
        if team_id:
            match = self._find_binding(BindingType.TEAM, team_id)
            if match:
                matches.append(match)
        
        if account_id:
            match = self._find_binding(BindingType.ACCOUNT, account_id)
            if match:
                matches.append(match)
        
        if not matches:
            return None
        
        matches.sort(key=lambda m: (
            self.PRIORITY_ORDER.index(m.binding.binding_type),
            -m.binding.priority,
            -m.match_score
        ))
        
        return matches[0]
    
    def _find_binding(
        self,
        binding_type: BindingType,
        target_id: str
    ) -> Optional[BindingMatch]:
        """查找指定类型和目标的绑定"""
        target_key = f"{binding_type.value}:{target_id}"
        binding_ids = self._bindings_by_target.get(target_key, [])
        
        enabled_bindings = [
            self._bindings[bid]
            for bid in binding_ids
            if bid in self._bindings and self._bindings[bid].enabled
        ]
        
        if not enabled_bindings:
            return None
        
        enabled_bindings.sort(key=lambda b: -b.priority)
        
        return BindingMatch(
            binding=enabled_bindings[0],
            match_score=1.0,
            match_details={"type": binding_type.value, "target": target_id}
        )
    
    def list_bindings(self, enabled_only: bool = True) -> List[Binding]:
        """列出所有绑定"""
        bindings = list(self._bindings.values())
        if enabled_only:
            bindings = [b for b in bindings if b.enabled]
        return bindings
    
    def enable_binding(self, binding_id: str) -> bool:
        """启用绑定"""
        binding = self._bindings.get(binding_id)
        if binding:
            binding.enabled = True
            return True
        return False
    
    def disable_binding(self, binding_id: str) -> bool:
        """禁用绑定"""
        binding = self._bindings.get(binding_id)
        if binding:
            binding.enabled = False
            return True
        return False


class BindingManager:
    """绑定管理器"""
    
    def __init__(self):
        self._router = BindingRouter()
        self._binding_counter = 0
    
    def create_binding(
        self,
        binding_type: BindingType,
        target_id: str,
        agent_id: str,
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Binding:
        """创建绑定"""
        self._binding_counter += 1
        binding_id = f"binding_{self._binding_counter}"
        
        binding = Binding(
            binding_id=binding_id,
            binding_type=binding_type,
            target_id=target_id,
            agent_id=agent_id,
            priority=priority,
            metadata=metadata or {}
        )
        
        self._router.add_binding(binding)
        return binding
    
    def delete_binding(self, binding_id: str) -> bool:
        """删除绑定"""
        return self._router.remove_binding(binding_id)
    
    def route_message(
        self,
        peer_id: Optional[str] = None,
        guild_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        team_id: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> Optional[str]:
        """路由消息，返回目标 Agent ID"""
        match = self._router.route(
            peer_id=peer_id,
            guild_id=guild_id,
            channel_id=channel_id,
            team_id=team_id,
            account_id=account_id
        )
        
        return match.binding.agent_id if match else None
    
    def get_router(self) -> BindingRouter:
        """获取路由器"""
        return self._router


_binding_manager: Optional[BindingManager] = None


def get_binding_manager() -> BindingManager:
    """获取绑定管理器单例"""
    global _binding_manager
    if _binding_manager is None:
        _binding_manager = BindingManager()
    return _binding_manager

"""
Agent 隔离管理模块
"""
import os
import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading
import shutil

logger = logging.getLogger(__name__)


class IsolationLevel(str, Enum):
    """隔离级别"""
    NONE = "none"
    BASIC = "basic"
    STANDARD = "standard"
    STRICT = "strict"


@dataclass
class AgentWorkspace:
    """Agent 工作空间"""
    agent_id: str
    workspace_path: Path
    created_at: datetime = field(default_factory=datetime.now)
    isolation_level: IsolationLevel = IsolationLevel.STANDARD
    allowed_paths: Set[str] = field(default_factory=set)
    denied_paths: Set[str] = field(default_factory=set)
    max_storage_mb: int = 100
    current_storage_mb: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSession:
    """Agent 会话"""
    session_id: str
    agent_id: str
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    state: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)


class WorkspaceManager:
    """工作空间管理器"""
    
    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path("workspaces")
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._workspaces: Dict[str, AgentWorkspace] = {}
        self._lock = threading.Lock()
    
    def create_workspace(
        self,
        agent_id: str,
        isolation_level: IsolationLevel = IsolationLevel.STANDARD,
        max_storage_mb: int = 100
    ) -> AgentWorkspace:
        """创建工作空间"""
        with self._lock:
            if agent_id in self._workspaces:
                return self._workspaces[agent_id]
            
            workspace_path = self.base_path / agent_id
            workspace_path.mkdir(parents=True, exist_ok=True)
            
            workspace = AgentWorkspace(
                agent_id=agent_id,
                workspace_path=workspace_path,
                isolation_level=isolation_level,
                max_storage_mb=max_storage_mb
            )
            
            workspace.allowed_paths.add(str(workspace_path))
            
            self._workspaces[agent_id] = workspace
            self._save_workspace_config(workspace)
            
            logger.info(f"创建工作空间: {agent_id}")
            return workspace
    
    def get_workspace(self, agent_id: str) -> Optional[AgentWorkspace]:
        """获取工作空间"""
        return self._workspaces.get(agent_id)
    
    def delete_workspace(self, agent_id: str) -> bool:
        """删除工作空间"""
        with self._lock:
            workspace = self._workspaces.get(agent_id)
            if not workspace:
                return False
            
            try:
                if workspace.workspace_path.exists():
                    shutil.rmtree(workspace.workspace_path)
                
                del self._workspaces[agent_id]
                logger.info(f"删除工作空间: {agent_id}")
                return True
            except Exception as e:
                logger.error(f"删除工作空间失败: {e}")
                return False
    
    def _save_workspace_config(self, workspace: AgentWorkspace) -> None:
        """保存工作空间配置"""
        config_path = workspace.workspace_path / ".workspace.json"
        config = {
            "agent_id": workspace.agent_id,
            "isolation_level": workspace.isolation_level.value,
            "allowed_paths": list(workspace.allowed_paths),
            "denied_paths": list(workspace.denied_paths),
            "max_storage_mb": workspace.max_storage_mb,
            "created_at": workspace.created_at.isoformat(),
        }
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    
    def list_workspaces(self) -> List[AgentWorkspace]:
        """列出所有工作空间"""
        return list(self._workspaces.values())


class SessionManager:
    """会话管理器"""
    
    def __init__(self):
        self._sessions: Dict[str, AgentSession] = {}
        self._agent_sessions: Dict[str, Set[str]] = {}
        self._lock = threading.Lock()
    
    def create_session(self, agent_id: str) -> AgentSession:
        """创建会话"""
        with self._lock:
            session_id = f"{agent_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            
            session = AgentSession(
                session_id=session_id,
                agent_id=agent_id
            )
            
            self._sessions[session_id] = session
            
            if agent_id not in self._agent_sessions:
                self._agent_sessions[agent_id] = set()
            self._agent_sessions[agent_id].add(session_id)
            
            logger.info(f"创建会话: {session_id}")
            return session
    
    def get_session(self, session_id: str) -> Optional[AgentSession]:
        """获取会话"""
        return self._sessions.get(session_id)
    
    def get_agent_sessions(self, agent_id: str) -> List[AgentSession]:
        """获取 Agent 的所有会话"""
        session_ids = self._agent_sessions.get(agent_id, set())
        return [self._sessions[sid] for sid in session_ids if sid in self._sessions]
    
    def update_session_state(self, session_id: str, state: Dict[str, Any]) -> bool:
        """更新会话状态"""
        session = self._sessions.get(session_id)
        if not session:
            return False
        
        session.state.update(state)
        session.last_active = datetime.now()
        return True
    
    def add_to_history(self, session_id: str, entry: Dict[str, Any]) -> bool:
        """添加历史记录"""
        session = self._sessions.get(session_id)
        if not session:
            return False
        
        session.history.append({
            **entry,
            "timestamp": datetime.now().isoformat()
        })
        session.last_active = datetime.now()
        return True
    
    def close_session(self, session_id: str) -> bool:
        """关闭会话"""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            
            agent_id = session.agent_id
            if agent_id in self._agent_sessions:
                self._agent_sessions[agent_id].discard(session_id)
            
            del self._sessions[session_id]
            logger.info(f"关闭会话: {session_id}")
            return True


class PathAccessController:
    """路径访问控制器"""
    
    def __init__(self, workspace_manager: WorkspaceManager):
        self.workspace_manager = workspace_manager
    
    def check_access(
        self,
        agent_id: str,
        path: str,
        operation: str = "read"
    ) -> bool:
        """检查路径访问权限"""
        workspace = self.workspace_manager.get_workspace(agent_id)
        if not workspace:
            return False
        
        resolved_path = str(Path(path).resolve())
        
        for denied in workspace.denied_paths:
            if resolved_path.startswith(denied):
                return False
        
        for allowed in workspace.allowed_paths:
            if resolved_path.startswith(allowed):
                return True
        
        return False
    
    def grant_access(self, agent_id: str, path: str) -> bool:
        """授予路径访问权限"""
        workspace = self.workspace_manager.get_workspace(agent_id)
        if not workspace:
            return False
        
        resolved_path = str(Path(path).resolve())
        workspace.allowed_paths.add(resolved_path)
        return True
    
    def revoke_access(self, agent_id: str, path: str) -> bool:
        """撤销路径访问权限"""
        workspace = self.workspace_manager.get_workspace(agent_id)
        if not workspace:
            return False
        
        resolved_path = str(Path(path).resolve())
        workspace.allowed_paths.discard(resolved_path)
        workspace.denied_paths.add(resolved_path)
        return True


class AgentIsolationManager:
    """Agent 隔离管理器"""
    
    def __init__(self, base_path: Optional[Path] = None):
        self.workspace_manager = WorkspaceManager(base_path)
        self.session_manager = SessionManager()
        self.access_controller = PathAccessController(self.workspace_manager)
    
    def create_agent(
        self,
        agent_id: str,
        isolation_level: IsolationLevel = IsolationLevel.STANDARD,
        max_storage_mb: int = 100
    ) -> AgentWorkspace:
        """创建隔离的 Agent 环境"""
        workspace = self.workspace_manager.create_workspace(
            agent_id=agent_id,
            isolation_level=isolation_level,
            max_storage_mb=max_storage_mb
        )
        
        return workspace
    
    def create_session(self, agent_id: str) -> AgentSession:
        """为 Agent 创建会话"""
        return self.session_manager.create_session(agent_id)
    
    def check_file_access(
        self,
        agent_id: str,
        file_path: str,
        operation: str = "read"
    ) -> bool:
        """检查文件访问权限"""
        return self.access_controller.check_access(agent_id, file_path, operation)
    
    def get_agent_workspace(self, agent_id: str) -> Optional[AgentWorkspace]:
        """获取 Agent 工作空间"""
        return self.workspace_manager.get_workspace(agent_id)
    
    def get_agent_sessions(self, agent_id: str) -> List[AgentSession]:
        """获取 Agent 的所有会话"""
        return self.session_manager.get_agent_sessions(agent_id)
    
    def delete_agent(self, agent_id: str) -> bool:
        """删除 Agent 及其所有资源"""
        sessions = self.session_manager.get_agent_sessions(agent_id)
        for session in sessions:
            self.session_manager.close_session(session.session_id)
        
        return self.workspace_manager.delete_workspace(agent_id)
    
    def get_storage_usage(self, agent_id: str) -> Dict[str, Any]:
        """获取存储使用情况"""
        workspace = self.workspace_manager.get_workspace(agent_id)
        if not workspace:
            return {"error": "Agent not found"}
        
        total_size = 0
        file_count = 0
        
        for root, dirs, files in os.walk(workspace.workspace_path):
            for file in files:
                file_path = Path(root) / file
                try:
                    total_size += file_path.stat().st_size
                    file_count += 1
                except Exception:
                    pass
        
        return {
            "agent_id": agent_id,
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "file_count": file_count,
            "max_storage_mb": workspace.max_storage_mb,
            "usage_percent": (total_size / (1024 * 1024)) / workspace.max_storage_mb * 100
        }


_isolation_manager: Optional[AgentIsolationManager] = None


def get_isolation_manager() -> AgentIsolationManager:
    """获取隔离管理器单例"""
    global _isolation_manager
    if _isolation_manager is None:
        _isolation_manager = AgentIsolationManager()
    return _isolation_manager

"""
Gateway agent isolation manager.
"""
import json
import os
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger_name = __name__


class IsolationLevel(str, Enum):
    NONE = "none"
    BASIC = "basic"
    STANDARD = "standard"
    STRICT = "strict"


@dataclass
class AgentWorkspace:
    agent_id: str
    workspace_path: Path
    created_at: datetime = field(default_factory=datetime.now)
    isolation_level: IsolationLevel = IsolationLevel.STANDARD
    allowed_paths: set[str] = field(default_factory=set)
    denied_paths: set[str] = field(default_factory=set)
    max_storage_mb: int = 100
    current_storage_mb: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSession:
    session_id: str
    agent_id: str
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    state: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)


class WorkspaceManager:
    def __init__(self, base_path: Path | None = None):
        self.base_path = base_path or Path("workspaces")
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._workspaces: dict[str, AgentWorkspace] = {}
        self._lock = threading.Lock()

    def create_workspace(
        self,
        agent_id: str,
        isolation_level: IsolationLevel = IsolationLevel.STANDARD,
        max_storage_mb: int = 100,
        metadata: dict[str, Any] | None = None,
    ) -> AgentWorkspace:
        with self._lock:
            if agent_id in self._workspaces:
                return self._workspaces[agent_id]

            workspace_path = self.base_path / agent_id
            workspace_path.mkdir(parents=True, exist_ok=True)

            workspace = AgentWorkspace(
                agent_id=agent_id,
                workspace_path=workspace_path,
                isolation_level=isolation_level,
                max_storage_mb=max_storage_mb,
                metadata=metadata or {},
            )
            workspace.allowed_paths.add(str(workspace_path.resolve()))

            self._workspaces[agent_id] = workspace
            self._save_workspace_config(workspace)
            return workspace

    def get_workspace(self, agent_id: str) -> AgentWorkspace | None:
        return self._workspaces.get(agent_id)

    def delete_workspace(self, agent_id: str) -> bool:
        with self._lock:
            workspace = self._workspaces.get(agent_id)
            if not workspace:
                return False
            if workspace.workspace_path.exists():
                shutil.rmtree(workspace.workspace_path)
            del self._workspaces[agent_id]
            return True

    def _save_workspace_config(self, workspace: AgentWorkspace) -> None:
        config_path = workspace.workspace_path / ".workspace.json"
        config = {
            "agent_id": workspace.agent_id,
            "isolation_level": workspace.isolation_level.value,
            "allowed_paths": list(workspace.allowed_paths),
            "denied_paths": list(workspace.denied_paths),
            "max_storage_mb": workspace.max_storage_mb,
            "created_at": workspace.created_at.isoformat(),
            "metadata": workspace.metadata,
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def list_workspaces(self) -> list[AgentWorkspace]:
        return list(self._workspaces.values())


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, AgentSession] = {}
        self._agent_sessions: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    def create_session(self, agent_id: str) -> AgentSession:
        with self._lock:
            session_id = f"{agent_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            session = AgentSession(session_id=session_id, agent_id=agent_id)
            self._sessions[session_id] = session
            self._agent_sessions.setdefault(agent_id, set()).add(session_id)
            return session

    def get_agent_sessions(self, agent_id: str) -> list[AgentSession]:
        return [self._sessions[sid] for sid in self._agent_sessions.get(agent_id, set()) if sid in self._sessions]

    def update_session_state(self, session_id: str, state: dict[str, Any]) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.state.update(state)
        session.last_active = datetime.now()
        return True

    def get_session(self, session_id: str) -> AgentSession | None:
        return self._sessions.get(session_id)

    def close_session(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            self._agent_sessions.get(session.agent_id, set()).discard(session_id)
            del self._sessions[session_id]
            return True


class PathAccessController:
    def __init__(self, workspace_manager: WorkspaceManager):
        self.workspace_manager = workspace_manager

    def check_access(self, agent_id: str, path: str, operation: str = "read") -> bool:
        workspace = self.workspace_manager.get_workspace(agent_id)
        if not workspace:
            return False

        resolved = str(Path(path).resolve())
        for denied in workspace.denied_paths:
            if resolved.startswith(denied):
                return False
        return any(
            resolved.startswith(allowed) for allowed in workspace.allowed_paths
        )


class AgentIsolationManager:
    def __init__(self, base_path: Path | None = None, base_workspace_path: Path | None = None):
        actual_base = base_workspace_path or base_path
        self.workspace_manager = WorkspaceManager(actual_base)
        self.session_manager = SessionManager()
        self.access_controller = PathAccessController(self.workspace_manager)
        self._agent_config: dict[str, dict[str, Any]] = {}
        self._session_kv: dict[str, dict[str, Any]] = {}
        # Compatibility alias for legacy tests/callers.
        self._workspaces = self.workspace_manager._workspaces

    def create_agent(
        self,
        agent_id: str,
        isolation_level: IsolationLevel = IsolationLevel.STANDARD,
        max_storage_mb: int = 100,
        name: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> AgentWorkspace:
        workspace = self.workspace_manager.create_workspace(
            agent_id=agent_id,
            isolation_level=isolation_level,
            max_storage_mb=max_storage_mb,
            metadata={"name": name} if name else {},
        )
        self._agent_config[agent_id] = config or {}
        self._session_kv.setdefault(agent_id, {})

        if name is not None and config is None:
            return True
        return workspace

    def create_session(self, agent_id: str) -> AgentSession:
        return self.session_manager.create_session(agent_id)

    def check_file_access(self, agent_id: str, file_path: str, operation: str = "read") -> bool:
        return self.access_controller.check_access(agent_id, file_path, operation)

    def get_agent_workspace(self, agent_id: str) -> AgentWorkspace | None:
        return self.workspace_manager.get_workspace(agent_id)

    def get_workspace(self, agent_id: str) -> Path | None:
        workspace = self.get_agent_workspace(agent_id)
        return workspace.workspace_path if workspace else None

    def get_all_workspaces(self) -> list[AgentWorkspace]:
        return self.workspace_manager.list_workspaces()

    def get_agent_sessions(self, agent_id: str) -> list[AgentSession]:
        return self.session_manager.get_agent_sessions(agent_id)

    def delete_agent(self, agent_id: str) -> bool:
        for session in self.session_manager.get_agent_sessions(agent_id):
            self.session_manager.close_session(session.session_id)
        self._agent_config.pop(agent_id, None)
        self._session_kv.pop(agent_id, None)
        return self.workspace_manager.delete_workspace(agent_id)

    def get_storage_usage(self, agent_id: str) -> dict[str, Any]:
        workspace = self.workspace_manager.get_workspace(agent_id)
        if not workspace:
            return {"error": "Agent not found"}

        total_size = 0
        file_count = 0
        for root, _, files in os.walk(workspace.workspace_path):
            for file in files:
                path = Path(root) / file
                try:
                    total_size += path.stat().st_size
                    file_count += 1
                except Exception:
                    pass

        total_mb = total_size / (1024 * 1024)
        return {
            "agent_id": agent_id,
            "total_size_bytes": total_size,
            "total_size_mb": total_mb,
            "file_count": file_count,
            "max_storage_mb": workspace.max_storage_mb,
            "usage_percent": (total_mb / workspace.max_storage_mb * 100) if workspace.max_storage_mb else 0,
        }

    def get_config(self, agent_id: str) -> Any:
        config = self._agent_config.get(agent_id, {})

        class _Cfg:
            pass

        cfg = _Cfg()
        for k, v in config.items():
            setattr(cfg, k, v)
        return cfg

    def set_session_data(self, agent_id: str, key: str, value: Any) -> bool:
        if not self.workspace_manager.get_workspace(agent_id):
            return False
        self._session_kv.setdefault(agent_id, {})[key] = value
        return True

    def get_session_data(self, agent_id: str, key: str) -> Any:
        return self._session_kv.get(agent_id, {}).get(key)

    def check_capability(self, agent_id: str, capability: str) -> bool:
        config = self._agent_config.get(agent_id, {})
        allowed = config.get("allowed_capabilities", [])
        if not allowed:
            return False
        return capability in allowed

    def get_agent_stats(self, agent_id: str) -> dict[str, Any]:
        workspace = self.workspace_manager.get_workspace(agent_id)
        return {
            "agent_id": agent_id,
            "workspace_exists": bool(workspace and workspace.workspace_path.exists()),
            "sessions": len(self.session_manager.get_agent_sessions(agent_id)),
            "has_config": agent_id in self._agent_config,
        }


_isolation_manager: AgentIsolationManager | None = None


def get_isolation_manager() -> AgentIsolationManager:
    global _isolation_manager
    if _isolation_manager is None:
        _isolation_manager = AgentIsolationManager()
    return _isolation_manager

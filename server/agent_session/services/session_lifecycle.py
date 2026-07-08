from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_session.models import (
    AgentMemoryFileResponse,
    AgentSessionCreate,
    AgentSessionOverviewResponse,
    AgentSessionPreferences,
    AgentSessionPreferencesUpdate,
    AgentSessionResponse,
)
from agent_session.permission import default_deepagents_permission_metadata
from agent_session.runtime_policy import build_agent_runtime_policy
from agent_session.state import ensure_session_state
from core.config import settings
from security.encryption import secure_storage
from workspace.local_paths import get_allowed_workspace_roots

if TYPE_CHECKING:
    from agent_session.service import AgentSessionService

SAVED_CLOUD_PROVIDER_PRIORITY = ("deepseek", "openrouter", "openai")


class SessionLifecycleService:
    def __init__(self, service: AgentSessionService) -> None:
        self.service = service

    def _default_project_path(self) -> str:
        env_path = settings.agent_default_project_path
        if env_path:
            candidate = Path(env_path)
            if candidate.exists() and candidate.is_dir():
                return str(candidate.resolve())
        base_dir = settings.base_dir.resolve()
        workspace = base_dir.parent if base_dir.name == "server" else base_dir
        return str(workspace)

    def validate_project_path(self, project_path: str | None) -> str:
        if not project_path or not project_path.strip():
            return self._default_project_path()
        resolved = Path(project_path).expanduser().resolve()
        if not resolved.exists():
            raise ValueError("project_path does not exist")
        if not resolved.is_dir():
            raise ValueError("project_path must be a directory")
        default_root = Path(self._default_project_path()).resolve()
        allowed_roots = get_allowed_workspace_roots({default_root, settings.base_dir.resolve(), Path.cwd().resolve()})

        if not any(resolved == allowed or resolved.is_relative_to(allowed) for allowed in allowed_roots):
            allowed = ", ".join(sorted(str(path) for path in allowed_roots))
            raise ValueError(f"project_path must be inside the workspace. Allowed roots: {allowed}")
        return str(resolved)

    def _validate_project_path(self, project_path: str | None) -> str:
        return self.validate_project_path(project_path)

    def create_session(self, request: AgentSessionCreate, user_id: str | None = None) -> AgentSessionResponse:
        project_path = self._validate_project_path(request.project_path)
        agent = self._require_direct_agent(request.agent_id)
        provider, model, model_configured = self.resolve_session_model_availability(agent.id, request.provider, request.model)
        enabled_skill_sources = self._normalize_enabled_skill_sources(request.enabled_skill_sources)
        metadata: dict[str, Any] = {
            "autonomy_mode": request.autonomy_mode or "safe_auto",
            **default_deepagents_permission_metadata(),
            "enabled_skill_sources": enabled_skill_sources,
            "model_configured": model_configured,
        }
        if user_id:
            metadata["user_id"] = user_id
        session = self.service.repository.create_session(
            {
                "chat_session_id": request.chat_session_id,
                "agent_id": agent.id,
                "title": request.title or "Agent Session",
                "project_path": project_path,
                "provider": provider,
                "model": model,
                "metadata": metadata,
            }
        )
        session["parts"] = []
        return AgentSessionResponse(**self.service.event_service._attach_recovery_diagnostics(session))

    def _require_direct_agent(self, agent_id: str):
        agent = self.service.agent_registry.get(agent_id)
        if agent is None:
            raise ValueError(f"Unknown agent id: {agent_id}")
        if not agent.can_start_directly:
            raise ValueError(f"Agent '{agent_id}' cannot be started directly in mode '{agent.mode}'")
        return agent

    def _resolve_session_model_defaults(self, agent_id: str, provider: str | None, model: str | None) -> tuple[str | None, str | None]:
        if provider and model:
            return provider, model
        if provider:
            saved_provider, saved_model = self._saved_cloud_provider_model(provider)
            if saved_provider and saved_model:
                return provider, model or saved_model
        if not provider and not model:
            saved_provider, saved_model = self._saved_cloud_provider_model()
            if saved_provider and saved_model:
                return saved_provider, saved_model
        agent = self.service.agent_registry.get(agent_id)
        return provider or (agent.default_provider if agent else None), model or (agent.default_model if agent else None)

    def resolve_session_model_availability(
        self,
        agent_id: str,
        provider: str | None,
        model: str | None,
    ) -> tuple[str | None, str | None, bool]:
        resolved_provider, resolved_model = self._resolve_session_model_defaults(agent_id, provider, model)
        configured = bool(self.service.model_call is not None) or self._has_saved_cloud_model(resolved_provider, resolved_model)
        return resolved_provider, resolved_model, configured

    def _saved_cloud_provider_model(self, provider: str | None = None) -> tuple[str | None, str | None]:
        providers = [provider] if provider else list(SAVED_CLOUD_PROVIDER_PRIORITY)
        if not provider:
            index = secure_storage.get("cloud_custom_provider_index") or {}
            if isinstance(index, dict):
                for candidate in index.get("providers") or []:
                    provider_id = str(candidate or "").strip()
                    if provider_id and provider_id not in providers:
                        providers.append(provider_id)

        for provider_id in providers:
            if not provider_id:
                continue
            key_data = secure_storage.get(f"cloud_{provider_id}_key") or {}
            if not isinstance(key_data, dict) or not key_data.get("api_key"):
                continue
            model = str(key_data.get("default_model") or "").strip()
            if not model:
                models = key_data.get("models") or []
                if models:
                    model = str(models[0] or "").strip()
            if model:
                return str(provider_id), model
        return None, None

    def _has_saved_cloud_model(self, provider: str | None, model: str | None) -> bool:
        if not provider or not model:
            return False
        key_data = secure_storage.get(f"cloud_{provider}_key") or {}
        if not isinstance(key_data, dict) or not key_data.get("api_key"):
            return False
        saved_model = str(key_data.get("default_model") or "").strip()
        models = [str(item or "").strip() for item in key_data.get("models") or []]
        return not saved_model or saved_model == model or model in models

    def get_session(self, session_id: str) -> AgentSessionResponse:
        session = self.service.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        session["parts"] = self.service.repository.list_parts(session_id)
        return AgentSessionResponse(**self.service.event_service._attach_recovery_diagnostics(session))

    def update_session_preferences(
        self,
        session_id: str,
        request: AgentSessionPreferencesUpdate,
    ) -> AgentSessionResponse:
        session = self.service.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        preferences = self._session_preferences(metadata).model_dump()
        if request.display_title is not None:
            display_title = request.display_title.strip()
            if not display_title:
                preferences["display_title"] = None
            else:
                preferences["display_title"] = display_title[:80]
        if request.pinned is not None:
            preferences["pinned"] = bool(request.pinned)
        if request.archived is not None:
            preferences["archived"] = bool(request.archived)
        preferences["updated_at"] = datetime.now().isoformat()
        metadata["ui_preferences"] = preferences
        updated = self.service.repository.update_session(session_id, metadata=metadata)
        updated["parts"] = self.service.repository.list_parts(session_id)
        return AgentSessionResponse(**self.service.event_service._attach_recovery_diagnostics(updated))

    def list_sessions(self, user_id: str, include_all: bool = False, limit: int = 100) -> list[AgentSessionResponse]:
        sessions = self.service.repository.list_sessions(limit)
        visible = []
        for session in sessions:
            owner = str((session.get("metadata") or {}).get("user_id") or "").strip()
            if include_all or not owner or owner == user_id:
                session["parts"] = []
                visible.append(AgentSessionResponse(**self.service.event_service._attach_recovery_diagnostics(session)))
        return visible

    def get_overview(self, session_id: str) -> AgentSessionOverviewResponse:
        session = self.get_session(session_id)
        metadata = dict(session.metadata or {})
        diagnostics = dict(metadata.get("diagnostics") or {})
        return AgentSessionOverviewResponse(
            session=session,
            recent_events=list(diagnostics.get("recent_events") or []),
            artifacts=self.service.event_service._build_artifacts(session.parts),
            diagnostics=diagnostics,
        )

    def get_workspace(self, session_id: str) -> Any:
        return self.service.workspace_view_service.get_workspace(session_id)

    def list_memory_files(self, session_id: str) -> list[AgentMemoryFileResponse]:
        session = self.get_session(session_id)
        from memory.memory_service import get_memory_service

        service = get_memory_service()
        namespaces = self._resource_profile_for_session(session).memory.get("namespaces") or []
        files = []
        for namespace in namespaces:
            if not isinstance(namespace, dict):
                continue
            files.extend(service.list_files(str(namespace.get("scope") or ""), str(namespace.get("namespace") or "")))
        return [AgentMemoryFileResponse(**file) for file in files]

    def read_memory_file(self, session_id: str, path: str) -> AgentMemoryFileResponse:
        session = self.get_session(session_id)
        scope, namespace, relative_path = self._resolve_memory_file_path(
            path,
            resource_profile=self._resource_profile_for_session(session).model_dump(),
        )
        from memory.memory_service import get_memory_service

        try:
            file = get_memory_service().store.read_file_by_path(scope, namespace, relative_path)
        except (FileNotFoundError, ValueError) as exc:
            raise ValueError("Memory file not found") from exc
        return AgentMemoryFileResponse(**file)

    def _resource_profile_for_session(self, session: AgentSessionResponse):
        agent_id = str(session.agent_id or "build")
        agent = self.service.agent_registry.get(agent_id)
        policy = build_agent_runtime_policy(
            agent=agent,
            agent_id=agent_id,
            project_path=session.project_path or ".",
            metadata=dict(session.metadata or {}),
            provider=session.provider,
            model=session.model,
            runtime_kind="agent_session",
            thread_id=str((session.metadata or {}).get("deepagents_thread_id") or f"agent_session:{session.id}:deepagents"),
            checkpointer=True,
            agent_registry=self.service.agent_registry,
        )
        return policy.resource_profile

    @staticmethod
    def _session_preferences(metadata: dict[str, Any]) -> AgentSessionPreferences:
        raw = metadata.get("ui_preferences")
        raw = raw if isinstance(raw, dict) else {}
        display_title = raw.get("display_title")
        display_title = display_title.strip()[:80] if isinstance(display_title, str) and display_title.strip() else None
        return AgentSessionPreferences(
            display_title=display_title,
            pinned=bool(raw.get("pinned")),
            archived=bool(raw.get("archived")),
            updated_at=str(raw.get("updated_at") or "") or None,
        )

    @staticmethod
    def _normalize_enabled_skill_sources(enabled_skill_sources: list[str] | None) -> list[str] | None:
        if enabled_skill_sources is None:
            return None
        return [source for source in (str(item).strip() for item in enabled_skill_sources) if source]

    @staticmethod
    def _resolve_memory_file_path(
        path: str,
        *,
        resource_profile: dict[str, Any],
    ) -> tuple[str, str, str]:
        normalized = path.strip().replace("\\", "/")
        for namespace in dict(resource_profile.get("memory") or {}).get("namespaces") or []:
            if not isinstance(namespace, dict):
                continue
            mount = str(namespace.get("mount") or "").rstrip("/") + "/"
            if normalized.startswith(mount):
                relative = normalized.removeprefix(mount).lstrip("/")
                return (
                    str(namespace.get("scope") or ""),
                    str(namespace.get("namespace") or ""),
                    SessionLifecycleService._validate_memory_relative_path(relative),
                )
        raise ValueError("Unsupported memory path")

    @staticmethod
    def _validate_memory_relative_path(relative_path: str) -> str:
        candidate = relative_path.strip().replace("\\", "/")
        path = Path(candidate)
        if not candidate or path.is_absolute() or ".." in path.parts or not candidate.endswith(".md"):
            raise ValueError("Unsupported memory path")
        return candidate

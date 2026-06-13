from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .deepagents_compat import patch_torch_pytree_for_transformers
from .runtime_contract import AgentRuntimeContract


def ensure_deepagents_available() -> None:
    patch_torch_pytree_for_transformers()
    try:
        import deepagents  # noqa: F401
    except Exception as exc:  # pragma: no cover - depends on optional runtime dependency
        from .deepagents_runtime import DeepAgentsUnavailable

        raise DeepAgentsUnavailable(f"DeepAgents is not installed or failed to import: {exc}") from exc


class DeepAgentsRuntimeFactory:
    """Single bridge from Finetune Platform runtime contracts to DeepAgents."""

    def build(self, contract: AgentRuntimeContract) -> Any:
        patch_torch_pytree_for_transformers()
        from deepagents import create_deep_agent

        return create_deep_agent(
            model=contract.model,
            tools=contract.tools or [],
            system_prompt=contract.system_prompt,
            middleware=contract.middleware or (),
            backend=self._backend_for(contract),
            memory=contract.memory,
            skills=contract.skills or [],
            subagents=contract.subagents or [],
            permissions=contract.permissions,
            interrupt_on=contract.interrupt_on,
            checkpointer=contract.checkpointer,
        )

    def _backend_for(self, contract: AgentRuntimeContract) -> Any:
        if contract.backend_mode == "project_chat_readonly":
            return self._readonly_project_backend(contract.project_path)

        from .runtime import build_deepagents_backend

        return build_deepagents_backend(
            contract.project_path,
            user_id=contract.user_id,
            agent_id=contract.agent_id,
            org_id=contract.org_id,
            enabled_skill_sources=contract.enabled_skill_sources,
        )

    @staticmethod
    def _readonly_project_backend(project_path: str) -> Any:
        from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend

        return CompositeBackend(
            default=StateBackend(),
            routes={
                "/workspace/": FilesystemBackend(root_dir=str(Path(project_path).resolve()), virtual_mode=True),
            },
        )


def build_deep_agent_from_contract(contract: AgentRuntimeContract) -> Any:
    return DeepAgentsRuntimeFactory().build(contract)


def deepagents_shell_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "TEMP", "TMP"}
    }


__all__ = ["DeepAgentsRuntimeFactory", "build_deep_agent_from_contract", "deepagents_shell_env", "ensure_deepagents_available"]

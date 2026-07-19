from __future__ import annotations

import os
import sys
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

        # Scheme A: apply platform token eviction defaults before graph assembly.
        try:
            from agent_session.tool_result_limits import apply_deepagents_tool_eviction_defaults

            apply_deepagents_tool_eviction_defaults()
        except Exception:
            pass

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
            controlled_execute=getattr(contract, "orchestration_mode", "legacy") == "controlled",
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
    """Build the environment for DeepAgents ``execute`` subprocesses.

    Uses an explicit allowlist (with ``inherit_env=False`` upstream) rather than
    full ``os.environ`` inheritance: an auditable, production-safe subset that
    still lets toolchains (npm, git, pip, conda) find their global config and
    user-site packages.

    The allowlist is platform-aware:
    - Windows: includes ``USERPROFILE``/``APPDATA``/``HOME`` etc. so that
      ``~/.npmrc``, ``~/.gitconfig``, pip cache, and Python user-site resolve
      correctly under ``cmd.exe``. Without these, tools silently fall back to
      defaults or fail -- a common source of "passed locally but failed in
      execute" false-negatives.
    - POSIX: a leaner set (``HOME``/``PATH``/locale).
    """
    allowed = _WINDOWS_SHELL_ENV_KEYS if sys.platform == "win32" else _POSIX_SHELL_ENV_KEYS
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


# Windows: system dirs + user dirs + venv + locale.
# ``USERPROFILE``/``APPDATA``/``LOCALAPPDATA``/``HOME`` are the key additions
# over the old 8-variable allowlist -- they let npm/git/pip/Python find global
# config and user-site packages. ``PROGRAMFILES`` lets ``%PROGRAMFILES%``
# lookups in commands resolve. None of these carry secrets.
_WINDOWS_SHELL_ENV_KEYS: frozenset[str] = frozenset(
    {
        # System / shell resolution (original 8)
        "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE",
        "COMSPEC", "TEMP", "TMP",
        # User directory -- lets npm/git/pip/conda find global config & caches
        "USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA",
        "HOMEDRIVE", "HOMEPATH", "USERNAME", "PROGRAMDATA",
        "PROGRAMFILES", "PROGRAMFILES(X86)",
        # Virtual environment identity
        "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "CONDA_PREFIX",
        # Language runtime defaults
        "PYTHONPATH", "PYTHONIOENCODING", "LANG", "LC_ALL",
    }
)

# POSIX: lean set. HOME covers ~ expansion; the rest are locale/venv.
_POSIX_SHELL_ENV_KEYS: frozenset[str] = frozenset(
    {
        "PATH", "HOME", "TMPDIR", "LANG", "LC_ALL",
        "VIRTUAL_ENV", "CONDA_PREFIX", "PYTHONPATH", "PYTHONIOENCODING",
    }
)


__all__ = [
    "DeepAgentsRuntimeFactory",
    "build_deep_agent_from_contract",
    "deepagents_shell_env",
    "ensure_deepagents_available",
]

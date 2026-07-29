"""Phase-3: secret redaction, total token budget, scope hard-gate, active context refresh."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from agent_session.task_scope import path_in_scope
from agent_session.trajectory import (
    TrajectoryGuardMiddleware,
    TrajectoryStateStore,
    _workspace_rel_for_refresh,
)
from context.deepagents import (
    MAX_TOTAL_CONTEXT_FILE_TOKENS,
    _apply_total_token_budget,
    build_deepagents_context_pack,
)
from context.redaction import REDACTED, redact_secrets


def test_redact_secrets_masks_keys_and_passwords():
    text = (
        "api_key=sk-abcdefghijklmnopqrstuvwxyz012345\n"
        "password: supersecret123\n"
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz\n"
        "postgres://user:hunter2@localhost/db\n"
        "normal code path remains C:/repo/server/main.py\n"
    )
    out = redact_secrets(text)
    assert "sk-abcdefghijklmnopqrstuvwxyz012345" not in out
    assert "supersecret123" not in out
    assert "hunter2" not in out
    assert REDACTED in out
    assert "C:/repo/server/main.py" in out


def test_apply_total_token_budget_keeps_task_and_drops_low_priority():
    files = {
        "/context/task.md": "task " * 20,
        "/context/retrieval/workspace-inventory.md": "inv " * 5000,
        "/context/retrieval/related.md": "rel " * 5000,
        "/context/editor/active-file.md": "active " * 50,
    }
    kept, dropped = _apply_total_token_budget(files, max_tokens=200)
    assert "/context/task.md" in kept
    assert dropped
    assert "/context/retrieval/workspace-inventory.md" in dropped or "/context/retrieval/related.md" in dropped
    total = sum(len(v.split()) for v in kept.values())  # coarse check not empty
    assert total > 0


@pytest.mark.asyncio
async def test_context_pack_redacts_secrets_and_drops_aliases():
    pack = await build_deepagents_context_pack(
        goal="fix with api_key=sk-abcdefghijklmnopqrstuvwxyz012345",
        active_context={
            "file_path": "server/config.py",
            "selection": {"text": "password = 'hunter2-not-for-prompt'\n"},
        },
        explicit_context=[],
        project_path=None,
        session_metadata={
            "context_refresh": {
                "changed_files": ["server/config.py"],
                "recent_failures": [{"tool": "execute", "path": "server/config.py", "reason": "exit 1"}],
            }
        },
    )
    listed = {item["path"] for item in pack.metadata.get("files") or []}
    # Canonical listing excludes alias bloat; injection may still carry VFS aliases.
    assert "/task.md" not in listed
    assert "/active-file.md" not in listed
    assert "/context/editor/active-file.md" in pack.files
    active = pack.files["/context/editor/active-file.md"]["content"]
    assert "hunter2-not-for-prompt" not in active
    assert REDACTED in active or "REDACTED" in active
    assert "sk-abcdefghijklmnopqrstuvwxyz012345" not in pack.prompt
    assert "Recently modified" in pack.prompt or "recently modified" in pack.prompt.lower() or "server/config.py" in pack.prompt
    assert pack.metadata.get("secret_redaction", {}).get("applied") is True
    assert pack.metadata.get("max_total_context_file_tokens") == MAX_TOTAL_CONTEXT_FILE_TOKENS
    assert pack.metadata.get("virtual_file_count") == len(listed)
    assert pack.metadata.get("injected_file_count", 0) >= pack.metadata.get("virtual_file_count", 0)


def test_path_in_scope_hard_gate_semantics():
    scope = {"paths": ["server/agent_session"]}
    assert path_in_scope("server/agent_session/service.py", scope) is True
    assert path_in_scope("server/other/x.py", scope) is False
    assert path_in_scope("client/src/App.tsx", scope) is False


def test_scope_write_block_message(tmp_path: Path):
    class FakeRepo:
        def get_session(self, _id):
            return {
                "metadata": {
                    "task_scope": {"paths": ["allowed"], "notes": ""},
                }
            }

        def update_session(self, *_a, **_k):
            return None

        def add_event(self, *_a, **_k):
            return {}

        def add_part(self, *_a, **_k):
            return {"id": "part_block", "type": "error", "status": "blocked", "content": "blocked"}

        def list_parts(self, *_a, **_k):
            return []

    mw = TrajectoryGuardMiddleware(
        repository=FakeRepo(),
        notify_event=lambda *_a, **_k: None,
        session_id="sess",
        project_path=str(tmp_path),
        policy={},
    )
    blocked = mw._check_scope_write("/workspace/outside/file.py")
    assert blocked is not None
    content = str(getattr(blocked, "content", None) or blocked)
    assert "scope" in content.lower() or "范围" in content


def test_workspace_rel_for_refresh():
    assert _workspace_rel_for_refresh("/workspace/server/a.py") == "server/a.py"
    assert _workspace_rel_for_refresh("server/a.py") == "server/a.py"


def test_context_scan_rejects_out_of_scope_path(tmp_path: Path):
    """C-2 回归：/context 扫描端点必须拒绝允许根之外的任意路径（防 LFI/路径遍历）。"""
    from fastapi import HTTPException

    from api.context import _resolve_project_path

    class _Req:
        def __init__(self, path: str):
            self.path = path
            self.project_path = None

    # 允许根内的路径（仓库根/cwd）应通过并返回解析后绝对路径
    resolved = _resolve_project_path(_Req(str(Path.cwd())))
    assert resolved

    # 允许根之外的临时目录应被拒绝（403）
    with pytest.raises(HTTPException) as exc:
        _resolve_project_path(_Req(str(tmp_path)))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_context_scan_error_does_not_leak_exception(caplog):
    """扫描异常时响应体不得回传原始异常字符串，原始异常仅留服务端 error 日志。"""
    from api.context import ScanRequest, scan_project

    class _FailingService:
        def scan_project(self, _path):
            raise RuntimeError("secret-internal-detail-XYZ")

    with caplog.at_level(logging.ERROR, logger="api.context"):
        resp = await scan_project(ScanRequest(path=str(Path.cwd())), service=_FailingService())

    assert resp.success is False
    assert resp.message
    assert "secret-internal-detail-XYZ" not in resp.message
    # 原始异常保留在服务端日志中，便于排查
    assert any("secret-internal-detail-XYZ" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_context_scan_path_not_found_returns_generic_message():
    """FileNotFoundError 分支也不得回传内部路径细节。"""
    from api.context import ScanRequest, scan_project

    class _MissingService:
        def scan_project(self, _path):
            raise FileNotFoundError("C:/secret/internal/location")

    resp = await scan_project(ScanRequest(path=str(Path.cwd())), service=_MissingService())
    assert resp.success is False
    assert "C:/secret/internal/location" not in resp.message
    assert resp.message == "project path not found"


@pytest.mark.asyncio
async def test_context_index_error_does_not_leak_exception(caplog):
    """索引异常时响应体不得回传原始异常字符串。"""
    from api.context import IndexRequest, index_project

    class _FailingService:
        def index_project(self, project_path, force_reindex=False):
            raise RuntimeError("secret-internal-detail-XYZ")

    with caplog.at_level(logging.ERROR, logger="api.context"):
        resp = await index_project(IndexRequest(path=str(Path.cwd())), service=_FailingService())

    assert resp.success is False
    assert resp.message
    assert "secret-internal-detail-XYZ" not in resp.message
    assert any("secret-internal-detail-XYZ" in r.getMessage() for r in caplog.records)

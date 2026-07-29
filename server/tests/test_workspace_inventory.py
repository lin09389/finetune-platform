"""Phase B1: lightweight workspace inventory for Agent kickoff."""
from __future__ import annotations

from pathlib import Path

import pytest

from context.deepagents import build_deepagents_context_pack
from context.pack import ContextBudget, ContextPack, ContextSource
from context.workspace_inventory import build_workspace_inventory, extract_goal_tokens


def test_extract_goal_tokens_finds_paths_and_identifiers():
    tokens = extract_goal_tokens("Fix off-by-one in src/counter.py validate_count function")
    joined = " ".join(tokens).lower()
    assert "counter" in joined or "src/counter.py" in joined
    assert "validate" in joined or "validate_count" in joined


def test_build_workspace_inventory_ranks_keyword_files(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "counter.py").write_text("def validate_count(n):\n    return n\n", encoding="utf-8")
    (tmp_path / "src" / "cli.py").write_text("print('cli')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "index.js").write_text("module.exports=1\n", encoding="utf-8")

    inv = build_workspace_inventory(
        tmp_path,
        "fix validate_count off-by-one in counter.py",
    )
    assert inv["status"] == "ok"
    assert inv["scanned_files"] >= 2
    reads = inv["recommended_reads"]
    assert any("counter" in p for p in reads)
    assert all("node_modules" not in p for p in inv["tree"])
    assert "Workspace Inventory" in inv["markdown"]
    assert "/workspace/" in inv["markdown"]


def test_build_workspace_inventory_respects_task_scope(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("a=1\n", encoding="utf-8")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "b.py").write_text("b=1\n", encoding="utf-8")

    inv = build_workspace_inventory(
        tmp_path,
        "update a.py and b.py helpers",
        task_scope={"paths": ["src"], "notes": None},
    )
    assert inv["status"] == "ok"
    assert inv["scoped"] is True
    assert all(p == "src" or p.startswith("src/") for p in inv["tree"] if not p.endswith("/"))
    assert all(not p.startswith("other/") for p in inv["recommended_reads"])


@pytest.mark.asyncio
async def test_context_pack_injects_inventory_when_project_retrieval_empty(tmp_path: Path, monkeypatch):
    (tmp_path / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    (tmp_path / "util.py").write_text("def helper():\n    return 2\n", encoding="utf-8")

    async def fake_retrieval(_goal, _project_path, **_kwargs):
        pack = ContextPack(
            query="fix app.py helper",
            sources=[
                ContextSource(id="memory:1", kind="memory", content="prefer concise", score=0.5, tokens=4),
            ],
            context_text="memory only",
            budget=ContextBudget(max_tokens=3200, used_tokens=4),
        )
        return pack, {
            "status": "empty",
            "reason": "no_project_sources",
            "project_source_count": 0,
            "total_sources": 1,
            "warnings": [],
        }

    monkeypatch.setattr("context.deepagents._build_retrieval_pack", fake_retrieval)

    pack = await build_deepagents_context_pack(
        goal="fix helper bug in app.py",
        active_context=None,
        explicit_context=[],
        project_path=str(tmp_path),
    )

    assert "/context/retrieval/workspace-inventory.md" in pack.files
    inventory_md = pack.files["/context/retrieval/workspace-inventory.md"]["content"]
    assert "app.py" in inventory_md
    assert pack.metadata["workspace_inventory"]["status"] == "ok"
    assert pack.metadata["project_retrieval"]["status"] == "empty"
    assert pack.metadata["project_retrieval"]["project_source_count"] == 0
    assert "Workspace context (B1)" in pack.prompt
    assert "project_retrieval" in pack.prompt
    assert "/workspace/app.py" in pack.prompt or "app.py" in pack.prompt


@pytest.mark.asyncio
async def test_context_pack_records_project_retrieval_ok(monkeypatch, tmp_path: Path):
    (tmp_path / "svc.py").write_text("x=1\n", encoding="utf-8")

    async def fake_retrieval(_goal, _project_path, **_kwargs):
        pack = ContextPack(
            query="explain svc",
            sources=[
                ContextSource(
                    id="project:1",
                    kind="project",
                    content="svc.py handles requests",
                    score=0.9,
                    tokens=8,
                    metadata={"path": "svc.py"},
                ),
            ],
            context_text="svc",
            budget=ContextBudget(max_tokens=3200, used_tokens=8),
        )
        return pack, {
            "status": "ok",
            "reason": None,
            "project_source_count": 1,
            "total_sources": 1,
            "warnings": [],
        }

    monkeypatch.setattr("context.deepagents._build_retrieval_pack", fake_retrieval)
    pack = await build_deepagents_context_pack(
        goal="explain svc.py",
        active_context=None,
        explicit_context=[],
        project_path=str(tmp_path),
    )
    assert pack.metadata["project_retrieval"]["status"] == "ok"
    assert pack.metadata["project_retrieval"]["project_source_count"] == 1
    assert "/context/retrieval/project.md" in pack.files
    # Inventory still present as a fallback map.
    assert pack.metadata["workspace_inventory"]["status"] == "ok"


def test_working_state_card_surfaces_b1_context():
    from agent_session.session_progress import build_working_state_card

    card = build_working_state_card(
        {
            "tool_metrics": {"tools_total": 1, "tools_failed": 0, "observe_total": 0},
            "deep_context": {
                "context_engineering": {
                    "project_retrieval": {"status": "empty", "project_source_count": 0},
                    "workspace_inventory": {
                        "status": "ok",
                        "recommended_reads": ["src/cli.py", "src/counter.py"],
                    },
                }
            },
        }
    )
    assert "上下文（B1）" in card
    assert "project_retrieval=`empty`" in card
    assert "/workspace/src/cli.py" in card

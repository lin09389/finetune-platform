"""Architecture guards for the Milestone 1 typed tool foundation."""

from __future__ import annotations

from pathlib import Path
from subprocess import check_output


SERVER = Path(__file__).resolve().parents[1]
PRODUCTION = [path for path in SERVER.rglob("*.py") if "tests" not in path.parts]


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_tool_platform_imports_use_the_canonical_package_name() -> None:
    forbidden_import = "server" + ".tool_platform"
    offenders = [path.relative_to(SERVER) for path in SERVER.rglob("*.py") if forbidden_import in _source(path)]

    assert offenders == []


def test_milestone_one_does_not_integrate_registry_or_gateway_with_deepagents() -> None:
    forbidden = ("ToolRegistry", "ToolGateway", "tool_platform.registry", "tool_platform.gateway")
    offenders = {
        path.name: [token for token in forbidden if token in _source(path)]
        for path in (
            SERVER / "agent_session" / "deepagents_runtime.py",
            SERVER / "agent_session" / "runtime_factory.py",
        )
        if path.exists()
    }

    assert offenders == {name: [] for name in offenders}


def test_tool_kind_has_one_production_definition() -> None:
    definitions = [path.relative_to(SERVER) for path in PRODUCTION if "class ToolKind(" in _source(path)]

    assert definitions == [Path("tool_platform/taxonomy.py")]


def test_milestone_one_adds_no_agent_session_approval_state_machine() -> None:
    prohibited = {
        "approval_repository.py",
        "approval_store.py",
        "session_state_machine.py",
        "approval_state_machine.py",
    }
    repository = SERVER.parent
    merge_base = check_output(
        ["git", "merge-base", "master", "HEAD"], cwd=repository, text=True
    ).strip()
    added = check_output(
        ["git", "diff", "--name-only", "--diff-filter=A", merge_base, "HEAD"],
        cwd=repository,
        text=True,
    ).splitlines()
    found = {Path(path).name for path in added if path.startswith("server/agent_session/")}

    assert prohibited.isdisjoint(found)


def test_milestone_one_production_package_has_only_expected_files() -> None:
    expected = {
        "__init__.py",
        "taxonomy.py",
        "models.py",
        "definition.py",
        "registry.py",
        "catalog.py",
    }
    tool_platform_files = {
        path.name for path in (SERVER / "tool_platform").glob("*.py") if path.is_file()
    }

    assert tool_platform_files == expected


def test_milestone_one_changes_only_expected_production_files() -> None:
    repository = SERVER.parent
    merge_base = check_output(
        ["git", "merge-base", "master", "HEAD"], cwd=repository, text=True
    ).strip()
    changed = check_output(
        ["git", "diff", "--name-only", merge_base, "HEAD"], cwd=repository, text=True
    ).splitlines()
    production_changes = {
        path
        for path in changed
        if path.startswith("server/") and not path.startswith("server/tests/")
    }
    expected = {
        "server/agent_session/execution_context.py",
        "server/agent_session/agent_registry.py",
        "server/tool_platform/__init__.py",
        "server/tool_platform/taxonomy.py",
        "server/tool_platform/models.py",
        "server/tool_platform/definition.py",
        "server/tool_platform/registry.py",
        "server/tool_platform/catalog.py",
    }

    assert production_changes <= expected

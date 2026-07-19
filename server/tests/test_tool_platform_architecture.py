"""Architecture guards for the Milestone 1 typed tool foundation."""

from __future__ import annotations

from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
PRODUCTION = [path for path in SERVER.rglob("*.py") if "tests" not in path.parts]


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_tool_platform_imports_use_the_canonical_package_name() -> None:
    forbidden_import = "server" + ".tool_platform"
    offenders = [path.relative_to(SERVER) for path in SERVER.rglob("*.py") if forbidden_import in _source(path)]

    assert offenders == []


def test_deepagents_runtime_keeps_handler_dispatch_inside_the_gateway() -> None:
    """Controlled mode routes tools through the Tool Gateway (9D-1), but the
    runtime must never call ``dispatch_handler`` or import ``tool_platform.handlers``
    directly — handler dispatch stays encapsulated inside the gateway."""
    forbidden = ("dispatch_handler",)
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
        "approval_state_machine.py",
    }
    found = {path.name for path in (SERVER / "agent_session").rglob("*.py")}

    assert prohibited.isdisjoint(found)


def test_tool_platform_production_package_has_only_expected_files() -> None:
    expected = {
        "__init__.py",
        "taxonomy.py",
        "models.py",
        "definition.py",
        "registry.py",
        "catalog.py",
        "policy.py",
        "handlers.py",
        "gateway.py",
        "projection.py",
    }
    tool_platform_files = {
        path.name for path in (SERVER / "tool_platform").glob("*.py") if path.is_file()
    }

    assert tool_platform_files == expected


def test_tool_platform_builtins_package_has_only_expected_files() -> None:
    expected = {
        "__init__.py",
        "filesystem.py",
        "git.py",
        "execute.py",
        "gateway_tools.py",
        "registry.py",
    }
    builtins_files = {
        path.name for path in (SERVER / "tool_platform" / "builtins").glob("*.py") if path.is_file()
    }

    assert builtins_files == expected


def test_tool_platform_builtins_define_no_second_toolkind_and_keep_deepagents_free() -> None:
    builtins_dir = SERVER / "tool_platform" / "builtins"
    offenders_kind = [
        path.relative_to(SERVER)
        for path in builtins_dir.rglob("*.py")
        if "class ToolKind(" in _source(path)
    ]
    offenders_deepagents = [
        path.relative_to(SERVER)
        for path in builtins_dir.rglob("*.py")
        if "import deepagents" in _source(path) or "from deepagents" in _source(path)
    ]

    assert offenders_kind == []
    assert offenders_deepagents == []


def test_agent_session_tool_platform_consumers_are_white_listed() -> None:
    consumers = {
        path.name
        for path in (SERVER / "agent_session").rglob("*.py")
        if "tool_platform" in _source(path)
    }

    assert consumers == {
        "execution_context.py",
        "agent_registry.py",
        "permission.py",
        "deepagents_events.py",
        "deepagents_runtime.py",
        "tool_projection.py",
    }

from __future__ import annotations

import types
from pathlib import Path

import pytest

from agent_session.runtime import DeepAgentRuntimeConfig, build_deep_agent_runtime, resolve_skill_sources
from skills import (
    MAX_DESCRIPTION_LENGTH,
    SkillSource,
    load_skill_manifest,
    parse_skill_frontmatter,
    resolve_skill_source_specs,
    scan_skill_manifests,
)


def _write_skill(root: Path, name: str, description: str = "Use this skill.") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\nmetadata:\n  author: test\nallowed-tools: read_file, grep\n---\n# {name}\n",
        encoding="utf-8",
    )
    return skill_dir


def test_parse_skill_frontmatter_supports_official_fields(tmp_path: Path):
    skill_dir = _write_skill(tmp_path, "repo-reader")

    manifest = load_skill_manifest(skill_dir)

    assert manifest is not None
    assert manifest.name == "repo-reader"
    assert manifest.description == "Use this skill."
    assert manifest.metadata == {"author": "test"}
    assert manifest.allowed_tools == ["read_file", "grep"]


def test_invalid_skill_directories_are_skipped(tmp_path: Path):
    _write_skill(tmp_path, "valid-skill")
    (tmp_path / "missing-md").mkdir()
    _write_skill(tmp_path, "bad/name")
    oversized = tmp_path / "oversized"
    oversized.mkdir()
    (oversized / "SKILL.md").write_bytes(b"x" * (10 * 1024 * 1024))

    manifests = scan_skill_manifests([SkillSource("test", tmp_path, "/skills/test/", 0)])

    assert [manifest.name for manifest in manifests] == ["valid-skill"]


def test_description_is_truncated_to_official_limit(tmp_path: Path):
    skill_dir = _write_skill(tmp_path, "long-description", "x" * (MAX_DESCRIPTION_LENGTH + 50))

    manifest = load_skill_manifest(skill_dir)

    assert manifest is not None
    assert len(manifest.description) == MAX_DESCRIPTION_LENGTH


def test_later_skill_sources_override_earlier_sources(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_skill(first, "same-skill", "first")
    _write_skill(second, "same-skill", "second")

    manifests = scan_skill_manifests(
        [
            SkillSource("first", first, "/skills/first/", 0),
            SkillSource("second", second, "/skills/second/", 1),
        ]
    )

    assert len(manifests) == 1
    assert manifests[0].description == "second"
    assert manifests[0].virtual_skill_file == "/skills/second/same-skill/SKILL.md"


def test_resolve_skill_sources_uses_official_precedence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    for path in [
        home / ".deepagents" / "build" / "skills",
        home / ".agents" / "skills",
        project / ".deepagents" / "skills",
        project / ".agents" / "skills",
    ]:
        path.mkdir(parents=True)
    monkeypatch.setattr("skills.deepagents.Path.home", lambda: home)

    sources = resolve_skill_sources(project, agent_id="build")

    assert sources == [
        "/skills/builtin/",
        "/skills/user-agent/",
        "/skills/user/",
        "/skills/project-deepagents/",
        "/skills/project-agents/",
    ]


def test_missing_project_skill_directories_do_not_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr("skills.deepagents.Path.home", lambda: tmp_path / "home")

    specs = resolve_skill_source_specs(tmp_path)

    assert [source.virtual_path for source in specs] == ["/skills/builtin/"]


def test_build_deep_agent_runtime_passes_skills(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_create_deep_agent(**kwargs):
        captured.update(kwargs)
        return object()

    fake_module = types.SimpleNamespace(create_deep_agent=fake_create_deep_agent)
    monkeypatch.setitem(__import__("sys").modules, "deepagents", fake_module)
    monkeypatch.setattr("agent_session.runtime.build_deepagents_backend", lambda *_args, **_kwargs: object())

    runtime = build_deep_agent_runtime(
        DeepAgentRuntimeConfig(
            model=object(),
            project_path=str(tmp_path),
            system_prompt="system",
            memory=[],
            checkpointer=object(),
            skills=["/skills/builtin/"],
        )
    )

    assert runtime is not None
    assert captured["skills"] == ["/skills/builtin/"]


def test_frontmatter_without_block_returns_empty_metadata():
    frontmatter, body = parse_skill_frontmatter("# Title\nBody")

    assert frontmatter == {}
    assert body == "# Title\nBody"

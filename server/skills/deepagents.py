from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MAX_SKILL_MD_BYTES = 10 * 1024 * 1024
MAX_DESCRIPTION_LENGTH = 1024
SKILL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


@dataclass(frozen=True)
class SkillSource:
    """A DeepAgents skill source mounted into the runtime backend."""

    name: str
    path: Path
    virtual_path: str
    priority: int


@dataclass(frozen=True)
class SkillManifest:
    """Validated metadata parsed from a DeepAgents SKILL.md file."""

    name: str
    description: str
    skill_dir: Path
    skill_file: Path
    source: SkillSource | None = None
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)
    module: str | None = None

    @property
    def virtual_skill_file(self) -> str | None:
        if not self.source:
            return None
        relative = self.skill_file.relative_to(self.source.path).as_posix()
        return f"{self.source.virtual_path.rstrip('/')}/{relative}"


def builtin_skills_dir() -> Path:
    return Path(__file__).resolve().parent / "builtin"


def resolve_skill_sources(
    project_path: str | Path,
    *,
    user_id: str = "default",
    agent_id: str = "build",
    org_id: str = "default-org",
) -> list[str]:
    """Return DeepAgents skill source paths in lowest-to-highest precedence order."""

    _ = user_id, org_id
    return [source.virtual_path for source in resolve_skill_source_specs(project_path, agent_id=agent_id)]


def resolve_skill_source_specs(
    project_path: str | Path,
    *,
    agent_id: str = "build",
) -> list[SkillSource]:
    project_root = Path(project_path).resolve()
    home = Path.home().resolve()
    candidates = [
        ("builtin", builtin_skills_dir(), "/skills/builtin/", 0),
        ("user-agent", home / ".deepagents" / agent_id / "skills", "/skills/user-agent/", 10),
        ("user", home / ".agents" / "skills", "/skills/user/", 20),
        ("project-deepagents", project_root / ".deepagents" / "skills", "/skills/project-deepagents/", 30),
        ("project-agents", project_root / ".agents" / "skills", "/skills/project-agents/", 40),
    ]
    return [
        SkillSource(name=name, path=path, virtual_path=virtual_path, priority=priority)
        for name, path, virtual_path, priority in candidates
        if path.exists() and path.is_dir()
    ]


def scan_skill_manifests(sources: list[SkillSource | str | Path]) -> list[SkillManifest]:
    """Scan source directories for valid DeepAgents skill manifests.

    Invalid skill directories are skipped so a single bad local skill cannot
    prevent an AgentSession from starting.
    """

    manifests_by_name: dict[str, SkillManifest] = {}
    for index, source in enumerate(sources):
        spec = _coerce_source(source, index)
        if not spec.path.exists() or not spec.path.is_dir():
            continue
        for skill_dir in sorted(path for path in spec.path.iterdir() if path.is_dir()):
            manifest = load_skill_manifest(skill_dir, source=spec)
            if manifest:
                manifests_by_name[manifest.name] = manifest
    return list(manifests_by_name.values())


def load_skill_manifest(skill_dir: str | Path, *, source: SkillSource | None = None) -> SkillManifest | None:
    root = Path(skill_dir).resolve()
    skill_file = root / "SKILL.md"
    if not skill_file.exists() or not skill_file.is_file():
        return None
    if skill_file.stat().st_size >= MAX_SKILL_MD_BYTES:
        return None

    try:
        content = skill_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None

    frontmatter, _body = parse_skill_frontmatter(content)
    name = str(frontmatter.get("name") or root.name).strip().strip("\"'")
    if not is_valid_skill_name(name):
        return None

    description = str(frontmatter.get("description") or "").strip().strip("\"'")
    description = description[:MAX_DESCRIPTION_LENGTH]
    module = _optional_string(frontmatter.get("module"))
    if module and not _is_safe_relative_file(root, module):
        return None

    return SkillManifest(
        name=name,
        description=description,
        skill_dir=root,
        skill_file=skill_file,
        source=source,
        license=_optional_string(frontmatter.get("license")),
        compatibility=_optional_string(frontmatter.get("compatibility")),
        metadata=frontmatter.get("metadata") if isinstance(frontmatter.get("metadata"), dict) else {},
        allowed_tools=_normalize_allowed_tools(frontmatter.get("allowed-tools")),
        module=module,
    )


def parse_skill_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    if not content.startswith("---"):
        return {}, content
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, content
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        return {}, content
    return _parse_simple_yaml(lines[1:end_index]), "\n".join(lines[end_index + 1 :])


def is_valid_skill_name(name: str) -> bool:
    return bool(SKILL_NAME_PATTERN.fullmatch(name)) and "/" not in name and "\\" not in name


def _parse_simple_yaml(lines: list[str]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_map_key: str | None = None
    for raw_line in lines:
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith((" ", "\t")) and current_map_key:
            child = raw_line.strip()
            if ":" in child and isinstance(data.get(current_map_key), dict):
                key, value = child.split(":", 1)
                data[current_map_key][key.strip()] = _parse_scalar(value.strip())
            continue
        current_map_key = None
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            data[key] = {}
            current_map_key = key
        else:
            data[key] = _parse_scalar(value)
    return data


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",")]
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value


def _coerce_source(source: SkillSource | str | Path, index: int) -> SkillSource:
    if isinstance(source, SkillSource):
        return source
    path = Path(source).resolve()
    return SkillSource(name=f"source-{index}", path=path, virtual_path=path.as_posix(), priority=index)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().strip("\"'")
    return text or None


def _normalize_allowed_tools(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _is_safe_relative_file(root: Path, value: str) -> bool:
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return candidate.is_file()


__all__ = [
    "MAX_DESCRIPTION_LENGTH",
    "MAX_SKILL_MD_BYTES",
    "SkillManifest",
    "SkillSource",
    "builtin_skills_dir",
    "is_valid_skill_name",
    "load_skill_manifest",
    "parse_skill_frontmatter",
    "resolve_skill_source_specs",
    "resolve_skill_sources",
    "scan_skill_manifests",
]

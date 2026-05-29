"""DeepAgents-compatible skill package support.

The AgentSession runtime uses official DeepAgents skills: directories that
contain a `SKILL.md` file plus optional referenced assets. The older Python
class-based skill framework remains in this package for historical direct
imports, but the public package entrypoint intentionally exposes only the
DeepAgents skill-source APIs.
"""

from .deepagents import (
    MAX_DESCRIPTION_LENGTH,
    MAX_SKILL_MD_BYTES,
    SkillManifest,
    SkillSource,
    builtin_skills_dir,
    is_valid_skill_name,
    load_skill_manifest,
    parse_skill_frontmatter,
    resolve_skill_source_specs,
    resolve_skill_sources,
    scan_skill_manifests,
)

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

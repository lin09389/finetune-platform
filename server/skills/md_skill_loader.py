"""Deprecated compatibility wrapper for DeepAgents skill manifests.

Markdown skills are no longer converted into executable `SkillBase` classes.
Use `skills.deepagents` to scan and pass official DeepAgents skill sources to
AgentSession runtimes.
"""

from .deepagents import (
    SkillManifest,
    SkillSource,
    load_skill_manifest,
    parse_skill_frontmatter,
    resolve_skill_source_specs,
    resolve_skill_sources,
    scan_skill_manifests,
)

__all__ = [
    "SkillManifest",
    "SkillSource",
    "load_skill_manifest",
    "parse_skill_frontmatter",
    "resolve_skill_source_specs",
    "resolve_skill_sources",
    "scan_skill_manifests",
]

from __future__ import annotations

from skills import scan_skill_manifests
from skills.deepagents import builtin_skills_dir


def test_builtin_deepagents_skills_are_discoverable():
    manifests = scan_skill_manifests([builtin_skills_dir()])

    names = {manifest.name for manifest in manifests}
    assert "frontend-design-ui-ux-pro-max" in names
    assert "github-project-analyzer" in names

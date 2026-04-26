"""v0.68 Track D: source-dir rename `knowledge-base/` -> `research-hub/`.

These tests pin the backward-compat alias so external callers that pass
the pre-rename name keep working with a DeprecationWarning until v0.70.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from unittest.mock import patch

import pytest


def test_get_bundled_skill_path_resolves_legacy_knowledge_base_name():
    """`get_bundled_skill_path('knowledge-base')` must still return the
    research-hub SKILL.md after the v0.68 rename."""
    from research_hub.skill_installer import get_bundled_skill_path

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the warn behavior is asserted in the next test
        path = get_bundled_skill_path("knowledge-base")
    assert path.name == "SKILL.md"
    # The resolved path now lives under research-hub/, not knowledge-base/
    assert "research-hub" in str(path).lower().replace("\\", "/")


def test_legacy_knowledge_base_name_emits_deprecation_warning():
    from research_hub.skill_installer import get_bundled_skill_path

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        get_bundled_skill_path("knowledge-base")
    msgs = [str(w.message) for w in captured if issubclass(w.category, DeprecationWarning)]
    assert any("knowledge-base" in m and "research-hub" in m for m in msgs), (
        f"Expected DeprecationWarning about the rename; got {msgs!r}"
    )


def test_install_skill_user_facing_target_unchanged_after_rename(tmp_path):
    """End-to-end smoke: after the v0.68 rename, install_skill still
    writes `<root>/.claude/skills/research-hub/SKILL.md` (the user-facing
    install target is unchanged; only the source dir name moved)."""
    import importlib

    with patch.object(Path, "home", staticmethod(lambda: tmp_path)):
        # Reimport so PLATFORMS picks up the patched Path.home()
        from research_hub import skill_installer
        importlib.reload(skill_installer)
        installed = skill_installer.install_skill("claude-code")

    targets = {Path(p).parent.name for p in installed}
    assert "research-hub" in targets, f"missing research-hub install target: {targets}"
    assert "knowledge-base" not in targets, (
        f"knowledge-base alias must NOT appear as a separate install target "
        f"(install dir map now matches source dir map): {targets}"
    )

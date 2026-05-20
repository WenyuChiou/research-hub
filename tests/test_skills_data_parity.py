"""Parity test: `skills/` (source-of-truth) ↔ `src/research_hub/skills_data/`
(installer mirror).

The installer (``research_hub.skill_installer``) copies skills out of
``src/research_hub/skills_data/``, not out of ``skills/``. Editing a
SKILL.md in ``skills/`` but forgetting the mirror means the change
ships to readers of the public repo but never reaches users who run
``research-hub install``.

This test catches the divergence at PR time instead of at user-report
time. Phase 7 Wave A surfaced the gap (the anti-leakage rule and
backup callout edits landed in ``skills/`` but not in ``skills_data/``
until the code-reviewer subagent flagged it).

If you intentionally need to ship a skill only via the marketplace
(not via ``research-hub install``), add the skill name to
``SHADOW_ONLY_IN_SKILLS_TREE`` below with a one-line comment. Today
the only such case is ``zotero-skills``, the vendored copy that
Item #3 of Phase 2 is scheduled to remove.
"""

from __future__ import annotations

import filecmp
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_TREE = REPO_ROOT / "skills"
SKILLS_DATA_TREE = REPO_ROOT / "src" / "research_hub" / "skills_data"

# Skills that intentionally live in ``skills/`` but not in
# ``skills_data/``. Add with a comment explaining why.
SHADOW_ONLY_IN_SKILLS_TREE: set[str] = {
    # Vendored copy of the standalone ``zotero-skills`` plugin; the
    # canonical lives at WenyuChiou/zotero-skills. Phase 2 Wave C
    # backlog item: delete this directory + update installer + tests
    # + docs in sync. Until then, the vendored copy is intentionally
    # absent from skills_data so ``research-hub install`` does not
    # double-ship it.
    "zotero-skills",
}


def _list_skill_names(root: Path) -> set[str]:
    return {p.name for p in root.iterdir() if p.is_dir()}


def _walk_relative(skill_root: Path) -> set[Path]:
    """Every file under skill_root, relative to skill_root."""
    return {p.relative_to(skill_root) for p in skill_root.rglob("*") if p.is_file()}


def test_skill_dir_lists_match_modulo_shadows():
    """Every skill in skills_data/ must also exist in skills/; any
    skill in skills/ but not skills_data/ must be declared in
    SHADOW_ONLY_IN_SKILLS_TREE."""
    in_skills = _list_skill_names(SKILLS_TREE)
    in_data = _list_skill_names(SKILLS_DATA_TREE)

    only_in_data = in_data - in_skills
    only_in_skills = in_skills - in_data
    unexpected_shadows = only_in_skills - SHADOW_ONLY_IN_SKILLS_TREE

    assert not only_in_data, (
        f"skills/ is missing these skills present in skills_data/: {sorted(only_in_data)}"
    )
    assert not unexpected_shadows, (
        f"skills/ has these skills not in skills_data/ AND not declared in "
        f"SHADOW_ONLY_IN_SKILLS_TREE: {sorted(unexpected_shadows)}. "
        f"Either copy the skill into skills_data/, or add it to the "
        f"shadow set with a comment explaining why."
    )


# Parametrize over the skills that should be byte-mirrored.
_MIRRORED_SKILLS = sorted(
    {p.name for p in SKILLS_DATA_TREE.iterdir() if p.is_dir()}
)


@pytest.mark.parametrize("skill", _MIRRORED_SKILLS)
def test_file_set_matches(skill):
    """skills/<skill>/ and skills_data/<skill>/ must contain the same
    set of relative file paths."""
    a = _walk_relative(SKILLS_TREE / skill)
    b = _walk_relative(SKILLS_DATA_TREE / skill)
    only_in_a = a - b
    only_in_b = b - a
    assert not only_in_a, (
        f"skills/{skill}/ has files missing from skills_data/{skill}/: "
        f"{sorted(str(p) for p in only_in_a)}"
    )
    assert not only_in_b, (
        f"skills_data/{skill}/ has files missing from skills/{skill}/: "
        f"{sorted(str(p) for p in only_in_b)}"
    )


@pytest.mark.parametrize("skill", _MIRRORED_SKILLS)
def test_file_contents_byte_identical(skill):
    """Every file present in both trees must be byte-identical.
    ``filecmp.cmp(shallow=False)`` does a true byte compare, not a
    stat-only compare."""
    skill_a = SKILLS_TREE / skill
    skill_b = SKILLS_DATA_TREE / skill
    diffs: list[str] = []
    for rel in _walk_relative(skill_a) & _walk_relative(skill_b):
        if not filecmp.cmp(skill_a / rel, skill_b / rel, shallow=False):
            diffs.append(str(rel))
    assert not diffs, (
        f"{skill}: these files diverge between skills/ and skills_data/: "
        f"{diffs}. Re-run `cp skills/{skill}/<file> "
        f"src/research_hub/skills_data/{skill}/<file>` for each."
    )

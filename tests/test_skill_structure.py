"""Structural + trust invariants for the SKILL.md files in this repo.

Frontmatter shape (`test_frontmatter_schema.py` / `test_v066_skill_schema.py`)
and the installer mirror (`test_skills_data_parity.py`) are already tested.
This file adds the three things that were unguarded and that a quality audit
(ai-research-skills, 2026-05-28) flagged as defended only by convention:

  1. the <=500-line progressive-disclosure ceiling,
  2. the anti-fabrication safety strings (so a reword/sync can't silently drop
     "Do not invent" / "status: gap" / the hallucination + ground-truth guards),
  3. the sibling disambiguation arrows (so the easily-confused trio + the zotero
     pair + the gap-to-topic handoff keep naming each other for auto-trigger).

All assertions were verified against the live SKILL.md files on master before
this test shipped — they pass today; their job is to keep passing.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"

MAX_LINES = 500

# Each skill must retain its anti-fabrication / fail-loud string. Substring
# match against the whole SKILL.md (robust to the string moving between the
# description and the body). Verified present on master 2026-05-28.
SAFETY_STRINGS = {
    "research-hub": "Do not invent",
    "paper-memory-builder": "status: gap",
    "paper-summarize": "hallucinated",
    "notebooklm-brief-verifier": "do NOT assume coverage",
}

# Each skill's SKILL.md must name these sibling skills so auto-trigger
# disambiguates the easily-confused cases. Verified present on master.
DISAMBIGUATION = {
    "paper-summarize": ["paper-memory-builder", "literature-triage-matrix"],
    "paper-memory-builder": ["paper-summarize"],
    "literature-triage-matrix": ["paper-memory-builder"],
    "zotero-library-curator": ["zotero-skills"],
    "gap-to-topic": ["literature-triage-matrix", "research-design-helper"],
}


def _skill_md_paths():
    return sorted(SKILLS_DIR.glob("*/SKILL.md"))


def _read(name):
    return (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")


def test_skills_dir_is_populated():
    paths = _skill_md_paths()
    assert paths, f"no skills/*/SKILL.md found under {SKILLS_DIR}"


@pytest.mark.parametrize("path", _skill_md_paths(), ids=lambda p: p.parent.name)
def test_skill_md_under_line_ceiling(path):
    n = len(path.read_text(encoding="utf-8").splitlines())
    assert n <= MAX_LINES, (
        f"{path.parent.name}/SKILL.md is {n} lines (> {MAX_LINES}); move deep "
        f"content into references/ to keep progressive disclosure"
    )


@pytest.mark.parametrize("skill, needle", sorted(SAFETY_STRINGS.items()))
def test_anti_fabrication_string_present(skill, needle):
    text = _read(skill)
    assert needle in text, (
        f"{skill}/SKILL.md no longer contains the anti-fabrication guard "
        f"{needle!r} — fail-loud / no-hallucination wording must survive every "
        f"edit and sync"
    )


@pytest.mark.parametrize(
    "skill, sibling",
    [(skill, s) for skill, siblings in sorted(DISAMBIGUATION.items()) for s in siblings],
    ids=lambda v: v,  # render ids as the literal skill / sibling name
)
def test_disambiguation_arrows_present(skill, sibling):
    text = _read(skill)
    assert sibling in text, (
        f"{skill}/SKILL.md no longer names sibling skill {sibling!r} — "
        f"disambiguation arrows keep auto-trigger from mis-firing between "
        f"the easily-confused skills"
    )

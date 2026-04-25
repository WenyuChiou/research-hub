"""v0.66 Track D1: schema validation for every packaged skill.

Validates frontmatter (name, description) and evals.json structure
(>=3 prompts, each with non-empty `prompt` text). The 5 new v0.66
skills are required to ship evals.json; existing knowledge-base and
research-hub-multi-ai are exempt for now (back-fill in v0.67+).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = REPO_ROOT / "skills"
SKILLS_DATA_ROOT = REPO_ROOT / "src" / "research_hub" / "skills_data"

V066_SKILLS = (
    "research-context-compressor",
    "research-project-orienter",
    "literature-triage-matrix",
    "paper-memory-builder",
    "notebooklm-brief-verifier",
)
LEGACY_SKILLS = ("knowledge-base", "research-hub-multi-ai")
ALL_SKILLS = V066_SKILLS + LEGACY_SKILLS

# Third-party / vendored skills under skills/ that we do NOT package
EXCLUDED_FROM_PACKAGING = {"zotero-skills"}


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Tiny YAML-frontmatter parser: only handles `key: value` lines."""
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    body = text[4:end]
    out: dict[str, str] = {}
    for line in body.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_skill_frontmatter_has_name_and_description(skill):
    skill_md = SKILLS_ROOT / skill / "SKILL.md"
    assert skill_md.exists(), f"{skill_md} missing"
    fm = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    assert "name" in fm and fm["name"], f"{skill}: missing/empty `name`"
    assert "description" in fm and fm["description"], (
        f"{skill}: missing/empty `description`"
    )
    # Description must be substantive (brief calls for at least 30 chars
    # to discourage "TODO" placeholders).
    assert len(fm["description"]) >= 30, (
        f"{skill}: description too short ({len(fm['description'])} chars)"
    )


@pytest.mark.parametrize("skill", V066_SKILLS)
def test_v066_skills_ship_evals_json_with_min_3_prompts(skill):
    evals_path = SKILLS_ROOT / skill / "evals" / "evals.json"
    assert evals_path.exists(), f"{evals_path} missing (v0.66 skills require evals)"
    payload = json.loads(evals_path.read_text(encoding="utf-8"))
    assert payload.get("skill") == skill, (
        f"{skill}: evals.json `skill` field mismatch (got {payload.get('skill')!r})"
    )
    evals = payload.get("evals", [])
    assert len(evals) >= 3, (
        f"{skill}: evals.json has {len(evals)} prompts; brief requires >=3"
    )
    for idx, item in enumerate(evals):
        assert isinstance(item, dict), f"{skill} eval[{idx}] not a dict"
        assert item.get("prompt"), f"{skill} eval[{idx}] has empty `prompt`"


@pytest.mark.parametrize("skill", V066_SKILLS)
def test_v066_skill_name_matches_directory(skill):
    skill_md = SKILLS_ROOT / skill / "SKILL.md"
    fm = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    assert fm.get("name") == skill, (
        f"{skill}: frontmatter name {fm.get('name')!r} != directory name"
    )


def test_v066_skills_do_not_overclaim_in_description():
    """Descriptions must not promise features that don't exist (CLI commands,
    cross-skill behaviors). Catches accidental marketing creep."""
    forbidden = re.compile(r"\b(automatically (publishes|deploys|emails))\b", re.I)
    for skill in V066_SKILLS:
        skill_md = SKILLS_ROOT / skill / "SKILL.md"
        fm = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        match = forbidden.search(fm.get("description", ""))
        assert match is None, (
            f"{skill}: description contains forbidden overclaim {match.group(0)!r}"
        )

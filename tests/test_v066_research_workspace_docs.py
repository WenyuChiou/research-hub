"""v0.66 Track D2: docs / packaging consistency tests.

Verifies the new workspace-manifest doc + ai-research-skills index exist
and that every packaged skill has a matching mirror under skills_data/.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = REPO_ROOT / "skills"
SKILLS_DATA_ROOT = REPO_ROOT / "src" / "research_hub" / "skills_data"
DOCS = REPO_ROOT / "docs"

V066_SKILLS = (
    "research-context-compressor",
    "research-project-orienter",
    "literature-triage-matrix",
    "paper-memory-builder",
    "notebooklm-brief-verifier",
    # v0.67: 6th skill from the brief
    "zotero-library-curator",
    # v0.68: Stage 3a/4 design helper
    "research-design-helper",
)
EXCLUDED_FROM_PACKAGING = {"zotero-skills"}


def test_research_workspace_manifest_doc_exists_and_lists_required_yaml_files():
    doc = DOCS / "research-workspace-manifest.md"
    assert doc.exists(), "docs/research-workspace-manifest.md must exist"
    text = doc.read_text(encoding="utf-8")
    for required in (
        "project_manifest.yml",
        "experiment_matrix.yml",
        "data_dictionary.yml",
        "literature_matrix.md",
        "claims.yml",
        "figures.yml",
    ):
        assert required in text, f"manifest doc missing schema for {required}"


def test_ai_research_skills_doc_exists_and_lists_all_v066_skills():
    doc = DOCS / "ai-research-skills.md"
    assert doc.exists(), "docs/ai-research-skills.md must exist"
    text = doc.read_text(encoding="utf-8")
    for skill in V066_SKILLS:
        assert skill in text, (
            f"ai-research-skills.md does not mention `{skill}` -- update the index"
        )


@pytest.mark.parametrize("skill", V066_SKILLS)
def test_packaged_skill_mirror_exists(skill):
    mirror = SKILLS_DATA_ROOT / skill / "SKILL.md"
    assert mirror.exists(), (
        f"{mirror} missing — every skills/<name>/SKILL.md needs a "
        f"src/research_hub/skills_data/<name>/SKILL.md mirror"
    )


@pytest.mark.parametrize("skill", V066_SKILLS)
def test_packaged_skill_mirror_byte_identical(skill):
    src = SKILLS_ROOT / skill / "SKILL.md"
    mirror = SKILLS_DATA_ROOT / skill / "SKILL.md"
    assert src.read_bytes() == mirror.read_bytes(), (
        f"{skill}: skills/ vs skills_data/ SKILL.md drifted; re-mirror"
    )


@pytest.mark.parametrize("skill", V066_SKILLS)
def test_packaged_evals_mirror_byte_identical(skill):
    src = SKILLS_ROOT / skill / "evals" / "evals.json"
    mirror = SKILLS_DATA_ROOT / skill / "evals" / "evals.json"
    assert src.exists() and mirror.exists()
    assert src.read_bytes() == mirror.read_bytes(), (
        f"{skill}: evals.json drifted between skills/ and skills_data/"
    )


def test_no_orphan_packaged_skill_without_root_source():
    """Every dir under skills_data/ must have a matching skills/ source
    (except legacy aliases). Catches orphaned mirrors after a rename."""
    # v0.68: alias map is now empty after the source-dir rename, but we
    # keep the variable as the extension point for any future renames.
    legacy_target_to_source: dict[str, str] = {}
    for child in SKILLS_DATA_ROOT.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        source_name = legacy_target_to_source.get(name, name)
        src = SKILLS_ROOT / source_name
        assert src.exists(), (
            f"{child} has no matching {src} — orphan mirror, run mirror sync"
        )

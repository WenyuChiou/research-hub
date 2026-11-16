"""Native reading guidance/package guards, not a model or science evaluation."""

import json
from pathlib import Path

import pytest

from research_hub import skill_installer


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills"
MIRROR = ROOT / "src/research_hub/skills_data"
REL = Path("paper-summarize/references/fulltext-summary.md")
FIELDS = ("why", "objective", "methods", "findings", "conclusions", "key_points", "limitations")


def _require(text, clauses):
    for clause in clauses:
        assert clause in text, f"missing guidance: {clause}"


@pytest.mark.parametrize("tree", [SOURCE, MIRROR], ids=["source", "packaged"])
def test_native_route_and_legacy_cli_remain_distinct(tree):
    text = (tree / "paper-summarize/SKILL.md").read_text()
    _require(text, (
        "## Native per-paper body summary",
        "references/fulltext-summary.md",
        "## Abstract-note mode (existing CLI)",
        "neither command becomes a full-text reader",
        "Do not silently downgrade a full-text request",
        "`supported`, `analyst_inference` and `unknown`",
        "Hub, Zotero, Obsidian and a separate LLM CLI are optional",
        "report saving as pending",
    ))
    assert text.index("## Native per-paper body summary") < text.index("## Abstract-note mode")


@pytest.mark.parametrize("field", FIELDS)
def test_fulltext_contract_preserves_every_question(field):
    text = (SOURCE / REL).read_text()
    assert f"(`{field}`)" in text


GUARDS = (
    "Relevance to the user's project is a different judgment",
    "partial body reading exhaustive full-paper review",
    "model agents are not human subjects",
    "qualitative, historical,",
    "`supported`", "`analyst_inference`", "`unknown`",
    "Do not fill missing facts with memory",
    "A true quote can be attached to a false conclusion",
    "the pending integration",
    "synthetic roundtrip or a file export alone",
)


def test_scope_semantics_and_destination_boundaries():
    _require((SOURCE / REL).read_text(), GUARDS)


@pytest.mark.parametrize("missing", GUARDS)
def test_mutated_guidance_cannot_silently_drop_a_boundary(missing):
    text = (SOURCE / REL).read_text()
    with pytest.raises(AssertionError, match="missing guidance"):
        _require(text.replace(missing, ""), GUARDS)


def test_observed_timing_preserves_identity_and_overlap():
    text = (SOURCE / "research-hub/references/research-protocol.md").read_text()
    _require(text, (
        "## Measure the observed stages",
        "new work identities from new source files/versions",
        "cold versus warm setup",
        "do not add parallel durations",
        "report unmeasured stages as `unknown`",
        "raw hits, deduplicated works, screened works",
        "independently of production structural/source-binding checks",
    ))


def test_evals_cover_fulltext_abstract_domain_timing_and_export():
    rows = json.loads((SOURCE / "paper-summarize/evals/evals.json").read_text())["evals"]
    native = rows[4:]
    assert len(native) == 5
    for needle in ("Hub is not installed", "only its abstract", "qualitative archival", "parallel", "adapter only accepts abstract"):
        assert any(needle in row["prompt"] for row in native)
    assert "fulltext_body" in native[1]["expected_behavior"]
    assert "analyst" in native[0]["expected_behavior"]
    assert "all-domain" in native[2]["expected_behavior"]
    assert "cold-start" in native[3]["expected_behavior"]
    assert "paper-abstract-draft" in native[4]["expected_behavior"]


def test_installation_copies_the_full_native_contract(tmp_path, monkeypatch):
    target = tmp_path / "skills"
    monkeypatch.setitem(skill_installer.PLATFORMS, "fixture",
                        skill_installer.PlatformConfig("Fixture", target))
    skill_installer.install_skill("fixture")
    for rel in (REL, Path("paper-summarize/SKILL.md"),
                Path("paper-summarize/evals/evals.json"),
                Path("research-hub/references/research-protocol.md")):
        assert (SOURCE / rel).read_bytes() == (MIRROR / rel).read_bytes()
        assert (target / rel).read_bytes() == (SOURCE / rel).read_bytes()


def test_plugin_cache_version_changes_but_frozen_abstract_profile_does_not():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    assert plugin["version"] == "0.5.29"
    frozen = MIRROR / "_profiles/abstract-draft-instructions-v1/paper-summarize/SKILL.md"
    assert "abstract" in frozen.read_text().lower()
    assert "## Native per-paper body summary" not in frozen.read_text()

"""Cross-skill integration test: gap-to-topic → research-design-helper.

This is the **first cross-skill handoff integration test** in the
research-hub skill family. Subsequent stage-to-stage wires (3a → 3b,
6 → 7, ...) should follow this shape:

  1. A frozen fixture under tests/fixtures/ representing the upstream
     skill's emitted artifact (here: topic_dossier.gaps.yml).
  2. Schema-parses-cleanly assertion (yaml.safe_load doesn't raise).
  3. Schema-key-presence assertions for the fields the downstream skill
     reads (here: gaps[].statement, gaps[].verdict, gaps[].feasibility,
     open_questions[].text).
  4. SKILL.md prose-contract assertions — the downstream skill's
     SKILL.md must literally mention reading the upstream artifact in
     its Inputs section, so the contract is documented for human
     readers AND machine-checkable.
  5. Inverse / regression assertions — the downstream skill must still
     describe a fallback path when the upstream artifact is absent.

Failures here indicate the handoff contract drifted between the two
skills' SKILL.md prose and the actual artifact schema. Fix by either
updating the fixture (if the schema was intentionally extended), the
SKILL.md (if the prose missed a field), or both.

See plan: ~/.claude/plans/enchanted-enchanting-anchor.md (PR 1 of the
Stage 2 → 3a → 3b handoff sequence).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "topic_dossier_sample.gaps.yml"
FIXTURE_MULTI_ELIGIBLE = (
    REPO_ROOT / "tests" / "fixtures" / "topic_dossier_multi_eligible_sample.gaps.yml"
)
DESIGN_HELPER_SKILL = (
    REPO_ROOT / "skills" / "research-design-helper" / "SKILL.md"
)
DESIGN_HELPER_TEMPLATE = (
    REPO_ROOT
    / "skills"
    / "research-design-helper"
    / "references"
    / "design_brief_template.md"
)
CONTEXT_COMPRESSOR_SKILL = (
    REPO_ROOT / "skills" / "research-context-compressor" / "SKILL.md"
)
GAP_TO_TOPIC_TEMPLATE = (
    REPO_ROOT
    / "skills"
    / "gap-to-topic"
    / "references"
    / "dossier-template.md"
)


# ---------------------------------------------------------------------------
# Fixture-level assertions — the upstream artifact has the shape the
# downstream skill expects.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def gaps_yaml() -> dict:
    """Parse the frozen .gaps.yml fixture once per test module."""
    assert FIXTURE.exists(), f"missing fixture: {FIXTURE}"
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_parses_as_valid_yaml(gaps_yaml: dict) -> None:
    """Trivial guard — the fixture must be loadable. If this fails the
    file was corrupted on disk, not a contract problem."""
    assert isinstance(gaps_yaml, dict), "fixture root must be a mapping"


def test_fixture_has_v0_3_10_plus_top_level_keys(gaps_yaml: dict) -> None:
    """The v0.3.6+ + v0.3.9+ schema (refreshed in plugin v0.3.11) has
    these top-level keys. Adding to this list is a SCHEMA EXTENSION —
    refresh `dossier-template.md` Schema reference + bump the plugin.
    Removing one is a BREAKING CHANGE.
    """
    expected = {
        "dossier",  # the topic area
        "generated",  # ISO date
        "run_type",  # short prose describing the run
        "recall",  # search backbone metadata + screen sub-block
        "pipeline",  # 4-step provenance chain
        "gaps",  # list of candidate gaps with verdicts
        "open_questions",  # list of unresolved questions the dossier surfaced
    }
    actual = set(gaps_yaml.keys())
    missing = expected - actual
    assert not missing, (
        f"fixture missing top-level keys the downstream consumer expects: "
        f"{sorted(missing)}"
    )


def test_fixture_recall_has_screen_subblock(gaps_yaml: dict) -> None:
    """`recall.screen` is the v0.3.6 fit-check BM25 gate metadata.
    The schema reference promises it; the fixture must have it."""
    assert "screen" in gaps_yaml["recall"], (
        "recall.screen sub-block missing — fit-check BM25 gate metadata"
    )
    screen_keys = set(gaps_yaml["recall"]["screen"].keys())
    expected = {"gate", "retrieved", "kept", "screened_out", "tier"}
    missing = expected - screen_keys
    assert not missing, (
        f"recall.screen missing keys: {sorted(missing)}"
    )


def test_fixture_gap_entry_has_downstream_consumer_fields(
    gaps_yaml: dict,
) -> None:
    """Each `gaps[]` entry must carry the fields the downstream consumer
    (research-design-helper §0) reads. If any is missing, pre-fill
    cannot run."""
    required_per_gap = {
        "id",  # G1, G2, ...
        "name",  # human-readable label
        "statement",  # one-sentence statement, feeds Segment 1 (RQ)
        "verdict",  # go | conditional-go | no-go — filter key
        "feasibility",  # informs Segment 5 (Risks)
    }
    for gap in gaps_yaml["gaps"]:
        actual = set(gap.keys())
        missing = required_per_gap - actual
        assert not missing, (
            f"gap {gap.get('id', '<unknown>')} missing fields: "
            f"{sorted(missing)}"
        )


def test_fixture_open_questions_have_text_field(gaps_yaml: dict) -> None:
    """`open_questions[]` feeds Segment 5 (Risk register) pre-fill —
    each entry needs a `text` field."""
    for q in gaps_yaml["open_questions"]:
        assert "text" in q, f"open_question missing text: {q}"
        assert q["text"], f"open_question has empty text: {q}"


def test_fixture_at_least_one_go_eligible_candidate(gaps_yaml: dict) -> None:
    """The §0 workflow filters gaps to `verdict in {conditional-go, go}`.
    An all-no-go fixture is a valid edge case (the §0 step would say
    'nothing to frame') but is not useful for testing the pre-fill
    path; our dogfood fixture must have at least one go-eligible gap.
    """
    go_eligible = [
        g for g in gaps_yaml["gaps"] if g["verdict"] in {"conditional-go", "go"}
    ]
    assert go_eligible, (
        "fixture has no conditional-go or go candidate; pre-fill path "
        "is unexercised. Refresh the fixture."
    )


# ---------------------------------------------------------------------------
# Downstream-skill contract assertions — research-design-helper's
# SKILL.md must literally describe reading .gaps.yml.
# ---------------------------------------------------------------------------


def test_design_helper_skill_md_lists_gaps_yml_as_input() -> None:
    """research-design-helper Inputs section must mention
    topic_dossier.gaps.yml. If this fails, the prose contract was
    rolled back without updating this test."""
    text = DESIGN_HELPER_SKILL.read_text(encoding="utf-8")
    inputs_section = _extract_section(text, "## Inputs")
    assert "topic_dossier.gaps.yml" in inputs_section, (
        "research-design-helper Inputs section no longer mentions "
        "topic_dossier.gaps.yml — handoff contract broke"
    )


def test_design_helper_skill_md_has_section_0_preamble() -> None:
    """The §0 workflow preamble (the auto-pre-fill logic) must exist
    AND describe verdict-based filtering inside the §0 block itself
    (not just anywhere in the file — `conditional-go` also appears in
    the Inputs section above, so we must scope to §0).
    """
    text = DESIGN_HELPER_SKILL.read_text(encoding="utf-8")
    assert "### §0 — Detect Stage 2 handoff" in text, (
        "Workflow §0 preamble missing — pre-fill logic undocumented"
    )
    section_0 = _extract_section(text, "### §0 — Detect Stage 2 handoff")
    # Filter-by-verdict logic must live inside the §0 block, not just
    # be incidentally present elsewhere
    assert "conditional-go" in section_0, (
        "§0 block does not mention `conditional-go` — filter logic absent"
    )
    assert "no-go" in section_0, (
        "§0 block does not mention `no-go` — three-branch logic incomplete"
    )
    # Fallback-on-absence must be the first branch
    assert "If absent" in section_0, (
        "§0 block missing the absent-fallback branch"
    )


def test_design_helper_skill_md_section_0_covers_three_branches() -> None:
    """The §0 block must describe all three filtered-list branches:
    exactly-one, 2+, zero. If any branch is silently deleted, the user
    experience regresses."""
    text = DESIGN_HELPER_SKILL.read_text(encoding="utf-8")
    section_0 = _extract_section(text, "### §0 — Detect Stage 2 handoff")
    # Exactly-one-candidate branch — auto-pre-fill
    assert "auto-pre-fill" in section_0.lower() or "auto pre-fill" in section_0.lower(), (
        "§0 missing the auto-pre-fill (exactly-one-candidate) branch"
    )
    # 2+ branch — ask the user
    assert "Which candidate" in section_0, (
        "§0 missing the 2+ candidates branch (ask-the-user)"
    )
    # zero branch — halt
    assert "No viable candidate" in section_0 or "nothing to frame" in section_0.lower(), (
        "§0 missing the zero-candidates branch (halt with nothing-to-frame)"
    )


def test_design_helper_skill_md_preserves_fallback_behaviour() -> None:
    """INVERSE assertion — if .gaps.yml is absent the skill must NOT
    regress. The Inputs section must still list its 4 fallback inputs
    (project_manifest.yml, design_brief.md, literature_matrix.md, free
    text) and the §0 preamble must say 'If absent → behave exactly as
    before'.
    """
    text = DESIGN_HELPER_SKILL.read_text(encoding="utf-8")
    inputs_section = _extract_section(text, "## Inputs")
    for required in (
        "project_manifest.yml",
        "design_brief.md",
        "literature_matrix.md",
    ):
        assert required in inputs_section, (
            f"Fallback input {required!r} removed from Inputs — regression"
        )
    assert "If absent" in text and "behave exactly as before" in text, (
        "§0 must explicitly preserve fallback behaviour when .gaps.yml is "
        "absent (no regression for standalone users)"
    )


def test_design_brief_template_has_provenance_frontmatter() -> None:
    """The design_brief.md frontmatter must accept the two new fields
    that record Stage 2 → 3a provenance."""
    text = DESIGN_HELPER_TEMPLATE.read_text(encoding="utf-8")
    # Extract the YAML frontmatter (between the first two `---` lines)
    m = re.search(r"\A---\n(.*?)\n---\n", text, re.S)
    assert m, "design_brief_template.md missing frontmatter"
    frontmatter = m.group(1)
    assert "source:" in frontmatter, (
        "frontmatter missing `source:` — Stage 2 provenance field"
    )
    assert "gap_verdict:" in frontmatter, (
        "frontmatter missing `gap_verdict:` — frozen verdict snapshot field"
    )


# ---------------------------------------------------------------------------
# 3a → 3b contract: research-context-compressor reads design_brief.md
# ---------------------------------------------------------------------------


def test_context_compressor_skill_md_reads_design_brief() -> None:
    """research-context-compressor Inputs must mention design_brief.md.
    The marketplace pipeline.md has long claimed it does; this fix
    makes the skill's own prose match.
    """
    text = CONTEXT_COMPRESSOR_SKILL.read_text(encoding="utf-8")
    inputs_section = _extract_section(text, "## Inputs")
    assert "design_brief.md" in inputs_section, (
        "research-context-compressor Inputs section does not mention "
        "design_brief.md — pipeline.md promise still uncorroborated"
    )


def test_context_compressor_skill_md_outputs_show_provenance_from_gap() -> None:
    """v0.3.13 (F1 fast-follow): compressor Outputs section must show
    the `provenance.from_gap` field in its example output. The schema
    doc (`docs/research-workspace-manifest.md`) and the Inputs section
    both mention the field, but if Outputs doesn't, a prose-driven
    agent may miss the wire and never emit provenance.from_gap.
    """
    text = CONTEXT_COMPRESSOR_SKILL.read_text(encoding="utf-8")
    outputs_section = _extract_section(text, "## Outputs you must produce")
    assert "provenance" in outputs_section, (
        "research-context-compressor Outputs section does not mention "
        "`provenance` — the Stage 2 → 3a wire example is missing from "
        "the skill's own Output spec (only documented in the schema doc + Inputs)"
    )
    assert "from_gap" in outputs_section, (
        "Outputs section mentions `provenance` but not `from_gap` — "
        "the example block must show the full field path"
    )


def test_multi_eligible_fixture_parses_and_has_2plus_go_eligible() -> None:
    """v0.3.15 (codex C2): the multi-eligible fixture exercises the §0
    2+ candidates branch. Filtering to verdict ∈ {conditional-go, go}
    must yield 2+ entries — otherwise the fixture has decayed and the
    branch is once again unexercised.
    """
    assert FIXTURE_MULTI_ELIGIBLE.exists(), (
        f"missing multi-eligible fixture: {FIXTURE_MULTI_ELIGIBLE}"
    )
    data = yaml.safe_load(FIXTURE_MULTI_ELIGIBLE.read_text(encoding="utf-8"))
    go_eligible = [
        g for g in data["gaps"] if g["verdict"] in {"conditional-go", "go"}
    ]
    assert len(go_eligible) >= 2, (
        f"multi-eligible fixture has only {len(go_eligible)} go-eligible "
        f"candidate(s); the §0 2+ branch is unexercised. Add another "
        f"conditional-go or go entry."
    )


@pytest.mark.parametrize(
    "fixture_path,expected_branch",
    [
        (
            "topic_dossier_sample.gaps.yml",
            "single-eligible-auto-prefill",
        ),
        (
            "topic_dossier_multi_eligible_sample.gaps.yml",
            "multi-eligible-ask-user",
        ),
    ],
)
def test_fixture_parses_and_drives_correct_section_0_branch(
    fixture_path: str, expected_branch: str
) -> None:
    """v0.3.15 (codex C2): both fixtures parse cleanly AND drive
    distinct §0 branches based on the count of go-eligible candidates
    (conditional-go or go). Parametrized so a future third fixture
    (e.g. all-no-go zero-eligible) can be added with one tuple
    instead of a new test function.
    """
    path = REPO_ROOT / "tests" / "fixtures" / fixture_path
    assert path.exists(), f"missing fixture: {path}"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    go_eligible = [
        g for g in data["gaps"] if g["verdict"] in {"conditional-go", "go"}
    ]
    n = len(go_eligible)
    if expected_branch == "single-eligible-auto-prefill":
        assert n == 1, (
            f"{fixture_path} should drive the auto-prefill branch "
            f"(exactly 1 go-eligible) but has {n}"
        )
    elif expected_branch == "multi-eligible-ask-user":
        assert n >= 2, (
            f"{fixture_path} should drive the ask-the-user branch "
            f"(2+ go-eligible) but has {n}"
        )
    elif expected_branch == "zero-eligible-halt":
        assert n == 0, (
            f"{fixture_path} should drive the halt branch "
            f"(0 go-eligible) but has {n}"
        )
    else:
        pytest.fail(f"unknown expected_branch: {expected_branch}")


def test_design_brief_template_has_placeholder_segments_field() -> None:
    """v0.3.15 (codex C4): design_brief frontmatter must accept an
    optional `placeholder_segments:` field so test-fit / dogfood
    placeholder content (segments filled by non-Socratic means) can be
    machine-flagged. A future tool can detect briefs with a non-empty
    list here and refuse to gate research on them.
    """
    text = DESIGN_HELPER_TEMPLATE.read_text(encoding="utf-8")
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    assert m, "design_brief_template.md missing frontmatter"
    frontmatter = m.group(1)
    assert "placeholder_segments:" in frontmatter, (
        "frontmatter missing `placeholder_segments:` — codex C4 "
        "(placeholder warning pattern) not shipped"
    )


def test_paper_memory_yaml_schemas_documents_file_sentinel_values() -> None:
    """v0.3.16 (F-cross2 fast-follow): figures.yml `file:` field has no
    natural value when figures are embedded inside .docx with no
    separable source file. v0.3.16 documents sentinel values
    (`embedded-in-manuscript`, `embedded-in-supporting-information`,
    `embedded-in-presentation`) in yaml-schemas.md so downstream
    consumers (academic-writing-skills figure-text checks) know how
    to interpret them.
    """
    schemas_doc = (
        REPO_ROOT / "skills" / "paper-memory-builder" / "references" / "yaml-schemas.md"
    )
    assert schemas_doc.exists(), f"missing yaml-schemas.md: {schemas_doc}"
    text = schemas_doc.read_text(encoding="utf-8")
    # All three sentinels must be documented in the schema doc
    for sentinel in (
        "embedded-in-manuscript",
        "embedded-in-supporting-information",
        "embedded-in-presentation",
    ):
        assert sentinel in text, (
            f"figures.yml `file:` sentinel `{sentinel}` not documented "
            f"in yaml-schemas.md — F-cross2 ship contract broken"
        )
    # W1 hardening: verify the documentation table header is present,
    # not just sentinel words floating in an example block (table could
    # be deleted while example still references sentinels)
    assert "| Sentinel | Use when |" in text, (
        "yaml-schemas.md sentinel-values TABLE header missing — table "
        "may have been removed while example YAML still references "
        "sentinels (W1 from v0.3.16 code-reviewer)"
    )


def test_paper_memory_skill_md_documents_evidence_artifact_scanning() -> None:
    """v0.3.16 (F-cross3 fast-follow): paper-memory-builder SKILL.md
    Inputs section now has a "Scanning the paper repo for evidence
    artifacts" sub-section that documents non-figure evidence types
    (simulation CSVs, analysis scripts, drawio sources, reviewer-
    response artifacts) and shows how to populate
    claims[].evidence_artifacts with their paths.
    """
    skill_md = REPO_ROOT / "skills" / "paper-memory-builder" / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    inputs_section = _extract_section(text, "## Inputs")
    assert "Scanning the paper repo" in inputs_section, (
        "SKILL.md Inputs section missing `### Scanning the paper repo for "
        "evidence artifacts` sub-section — F-cross3 ship contract broken"
    )
    # Must mention all 4 non-figure evidence types (W2 hardening:
    # was "at least 3 of 4" — tightened to require all 4 so a future
    # edit can't silently delete one type and still pass the test)
    for artifact_type in (
        "Simulation",
        "Analysis scripts",
        "Drawio",
        "Reviewer-response",
    ):
        assert artifact_type in inputs_section, (
            f"Scanning sub-section missing `{artifact_type}` — incomplete "
            f"coverage of non-figure evidence artifact types"
        )


def test_design_helper_has_brief_to_docx_script_and_skill_md_section() -> None:
    """v0.3.14 (F4 fast-follow): research-design-helper ships
    `scripts/brief_to_docx.js` as the sister generator to
    gap-to-topic's `scripts/dossier_to_docx.js`. The .docx is an
    optional convenience for human review (not contracted output).
    """
    script_path = (
        REPO_ROOT / "skills" / "research-design-helper" / "scripts" / "brief_to_docx.js"
    )
    assert script_path.exists(), (
        "research-design-helper/scripts/brief_to_docx.js missing — "
        "v0.3.14 F4 ship contract broken"
    )
    # Default stem must be design_brief, not the dossier sibling's default
    script_text = script_path.read_text(encoding="utf-8")
    assert '|| "design_brief"' in script_text, (
        "brief_to_docx.js default stem is not `design_brief` — copy "
        "from dossier_to_docx.js was incomplete (forgot to change the "
        "fallback in the ARG line)"
    )
    # SKILL.md gains the optional .docx section
    skill_text = DESIGN_HELPER_SKILL.read_text(encoding="utf-8")
    assert "## Generate .docx (optional" in skill_text, (
        "research-design-helper SKILL.md missing the `## Generate .docx "
        "(optional ...)` section that documents brief_to_docx.js usage"
    )
    # Mirror parity check (skills_data/ has the same script)
    mirror_path = (
        REPO_ROOT
        / "src"
        / "research_hub"
        / "skills_data"
        / "research-design-helper"
        / "scripts"
        / "brief_to_docx.js"
    )
    assert mirror_path.exists(), (
        "Mirror `src/research_hub/skills_data/research-design-helper/"
        "scripts/brief_to_docx.js` missing — version-sync test will fail"
    )


def test_design_helper_skill_md_segment_1_no_prefill_annotation_rule() -> None:
    """v0.3.13 (F2 fast-follow): §0 must explicitly forbid writing a
    `_PRE-FILL_`-style annotation inside the design_brief.md file
    content. The chat message signals pre-fill; the file content stays
    clean so segment 1 dialog can simply overwrite the statement with
    the sharpened RQ.

    Asserts both halves of the rule:
      (a) the word "verbatim" appears (write the statement as-is), AND
      (b) an explicit NEGATION of annotation in file content — not
          just the word "annotation". This guards against future
          rewrites that drop the prohibition while keeping the word
          (e.g. "use annotation to mark pre-fill" would be a regression
          that a presence-only check would miss).
    """
    text = DESIGN_HELPER_SKILL.read_text(encoding="utf-8")
    section_0 = _extract_section(text, "### §0 — Detect Stage 2 handoff")
    assert "verbatim" in section_0.lower(), (
        "§0 must tell the agent to write gaps[].statement verbatim"
    )
    # Negation regex: any of "do not <words> annotation", "no <words> annotation",
    # or "forbid <words> annotation" within a short window. Case-insensitive,
    # multiline. The 0-40 char window allows phrases like "Do not add any
    # `_PRE-FILL_`-style annotation".
    assert re.search(
        r"(?:do not|don't|never|no)[^.]{0,40}annotation|forbid[^.]{0,40}annotation",
        section_0,
        re.I | re.S,
    ), (
        "§0 must explicitly FORBID `_PRE-FILL_` annotations in file "
        "content (negation not found near `annotation` — a rewrite "
        "may have dropped the prohibition while keeping the word)"
    )


# ---------------------------------------------------------------------------
# Schema-reference vs fixture: the upstream skill's schema doc must
# cover the keys the fixture has.
# ---------------------------------------------------------------------------


def test_gap_to_topic_schema_reference_covers_fixture_top_level_keys(
    gaps_yaml: dict,
) -> None:
    """Defensive check — the Schema reference section in
    skills/gap-to-topic/references/dossier-template.md must document
    every top-level key the fixture contains. If a key is in the
    fixture but not in the schema reference, the contract doc is
    stale."""
    schema_text = GAP_TO_TOPIC_TEMPLATE.read_text(encoding="utf-8")
    schema_section = _extract_section(schema_text, "## Schema reference")
    for key in gaps_yaml.keys():
        # Allow the key to appear either as a top-level YAML key
        # (e.g. `dossier:` at column 0) or as inline prose
        # (e.g. "top-level `recall`"). Both are valid documentation.
        if re.search(rf"^\s*{re.escape(key)}:", schema_section, re.M):
            continue
        if f"`{key}`" in schema_section:
            continue
        pytest.fail(
            f"top-level key {key!r} appears in fixture but not in the "
            f"gap-to-topic Schema reference — contract drift"
        )


def test_gap_to_topic_schema_reference_covers_fixture_per_gap_fields(
    gaps_yaml: dict,
) -> None:
    """Per-gap-field drift detector. If gap-to-topic starts emitting
    a new per-gap key (e.g. `impact_magnitude`) but the schema
    reference forgets to document it, this test catches the drift in
    CI rather than 6 months later.

    Reads the `gaps:` block from the schema reference and asserts every
    key present in `gaps[0]` of the fixture is also documented there
    (either as a literal key under `gaps:` in the example YAML, or as
    inline prose with backticks).
    """
    schema_text = GAP_TO_TOPIC_TEMPLATE.read_text(encoding="utf-8")
    schema_section = _extract_section(schema_text, "## Schema reference")

    # Use the first gap as the canonical key-set sample
    gap_sample = gaps_yaml["gaps"][0]
    for field in gap_sample.keys():
        # The schema reference shows the field either as an indented
        # YAML key under `gaps:` — possibly with a leading list-marker
        # (e.g. `  - id: G1`) or just indented (e.g. `    name: ...`) —
        # or as inline prose with backticks (e.g. "per-gap `verdict`").
        if re.search(rf"^\s+(?:- )?{re.escape(field)}:", schema_section, re.M):
            continue
        if f"`{field}`" in schema_section:
            continue
        pytest.fail(
            f"per-gap field {field!r} appears in fixture but not in the "
            f"gap-to-topic Schema reference `gaps:` block — contract drift"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_section(markdown_text: str, heading: str) -> str:
    """Return the text from `heading` to the next `## ` heading.

    `heading` should include the leading hashes (e.g. `## Inputs`).
    """
    m = re.search(
        rf"^{re.escape(heading)}.*?(?=^## \w|\Z)",
        markdown_text,
        re.S | re.M,
    )
    if not m:
        raise AssertionError(f"section {heading!r} not found")
    return m.group(0)

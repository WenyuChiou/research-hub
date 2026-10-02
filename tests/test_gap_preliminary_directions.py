"""Offline Stage 2 alignment: executable preservation/boundary checks.

Supplied assessments are synthetic controlled inputs, not model discoveries.
Prompt-contract assertions and handoff prose tests do not prove live model
compliance, scientific sufficiency or actual user selection.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from research_hub.gap_analysis import build_cluster_digest, emit_gap_prompt, emit_cross_cluster_gap_prompt


CASES = [
    ("annual-material-monthly-question", {"question": "monthly change", "variable_granularity": "annual totals",
       "assessment": "revise", "next_check": "ask whether an annual question preserves the objective; otherwise seek monthly variables"},
     "Revise the substantive material/question mismatch; ask about annual scope or park pending monthly data."),
    ("critical-access-unknown", {"materials_status": "unknown", "score": None, "blocking": True,
       "value": "important", "next_check": "confirm required access with data owner"},
     "Park: critical access is unknown, not zero; high value does not compensate. Confirm access before commitment."),
    ("too-large-minimum-execution", {"minimum_compute_hours": 5000, "confirmed_compute_hours": 10,
       "assessment": "revise", "next_check": "compare a value-preserving minimum study to the ten-hour envelope"},
     "Revise within confirmed resources or park; do not silently promise more compute or change the objective."),
    ("novel-method-untested-effect", {"premise": "baseline error is observed", "explicit_gap_in_source": False,
       "proposed_mechanism": "adaptive correction", "effectiveness": "untested research question",
       "materials_access": "public synthetic material", "minimum_test": "same-budget baseline comparison",
       "unsupported_claim_limit": "does not establish general population validity"},
     "Candidate for user consideration: premises motivate adaptive correction; effect is untested. Same-budget comparison can answer local performance, not general population validity."),
    ("simple-sufficient-validation", {"approach": "simple matched baseline", "answerable_question": "measurement stability",
       "minimum_test": "held-out comparison", "resources": "within stated envelope"},
     "Keep the simple validation option; complexity is not a scoring bonus. User choice remains pending."),
    ("withdraw-novelty-retain-increment", {"closest_work": "already implements the same mechanism",
       "remaining_difference": "independent validation under sparse observations", "assessment": "revise",
       "next_check": "check sparse-case baselines and applicability conditions"},
     "Withdraw novelty claim; retain the useful narrower validation candidate pending closest-work and contrary checks."),
    ("mixed-portfolio", {"candidate_A": "same-budget test has suitable materials", "candidate_B": "critical access unknown",
       "candidate_B_score": None, "candidate_B_next_check": "bounded access check"},
     "Keep A as an option; park B with the access check. B does not erase A, and A's value does not clear B's blocker."),
    ("all-blocked-zero-options", {"candidate_A": "required variable absent", "candidate_B": "access unknown",
       "candidate_B_score": None, "next_check": "identify suitable material or obtain a user scope decision"},
     "Zero recommendations: explain the material/access blocks and bounded next checks; do not manufacture an option."),
]


@pytest.mark.parametrize("name,observation,response", CASES, ids=[case[0] for case in CASES])
def test_supplied_preliminary_cases_are_preserved_without_validation_or_selection(tmp_path, name, observation, response):
    from research_hub.cli_paper import _cmd_paper_gaps
    cfg = SimpleNamespace(root=tmp_path, raw=tmp_path / "raw", hub=tmp_path / "hub",
                          clusters_file=tmp_path / "clusters.yaml", research_hub_dir=tmp_path / ".research_hub")
    folder = cfg.raw / "topic"; folder.mkdir(parents=True)
    record = {"source_id": "S1", "locator": "Synthetic material dictionary §2", "observation": observation}
    note = {"title": name, "abstract": "A supplied premise; no explicit gap is named.",
            "source_records": [record], "provenance": {"research": {"geography": "unrestricted"}}}
    (folder / "paper.md").write_text("---\n" + yaml.safe_dump(note, sort_keys=False) + "---\n")
    overview = cfg.hub / "topic" / "00_overview.md"; overview.parent.mkdir(parents=True)
    overview.write_text("# Topic\n\nHuman notes.\n")
    digest = build_cluster_digest(cfg, "topic")
    prompt = emit_gap_prompt(digest)
    assert name in prompt and json.dumps(observation, ensure_ascii=False) in prompt
    # These are instructions in the actual consumer prompt, not proof that a model follows them.
    assert "A source need not explicitly name a gap" in prompt
    assert "Untested method" in prompt and "not automatic infeasibility" in prompt
    assert "which claims that result would still not establish" in prompt
    assert "variables, granularity" in prompt and "confirmed time, compute/API" in prompt
    assert "unknown is null/unassessed" in prompt and "hard\nblocker cannot be offset" in prompt
    assert "even when it is the only" in prompt
    raw = "### Actionable Research Directions\n" + response + "\n"
    with patch("research_hub.llm_cli.detect_llm_cli", return_value="fixture"), \
         patch("research_hub.llm_cli.invoke_llm_cli", return_value=raw):
        _cmd_paper_gaps(cfg, SimpleNamespace(cluster="topic", compare_cluster=None, no_llm=False, llm_cli=None))
    report = cfg.hub / "topic" / "research-gaps.md"
    assert report.with_name("research-gaps-model-output.txt").read_bytes() == raw.encode()
    snapshot = json.loads(report.with_name("research-gaps-context.json").read_text())
    assert snapshot["assessment"] == "unassessed" and snapshot["scientific_validation"] == "not-performed"
    assert snapshot["digests"][0]["papers"][0]["source_records"] == [record]
    text = report.read_text()
    boundary = text.split("## Unverified model draft", 1)[0]
    assert "requirements have not been validated" in boundary
    assert "a sole eligible candidate, is not a recorded user choice" in boundary
    assert response in text and response not in overview.read_text()


def test_cross_prompt_applies_same_preliminary_checks_without_importing_a_score_engine():
    from research_hub.gap_analysis import ClusterDigest
    prompt = emit_cross_cluster_gap_prompt(ClusterDigest("a"), ClusterDigest("b"))
    assert "Answerability:" in prompt and "Materials:" in prompt and "Execution:" in prompt
    assert "unknown is null/unassessed" in prompt
    assert "Stage2Check" not in prompt and "stage2_check" not in prompt
    assert "score != 2" not in prompt


def test_prompt_and_dossier_name_bounded_reason_specific_next_checks():
    from research_hub.gap_analysis import ClusterDigest
    prompt = emit_gap_prompt(ClusterDigest("topic"))
    for route in ("missing closest/contrary evidence", "already-realized increment",
                  "material/granularity mismatch", "resource overrun", "critical access unknown"):
        assert route in prompt
    assert "user question/scope decision" in prompt and "value-preserving minimum version" in prompt
    dossier = (Path(__file__).resolve().parents[1] / "skills/gap-to-topic/references/dossier-template.md").read_text()
    steps = dossier.split("## 7. Recommended Next Steps", 1)[1].split("\n---", 1)[0]
    for route in ("Missing closest/contrary evidence", "already realized", "Material/variable/granularity mismatch",
                  "Resource overrun", "Critical access/permission unknown"):
        assert route in steps

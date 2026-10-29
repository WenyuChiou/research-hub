"""Documentation contracts only, not statistical validation or agent-behavior tests.

These checks preserve explicit interpretation boundaries in the host-readable
skill. They do not evaluate a paper, execute a model, or prove semantic support.
"""
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
AUDIT = "research-hub/references/source-claim-audit.md"

# No private paper data or inferred scientific verdicts: these are instructions.
BOUNDARIES = [
    ("analysis-target", (
        "Keep each estimate, uncertainty interval and test result attached to its actual analysis",
        "study/part, sample or subgroup, pooled population, outcome, model and contrast",
        "Do not move a statistic between parts, subgroups or pooled analyses",
    )),
    ("non-significance", (
        "A non-significant difference does not establish equivalence or no effect",
        "An equivalence claim needs an appropriate analysis with justified equivalence bounds",
    )),
    ("effect-target", (
        "Distinguish main effects, interactions and simple/conditional effects",
        "An interaction is not an unconditional main effect",
        "one subgroup is significant and another is not does not itself establish an interaction",
    )),
    ("causal-scope", (
        "Observational mediation alone does not establish a causal mechanism",
        "causal wording needs a defensible design/identification argument",
        "retain its assumptions and unresolved confounding or temporal-order limits",
    )),
    ("target-transfer", (
        "Separate the studied population/system from the proposed target",
        "A human-only finding is not direct evidence about model-agent behavior",
        "label the transfer as an inference and identify the missing target-specific evidence",
    )),
]


def _require_clauses(text, clauses):
    normalized = " ".join(text.split())
    for clause in clauses:
        assert clause in normalized, f"missing interpretation boundary: {clause}"


@pytest.mark.parametrize("label,clauses", BOUNDARIES, ids=[row[0] for row in BOUNDARIES])
def test_source_audit_states_interpretation_boundaries(label, clauses):
    _require_clauses((ROOT / "skills" / AUDIT).read_text(encoding="utf-8"), clauses)


def test_source_audit_mirror_preserves_the_same_instructions():
    assert (ROOT / "skills" / AUDIT).read_bytes() == (
        ROOT / "src/research_hub/skills_data" / AUDIT).read_bytes()


@pytest.mark.parametrize("label,clauses", BOUNDARIES, ids=[row[0] for row in BOUNDARIES])
def test_contract_accepts_reflow_but_rejects_missing_boundary(label, clauses):
    authored = "\n".join(clauses)
    _require_clauses(authored.replace(" ", "\n"), clauses)
    with pytest.raises(AssertionError, match="missing interpretation boundary"):
        _require_clauses("\n".join(clauses[1:]), clauses)


@pytest.mark.parametrize("statement", [
    "A non-significant difference does not establish equivalence or no effect",
    "An interaction is not an unconditional main effect",
    "Observational mediation alone does not establish a causal mechanism",
    "A human-only finding is not direct evidence about model-agent behavior",
])
def test_contract_rejects_lost_negation(statement):
    with pytest.raises(AssertionError, match="missing interpretation boundary"):
        _require_clauses(statement.replace(" not ", " "), [statement])

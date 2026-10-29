"""Static contract checks for best-effort budgeted Stage 1 delivery."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills/research-hub/references/research-protocol.md"
MIRROR = ROOT / "src/research_hub/skills_data/research-hub/references/research-protocol.md"


def _text():
    return " ".join(SOURCE.read_text(encoding="utf-8").split())


def test_finalization_is_inside_total_budget_and_tiny_budgets_are_honest():
    text = _text()
    assert "reserve time for finalization inside the total budget" in text
    assert "tiny or unknown budget" in text
    assert "do not assume a reserve is available" in text


def test_reuse_requires_verified_identity_version_and_reading_scope():
    text = _text()
    assert "verify source identity, version and actual reading scope" in text
    assert "a state entry alone does not verify them" in text


def test_insufficient_budget_stops_expansion_and_discloses_partial_scope():
    text = _text()
    assert "Before starting further work, consider the remaining budget and finalization" in text
    assert "if insufficient, stop expanding and, where possible, give a brief partial result" in text
    assert "covered and unresolved needs, actual reading scope, source versions, limitations and next steps" in text


def test_hard_cutoff_may_prevent_any_output():
    text = _text()
    assert "A hard host cutoff or stuck call can prevent any output" in text
    assert "no delivery or savings are guaranteed" in text


def test_source_and_packaged_protocol_are_identical():
    assert SOURCE.read_bytes() == MIRROR.read_bytes()

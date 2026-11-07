"""Adversarial-recall search — query expansion + recall report.

Covers `research_hub.search.query_expansion.expand_query` and the
`adversarial_search` observed-yield report in `fallback.py`.
"""

from __future__ import annotations

from research_hub.search import fallback
from research_hub.search.base import SearchResult
from research_hub.search.fallback import (
    RecallReport,
    adversarial_search,
)
from research_hub.search.query_expansion import _deterministic_variants, expand_query


# --- expand_query -----------------------------------------------------------

def test_expand_query_original_is_always_first():
    out = expand_query("anchoring bias in LLMs", max_variants=3, _detect=lambda: None)
    assert out[0] == "anchoring bias in LLMs"


def test_expand_query_empty_returns_empty():
    assert expand_query("", _detect=lambda: None) == []
    assert expand_query("   ", _detect=lambda: None) == []


def test_expand_query_uses_llm_when_available():
    def fake_invoke(cli, prompt, timeout_sec=60.0):
        return "LLM cognitive bias\nanchoring effect in language models\n"

    out = expand_query(
        "anchoring bias in LLMs", max_variants=5,
        _detect=lambda: "claude", _invoke=fake_invoke,
    )
    assert out[0] == "anchoring bias in LLMs"
    assert "LLM cognitive bias" in out
    assert "anchoring effect in language models" in out


def test_expand_query_falls_back_on_llm_failure():
    def boom(cli, prompt, timeout_sec=60.0):
        raise RuntimeError("llm cli unavailable")

    out = expand_query(
        "anchoring bias in large models", max_variants=5,
        _detect=lambda: "claude", _invoke=boom,
    )
    assert out[0] == "anchoring bias in large models"
    assert len(out) > 1  # deterministic fallback supplied variants


def test_expand_query_strips_llm_list_markers():
    def fake_invoke(cli, prompt, timeout_sec=60.0):
        return "1. first variant\n- second variant\n* third variant\n"

    out = expand_query(
        "x y z", max_variants=5, _detect=lambda: "claude", _invoke=fake_invoke,
    )
    assert "first variant" in out
    assert "second variant" in out
    assert "1. first variant" not in out


def test_expand_query_caps_variant_count():
    def fake_invoke(cli, prompt, timeout_sec=60.0):
        return "\n".join(f"variant {i}" for i in range(20))

    out = expand_query(
        "topic", max_variants=4, _detect=lambda: "claude", _invoke=fake_invoke,
    )
    assert len(out) == 5  # original + 4


def test_deterministic_variants_narrow_and_broaden():
    variants = _deterministic_variants("agent based flood model", max_variants=5)
    assert '"agent based flood model"' in variants          # narrowed
    assert "agent based flood" in variants                   # broadened (drop last)
    assert "based flood model" in variants                   # broadened (drop first)


# --- adversarial_search -----------------------------------------------------

def _result(doi: str, title: str = "paper") -> SearchResult:
    return SearchResult(title=title, doi=doi)


def test_adversarial_search_unions_and_dedups(monkeypatch):
    monkeypatch.setattr(
        "research_hub.search.query_expansion.expand_query",
        lambda query, **kwargs: ["q1", "q2"],
    )
    per_variant = {
        "q1": [_result("10.1/a"), _result("10.1/b")],
        "q2": [_result("10.1/b"), _result("10.1/c")],  # b overlaps q1
    }
    monkeypatch.setattr(fallback, "search_papers", lambda variant, **kw: per_variant[variant])

    results, report = adversarial_search("q1", limit=10)

    assert sorted(r.doi for r in results) == ["10.1/a", "10.1/b", "10.1/c"]
    assert report.queries_run == 2
    assert report.total_unique == 3
    assert report.new_per_query == [2, 1]  # q2 added only 'c'


def test_adversarial_search_returns_recall_report(monkeypatch):
    monkeypatch.setattr(
        "research_hub.search.query_expansion.expand_query",
        lambda query, **kwargs: ["q1", "q2", "q3"],
    )
    monkeypatch.setattr(
        fallback, "search_papers",
        lambda variant, **kw: [_result(f"10.1/{variant}")],
    )

    results, report = adversarial_search("q1", limit=10)

    assert isinstance(report, RecallReport)
    assert report.queries_run == 3
    assert report.total_unique == 3
    assert report.variants == ["q1", "q2", "q3"]


def test_adversarial_search_empty_expansion_is_safe(monkeypatch):
    monkeypatch.setattr(
        "research_hub.search.query_expansion.expand_query",
        lambda query, **kwargs: [],
    )
    results, report = adversarial_search("", limit=10)
    assert results == []
    assert report.queries_run == 0
    assert report.confidence == "unassessed"
    assert report.saturated is False


# --- regression tests (2026-05-21 code review) ------------------------------

def test_expand_query_does_not_strip_digit_prefixed_variants():
    """Regression: the list-marker regex must not eat a leading digit.
    '3D flood model' / '10x faster training' are valid phrasings, not
    numbered list items."""
    def fake_invoke(cli, prompt, timeout_sec=60.0):
        return "3D flood model\n10x faster training\n"

    out = expand_query(
        "flood simulation", max_variants=5,
        _detect=lambda: "claude", _invoke=fake_invoke,
    )
    assert "3D flood model" in out
    assert "10x faster training" in out


def test_expand_query_still_strips_numbered_list_markers():
    """The fixed regex must still strip genuine '1. ' / '2) ' markers."""
    def fake_invoke(cli, prompt, timeout_sec=60.0):
        return "1. first variant\n2) second variant\n"

    out = expand_query(
        "topic", max_variants=5, _detect=lambda: "claude", _invoke=fake_invoke,
    )
    assert "first variant" in out
    assert "second variant" in out
    assert not any(v.startswith(("1.", "2)")) for v in out)


def test_adversarial_search_all_empty_leaves_recall_unassessed(monkeypatch):
    """Finding nothing does not measure recall, even as low confidence."""
    monkeypatch.setattr(
        "research_hub.search.query_expansion.expand_query",
        lambda query, **kwargs: ["q1", "q2", "q3"],
    )
    monkeypatch.setattr(fallback, "search_papers", lambda variant, **kw: [])

    results, report = adversarial_search("q1", limit=10)
    assert results == []
    assert report.total_unique == 0
    assert report.confidence == "unassessed"
    assert report.saturated is False

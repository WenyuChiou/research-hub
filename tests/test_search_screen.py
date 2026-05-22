"""`search --screen` — wires the fit-check BM25 relevance gate onto the
standalone `search` command.

`--screen` runs the existing `screen_relevance` gate over the retrieved
results, tags each with a relevance score + keep/screened-out verdict,
and prints a screening summary. It is recall-preserving: it never drops a
paper from the output, so a downstream caller (gap-to-topic Gate 1) can
still audit the full retrieved count.
"""

from __future__ import annotations

import json

import pytest

import research_hub.cli as cli_mod
from research_hub.cli import _search
from research_hub.dedup import DedupIndex
from research_hub.search.base import SearchResult


class _EmptyIndex:
    """A dedup index that filters nothing."""
    doi_to_hits: dict = {}


def _result(title: str, abstract: str, doi: str) -> SearchResult:
    return SearchResult(title=title, abstract=abstract, doi=doi, year=2025, source="test")


# A contaminated batch: 3 genuine LLM x water-resources papers far
# out-scoring 8 generic hydrology papers -> a blatant BM25 gap the gate
# splits on.
_GENUINE = [
    _result(
        "Large Language Models as Calibration Agents in Hydrological Modeling",
        "We employ a large language model to calibrate a hydrological model "
        "for streamflow in water resources.",
        "10.0/g1",
    ),
    _result(
        "Retrieval-augmented large language models for water resources decisions",
        "A large language model with retrieval augmentation supports water "
        "resources management decisions.",
        "10.0/g2",
    ),
    _result(
        "Evaluating large language model agents for streamflow forecasting",
        "Large language model agents are evaluated for streamflow forecasting "
        "against a hydrological model baseline.",
        "10.0/g3",
    ),
]
_HYDRO = [
    _result(f"Hydrology study {i}: streamflow and irrigation",
            "A hydrological model for streamflow and irrigation in water "
            "resources management with no language component.",
            f"10.0/h{i}")
    for i in range(8)
]
_BATCH = _GENUINE + _HYDRO
_TOPIC = "large language model water resources"


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """Run `_search` fully offline: stub config, dedup index, and the
    search backends."""
    cfg = type("Cfg", (), {"research_hub_dir": tmp_path})()
    monkeypatch.setattr(cli_mod, "get_config", lambda: cfg)
    monkeypatch.setattr(DedupIndex, "load", classmethod(lambda cls, _p: _EmptyIndex()))
    import research_hub.search as search_mod
    monkeypatch.setattr(search_mod, "search_papers", lambda *a, **k: list(_BATCH))
    return monkeypatch


def _capture_json(capsys) -> object:
    return json.loads(capsys.readouterr().out)


# ---------------------------------------------------------------------------
# --screen present
# ---------------------------------------------------------------------------

def test_screen_json_has_summary_and_per_paper_relevance(wired, capsys):
    rc = _search(_TOPIC, 20, emit_json=True, screen=True)
    assert rc == 0
    payload = _capture_json(capsys)

    # object shape: {screening_summary, results}
    assert set(payload) == {"screening_summary", "results"}
    summary = payload["screening_summary"]
    assert summary["retrieved"] == len(_BATCH)
    assert summary["kept"] + summary["screened_out"] == len(_BATCH)
    # every result carries a relevance verdict
    for row in payload["results"]:
        assert set(row["relevance"]) == {"score", "kept", "tier", "reason"}


def test_screen_is_recall_preserving(wired, capsys):
    """--screen tags but never drops: every retrieved paper is still in the
    output, even the screened-out ones."""
    _search(_TOPIC, 20, emit_json=True, screen=True)
    payload = _capture_json(capsys)
    assert len(payload["results"]) == len(_BATCH)


def test_screen_splits_the_contaminated_batch(wired, capsys):
    """On this contaminated batch the gate fires: the hydrology papers are
    marked screened-out, the genuine LLM papers kept."""
    _search(_TOPIC, 20, emit_json=True, screen=True)
    payload = _capture_json(capsys)
    by_doi = {r["doi"]: r["relevance"]["kept"] for r in payload["results"]}
    assert by_doi["10.0/g1"] is True
    assert by_doi["10.0/h0"] is False
    assert payload["screening_summary"]["screened_out"] >= 8


def test_screen_summary_printed_to_stderr(wired, capsys):
    _search(_TOPIC, 20, emit_json=True, screen=True)
    err = capsys.readouterr().err
    assert "[screen]" in err
    assert "retrieved" in err


def test_screen_composes_with_adversarial(monkeypatch, wired, capsys):
    """--screen works on top of --adversarial (which returns a different
    retrieval tuple)."""
    import research_hub.search as search_mod

    class _Recall:
        queries_run = 3
        total_unique = len(_BATCH)
        confidence = "high"
        saturated = False

    monkeypatch.setattr(
        search_mod, "adversarial_search",
        lambda *a, **k: (list(_BATCH), _Recall()),
    )
    rc = _search(_TOPIC, 20, emit_json=True, screen=True, adversarial=True)
    assert rc == 0
    payload = _capture_json(capsys)
    assert "screening_summary" in payload
    assert len(payload["results"]) == len(_BATCH)


# ---------------------------------------------------------------------------
# --screen absent — regression: behaviour unchanged
# ---------------------------------------------------------------------------

def test_no_screen_json_is_a_bare_array(wired, capsys):
    """Without --screen the JSON output is the original bare array — no
    object wrapper, no relevance key."""
    rc = _search(_TOPIC, 20, emit_json=True, screen=False)
    assert rc == 0
    payload = _capture_json(capsys)
    assert isinstance(payload, list)
    assert len(payload) == len(_BATCH)
    assert "relevance" not in payload[0]


def test_no_screen_prints_no_screening_summary(wired, capsys):
    _search(_TOPIC, 20, emit_json=True, screen=False)
    assert "[screen]" not in capsys.readouterr().err


def test_no_screen_text_output_unchanged(wired, capsys):
    """Text mode without --screen: lines carry no KEEP/SCREENED-OUT tag."""
    _search(_TOPIC, 20, emit_json=False, screen=False)
    out = capsys.readouterr().out
    assert "KEEP" not in out
    assert "SCREENED-OUT" not in out


# ---------------------------------------------------------------------------
# edge cases
# ---------------------------------------------------------------------------

def test_screen_with_to_papers_input_emits_unscreened_json(wired, monkeypatch, capsys):
    """--screen + --to-papers-input: the papers_input branch returns early
    with the unscreened results, but the screening summary still reaches
    stderr (documented asymmetry)."""
    received = {}
    monkeypatch.setattr(
        cli_mod, "_emit_papers_input_json",
        lambda results, slug: received.update(n=len(results)),
    )
    rc = _search(_TOPIC, 20, screen=True, to_papers_input=True, cluster_slug=None)
    assert rc == 0
    assert received["n"] == len(_BATCH)          # unscreened: all results passed through
    assert "[screen]" in capsys.readouterr().err  # summary still printed


def test_screen_small_batch_defers_to_cold_start(monkeypatch, wired, capsys):
    """Fewer than the gate's minimum batch size -> cold-start: all kept,
    nothing screened out."""
    import research_hub.search as search_mod
    monkeypatch.setattr(search_mod, "search_papers", lambda *a, **k: list(_GENUINE))
    _search(_TOPIC, 20, emit_json=True, screen=True)
    payload = _capture_json(capsys)
    assert payload["screening_summary"]["screened_out"] == 0
    assert all(r["relevance"]["tier"] == "cold-start" for r in payload["results"])

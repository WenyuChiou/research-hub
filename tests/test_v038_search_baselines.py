"""v0.38 search recall baselines: record metrics instead of failing."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from research_hub.utils.doi import normalize_doi

METRICS_PATH = Path(__file__).resolve().parents[1] / "metrics" / "search_recall.json"
VERSION = "v0.38.0"


@pytest.fixture
def golden_fixture() -> dict:
    path = Path(__file__).resolve().parent / "evals" / "fixtures" / "golden_llm_agents_se.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _golden_dois(golden_fixture: dict) -> set[str]:
    return {
        normalize_doi(paper["doi"])
        for paper in golden_fixture["golden_papers"]
        if paper.get("doi")
    }


def _recall_at_k(results, expected: set[str], k: int = 10) -> float:
    top_k = {normalize_doi(result.doi) for result in results[:k] if getattr(result, "doi", None)}
    if not expected:
        return 0.0
    return len(top_k & expected) / len(expected)


def _append_metric(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    else:
        existing = []
    existing.append(payload)
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def _record_recall_baseline(query: str, golden_fixture: dict) -> float:
    from tests.evals.test_search_accuracy import search_papers

    recall = _recall_at_k(search_papers(query, limit=10), _golden_dois(golden_fixture), k=10)
    _append_metric(
        METRICS_PATH,
        {
            "version": VERSION,
            "scenario": query,
            "recall_at_10": recall,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    return recall


@pytest.mark.evals
def test_recall_baseline_first_scenario_records_metric(tmp_path: Path, monkeypatch, golden_fixture):
    import tests.test_v038_search_baselines as baseline_mod
    from research_hub.search.base import SearchResult

    monkeypatch.setattr(baseline_mod, "METRICS_PATH", tmp_path / "search_recall.json")
    expected = list(_golden_dois(golden_fixture))
    query = golden_fixture["cluster_queries"][0]
    monkeypatch.setattr(
        "tests.evals.test_search_accuracy.search_papers",
        lambda _query, limit=10: [
            SearchResult(doi=expected[0], title="hit-1", source="mock"),
            SearchResult(doi=expected[1], title="hit-2", source="mock"),
            SearchResult(doi="10.9999/miss", title="miss", source="mock"),
        ][:limit],
    )

    recall = _record_recall_baseline(query, golden_fixture)
    saved = json.loads((tmp_path / "search_recall.json").read_text(encoding="utf-8"))

    assert recall == pytest.approx(2 / len(expected))
    assert saved[0]["scenario"] == query
    assert saved[0]["recall_at_10"] == pytest.approx(recall)


@pytest.mark.evals
def test_recall_baseline_second_scenario_appends_metric(tmp_path: Path, monkeypatch, golden_fixture):
    import tests.test_v038_search_baselines as baseline_mod
    from research_hub.search.base import SearchResult

    monkeypatch.setattr(baseline_mod, "METRICS_PATH", tmp_path / "search_recall.json")
    expected = list(_golden_dois(golden_fixture))
    query_a, query_b = golden_fixture["cluster_queries"][:2]

    responses = {
        query_a: [SearchResult(doi=expected[0], title="a", source="mock")],
        query_b: [
            SearchResult(doi=expected[0], title="a", source="mock"),
            SearchResult(doi=expected[1], title="b", source="mock"),
            SearchResult(doi=expected[2], title="c", source="mock"),
        ],
    }
    monkeypatch.setattr(
        "tests.evals.test_search_accuracy.search_papers",
        lambda query, limit=10: responses[query][:limit],
    )

    _record_recall_baseline(query_a, golden_fixture)
    recall = _record_recall_baseline(query_b, golden_fixture)
    saved = json.loads((tmp_path / "search_recall.json").read_text(encoding="utf-8"))

    assert len(saved) == 2
    assert saved[1]["scenario"] == query_b
    assert recall == pytest.approx(3 / len(expected))


def test_append_metric_bootstraps_empty_file(tmp_path: Path):
    payload = {"scenario": "bootstrap", "recall_at_10": 0.5}
    path = tmp_path / "metrics.json"

    _append_metric(path, payload)

    assert json.loads(path.read_text(encoding="utf-8")) == [payload]


def test_append_metric_preserves_existing_entries(tmp_path: Path):
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps([{"scenario": "old", "recall_at_10": 0.1}]), encoding="utf-8")

    _append_metric(path, {"scenario": "new", "recall_at_10": 0.9})

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert [entry["scenario"] for entry in saved] == ["old", "new"]

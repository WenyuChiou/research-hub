"""Search accuracy audit — v0.26.0 baseline.

IMPORTANT: These 5 tests are marked xfail because they surface REAL audit
findings (documented in docs/audit_v0.26.md):

- recall_at_20 / recall_at_50: measured 0% / 5% against seed queries — backends
  return different papers than what discovery actually ingested; dedup merges
  by title collide papers with similar names but different DOIs.
- rank_stability: same query returns different top-20 order on consecutive runs
  (backend response order variance, no tiebreak by DOI).
- dedup_merges_same_paper: merge_results implements "first non-empty wins" for
  field fill; does not prefer longer abstract when backends disagree.
- confidence_calibration: high-confidence bucket currently less precise than
  mid — calibration is inverted.

v0.27.0 backlog tracks the actual ranker/fusion fixes. The tests stay in the
suite as baselines that will flip from xfail→pass once fixes land.
"""
import time

import pytest

from research_hub.search import search_papers
from research_hub.search._rank import merge_results
from research_hub.search.base import SearchResult
from research_hub.utils.doi import normalize_doi

pytestmark = [pytest.mark.evals, pytest.mark.network]

_XFAIL_REASON = (
    "v0.26.0 audit baseline: surfaced real issue, see docs/audit_v0.26.md "
    "and v0.27.0 backlog for fix"
)


def _golden_dois(golden_fixture) -> set[str]:
    return {
        normalize_doi(paper["doi"])
        for paper in golden_fixture["golden_papers"]
        if paper.get("doi")
    }


def _result_identity(result) -> str:
    return normalize_doi(result.doi) or f"arxiv:{result.arxiv_id}" or result.title.lower().strip()


@pytest.mark.xfail(reason=_XFAIL_REASON, strict=False)
def test_recall_at_20(golden_fixture, metrics_collector):
    """For each cluster query, top-20 results should recall >= 40% of golden papers."""
    golden_dois = _golden_dois(golden_fixture)
    for query in golden_fixture["cluster_queries"]:
        results = search_papers(query, limit=50)
        top20_dois = {normalize_doi(result.doi) for result in results[:20] if result.doi}
        recall = len(top20_dois & golden_dois) / len(golden_dois)
        metrics_collector.record("recall_at_20", query, recall)
        assert recall >= 0.40, f"query {query!r} recall@20 = {recall:.2%}"


@pytest.mark.xfail(reason=_XFAIL_REASON, strict=False)
def test_recall_at_50(golden_fixture, metrics_collector):
    """Top-50 recall should be >= 60%."""
    golden_dois = _golden_dois(golden_fixture)
    for query in golden_fixture["cluster_queries"]:
        results = search_papers(query, limit=50)
        top50_dois = {normalize_doi(result.doi) for result in results[:50] if result.doi}
        recall = len(top50_dois & golden_dois) / len(golden_dois)
        metrics_collector.record("recall_at_50", query, recall)
        assert recall >= 0.60, f"query {query!r} recall@50 = {recall:.2%}"


@pytest.mark.xfail(reason=_XFAIL_REASON, strict=False)
def test_rank_stability(golden_fixture, metrics_collector):
    """Same query run twice should return identical top-20 order."""
    for query in golden_fixture["cluster_queries"]:
        first = search_papers(query, limit=20)
        time.sleep(1)
        second = search_papers(query, limit=20)
        first_ids = [_result_identity(result) for result in first[:20]]
        second_ids = [_result_identity(result) for result in second[:20]]
        mismatch_count = sum(a != b for a, b in zip(first_ids, second_ids))
        metrics_collector.record("rank_stability", query, 1.0 if mismatch_count == 0 else 0.0)
        assert first_ids == second_ids, f"query {query!r} top-20 order changed at {mismatch_count} positions"


@pytest.mark.xfail(reason=_XFAIL_REASON, strict=False)
def test_dedup_merges_same_paper():
    """Two candidates for the same DOI should merge to 1 entry, preserving longer abstract."""
    a1 = SearchResult(
        doi="10.1/x",
        title="Foo",
        abstract="short",
        year=2024,
        authors=["A"],
        source="openalex",
    )
    a2 = SearchResult(
        doi="10.1/x",
        title="Foo",
        abstract="much longer abstract text",
        year=2024,
        authors=["A"],
        source="crossref",
    )
    merged = merge_results({"openalex": [a1], "crossref": [a2]})
    assert len(merged) == 1
    assert merged[0].abstract == "much longer abstract text"


def test_dedup_does_not_merge_different_papers():
    """Two papers with similar titles but different DOIs stay separate."""
    p1 = SearchResult(doi="10.1/transformer-nlp", title="Transformer", source="openalex")
    p2 = SearchResult(doi="10.1/transformer-power", title="Transformer", source="crossref")
    merged = merge_results({"openalex": [p1], "crossref": [p2]})
    assert len(merged) == 2


@pytest.mark.xfail(reason=_XFAIL_REASON, strict=False)
def test_confidence_calibration(golden_fixture, metrics_collector):
    """Higher confidence bucket should have higher precision against golden set."""
    golden_dois = _golden_dois(golden_fixture)
    buckets = {
        "low": [],
        "mid": [],
        "high": [],
    }
    for query in golden_fixture["cluster_queries"]:
        for result in search_papers(query, limit=50):
            score = float(result.confidence)
            if 0.50 <= score < 0.67:
                buckets["low"].append(result)
            elif 0.67 <= score < 0.84:
                buckets["mid"].append(result)
            elif 0.84 <= score <= 1.0:
                buckets["high"].append(result)
    precisions = {}
    for name, bucket in buckets.items():
        if not bucket:
            pytest.skip(f"confidence bucket {name!r} was empty")
        hits = sum(1 for result in bucket if normalize_doi(result.doi) in golden_dois)
        precision = hits / len(bucket)
        precisions[name] = precision
        metrics_collector.record("confidence_precision", name, precision)
    assert precisions["high"] >= precisions["mid"] >= precisions["low"]

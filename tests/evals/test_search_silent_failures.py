import logging
from unittest.mock import patch

from research_hub.discover import _expand_citations
from research_hub.fit_check import compute_auto_threshold
from research_hub.search.fallback import search_papers


def test_all_backends_fail_raises_warning(caplog):
    """If every backend raises, fallback should log a warning (not silent empty list)."""
    with patch("research_hub.search.openalex.OpenAlexBackend.search") as openalex_search, patch(
        "research_hub.search.arxiv_backend.ArxivBackend.search"
    ) as arxiv_search, patch(
        "research_hub.search.semantic_scholar.SemanticScholarClient.search"
    ) as s2_search:
        openalex_search.side_effect = RuntimeError("backend 1 down")
        arxiv_search.side_effect = RuntimeError("backend 2 down")
        s2_search.side_effect = RuntimeError("backend 3 down")

        with caplog.at_level(logging.WARNING):
            results = search_papers(
                "test query",
                backends=("openalex", "arxiv", "semantic-scholar"),
            )

    assert results == []
    assert any(
        ("backend" in record.message.lower()) and record.levelname == "WARNING"
        for record in caplog.records
    ), "Expected at least one WARNING log when all backends fail"


def test_auto_threshold_not_below_floor():
    """compute_auto_threshold with all-1 scores should clamp to 2."""
    scores = [1, 1, 1, 1, 1]
    threshold = compute_auto_threshold(scores)
    assert threshold >= 2


def test_citation_expansion_failure_logged(caplog):
    """If all citation-graph calls fail, a WARNING should be logged."""
    with patch(
        "research_hub.citation_graph.CitationGraphClient.get_references",
        side_effect=RuntimeError("references down"),
    ), patch(
        "research_hub.citation_graph.CitationGraphClient.get_citations",
        side_effect=RuntimeError("citations down"),
    ):
        with caplog.at_level(logging.WARNING):
            results = _expand_citations(["10.1/example-doi"], per_seed_limit=5)

    assert results == []
    assert any("citation expansion" in record.message.lower() for record in caplog.records)

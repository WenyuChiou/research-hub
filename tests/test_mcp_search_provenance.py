"""Offline MCP search provenance regressions with synthetic observations.

These exercise the registered function and production merge/serialization,
not a live MCP host, provider response, source truth, or literature recall.
"""

import json
from types import SimpleNamespace

import pytest

from research_hub import mcp_server
from research_hub.dedup import DedupHit, DedupIndex
from research_hub.search.base import SearchResult
from research_hub.verify import VerificationResult
from tests._mcp_helpers import _get_mcp_tool


DOI = "10.1234/mcp-provenance-fixture"


@pytest.fixture
def configured_search(tmp_path, monkeypatch):
    cfg = SimpleNamespace(research_hub_dir=tmp_path / ".research_hub")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    tool = _get_mcp_tool(mcp_server.mcp, "search_papers")
    assert tool is not None  # Exercise the registered tool, with no module fallback.
    return tool.fn, cfg


@pytest.mark.parametrize(
    "abstract,abstract_source,year,metadata_year",
    [
        ("Observed text", "crossref", 2026, 2025),
        ("Observed text", "openalex", 2026, 2026),
        ("Unattributed text", "", 2026, None),
        ("", "", None, None),
        ("Observed text", "crossref", None, 2025),
    ],
)
def test_registered_search_preserves_observed_and_unknown_fields(
    configured_search, monkeypatch, abstract, abstract_source, year, metadata_year,
):
    search, _ = configured_search
    result = SearchResult(
        title="Synthetic candidate", doi=DOI, abstract=abstract,
        abstract_source=abstract_source, year=year, metadata_year=metadata_year,
        source="openalex", found_in=["openalex", "crossref"],
    )
    monkeypatch.setattr("research_hub.search.search_papers", lambda *a, **kw: [result])

    rows = json.loads(json.dumps(search("synthetic")))

    assert rows == [{
        "title": "Synthetic candidate", "doi": DOI, "arxiv_id": "",
        "authors": [], "year": year, "metadata_year": metadata_year,
        "venue": "", "citation_count": 0, "url": "", "pdf_url": "",
        "abstract": abstract, "abstract_source": abstract_source,
        "source": "openalex", "confidence": 0.5,
        "found_in": ["openalex", "crossref"], "doc_type": "",
        "already_in_vault": False,
    }]


@pytest.mark.parametrize("abstract_source", ["crossref", ""])
def test_search_merge_keeps_abstract_attribution_separate_from_aggregate_source(
    configured_search, monkeypatch, abstract_source,
):
    search, _ = configured_search
    from research_hub.search import fallback

    class MetadataBackend:
        def search(self, *args, **kwargs):
            return [SearchResult(title="Synthetic candidate", doi=DOI,
                                 source="openalex", year=2026, metadata_year=2025)]

    class AbstractBackend:
        def search(self, *args, **kwargs):
            return [SearchResult(title="Synthetic candidate", doi=DOI,
                                 abstract="Other provider text", abstract_source=abstract_source,
                                 source="crossref", year=2024, metadata_year=2023)]

    monkeypatch.setitem(fallback._BACKEND_REGISTRY, "openalex", MetadataBackend)
    monkeypatch.setitem(fallback._BACKEND_REGISTRY, "crossref", AbstractBackend)

    # Real orchestration, merge, ranking and MCP function. Only provider calls
    # are replaced; unknown attribution must not be inferred from a backend name.
    rows = json.loads(json.dumps(search("synthetic", backends=["openalex", "crossref"])))

    assert len(rows) == 1
    row = rows[0]
    assert row["abstract"] == "Other provider text"
    assert row["abstract_source"] == abstract_source
    assert row["source"] == "openalex"
    assert (row["year"], row["metadata_year"]) == (2026, 2025)
    assert row["found_in"] == ["openalex", "crossref"]


@pytest.mark.parametrize("ok", [True, False])
def test_identifier_verification_and_existing_vault_flags_remain_independent(
    configured_search, monkeypatch, ok,
):
    search, cfg = configured_search
    index = DedupIndex(doi_to_hits={DOI: [DedupHit(source="zotero", doi=DOI)]})
    index.save(cfg.research_hub_dir / "dedup_index.json")
    monkeypatch.setattr("research_hub.search.search_papers", lambda *a, **kw: [
        SearchResult(title="Synthetic candidate", doi=DOI, source="openalex",
                     abstract="Unattributed text", year=2026),
    ])
    checked = []

    def verify_doi(doi):
        checked.append(doi)
        return VerificationResult(ok=ok, source="doi.org", reason="Synthetic result")

    monkeypatch.setattr("research_hub.verify.verify_doi", verify_doi)

    row = search("synthetic", verify=True)[0]

    assert checked == [DOI]
    assert row["already_in_vault"] is True
    assert row["verified"] is ok
    assert row["verification_reason"] == "Synthetic result"
    assert row["abstract_source"] == ""
    assert row["metadata_year"] is None


def test_empty_search_retains_empty_list_contract(configured_search, monkeypatch):
    search, _ = configured_search
    monkeypatch.setattr("research_hub.search.search_papers", lambda *a, **kw: [])
    assert search("synthetic") == []


def test_search_error_retains_error_contract(configured_search, monkeypatch):
    search, _ = configured_search

    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic search failure")

    monkeypatch.setattr("research_hub.search.search_papers", fail)
    result = search("synthetic")
    assert result == {"error": "Synthetic search failure"}

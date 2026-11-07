"""Synthetic HTTP regressions for exact arXiv version binding, not live acceptance."""

from dataclasses import asdict
import json
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock

import pytest
import responses

from research_hub.search.arxiv_backend import ARXIV_BASE, ArxivBackend
from research_hub.search.base import SearchResult
from research_hub.search.enrich import enrich_candidates


def _feed(identifier="2411.12345v1", *, abstract="Synthetic version one text", doi=""):
    return f'''<feed xmlns="http://www.w3.org/2005/Atom"
        xmlns:arxiv="http://arxiv.org/schemas/atom"><entry>
        <id>http://arxiv.org/abs/{identifier}</id>
        <title>Synthetic version fixture</title><summary>{abstract}</summary>
        <published>2024-11-01T00:00:00Z</published>
        <arxiv:doi>{doi}</arxiv:doi></entry></feed>'''


@responses.activate
def test_exact_version_is_requested_and_kept_in_pdf_handoff():
    responses.get(ARXIV_BASE, body=_feed())
    result = ArxivBackend(delay_seconds=0).get_paper(" 2411.12345v1 ")
    assert parse_qs(urlparse(responses.calls[0].request.url).query)["id_list"] == ["2411.12345v1"]
    assert result is not None
    assert result.arxiv_id == "2411.12345"  # Work-level dedup key remains compatible.
    row = json.loads(json.dumps(asdict(result)))
    assert row["url"] == "http://arxiv.org/abs/2411.12345v1"
    assert row["pdf_url"] == "https://arxiv.org/pdf/2411.12345v1.pdf"
    assert row["abstract_source"] == "arxiv"


@responses.activate
@pytest.mark.parametrize("returned", ["2411.12345v2", "2411.12345", "2411.99999v1"])
def test_exact_version_rejects_different_or_unbound_response(returned):
    responses.get(ARXIV_BASE, body=_feed(returned))
    assert ArxivBackend(delay_seconds=0).get_paper("2411.12345v1") is None


@responses.activate
def test_unversioned_lookup_keeps_observed_version_without_pinning_request():
    responses.get(ARXIV_BASE, body=_feed("2411.12345v3"))
    result = ArxivBackend(delay_seconds=0).get_paper("2411.12345")
    assert parse_qs(urlparse(responses.calls[0].request.url).query)["id_list"] == ["2411.12345"]
    assert result.pdf_url == "https://arxiv.org/pdf/2411.12345v3.pdf"


@responses.activate
def test_unversioned_lookup_rejects_different_work():
    responses.get(ARXIV_BASE, body=_feed("2411.99999v3"))
    assert ArxivBackend(delay_seconds=0).get_paper("2411.12345") is None


@responses.activate
def test_missing_observed_version_is_not_invented():
    responses.get(ARXIV_BASE, body=_feed("2411.12345", abstract=""))
    result = ArxivBackend(delay_seconds=0).get_paper("2411.12345")
    assert result.pdf_url == "https://arxiv.org/pdf/2411.12345.pdf"
    assert result.abstract_source == ""


@responses.activate
def test_search_pdf_is_bound_to_observed_atom_version():
    responses.get(ARXIV_BASE, body=_feed("2411.12345v3"))
    row = ArxivBackend(delay_seconds=0).search("synthetic")[0]
    assert row.pdf_url == "https://arxiv.org/pdf/2411.12345v3.pdf"
    assert row.arxiv_id == "2411.12345"


@responses.activate
def test_foreign_atom_identity_is_not_treated_as_arxiv():
    responses.get(ARXIV_BASE, body=_feed().replace("http://arxiv.org/", "https://example.invalid/"))
    assert ArxivBackend(delay_seconds=0).get_paper("2411.12345v1") is None


@pytest.fixture
def other_backends(monkeypatch):
    result = SearchResult(title="Unbound work metadata", arxiv_id="2411.12345", abstract="Latest text", source="openalex")
    openalex = Mock(return_value=result)
    semantic_scholar = Mock(return_value=result)
    recovery = Mock(side_effect=AssertionError("Unbound recovery must not replace pinned content"))
    monkeypatch.setattr("research_hub.search.enrich.OpenAlexBackend.get_paper", openalex)
    monkeypatch.setattr("research_hub.search.enrich.SemanticScholarClient.get_paper", semantic_scholar)
    monkeypatch.setattr("research_hub.search.enrich.recover_abstract", recovery)
    return openalex, semantic_scholar, recovery


@responses.activate
def test_enrichment_uses_exact_arxiv_instead_of_first_unversioned_provider(other_backends):
    responses.get(ARXIV_BASE, body=_feed())
    result = enrich_candidates(["2411.12345v1"])[0]
    assert result.abstract == "Synthetic version one text"
    assert result.pdf_url.endswith("2411.12345v1.pdf")
    for backend in other_backends:
        backend.assert_not_called()


@responses.activate
@pytest.mark.parametrize("backends", [("openalex", "semantic-scholar"), ()])
def test_pinned_request_without_arxiv_enabled_stays_unresolved(backends, other_backends):
    assert enrich_candidates(["2411.12345v1"], backends=backends) == [None]
    assert len(responses.calls) == 0
    for backend in other_backends:
        backend.assert_not_called()


@responses.activate
@pytest.mark.parametrize("body,status", [(_feed("2411.12345v2"), 200), ("", 503), ("not xml", 200)])
def test_pinned_failure_does_not_fall_back_to_work_level_metadata(body, status, other_backends):
    responses.get(ARXIV_BASE, body=body, status=status)
    assert enrich_candidates(["2411.12345v1"]) == [None]
    assert len(responses.calls) == 1
    for backend in other_backends:
        backend.assert_not_called()


@responses.activate
def test_pinned_empty_abstract_does_not_borrow_journal_doi_text(other_backends):
    responses.get(ARXIV_BASE, body=_feed(abstract="", doi="10.1234/journal-version"))
    result = enrich_candidates(["2411.12345v1"])[0]
    assert result is not None and result.abstract == "" and result.abstract_source == ""
    for backend in other_backends:
        backend.assert_not_called()


def test_unversioned_enrichment_retains_existing_provider_precedence(other_backends):
    result = enrich_candidates(["2411.12345"])[0]
    assert result.source == "openalex"
    other_backends[0].assert_called_once_with("2411.12345")
    other_backends[1].assert_not_called()
    other_backends[2].assert_not_called()


@responses.activate
@pytest.mark.parametrize("matched", [True, False])
def test_cli_and_audit_keep_pinned_request_and_only_matching_result(
    matched, other_backends, tmp_path, capsys, monkeypatch
):
    from research_hub.cli import main

    responses.get(ARXIV_BASE, body=_feed("2411.12345v1" if matched else "2411.12345v2"))
    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(tmp_path))
    audit_dir = tmp_path / "audit"
    assert main(["enrich", "2411.12345v1", "--audit-output", str(audit_dir)]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == int(matched)
    if matched:
        assert rows[0]["pdf_url"].endswith("2411.12345v1.pdf")
    events = [json.loads(line) for line in (audit_dir / "events.jsonl").read_text().splitlines()]
    finished = next(e for e in events if e["event"] == "finished" and e["operation"] == "enrich-candidates")
    artifact = next(a for a in finished["artifacts"] if a["path"].endswith(".json"))
    saved = json.loads((audit_dir / artifact["path"]).read_text())
    assert saved == (rows if matched else [None])
    assert parse_qs(urlparse(responses.calls[0].request.url).query)["id_list"] == ["2411.12345v1"]
    assert len(responses.calls) == 1
    for backend in other_backends:
        backend.assert_not_called()


@responses.activate
@pytest.mark.parametrize("matched", [True, False])
def test_mcp_entrypoint_keeps_only_matching_version(matched, other_backends):
    from research_hub.mcp_server import enrich_candidates as mcp_enrich

    responses.get(ARXIV_BASE, body=_feed("2411.12345v1" if matched else "2411.12345v2"))
    rows = mcp_enrich(["2411.12345v1"])
    assert isinstance(rows, list) and len(rows) == int(matched)
    if matched:
        assert rows[0]["url"].endswith("2411.12345v1")
        assert rows[0]["pdf_url"].endswith("2411.12345v1.pdf")
        assert rows[0]["abstract_source"] == "arxiv"
    for backend in other_backends:
        backend.assert_not_called()

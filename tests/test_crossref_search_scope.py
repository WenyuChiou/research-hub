"""Synthetic request-sensitive checks, not evidence of live search recall."""

import json
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from research_hub.search.crossref import CROSSREF_BASE, CrossrefBackend
from research_hub.search.fallback import search_papers


def _work(kind, year=2025):
    return {
        "DOI": f"10.1234/synthetic-{kind}",
        "title": [f"Synthetic {kind} paper"],
        "author": [{"given": "Test", "family": "Author"}],
        "issued": {"date-parts": [[year]]},
        "type": kind,
        "event": {"name": "Synthetic conference"} if kind == "proceedings-article" else {},
    }


def _register_search(kinds=("journal-article", "proceedings-article", "posted-content")):
    def respond(request):
        query = parse_qs(urlparse(request.url).query)
        filters = query.get("filter", [""])[0].split(",")
        restricted_type = next((v.split(":", 1)[1] for v in filters if v.startswith("type:")), None)
        items = [_work(kind) for kind in kinds if restricted_type is None or kind == restricted_type]
        return 200, {"Content-Type": "application/json"}, json.dumps({"message": {"items": items}})

    responses.add_callback(responses.GET, CROSSREF_BASE, callback=respond)


@responses.activate
@pytest.mark.parametrize("years,expected_filter", [
    ({}, None),
    ({"year_from": 2024}, "from-pub-date:2024-01-01"),
    ({"year_to": 2026}, "until-pub-date:2026-12-31"),
    ({"year_from": 2024, "year_to": 2026}, "from-pub-date:2024-01-01,until-pub-date:2026-12-31"),
])
def test_generic_crossref_query_does_not_silently_restrict_publication_type(years, expected_filter):
    _register_search()
    results = CrossrefBackend(delay_seconds=0).search("synthetic agents", limit=9, **years)
    query = parse_qs(urlparse(responses.calls[0].request.url).query)
    assert query.get("filter", [None])[0] == expected_filter
    assert query["query"] == ["synthetic agents"] and query["rows"] == ["9"]
    assert {r.doc_type for r in results} == {"journal-article", "proceedings-article", "posted-content"}
    assert next(r for r in results if r.doc_type == "proceedings-article").venue == "Synthetic conference"


@responses.activate
@pytest.mark.parametrize("limit,expected", [(5, 5), (150, 100)])
def test_existing_rows_cap_and_journal_parsing_are_preserved(limit, expected):
    _register_search(("journal-article",))
    result = CrossrefBackend(delay_seconds=0).search("synthetic", limit=limit)[0]
    query = parse_qs(urlparse(responses.calls[0].request.url).query)
    assert query["rows"] == [str(expected)]
    assert result.doc_type == "journal-article"
    assert result.doi == "10.1234/synthetic-journal-article"


@responses.activate
@pytest.mark.parametrize("excluded,expected", [
    ((), {"journal-article", "proceedings-article", "posted-content"}),
    (("posted-content",), {"journal-article", "proceedings-article"}),
    (("proceedings-article",), {"journal-article", "posted-content"}),
])
def test_search_orchestrator_retains_explicit_type_exclusions(excluded, expected):
    _register_search()
    results = search_papers("synthetic", backends=("crossref",), exclude_types=excluded)
    assert {r.doc_type for r in results} == expected
    assert all(r.found_in == ["crossref"] and r.confidence == 0.5 for r in results)


@responses.activate
@pytest.mark.parametrize("peer_reviewed", [False, True])
def test_normal_cli_and_audit_retain_conference_results_and_requested_filters(
    peer_reviewed, tmp_path, monkeypatch, capsys,
):
    from research_hub.cli import main

    _register_search()
    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(tmp_path))
    audit_dir = tmp_path / "audit"
    args = ["search", "synthetic", "--backend", "crossref", "--json", "--audit-output", str(audit_dir)]
    if peer_reviewed:
        args.append("--peer-reviewed")
    assert main(args) == 0
    rows = json.loads(capsys.readouterr().out)
    expected = {"journal-article", "proceedings-article"}
    if not peer_reviewed:
        expected.add("posted-content")
    assert {r["doc_type"] for r in rows} == expected
    events = [json.loads(line) for line in (audit_dir / "events.jsonl").read_text().splitlines()]
    event = next(e for e in events if e["event"] == "finished" and e["operation"] == "search-query")
    artifact = next(a for a in event["artifacts"] if a["path"].endswith(".json"))
    assert json.loads((audit_dir / artifact["path"]).read_text()) == rows
    assert len(responses.calls) == 1


@responses.activate
@pytest.mark.parametrize("exclude_types", [None, ["posted-content"]])
def test_mcp_search_entrypoint_retains_publication_scope(exclude_types, monkeypatch, tmp_path):
    from research_hub.mcp_server import search_papers as mcp_search

    _register_search()
    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(tmp_path))
    rows = mcp_search("synthetic", backends=["crossref"], exclude_types=exclude_types)
    assert isinstance(rows, list)
    expected = {"journal-article", "proceedings-article"}
    if not exclude_types:
        expected.add("posted-content")
    assert {r["doc_type"] for r in rows} == expected
    assert len(responses.calls) == 1

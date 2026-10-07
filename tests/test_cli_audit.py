"""Exercise the optional public CLI audit surface with real offline responses."""

import json
import re

import pytest
import requests
import responses

from research_hub.cli import main
from research_hub.dedup import DedupIndex
from research_hub.citation_graph import CitationGraphClient
from research_hub.search.semantic_scholar import SemanticScholarClient


def records(directory):
    return [
        json.loads(line)
        for line in (directory / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    class Config:
        research_hub_dir = tmp_path / "workspace"

    Config.research_hub_dir.mkdir()
    DedupIndex().save(Config.research_hub_dir / "dedup_index.json")
    monkeypatch.setattr("research_hub.cli.get_config", lambda: Config())
    monkeypatch.setattr(CitationGraphClient, "_throttle", lambda self: None)
    monkeypatch.setattr("research_hub.citation_graph.time.sleep", lambda value: None)
    monkeypatch.setattr(SemanticScholarClient, "_throttle", lambda self: None)
    return Config()


@responses.activate
@pytest.mark.parametrize("command", ["references", "cited-by"])
@pytest.mark.parametrize(
    "status,expected",
    [(200, "success_empty"), (404, "not_found"), (429, "rate_limited")],
)
def test_citation_default_output_compatible_but_audit_distinguishes(
    cfg, tmp_path, capsys, command, status, expected
):
    edge = "references" if command == "references" else "citations"
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:10.5555/synthetic/{edge}"
    responses.get(url, json={"data": []}, status=status)
    args = [command, "10.5555/synthetic", "--json"]
    assert main(args) == 0
    default = capsys.readouterr().out
    directory = tmp_path / "audit"
    assert main([*args, "--audit-output", str(directory)]) == 0
    assert capsys.readouterr().out == default == "[]\n"
    result = next(
        e
        for e in records(directory)
        if e["event"] == "finished" and e["operation"] == command
    )
    assert result["outcome"] == expected


@responses.activate
def test_multi_backend_partial_failure_preserves_duplicates_and_variants(
    cfg, tmp_path, monkeypatch, capsys
):
    responses.get(
        "https://api.openalex.org/works",
        json={
            "results": [
                {
                    "id": "synthetic:a",
                    "doi": "https://doi.org/10.5555/synthetic",
                    "title": "Synthetic shared work",
                    "publication_year": 2025,
                }
            ]
        },
    )
    responses.get(
        "https://api.crossref.org/works",
        json={
            "message": {
                "items": [
                    {
                        "DOI": "10.5555/synthetic",
                        "title": ["Synthetic shared work"],
                        "issued": {"date-parts": [[2025]]},
                    }
                ]
            }
        },
    )
    responses.get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        status=429,
        json={"message": "wait"},
    )
    monkeypatch.setattr(
        "research_hub.search.query_expansion.expand_query",
        lambda *args, **kwargs: ["synthetic question", "synthetic alternative"],
    )
    directory = tmp_path / "audit"
    assert (
        main(
            [
                "search",
                "synthetic question",
                "--backend",
                "openalex,crossref,semantic-scholar",
                "--adversarial",
                "--json",
                "--audit-output",
                str(directory),
            ]
        )
        == 0
    )
    assert len(json.loads(capsys.readouterr().out)) == 1
    events = records(directory)
    queries = [
        e
        for e in events
        if e["operation"] == "search-query" and e["event"] == "started"
    ]
    assert [e["parameters"]["args"][0] for e in queries] == [
        "synthetic question",
        "synthetic alternative",
    ]
    backend = [
        e
        for e in events
        if e["operation"] == "backend-search" and e["event"] == "finished"
    ]
    assert len(backend) == 6
    assert sum(e["outcome"] == "rate_limited" for e in backend) == 2
    assert sum(e["record_count"] == 1 for e in backend) == 4
    assert all(e["artifacts"] for e in backend)
    assert events[-1]["outcome"] == "partial"


@responses.activate
@pytest.mark.parametrize("payload", ["not json", '{"unexpected": []}'])
def test_bad_response_not_reported_as_empty(cfg, tmp_path, capsys, payload):
    responses.get(
        "https://api.openalex.org/works", body=payload, content_type="application/json"
    )
    directory = tmp_path / "audit"
    assert (
        main(
            [
                "search",
                "synthetic",
                "--backend",
                "openalex",
                "--json",
                "--audit-output",
                str(directory),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == []
    assert any(
        e.get("outcome") == "parse_error" and e["operation"] == "backend-search"
        for e in records(directory)
    )


@responses.activate
def test_enrich_records_fallback_and_verify_is_only_resolver_evidence(
    cfg, tmp_path, capsys
):
    responses.get(
        "https://api.openalex.org/works/https://doi.org/10.5555%2Fsynthetic", status=404
    )
    responses.get(
        "https://api.semanticscholar.org/graph/v1/paper/10.5555/synthetic",
        json={
            "title": "Synthetic work",
            "abstract": "Synthetic abstract.",
            "externalIds": {"DOI": "10.5555/synthetic"},
        },
    )
    directory = tmp_path / "enrich"
    assert (
        main(
            [
                "enrich",
                "10.5555/synthetic",
                "--backend",
                "openalex,semantic-scholar",
                "--audit-output",
                str(directory),
            ]
        )
        == 0
    )
    assert len(json.loads(capsys.readouterr().out)) == 1
    attempts = [
        e
        for e in records(directory)
        if e["operation"] == "backend-lookup" and e["event"] == "finished"
    ]
    assert [e["outcome"] for e in attempts] == ["not_found", "success"]
    responses.head("https://doi.org/10.5555/synthetic", status=200)
    verify = tmp_path / "verify"
    assert (
        main(["verify", "--doi", "10.5555/synthetic", "--audit-output", str(verify)])
        == 0
    )
    event = next(
        e
        for e in records(verify)
        if e["operation"] == "verify-doi" and e["event"] == "finished"
    )
    result = json.loads((verify / event["artifacts"][0]["path"]).read_text())
    assert result["source"] == "doi.org" and result["title_match"] == 0.0
    assert "identity_verified" not in result


@responses.activate
@pytest.mark.parametrize(
    "backend,payload",
    [
        ("openalex", {"results": []}),
        ("crossref", {"message": {"items": []}}),
        ("semantic-scholar", {"data": []}),
        ("dblp", {"result": {"hits": {"@total": "0"}}}),
        ("arxiv", '<feed xmlns="http://www.w3.org/2005/Atom"/>'),
        ("cinii", '<feed xmlns="http://www.w3.org/2005/Atom"/>'),
        ("biorxiv", {"collection": []}),
        ("medrxiv", {"collection": []}),
        ("chemrxiv", []),
        ("eric", {"response": {"docs": []}}),
        ("nasa-ads", {"response": {"docs": []}}),
        ("kci", {"articles": []}),
        ("pubmed", {"esearchresult": {"idlist": []}}),
        ("ssrn", {"papers": []}),
    ],
)
def test_registry_empty_response_contracts(
    cfg, tmp_path, monkeypatch, capsys, backend, payload
):
    monkeypatch.setenv("ADS_DEV_KEY", "synthetic-test-key")
    kwargs = (
        {"body": payload, "content_type": "application/atom+xml"}
        if isinstance(payload, str)
        else {"json": payload}
    )
    for method in (responses.GET, responses.POST):
        responses.add(method, re.compile(r"https?://.*"), **kwargs)
    directory = tmp_path / "audit"
    assert (
        main(
            [
                "search",
                "synthetic",
                "--backend",
                backend,
                "--json",
                "--audit-output",
                str(directory),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == []
    result = next(
        e
        for e in records(directory)
        if e["event"] == "finished" and e["operation"] == "backend-search"
    )
    assert result["outcome"] == "success_empty"


@responses.activate
@pytest.mark.parametrize(
    "backend",
    [
        "openalex",
        "crossref",
        "semantic-scholar",
        "dblp",
        "arxiv",
        "cinii",
        "biorxiv",
        "medrxiv",
        "chemrxiv",
        "eric",
        "nasa-ads",
        "kci",
        "pubmed",
        "ssrn",
        "repec",
        "websearch",
    ],
)
def test_all_requests_backends_preserve_429(
    cfg, tmp_path, monkeypatch, capsys, backend
):
    monkeypatch.setenv("ADS_DEV_KEY", "synthetic-test-key")
    for key in (
        "TAVILY_API_KEY",
        "BRAVE_SEARCH_API_KEY",
        "GOOGLE_CSE_API_KEY",
        "GOOGLE_CSE_CX",
    ):
        monkeypatch.delenv(key, raising=False)
    for method in (responses.GET, responses.POST):
        responses.add(
            method, re.compile(r"https?://.*"), status=429, json={"message": "wait"}
        )
    directory = tmp_path / "audit"
    assert (
        main(
            [
                "search",
                "synthetic",
                "--backend",
                backend,
                "--json",
                "--audit-output",
                str(directory),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == []
    result = next(
        e
        for e in records(directory)
        if e["event"] == "finished" and e["operation"] == "backend-search"
    )
    assert result["outcome"] == "rate_limited"


@responses.activate
def test_cli_timeout_and_unknown_backend_are_not_empty_success(cfg, tmp_path, capsys):
    responses.get(
        "https://api.openalex.org/works", body=requests.Timeout("synthetic timeout")
    )
    directory = tmp_path / "audit"
    assert (
        main(
            [
                "search",
                "synthetic",
                "--backend",
                "openalex,unknown-name",
                "--json",
                "--audit-output",
                str(directory),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == []
    outcomes = {
        e["backend"]: e["outcome"]
        for e in records(directory)
        if e["operation"] == "backend-search" and e["event"] == "finished"
    }
    assert outcomes == {"openalex": "timeout", "unknown-name": "unknown"}

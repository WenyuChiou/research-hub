"""Preserve observed search metadata through real offline production paths.

HTTP records are synthetic. These checks establish plumbing and attribution,
not current provider behavior, source truth or scientific literature coverage.
"""

from dataclasses import asdict, replace
import json

import pytest
import responses

from research_hub.audit import audit_command
from research_hub.discover import _search_result_to_candidate, _to_papers_input, apply_variations
from research_hub.search._rank import merge_results
from research_hub.search.base import SearchResult
from research_hub.search.fallback import search_papers


_DOI = "10.1234/provenance-fixture"
_ABSTRACT = "Synthetic observed abstract"
_BACKEND_ORDERS = [("openalex", "crossref"), ("crossref", "openalex")]


def _responses():
    # Controlled parser fixtures, not evidence of the current live API shape.
    # Crossref's search select excludes abstract, so its fixture omits it.
    responses.get("https://api.openalex.org/works", json={"results": [{
        "id": "https://openalex.org/W1234567890",
        "doi": f"https://doi.org/{_DOI}",
        "title": "Synthetic provenance paper",
        "publication_year": 2026,
        "biblio": {"issued_date": "2025-12-01"},
        "abstract_inverted_index": {"Synthetic": [0], "observed": [1], "abstract": [2]},
    }]})
    responses.get("https://api.crossref.org/works", json={"message": {"items": [{
        "DOI": _DOI,
        "title": ["Synthetic provenance paper"],
        "issued": {"date-parts": [[2026]]},
    }]}})


@pytest.mark.parametrize("metadata_year,abstract_source", [(2025, "openalex"), (None, "")])
def test_dataclass_copy_and_json_keep_observed_or_unknown_metadata(metadata_year, abstract_source):
    original = SearchResult(
        title="Synthetic", abstract=_ABSTRACT, year=2026,
        metadata_year=metadata_year, abstract_source=abstract_source,
    )
    copied = replace(original, confidence=0.75)
    assert copied.metadata_year == metadata_year
    assert copied.abstract_source == abstract_source
    encoded = json.loads(json.dumps(asdict(copied)))
    assert encoded["metadata_year"] == metadata_year
    assert encoded["abstract_source"] == abstract_source
    assert original.confidence == 0.5


@pytest.mark.parametrize("incoming_source", ["crossref", ""])
def test_filled_abstract_keeps_its_own_provenance(incoming_source):
    base = SearchResult(title="Synthetic", doi=_DOI, year=2026, metadata_year=2025)
    incoming = SearchResult(
        title="Synthetic", doi=_DOI, abstract=_ABSTRACT,
        abstract_source=incoming_source, year=2024, metadata_year=2023,
    )
    result = merge_results({"openalex": [base], "crossref": [incoming]})[0]
    assert result.abstract == _ABSTRACT
    assert result.abstract_source == incoming_source  # Unknown is not inferred from the backend key.
    assert (result.year, result.metadata_year) == (2026, 2025)
    assert base.abstract == "" and incoming.metadata_year == 2023


def test_retained_abstract_does_not_borrow_another_records_source():
    original = SearchResult(title="Synthetic", doi=_DOI, abstract="First text", abstract_source="openalex")
    incoming = SearchResult(title="Synthetic", doi=_DOI, abstract="Other text", abstract_source="crossref")
    result = merge_results({"openalex": [original], "crossref": [incoming]})[0]
    assert (result.abstract, result.abstract_source) == ("First text", "openalex")


@responses.activate
@pytest.mark.parametrize("backends", _BACKEND_ORDERS)
@pytest.mark.parametrize("audit_enabled", [False, True])
def test_search_merge_and_audit_preserve_provenance(tmp_path, backends, audit_enabled):
    _responses()
    directory = tmp_path / "audit" if audit_enabled else None
    with audit_command(directory, ["search", "synthetic"]) as command:
        results = search_papers("synthetic", backends=backends)
        command.exit_code = 0
    assert len(responses.calls) == 2
    assert len(results) == 1
    result = results[0]
    expected_metadata_year = 2025 if backends[0] == "openalex" else 2026
    assert result.source == backends[0]
    assert result.abstract == _ABSTRACT
    assert result.abstract_source == "openalex"
    assert result.metadata_year == expected_metadata_year
    assert result.found_in == list(backends)
    assert result.confidence == 0.75
    candidate = _search_result_to_candidate(result)
    paper = _to_papers_input([candidate], None)[0]
    assert paper["abstract_source"] == "openalex"
    assert paper["metadata_year"] == expected_metadata_year
    if expected_metadata_year == 2025:
        assert paper["year_drift_warning"] == "ingest_year=2026 differs from doi_lookup_year=2025"
    else:
        assert "year_drift_warning" not in paper
    if audit_enabled:
        events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
        event = next(e for e in events if e["event"] == "finished" and e["operation"] == "search-query")
        artifact = next(a for a in event["artifacts"] if a["path"].endswith(".json"))
        row = json.loads((directory / artifact["path"]).read_text())[0]
        assert row["abstract_source"] == "openalex"
        assert row["metadata_year"] == expected_metadata_year


@responses.activate
@pytest.mark.parametrize("backends", _BACKEND_ORDERS)
def test_discovery_variation_merge_keeps_metadata(backends):
    _responses()
    candidates = apply_variations(
        None, "synthetic", [{"query": "first wording"}, {"query": "second wording"}],
        backends=backends,
    )
    assert len(responses.calls) == 4
    assert len(candidates) == 1
    assert candidates[0]["abstract_source"] == "openalex"
    assert candidates[0]["metadata_year"] == (2025 if backends[0] == "openalex" else 2026)
    assert candidates[0]["_discover_meta"]["matched_variations"] == ["first wording", "second wording"]


@responses.activate
@pytest.mark.parametrize("output_flag", ["--json", "--to-papers-input"])
@pytest.mark.parametrize("adversarial", [False, True])
def test_cli_search_handoff_keeps_abstract_source_and_year_warning(
    monkeypatch, tmp_path, capsys, output_flag, adversarial
):
    from research_hub.cli import main
    from research_hub.dedup import DedupIndex

    class Config:
        research_hub_dir = tmp_path / "workspace"

    Config.research_hub_dir.mkdir()
    DedupIndex().save(Config.research_hub_dir / "dedup_index.json")
    monkeypatch.setattr("research_hub.cli.get_config", lambda: Config())
    monkeypatch.setattr(
        "research_hub.search.query_expansion.expand_query",
        lambda *args, **kwargs: ["first wording", "second wording"],
    )
    _responses()
    args = ["search", "synthetic", "--backend", "openalex,crossref", output_flag]
    if adversarial:
        args.append("--adversarial")
    assert main(args) == 0
    row = json.loads(capsys.readouterr().out)[0]
    assert row["abstract_source"] == "openalex"
    assert row["metadata_year"] == 2025
    if output_flag == "--to-papers-input":
        assert row["year_drift_warning"] == "ingest_year=2026 differs from doi_lookup_year=2025"
    assert len(responses.calls) == (4 if adversarial else 2)

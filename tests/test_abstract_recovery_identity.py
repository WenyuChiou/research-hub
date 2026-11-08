"""Synthetic HTTP checks for DOI-bound recovery, not live metadata validation."""

import json
from unittest.mock import Mock
from urllib.parse import quote, parse_qs, urlparse

import pytest
import responses

from research_hub.search import abstract_recovery as recovery
from research_hub.search.base import SearchResult


DOI = "10.1234/identity-fixture"
OTHER = "10.1234/other-work"
TEXT = "Synthetic observed abstract"
OA = "https://example.invalid/selected-paper.pdf"
PROVIDERS = ("crossref", "unpaywall", "openalex", "semantic_scholar")


def _url(provider):
    encoded = quote(DOI, safe="")
    return {
        "crossref": f"https://api.crossref.org/works/{encoded}",
        "unpaywall": f"https://api.unpaywall.org/v2/{encoded}",
        "openalex": f"https://api.openalex.org/works/doi:{encoded}",
        "semantic_scholar": f"https://api.semanticscholar.org/graph/v1/paper/DOI:{encoded}",
    }[provider]


def _payload(provider, observed=DOI, *, text=TEXT, oa_url=OA):
    if provider == "crossref":
        return {"message": {"DOI": observed, "abstract": f"<jats:p>{text}</jats:p>"}}
    if provider == "unpaywall":
        return {"doi": observed, "best_oa_location": {"url": oa_url}}
    if provider == "openalex":
        return {"doi": observed, "abstract_inverted_index": {text: [0]} if text else {}}
    return {"externalIds": {"DOI": observed}, "abstract": text}


@responses.activate
@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("observed", [OTHER, None, "", [DOI]])
def test_provider_rejects_mismatched_unknown_or_malformed_doi(provider, observed):
    responses.get(_url(provider), json=_payload(provider, observed))
    result = getattr(recovery, f"_recover_from_{provider}")(DOI)
    assert result == recovery.RecoveredAbstract(text="", source="")


@responses.activate
@pytest.mark.parametrize("provider", PROVIDERS)
def test_provider_does_not_infer_identity_from_requested_url(provider):
    payload = _payload(provider)
    if provider == "crossref":
        del payload["message"]["DOI"]
    elif provider == "semantic_scholar":
        del payload["externalIds"]
    else:
        del payload["doi"]
    responses.get(_url(provider), json=payload)
    assert getattr(recovery, f"_recover_from_{provider}")(DOI) == recovery.RecoveredAbstract(text="", source="")


@responses.activate
@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("observed", [DOI, f" HTTPS://DOI.ORG/{DOI.upper()} "])
def test_provider_accepts_matching_normalized_doi(provider, observed):
    responses.get(_url(provider), json=_payload(provider, observed))
    result = getattr(recovery, f"_recover_from_{provider}")(DOI)
    assert result.source == ("s2" if provider == "semantic_scholar" else provider)
    assert (result.text, result.oa_url) == (("", OA) if provider == "unpaywall" else (TEXT, ""))
    if provider == "semantic_scholar":
        fields = parse_qs(urlparse(responses.calls[0].request.url).query)["fields"][0]
        assert "externalIds" in fields.split(",")


@responses.activate
def test_chain_rejects_wrong_early_abstract_then_uses_matching_later_provider():
    responses.get(_url("crossref"), json=_payload("crossref", OTHER, text="Wrong paper text"))
    responses.get(_url("unpaywall"), json=_payload("unpaywall", OTHER))
    responses.get(_url("openalex"), json=_payload("openalex"))
    result = recovery.recover_abstract(DOI)
    assert result.text == TEXT and result.source == "openalex" and result.oa_url == ""
    assert len(responses.calls) == 3


@responses.activate
@pytest.mark.parametrize("matching_oa", [False, True])
def test_oa_only_fallback_requires_matching_doi(matching_oa):
    for provider in PROVIDERS:
        responses.get(_url(provider), json=_payload(
            provider, DOI if provider == "unpaywall" and matching_oa else OTHER,
        ))
    result = recovery.recover_abstract(DOI)
    assert result.text == ""
    assert (result.source, result.oa_url) == (("unpaywall", OA) if matching_oa else ("", ""))
    assert len(responses.calls) == 4


@responses.activate
@pytest.mark.parametrize("matched", [False, True])
def test_s2_tldr_has_same_identity_gate_and_retains_derived_label(matched):
    responses.get(_url("semantic_scholar"), json={
        "externalIds": {"DOI": DOI if matched else OTHER},
        "abstract": "", "tldr": {"text": "Synthetic generated TLDR"},
    })
    result = recovery._recover_from_semantic_scholar(DOI)
    assert result.text == ("Synthetic generated TLDR" if matched else "")
    assert result.source == ("s2-tldr" if matched else "")


@responses.activate
def test_recovery_normalizes_requested_doi_before_http_lookup():
    responses.get(_url("crossref"), json=_payload("crossref"))
    assert recovery.recover_abstract(f" https://doi.org/{DOI.upper()} ").text == TEXT
    assert len(responses.calls) == 1


def test_blank_requested_doi_does_not_attempt_recovery(monkeypatch):
    get = Mock(side_effect=AssertionError("No request for blank DOI"))
    monkeypatch.setattr(recovery, "http_request", get)
    assert recovery.recover_abstract(" \t ") == recovery.RecoveredAbstract(text="", source="")
    get.assert_not_called()


@responses.activate
def test_cli_enrich_only_attaches_doi_matched_recovery_text(monkeypatch, tmp_path, capsys):
    from research_hub.cli import main

    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(tmp_path))
    monkeypatch.setattr("research_hub.search.enrich.OpenAlexBackend.get_paper", lambda self, identifier: SearchResult(
        title="Synthetic selected paper", doi=DOI, source="openalex",
    ))
    responses.get(_url("crossref"), json=_payload("crossref", OTHER, text="Wrong paper text"))
    responses.get(_url("unpaywall"), json=_payload("unpaywall", OTHER))
    responses.get(_url("openalex"), json=_payload("openalex"))
    audit_dir = tmp_path / "audit"
    assert main(["enrich", DOI, "--backend", "openalex", "--audit-output", str(audit_dir)]) == 0
    row = json.loads(capsys.readouterr().out)[0]
    assert row["doi"] == DOI and row["abstract"] == TEXT and row["abstract_source"] == "openalex"
    events = [json.loads(line) for line in (audit_dir / "events.jsonl").read_text().splitlines()]
    finished = next(e for e in events if e["event"] == "finished" and e["operation"] == "enrich-candidates")
    artifact = next(a for a in finished["artifacts"] if a["path"].endswith(".json"))
    assert json.loads((audit_dir / artifact["path"]).read_text()) == [row]

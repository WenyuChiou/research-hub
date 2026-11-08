from __future__ import annotations

from types import SimpleNamespace

from research_hub.discover import _to_papers_input
from research_hub.search.abstract_recovery import RecoveredAbstract, recover_abstract


def test_recover_abstract_uses_semantic_scholar_after_crossref_and_unpaywall(monkeypatch):
    def fake_get(url, **kwargs):
        if "crossref" in url:
            return SimpleNamespace(status_code=200, json=lambda: {"message": {}})
        if "unpaywall" in url:
            return SimpleNamespace(status_code=200, json=lambda: {"best_oa_location": {}})
        if "semanticscholar" in url:
            return SimpleNamespace(status_code=200, json=lambda: {
                "externalIds": {"DOI": "10.1/example"}, "abstract": "Recovered from S2",
            })
        raise AssertionError(url)

    monkeypatch.setattr("research_hub.search.abstract_recovery.requests.get", fake_get)

    recovered = recover_abstract("10.1/example")

    assert recovered.text == "Recovered from S2"
    assert recovered.source == "s2"


def test_recover_abstract_uses_semantic_scholar_tldr_fallback(monkeypatch):
    def fake_get(url, **kwargs):
        if "crossref" in url:
            return SimpleNamespace(status_code=200, json=lambda: {"message": {}})
        if "unpaywall" in url:
            return SimpleNamespace(status_code=200, json=lambda: {"best_oa_location": {}})
        if "semanticscholar" in url:
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"externalIds": {"DOI": "10.1/example"}, "abstract": "", "tldr": {"text": "Short TLDR"}},
            )
        raise AssertionError(url)

    monkeypatch.setattr("research_hub.search.abstract_recovery.requests.get", fake_get)

    recovered = recover_abstract("10.1/example")

    assert recovered.text == "Short TLDR"
    assert recovered.source == "s2-tldr"


def test_to_papers_input_recovers_missing_abstract(monkeypatch):
    monkeypatch.setattr(
        "research_hub.search.abstract_recovery.recover_abstract",
        lambda doi, timeout=10: RecoveredAbstract(text="Recovered abstract body", source="s2"),
    )

    paper = _to_papers_input(
        [
            {
                "title": "Recovered Paper",
                "authors": ["Jane Doe"],
                "year": 2026,
                "doi": "10.1/recovered",
                "abstract": "(no abstract)",
            }
        ],
        "agents",
    )[0]

    assert paper["abstract"] == "Recovered abstract body"
    assert paper["abstract_source"] == "s2"
    assert not paper["summary"].startswith("[TODO]")
    assert paper["key_findings"] == ["[review and extract from Abstract section above]"]


def test_to_papers_input_keeps_todo_when_recovery_fails(monkeypatch):
    monkeypatch.setattr(
        "research_hub.search.abstract_recovery.recover_abstract",
        lambda doi, timeout=10: RecoveredAbstract(text="", source=""),
    )

    paper = _to_papers_input(
        [
            {
                "title": "No Abstract Paper",
                "authors": ["Jane Doe"],
                "year": 2026,
                "doi": "10.1/missing",
                "abstract": "",
            }
        ],
        "agents",
    )[0]

    assert paper["abstract"] == "(no abstract)"
    assert paper["summary"].startswith("[TODO] No Abstract Paper")
    assert paper["key_findings"] == ["[TODO: fill from abstract]"]

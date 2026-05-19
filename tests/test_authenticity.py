from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    cfg = SimpleNamespace(
        root=root,
        raw=root / "raw",
        hub=root / "hub",
        logs=root / "logs",
        research_hub_dir=root / ".research_hub",
        clusters_file=root / ".research_hub" / "clusters.yaml",
        zotero_library_id="",
        zotero_default_collection=None,
        zotero_collections={},
    )
    for path in (cfg.raw, cfg.hub, cfg.logs, cfg.research_hub_dir):
        path.mkdir(parents=True, exist_ok=True)
    return cfg


def _paper(title: str = "Real Paper", doi: str = "10.1000/real", **extra) -> dict:
    paper = {
        "title": title,
        "doi": doi,
        "authors": [{"creatorType": "author", "firstName": "Jane", "lastName": "Doe"}],
        "authors_str": "Doe, Jane",
        "year": 2024,
        "journal": "Journal of Testing",
        "venue": "Journal of Testing",
        "abstract": "A real abstract.",
        "summary": "Summary",
        "key_findings": ["One"],
        "methodology": "Survey",
        "relevance": "Relevant",
        "slug": title.lower().replace(" ", "-"),
        "sub_category": "agents",
        "tags": [],
    }
    paper.update(extra)
    return paper


def _ok_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("research_hub.authenticity.requests.head", lambda *a, **k: _Response(200))


def test_l0_no_identifier_is_quarantined(tmp_path):
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    paper = _paper(doi="", arxiv_id="")

    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert accepted == []
    assert quarantined[0]["reason"] == "no_identifier"
    assert (cfg.research_hub_dir / "quarantine" / "agents" / f"{paper['slug']}.json").exists()


def test_l1_doi_404_quarantines_and_uses_cache(tmp_path, monkeypatch):
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    calls: list[str] = []

    def fake_head(url, **kwargs):
        calls.append(url)
        return _Response(404)

    monkeypatch.setattr("research_hub.authenticity.requests.head", fake_head)
    paper = _paper(doi="10.1000/missing")

    _accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")
    assert quarantined[0]["reason"] == "doi_unresolved"

    cache_path = cfg.research_hub_dir / "doi_resolve_cache.json"
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.1"
    assert "doi:10.1000/missing" in payload["results"]

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("cached DOI should not be re-HEADed")

    monkeypatch.setattr("research_hub.authenticity.requests.head", fail_if_called)
    _accepted2, quarantined2 = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert quarantined2[0]["reason"] == "doi_unresolved"
    assert calls == ["https://doi.org/10.1000/missing"]


def test_l1_request_exception_is_fail_closed(tmp_path, monkeypatch):
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)

    def fake_head(*_args, **_kwargs):
        raise requests.RequestException("offline")

    monkeypatch.setattr("research_hub.authenticity.requests.head", fake_head)

    _accepted, quarantined = verify_authenticity(
        [_paper(doi="10.1000/offline")],
        cfg,
        cluster_slug="agents",
    )

    assert quarantined[0]["reason"] == "doi_check_unavailable"


def test_l2_single_source_accepts_and_two_backends_corroborate(tmp_path, monkeypatch):
    """Corroboration gate behaviour:

    - single-source with 0 citations and no arXiv/PMID → quarantined L2 uncorroborated
      (gate added in fix/authenticity-corroboration-gate).
    - corroborated (2+ backends) → accepted regardless of citation count.
    - single-source with sufficient citations (>=1 default) → accepted.
    """
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    # Will be quarantined: single-source, 0 citations, no arxiv/pmid
    single = _paper("Single Source", doi="10.1000/single", source="openalex")
    # Will be accepted: corroborated by 2 backends
    double = _paper("Double Source", doi="10.1000/double", found_in=["openalex", "crossref"])
    # Will be accepted: single-source but has sufficient citations (>=1)
    cited = _paper("Cited Single Source", doi="10.1000/cited", source="openalex", citation_count=5)

    accepted, quarantined = verify_authenticity([single, double, cited], cfg, cluster_slug="agents")

    by_title = {paper["title"]: paper for paper in accepted}
    assert "Double Source" in by_title, f"corroborated paper must be accepted; accepted={list(by_title)}"
    assert "Cited Single Source" in by_title, f"cited single-source must be accepted; accepted={list(by_title)}"
    assert by_title["Double Source"]["provenance"]["corroboration"] == "corroborated"

    quarantined_slugs = [q["slug"] for q in quarantined]
    assert any("single-source" in slug for slug in quarantined_slugs), (
        f"single-source/zero-citations paper must be quarantined; quarantined={quarantined_slugs}"
    )
    single_q = next(q for q in quarantined if "single-source" in q.get("slug", ""))
    assert single_q["layer"] == "L2"
    assert single_q["reason"] == "uncorroborated"


@pytest.mark.parametrize(
    "bad_patch",
    [
        {"authors": ["Jane Doe +3 more"]},
        {"year": 3000},
        {"title": "嚙窯 Broken Title"},
    ],
)
def test_l3_metadata_invalid_routes_to_quarantine(tmp_path, monkeypatch, bad_patch):
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    paper = _paper("Bad Metadata", doi="10.1000/bad")
    paper.update(bad_patch)
    _accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert quarantined[0]["reason"] == "metadata_invalid"


def test_l4_fit_check_unjudged_and_low_score_quarantine(tmp_path, monkeypatch):
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    _accepted, quarantined = verify_authenticity(
        [_paper("Unjudged", doi="10.1000/unjudged")],
        cfg,
        cluster_slug="agents",
        do_fit_check=True,
    )
    assert quarantined[0]["reason"] == "relevance_unjudged"

    cluster_dir = cfg.hub / "agents"
    cluster_dir.mkdir(parents=True, exist_ok=True)
    (cluster_dir / ".fit_check_rejected.json").write_text(
        json.dumps(
            {
                "cluster_slug": "agents",
                "threshold": 3,
                "rejected": [
                    {
                        "doi": "10.1000/low",
                        "title": "Low Score",
                        "score": 1,
                        "reason": "off topic",
                        "kept": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    _accepted2, quarantined2 = verify_authenticity(
        [_paper("Low Score", doi="10.1000/low")],
        cfg,
        cluster_slug="agents",
        do_fit_check=True,
    )
    assert quarantined2[0]["reason"] == "low_relevance"


def test_accepted_paper_provenance_and_pipeline_note_write(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)
    monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)
    # citation_count=3 and found_in=["openalex", "crossref"] ensure the paper
    # passes the L2b corroboration gate (corroborated by 2 backends).
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Accepted Paper", doi="10.1000/accepted",
                           found_in=["openalex", "crossref"], citation_count=3)]),
        encoding="utf-8",
    )

    assert pipeline.run_pipeline(verify=False) == 0

    note = cfg.raw / "agents" / "accepted-paper.md"
    text = note.read_text(encoding="utf-8")
    assert "provenance:" in text
    assert 'resolved_via: "doi.org"' in text
    assert 'corroboration: "corroborated"' in text


def test_quarantine_cli_list_show_restore_round_trip(tmp_path, monkeypatch, capsys):
    from research_hub import cli
    from research_hub.authenticity import DoiResolveCache, ResolveOutcome, quarantine_paper

    cfg = _cfg(tmp_path)
    candidate = _paper("Restore Me", doi="10.1000/restore")
    quarantine_paper(
        cfg,
        candidate,
        cluster_slug="agents",
        layer="L1",
        reason="doi_check_unavailable",
    )
    cache = DoiResolveCache()
    cache.put(
        ResolveOutcome(
            ok=False,
            key="doi:10.1000/restore",
            resolved_via="doi.org",
            checked_at="2026-05-17T00:00:00Z",
            reason="doi_check_unavailable",
            url="https://doi.org/10.1000/restore",
        )
    )
    cache.save(cfg.research_hub_dir / "doi_resolve_cache.json")
    monkeypatch.setattr(cli, "get_config", lambda: cfg)

    assert cli.main(["quarantine", "list"]) == 0
    assert "Restore Me".lower().replace(" ", "-") in capsys.readouterr().out

    assert cli.main(["quarantine", "show", "restore-me"]) == 0
    shown = capsys.readouterr().out
    assert '"reason": "doi_check_unavailable"' in shown

    assert cli.main(["quarantine", "restore", "restore-me", "--cluster", "agents"]) == 0
    assert not (cfg.research_hub_dir / "quarantine" / "agents" / "restore-me.json").exists()
    restored = json.loads((cfg.root / "papers_input.json").read_text(encoding="utf-8"))
    assert restored[0]["doi"] == "10.1000/restore"
    cache_payload = json.loads((cfg.research_hub_dir / "doi_resolve_cache.json").read_text(encoding="utf-8"))
    assert "doi:10.1000/restore" not in cache_payload["results"]

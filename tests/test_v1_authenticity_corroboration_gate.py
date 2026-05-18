"""Tests for the L2 corroboration gate added in fix/authenticity-corroboration-gate.

Covers:
(a) DOI 10.55041/ijsrem60201 (IJSREM predatory prefix) → quarantined L2 predatory_venue.
(b) generic resolvable DOI, single-source, 0 citations, no arxiv/pmid → quarantined L2 uncorroborated.
(c) single-source arXiv-only preprint (arxiv_id set, 0 citations) → ACCEPTED (false-positive guard).
(d) single-source PMID-only, 0 citations → ACCEPTED (PMID exemption).
(e) corroborated (found_in >= 2 backends) DOI → ACCEPTED.
(f) single-source DOI with citation_count >= floor (default 1) → ACCEPTED.
(g) quarantined L2 item round-trips through restore_quarantine.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


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


# (a) IJSREM predatory prefix → quarantined L2 predatory_venue, NOT in accepted
def test_predatory_doi_prefix_quarantined(tmp_path, monkeypatch):
    """DOI 10.55041/ijsrem60201 (Edtech Publishers OPC, IJSREM) must be quarantined at L2
    with reason predatory_venue, even if it resolves 200 and is corroborated."""
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    paper = _paper(
        "IJSREM Flood Forecasting",
        doi="10.55041/ijsrem60201",
        citation_count=5,
        found_in=["crossref", "openalex"],
    )
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert accepted == [], f"predatory paper must not be accepted; accepted={accepted}"
    assert len(quarantined) == 1
    q = quarantined[0]
    assert q["layer"] == "L2", f"expected L2, got {q['layer']}"
    assert q["reason"] == "predatory_venue", f"expected predatory_venue, got {q['reason']}"
    assert q["details"]["doi_prefix"] == "10.55041"


# (a2) IJASRE prefix — second seed prefix
def test_ijasre_doi_prefix_quarantined(tmp_path, monkeypatch):
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    paper = _paper("IJASRE Paper", doi="10.31695/IJASRE.2023.001", citation_count=0)
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert accepted == []
    q = quarantined[0]
    assert q["layer"] == "L2"
    assert q["reason"] == "predatory_venue"
    assert q["details"]["doi_prefix"] == "10.31695"


# (a3) cfg.predatory_doi_prefixes extension merges with builtins
def test_cfg_extension_predatory_prefixes(tmp_path, monkeypatch):
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    cfg.predatory_doi_prefixes = ("10.99999",)  # custom extension
    _ok_head(monkeypatch)

    paper = _paper("Custom Predatory", doi="10.99999/custom", citation_count=10,
                   found_in=["crossref", "openalex"])
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert accepted == []
    assert quarantined[0]["reason"] == "predatory_venue"
    assert quarantined[0]["details"]["doi_prefix"] == "10.99999"


# (b) generic resolvable DOI, single-source, 0 citations, no arxiv/pmid → quarantined L2 uncorroborated
def test_single_source_zero_citations_quarantined(tmp_path, monkeypatch):
    """Single-source DOI with 0 citations and no arXiv/PMID must be quarantined at L2
    with reason uncorroborated (fail-closed)."""
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    paper = _paper("Obscure Single Source", doi="10.9999/unknown",
                   citation_count=0, source="openalex")
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert accepted == [], f"single-source/0-citation paper must not be accepted; accepted={accepted}"
    assert len(quarantined) == 1
    q = quarantined[0]
    assert q["layer"] == "L2", f"expected L2, got {q['layer']}"
    assert q["reason"] == "uncorroborated", f"expected uncorroborated, got {q['reason']}"
    assert q["details"]["citation_count"] == 0
    assert q["details"]["corroboration"] == "single-source"


# (b2) missing citation_count field treated as 0
def test_single_source_missing_citation_count_quarantined(tmp_path, monkeypatch):
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    paper = _paper("No Cit Count", doi="10.9999/nocitcount", source="openalex")
    # citation_count field absent entirely
    paper.pop("citation_count", None)
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert accepted == []
    q = quarantined[0]
    assert q["reason"] == "uncorroborated"
    assert q["details"]["citation_count"] == 0


# (c) single-source arXiv-only preprint (arxiv_id set, 0 citations, no DOI) → ACCEPTED
def test_single_source_arxiv_preprint_accepted(tmp_path, monkeypatch):
    """ArXiv preprints are inherently single-source. Must NOT be quarantined by L2b
    even with 0 citations — this is the primary false-positive guard."""
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    paper = _paper("ArXiv Preprint", doi="", arxiv_id="2301.00001",
                   citation_count=0, source="arxiv")
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert any(p.get("arxiv_id") == "2301.00001" for p in accepted), (
        f"ArXiv preprint must be accepted (not quarantined by L2b); "
        f"accepted={[p.get('arxiv_id') for p in accepted]}, "
        f"quarantined={[(q['reason'], q.get('details')) for q in quarantined]}"
    )


# (c2) bioRxiv/medRxiv DOI prefix 10.1101 → ACCEPTED even single-source, 0 citations
def test_biorxiv_doi_accepted(tmp_path, monkeypatch):
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    paper = _paper("BioRxiv Paper", doi="10.1101/2023.01.01.000001",
                   citation_count=0, source="biorxiv")
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert any(p["doi"] == "10.1101/2023.01.01.000001" for p in accepted), (
        f"bioRxiv paper must be accepted; quarantined={[(q['reason']) for q in quarantined]}"
    )


# (d) single-source PMID-only, 0 citations → ACCEPTED (PMID exemption)
def test_single_source_pmid_accepted(tmp_path, monkeypatch):
    """Papers with a PMID are indexed by PubMed, a curated database. They are
    exempt from L2b even with 0 citations and no arXiv id."""
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    # PMID is a resolvable identifier (pubmed.ncbi.nlm.nih.gov); doi="" so L0 routes via PMID.
    paper = _paper("PubMed Paper", doi="", pmid="12345678",
                   citation_count=0, source="pubmed")
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert any(p.get("pmid") == "12345678" for p in accepted), (
        f"PMID paper must be accepted (PMID exemption); "
        f"quarantined={[(q['reason'], q.get('details')) for q in quarantined]}"
    )


# (e) corroborated (found_in >= 2 backends, or crossref in backends) → ACCEPTED
def test_corroborated_doi_accepted(tmp_path, monkeypatch):
    """Corroborated papers pass L2b regardless of citation count."""
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    paper = _paper("Corroborated Paper", doi="10.1000/corroborated",
                   citation_count=0, found_in=["openalex", "crossref"])
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert any(p["doi"] == "10.1000/corroborated" for p in accepted), (
        f"Corroborated paper must be accepted; quarantined={quarantined}"
    )
    assert quarantined == []


# (e2) crossref alone in backends also corroborates
def test_crossref_backend_corroborates(tmp_path, monkeypatch):
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    paper = _paper("CrossRef Paper", doi="10.1000/crossref",
                   citation_count=0, backend="crossref")
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert any(p["doi"] == "10.1000/crossref" for p in accepted), (
        f"crossref-backend paper must be corroborated and accepted; quarantined={quarantined}"
    )


# (f) single-source DOI with citation_count >= floor (default 1) → ACCEPTED
def test_single_source_sufficient_citations_accepted(tmp_path, monkeypatch):
    """Single-source papers with >= min_corroboration_citations (default 1) are accepted."""
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    paper = _paper("Cited Single Source", doi="10.1000/cited",
                   citation_count=3, source="openalex")
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert any(p["doi"] == "10.1000/cited" for p in accepted), (
        f"Paper with 3 citations must be accepted; quarantined={quarantined}"
    )
    assert quarantined == []


# (f2) exactly at floor (citation_count == 1, floor == 1) → ACCEPTED
def test_single_source_exactly_at_floor_accepted(tmp_path, monkeypatch):
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    paper = _paper("At Floor", doi="10.1000/atfloor", citation_count=1, source="openalex")
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert any(p["doi"] == "10.1000/atfloor" for p in accepted), (
        f"citation_count=1 (== floor) must be accepted; quarantined={quarantined}"
    )


# (f3) cfg.min_corroboration_citations override respected
def test_cfg_min_corroboration_citations_override(tmp_path, monkeypatch):
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    cfg.min_corroboration_citations = 5  # raise the bar
    _ok_head(monkeypatch)

    paper_low = _paper("Low Cit", doi="10.1000/lowcit", citation_count=3, source="openalex")
    paper_high = _paper("High Cit", doi="10.1000/highcit", citation_count=10, source="openalex")
    accepted, quarantined = verify_authenticity([paper_low, paper_high], cfg, cluster_slug="agents")

    accepted_dois = {p["doi"] for p in accepted}
    assert "10.1000/highcit" in accepted_dois, "high citation paper must pass raised floor"
    assert "10.1000/lowcit" not in accepted_dois, "low citation paper must fail raised floor"
    assert any(q["reason"] == "uncorroborated" for q in quarantined)


# (g) quarantined L2 item round-trips through restore_quarantine
def test_l2_predatory_quarantine_restore_roundtrip(tmp_path, monkeypatch):
    """A predatory-venue quarantine can be manually restored via restore_quarantine,
    re-queuing the candidate in papers_input.json and deleting the quarantine file."""
    from research_hub.authenticity import verify_authenticity, restore_quarantine

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    paper = _paper("Predatory Paper", doi="10.55041/restore-me",
                   citation_count=0, source="openalex")
    _accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")
    assert len(quarantined) == 1
    assert quarantined[0]["reason"] == "predatory_venue"

    slug = quarantined[0]["slug"]
    result = restore_quarantine(cfg, slug, "agents")

    assert result["cluster"] == "agents"
    assert result["slug"] == slug
    papers_input = Path(result["papers_input"])
    assert papers_input.exists(), "restore must write to papers_input.json"
    data = json.loads(papers_input.read_text(encoding="utf-8"))
    assert any(
        p.get("doi", "").startswith("10.55041") for p in data
    ), f"restored candidate must appear in papers_input; data={data}"
    # quarantine file must be removed
    assert not Path(quarantined[0]["path"]).exists(), "quarantine file must be deleted after restore"


# (g2) uncorroborated quarantine also restores
def test_l2_uncorroborated_quarantine_restore_roundtrip(tmp_path, monkeypatch):
    from research_hub.authenticity import verify_authenticity, restore_quarantine

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    paper = _paper("Uncorroborated Paper", doi="10.9999/uncorr",
                   citation_count=0, source="openalex")
    _accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")
    assert quarantined[0]["reason"] == "uncorroborated"

    slug = quarantined[0]["slug"]
    result = restore_quarantine(cfg, slug, "agents")
    data = json.loads(Path(result["papers_input"]).read_text(encoding="utf-8"))
    assert any(p.get("doi") == "10.9999/uncorr" for p in data)


# (h) predatory-prefix BOUNDARY guard: a different registrant whose prefix
# string-extends a denylisted one ("10.550410" vs denylisted "10.55041")
# must NOT be quarantined as predatory_venue.
def test_predatory_prefix_boundary_no_false_positive(tmp_path, monkeypatch):
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    # 10.550410 is a distinct registrant; bare startswith("10.55041") would
    # wrongly match it. Corroborated so L2b is not the variable under test.
    paper = _paper(
        "Legit Different Registrar",
        doi="10.550410/legit.2026.1",
        citation_count=4,
        found_in=["crossref", "openalex"],
    )
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert any(p["doi"] == "10.550410/legit.2026.1" for p in accepted), (
        f"non-denylisted registrant must NOT be quarantined as predatory; "
        f"quarantined={[(q['reason'], q.get('details')) for q in quarantined]}"
    )
    assert not any(q["reason"] == "predatory_venue" for q in quarantined)


# (h2) bioRxiv-exemption BOUNDARY guard: "10.11010/x" string-extends the
# bioRxiv registrant "10.1101" but is a different registrant — it must NOT
# be exempted; single-source + 0 citations → quarantined uncorroborated.
def test_biorxiv_exemption_boundary_not_over_exempted(tmp_path, monkeypatch):
    from research_hub.authenticity import verify_authenticity

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    paper = _paper(
        "Not Actually bioRxiv",
        doi="10.11010/not-biorxiv.1",
        citation_count=0,
        source="openalex",
    )
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert accepted == [], f"10.11010 must not be bioRxiv-exempted; accepted={accepted}"
    assert len(quarantined) == 1
    assert quarantined[0]["reason"] == "uncorroborated", (
        f"expected uncorroborated, got {quarantined[0]['reason']}"
    )

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

import research_hub.authenticity as auth
from research_hub.authenticity import (
    CROSSREF_VERIFY_CACHE,
    CrossrefVerifyCache,
    verify_authenticity,
)


class _Resp:
    def __init__(self, status_code: int = 200, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


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


def _paper(
    title: str = "Review and Intercomparison of Machine Learning Applications for Short-term Flood Forecasting",
    doi: str = "10.1007/s11269-025-04093-x",
    **extra,
) -> dict:
    paper = {
        "title": title,
        "doi": doi,
        "authors": [{"creatorType": "author", "firstName": "Jane", "lastName": "Doe"}],
        "authors_str": "Doe, Jane",
        "year": 2025,
        "journal": "Journal of Testing",
        "venue": "Journal of Testing",
        "abstract": "A real abstract.",
        "summary": "Summary",
        "key_findings": ["One"],
        "methodology": "Survey",
        "relevance": "Relevant",
        "slug": title.lower().replace(" ", "-")[:80],
        "sub_category": "agents",
        "tags": [],
        "source": "openalex",
        "citation_count": 0,
    }
    paper.update(extra)
    return paper


def _work(
    *,
    doi: str = "10.1007/s11269-025-04093-x",
    title: str = "Review and Intercomparison of Machine Learning Applications for Short-term Flood Forecasting",
    year: int = 2025,
    family: str = "Doe",
    given: str = "Jane",
) -> dict:
    return {
        "DOI": doi,
        "title": [title],
        "author": [{"family": family, "given": given}],
        "issued": {"date-parts": [[year, 1, 1]]},
        "container-title": ["Journal of Testing"],
        "type": "journal-article",
    }


def _ok_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth.requests, "head", lambda *a, **k: _Resp(200))


def _crossref_get(monkeypatch: pytest.MonkeyPatch, response: _Resp) -> None:
    monkeypatch.setattr("research_hub.search.crossref.requests.get", lambda *a, **k: response)


def _cache_payload(cfg: SimpleNamespace) -> dict:
    return json.loads((cfg.research_hub_dir / CROSSREF_VERIFY_CACHE).read_text(encoding="utf-8"))


def _write_verify_cache(cfg: SimpleNamespace, doi: str, verified: bool) -> None:
    path = cfg.research_hub_dir / CROSSREF_VERIFY_CACHE
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "results": {
                    f"doi:{auth.normalize_doi(doi)}": {
                        "verified": verified,
                        "checked_at": "2026-05-20T00:00:00Z",
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_openalex_only_single_source_crossref_match_passes_l2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)
    _crossref_get(monkeypatch, _Resp(payload={"message": _work()}))

    paper = _paper()
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert quarantined == []
    assert len(accepted) == 1
    accepted_paper = accepted[0]
    assert "crossref" in accepted_paper["backends"]
    assert any(record.get("source") == "crossref" for record in accepted_paper["source_records"])
    assert accepted_paper["provenance"]["corroboration"] == "corroborated"
    entry = _cache_payload(cfg)["results"]["doi:10.1007/s11269-025-04093-x"]
    assert entry["verified"] is True


def test_crossref_404_keeps_single_source_quarantined_and_caches_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)
    _crossref_get(monkeypatch, _Resp(status_code=404))

    accepted, quarantined = verify_authenticity([_paper()], cfg, cluster_slug="agents")

    assert accepted == []
    assert len(quarantined) == 1
    assert quarantined[0]["layer"] == "L2"
    assert quarantined[0]["reason"] == "uncorroborated"
    entry = _cache_payload(cfg)["results"]["doi:10.1007/s11269-025-04093-x"]
    assert entry["verified"] is False


def test_crossref_different_paper_does_not_satisfy_l2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)
    _crossref_get(
        monkeypatch,
        _Resp(
            payload={
                "message": _work(
                    title="A Different Article About Bridge Inspection",
                    year=2020,
                    family="Smith",
                    given="Alex",
                )
            }
        ),
    )

    paper = _paper()
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert accepted == []
    assert len(quarantined) == 1
    assert quarantined[0]["layer"] == "L2"
    assert quarantined[0]["reason"] == "uncorroborated"
    assert "crossref" not in [str(name).casefold() for name in paper.get("backends", [])]
    assert not any(record.get("source") == "crossref" for record in paper.get("source_records", []))
    entry = _cache_payload(cfg)["results"]["doi:10.1007/s11269-025-04093-x"]
    assert entry["verified"] is False


def test_already_two_backend_paper_does_not_fetch_crossref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("CrossRef should not be fetched for already corroborated papers")

    monkeypatch.setattr(auth.CrossrefBackend, "get_paper", fail_if_called)
    paper = _paper(backends=["crossref", "openalex"])

    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert quarantined == []
    assert len(accepted) == 1
    assert not (cfg.research_hub_dir / CROSSREF_VERIFY_CACHE).exists()


def test_no_doi_paper_does_not_fetch_or_augment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("CrossRef should not be fetched without a DOI")

    monkeypatch.setattr(auth.CrossrefBackend, "get_paper", fail_if_called)
    paper = _paper(doi="", openalex_id="W12345")

    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert accepted == []
    assert len(quarantined) == 1
    assert quarantined[0]["layer"] == "L2"
    assert quarantined[0]["reason"] == "uncorroborated"
    assert "backends" not in paper
    assert "source_records" not in paper


def test_crossref_exception_fails_quiet_and_does_not_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)

    def raise_request_error(*_args, **_kwargs):
        raise requests.RequestException("timeout")

    monkeypatch.setattr("research_hub.search.crossref.requests.get", raise_request_error)
    paper = _paper()

    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert accepted == []
    assert len(quarantined) == 1
    assert quarantined[0]["reason"] == "uncorroborated"
    assert not (cfg.research_hub_dir / CROSSREF_VERIFY_CACHE).exists()
    assert "backends" not in paper
    assert "source_records" not in paper


def test_crossref_5xx_fails_quiet_and_does_not_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)
    _crossref_get(monkeypatch, _Resp(status_code=500))
    paper = _paper()

    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert accepted == []
    assert len(quarantined) == 1
    assert quarantined[0]["reason"] == "uncorroborated"
    assert not (cfg.research_hub_dir / CROSSREF_VERIFY_CACHE).exists()
    assert "backends" not in paper
    assert "source_records" not in paper


def test_crossref_200_empty_body_fails_quiet_and_does_not_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W2: a 200 OK with missing/empty `message` is a transient CrossRef
    API anomaly, not a definitive negative -- must fail quiet (no cache
    write) so the next run retries instead of permanently blocking the
    paper. Anti-fabrication still safe: paper stays uncorroborated."""
    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)
    _crossref_get(monkeypatch, _Resp(status_code=200, payload={}))
    paper = _paper()

    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert accepted == []
    assert len(quarantined) == 1
    assert quarantined[0]["reason"] == "uncorroborated"
    assert not (cfg.research_hub_dir / CROSSREF_VERIFY_CACHE).exists()
    assert "backends" not in paper
    assert "source_records" not in paper


def test_verified_true_cache_hit_augments_without_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)
    doi = "10.1007/s11269-025-04093-x"
    _write_verify_cache(cfg, doi, verified=True)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("verified cache hit should not fetch CrossRef")

    monkeypatch.setattr(auth.CrossrefBackend, "get_paper", fail_if_called)
    paper = _paper(doi=doi)

    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert quarantined == []
    assert len(accepted) == 1
    assert "crossref" in paper["backends"]
    assert any(record.get("source") == "crossref" for record in paper["source_records"])


def test_verified_false_cache_hit_does_not_augment_or_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)
    doi = "10.1007/s11269-025-04093-x"
    _write_verify_cache(cfg, doi, verified=False)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("negative cache hit should not fetch CrossRef")

    monkeypatch.setattr(auth.CrossrefBackend, "get_paper", fail_if_called)
    paper = _paper(doi=doi)

    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert accepted == []
    assert len(quarantined) == 1
    assert quarantined[0]["reason"] == "uncorroborated"
    assert "backends" not in paper
    assert "source_records" not in paper


def test_crossref_verify_cache_loads_missing_and_corrupt_as_empty(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert CrossrefVerifyCache.load(missing).results == {}

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    assert CrossrefVerifyCache.load(corrupt).results == {}

    malformed = tmp_path / "malformed.json"
    malformed.write_text("[]", encoding="utf-8")
    assert CrossrefVerifyCache.load(malformed).results == {}


def test_crossref_verify_cache_save_writes_schema_and_results(tmp_path: Path) -> None:
    path = tmp_path / CROSSREF_VERIFY_CACHE
    cache = CrossrefVerifyCache()
    cache.put("doi:10.1000/example", verified=True)
    cache.save(path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert set(payload["results"]["doi:10.1000/example"]) == {"verified", "checked_at"}
    assert payload["results"]["doi:10.1000/example"]["verified"] is True
    assert payload["results"]["doi:10.1000/example"]["checked_at"].endswith("Z")

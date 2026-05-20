"""PR-B: L1-deferred (transient DOI HEAD failure) papers fall through to
L2 / L3 / fit-check instead of fail-closing at L1-deferred. If those
gates pass, the paper is accepted with
``provenance.doi_recheck_pending = True`` so a future tool can re-verify
the DOI when the publisher's anti-bot wall lifts. Definitive L1 failure
(HTTP 404 / 410) still quarantines at L1 — the anti-fabrication
guarantee is unchanged. L2 corroboration + L3 metadata integrity remain
the fabrication gate; the change only stops L1-anti-bot from masking
otherwise-verifiable papers.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import research_hub.authenticity as auth
from research_hub.authenticity import (
    DEFERRED_LAYER,
    verify_authenticity,
)


class _Resp:
    def __init__(self, status_code: int = 200, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth.time, "sleep", lambda *_a, **_k: None)


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    rh = root / ".research_hub"
    rh.mkdir(parents=True)
    return SimpleNamespace(research_hub_dir=rh)


def _paper(
    *,
    title: str = "A Real Paper About Reservoirs",
    doi: str = "10.1000/real",
    year: int = 2025,
    backends: list[str] | None = None,
    **extra,
) -> dict:
    paper = {
        "title": title,
        "doi": doi,
        "year": year,
        "abstract": "x" * 200,
        "authors": [{"firstName": "Jane", "lastName": "Doe"}],
        "source": "openalex",
        "citation_count": 5,
    }
    if backends is not None:
        paper["backends"] = backends
    paper.update(extra)
    return paper


def _head(monkeypatch: pytest.MonkeyPatch, status_code: int) -> None:
    monkeypatch.setattr(auth.requests, "head", lambda *a, **k: _Resp(status_code=status_code))


def _crossref_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub CrossRef-verify path so PR-A's augment never accidentally
    corroborates (each test sets corroboration explicitly via the paper
    fixture)."""
    monkeypatch.setattr(
        "research_hub.search.crossref.requests.get",
        lambda *a, **k: _Resp(status_code=404),
    )


# --- 1. L1-deferred + L2 corroborated + L3 OK -> accepted with recheck marker ---


def test_l1_deferred_with_l2_corroborated_is_accepted_with_recheck_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _head(monkeypatch, 403)
    _crossref_no_match(monkeypatch)
    paper = _paper(backends=["crossref", "openalex"])

    accepted, quarantined = verify_authenticity([paper], _cfg(tmp_path), cluster_slug="c")

    assert quarantined == []
    assert len(accepted) == 1
    prov = accepted[0]["provenance"]
    assert prov.get("doi_recheck_pending") is True
    details = prov.get("doi_recheck_details") or {}
    assert details.get("status_code") == 403
    assert details.get("reason") == "doi_check_unavailable"
    assert details.get("resolved_via") == "doi.org"


def test_l1_deferred_418_with_l2_corroborated_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _head(monkeypatch, 418)
    _crossref_no_match(monkeypatch)
    paper = _paper(doi="10.3724/j.slxb.20250344", backends=["crossref", "openalex"])

    accepted, quarantined = verify_authenticity([paper], _cfg(tmp_path), cluster_slug="c")

    assert quarantined == []
    assert len(accepted) == 1
    assert accepted[0]["provenance"]["doi_recheck_pending"] is True
    assert accepted[0]["provenance"]["doi_recheck_details"]["status_code"] == 418


# --- 2. L1-deferred + L2 uncorroborated -> L2 quarantine (NOT L1, NOT DEFERRED_LAYER) ---


def test_l1_deferred_uncorroborated_goes_to_L2_not_L1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _head(monkeypatch, 403)
    _crossref_no_match(monkeypatch)
    paper = _paper(citation_count=0)  # single-source openalex, no corroboration

    accepted, quarantined = verify_authenticity([paper], _cfg(tmp_path), cluster_slug="c")

    assert accepted == []
    assert len(quarantined) == 1
    q = quarantined[0]
    assert q["layer"] == "L2"
    assert q["reason"] == "uncorroborated"
    # Anti-fabrication regression guards:
    # - 403 anti-bot is NOT treated as `doi_unresolved` fabrication evidence
    # - L1-deferred bucket is structurally empty post-PR-B
    assert q["reason"] != "doi_unresolved"
    assert q["layer"] != DEFERRED_LAYER


# --- 3. L1-deferred + L3 integrity fails -> L3 quarantine ---


def test_l1_deferred_l3_integrity_fail_goes_to_L3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _head(monkeypatch, 403)
    _crossref_no_match(monkeypatch)
    # Invalid year triggers _metadata_integrity_reason -> "invalid year".
    # Corroborated so L2 would pass; the L3 check runs first and quarantines.
    paper = _paper(year="not-a-number", backends=["crossref", "openalex"])

    accepted, quarantined = verify_authenticity([paper], _cfg(tmp_path), cluster_slug="c")

    assert accepted == []
    assert len(quarantined) == 1
    assert quarantined[0]["layer"] == "L3"
    assert quarantined[0]["reason"] == "metadata_invalid"


# --- 4. L1-deferred + L2a predatory venue -> L2 predatory quarantine ---


def test_l1_deferred_predatory_doi_goes_to_L2_predatory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _head(monkeypatch, 418)
    _crossref_no_match(monkeypatch)
    # 10.55041 is in _PREDATORY_DOI_PREFIXES.
    paper = _paper(doi="10.55041/ijsrem.fake", backends=["crossref", "openalex"])

    accepted, quarantined = verify_authenticity([paper], _cfg(tmp_path), cluster_slug="c")

    assert accepted == []
    assert len(quarantined) == 1
    assert quarantined[0]["layer"] == "L2"
    assert quarantined[0]["reason"] == "predatory_venue"


# --- 5. L1 permanent (404 / 410) -> L1 quarantine, anti-fabrication intact ---


@pytest.mark.parametrize("status_code", [404, 410])
def test_l1_permanent_failure_still_quarantines_at_L1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status_code: int,
) -> None:
    _head(monkeypatch, status_code)
    _crossref_no_match(monkeypatch)
    # Even with backends already corroborated, permanent L1 wins (DOI definitively
    # not registered -> fabrication evidence).
    paper = _paper(backends=["crossref", "openalex"])

    accepted, quarantined = verify_authenticity([paper], _cfg(tmp_path), cluster_slug="c")

    assert accepted == []
    assert len(quarantined) == 1
    q = quarantined[0]
    assert q["layer"] == "L1"
    assert q["reason"] == "doi_unresolved"
    # L1 permanent records carry no recheck marker.
    assert "doi_recheck_pending" not in (q.get("details") or {})


# --- 6. L1 OK -> normal accepted, no recheck marker ---


def test_l1_ok_normal_accept_no_recheck_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _head(monkeypatch, 200)
    _crossref_no_match(monkeypatch)
    paper = _paper(backends=["crossref", "openalex"])

    accepted, quarantined = verify_authenticity([paper], _cfg(tmp_path), cluster_slug="c")

    assert quarantined == []
    assert len(accepted) == 1
    prov = accepted[0]["provenance"]
    assert "doi_recheck_pending" not in prov
    assert "doi_recheck_details" not in prov


# --- 7. No DOI -> L0 handling, no recheck leak ---


def test_no_doi_paper_goes_to_L0_no_recheck_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _head(monkeypatch, 418)
    _crossref_no_match(monkeypatch)
    paper = _paper(doi="")  # no identifier

    accepted, quarantined = verify_authenticity([paper], _cfg(tmp_path), cluster_slug="c")

    assert accepted == []
    assert len(quarantined) == 1
    q = quarantined[0]
    assert q["layer"] == "L0"
    assert q["reason"] == "no_identifier"
    assert "doi_recheck_pending" not in (q.get("details") or {})


# --- 8. Iteration isolation: L1-OK paper after an L1-deferred one does not inherit the flag ---


def test_recheck_marker_is_per_iteration_not_leaked_across_papers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: the new local vars `doi_recheck_pending` /
    `doi_recheck_details` MUST reset each loop iteration. If they
    leaked from a prior transient paper, a subsequent L1-OK paper would
    wrongly carry the marker."""
    def head_by_url(url, *_a, **_k):
        # Per-URL discrimination -- `_resolve_head_with_retry` may retry
        # the same DOI up to 3 times for transient statuses, so a
        # call-count toggle is unsafe.
        return _Resp(status_code=403 if "transient" in url else 200)

    monkeypatch.setattr(auth.requests, "head", head_by_url)
    _crossref_no_match(monkeypatch)
    transient_paper = _paper(doi="10.1/transient", backends=["crossref", "openalex"])
    clean_paper = _paper(doi="10.1/clean", backends=["crossref", "openalex"])

    accepted, quarantined = verify_authenticity(
        [transient_paper, clean_paper], _cfg(tmp_path), cluster_slug="c",
    )

    assert quarantined == []
    assert len(accepted) == 2
    by_doi = {p["doi"]: p for p in accepted}
    assert by_doi["10.1/transient"]["provenance"].get("doi_recheck_pending") is True
    # Critical regression: clean paper must NOT inherit the marker.
    assert "doi_recheck_pending" not in by_doi["10.1/clean"]["provenance"]
    assert "doi_recheck_details" not in by_doi["10.1/clean"]["provenance"]

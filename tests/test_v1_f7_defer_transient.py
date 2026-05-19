"""PR-C (deep F7): a TRANSIENT identifier-resolution failure (doi.org /
Crossref rate-limit, after PR-B's bounded retry) is recorded under the
distinct `L1-deferred` layer (reported as "deferred, retryable"), NOT
the plain `L1` quarantine (reported as "rejected"). Permanent failures
(404/410 -> `*_unresolved`) stay `L1` — the anti-fabrication guarantee
is unchanged. In both cases the paper is still held out of ingest
(fail-closed); only the classification/labelling differs.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import research_hub.authenticity as auth
from research_hub.authenticity import (
    DEFERRED_LAYER,
    is_transient_reason,
    verify_authenticity,
)


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    rh = root / ".research_hub"
    rh.mkdir(parents=True)
    return SimpleNamespace(research_hub_dir=rh)


def _paper(doi: str = "10.1000/real") -> dict:
    return {"title": "A Real Paper", "doi": doi, "abstract": "x" * 80}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(auth.time, "sleep", lambda *_a, **_k: None)


# ---- unit: classifier ----

@pytest.mark.parametrize("reason,expected", [
    ("doi_check_unavailable", True),
    ("arxiv_check_unavailable", True),
    ("identifier_check_unavailable", True),
    ("doi_unresolved", False),
    ("arxiv_unresolved", False),
    ("no_identifier", False),
    ("predatory_venue", False),
    ("", False),
])
def test_is_transient_reason(reason, expected):
    assert is_transient_reason(reason) is expected


# ---- gate: transient -> deferred, permanent -> L1 ----

def test_transient_418_is_deferred_not_quarantined(tmp_path, monkeypatch):
    # doi.org 418 (anti-bot) persists through PR-B's bounded retry ->
    # transient -> ok=False reason=doi_check_unavailable.
    monkeypatch.setattr("research_hub.authenticity.requests.head",
                        lambda *a, **k: _Response(418))
    accepted, quarantined = verify_authenticity(
        [_paper(doi="10.1109/access.2025.3548451")], _cfg(tmp_path),
        cluster_slug="c",
    )
    assert accepted == []                       # still held out (fail-closed)
    assert len(quarantined) == 1
    assert quarantined[0]["layer"] == DEFERRED_LAYER
    assert quarantined[0]["reason"] == "doi_check_unavailable"


def test_permanent_404_stays_L1_quarantine(tmp_path, monkeypatch):
    # Anti-fabrication regression guard: a genuine 404 is NOT transient
    # and must remain a plain L1 quarantine, exactly as before PR-C.
    monkeypatch.setattr("research_hub.authenticity.requests.head",
                        lambda *a, **k: _Response(404))
    accepted, quarantined = verify_authenticity(
        [_paper(doi="10.9999/does-not-exist")], _cfg(tmp_path),
        cluster_slug="c",
    )
    assert accepted == []
    assert len(quarantined) == 1
    assert quarantined[0]["layer"] == "L1"
    assert quarantined[0]["reason"] == "doi_unresolved"
    assert quarantined[0]["layer"] != DEFERRED_LAYER


def test_mixed_batch_splits_transient_and_permanent(tmp_path, monkeypatch):
    """One transient (418) + one permanent (404) in the same batch:
    both held out of ingest, but recorded under the correct layers."""
    def fake_head(url, **kwargs):
        return _Response(418 if "transient" in url else 404)

    monkeypatch.setattr("research_hub.authenticity.requests.head", fake_head)
    accepted, quarantined = verify_authenticity(
        [_paper(doi="10.1/transient-blocked"),
         _paper(doi="10.9/permanent-missing")],
        _cfg(tmp_path), cluster_slug="c",
    )
    assert accepted == []
    by_slug = {q["reason"]: q["layer"] for q in quarantined}
    assert by_slug["doi_check_unavailable"] == DEFERRED_LAYER
    assert by_slug["doi_unresolved"] == "L1"

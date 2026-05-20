"""PR-C / F7 deep transient classifier (still authoritative) + PR-B flow.

PR-C (deep F7) introduced the transient/permanent classification:
- Transient (anti-bot / rate-limit / unreachable, status -> `*_check_unavailable`)
- Permanent (404/410, status -> `*_unresolved`)

PR-B then changed where transient papers LAND: they no longer
quarantine at `L1-deferred`. Instead the gate falls through to
L2 (corroboration) + L3 (integrity) + fit-check; the paper is either
accepted (with `provenance.doi_recheck_pending=True`) or quarantined at
the failing downstream gate. The L1-deferred bucket is structurally
empty post-PR-B; ``DEFERRED_LAYER`` survives as a public constant used
by docs / reporting / tests.

Permanent failures (404/410) still quarantine at `L1 / doi_unresolved`
- the anti-fabrication guarantee is unchanged.
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
    return {
        "title": "A Real Paper",
        "doi": doi,
        "abstract": "x" * 80,
        "year": 2025,
        "authors": [{"firstName": "Jane", "lastName": "Doe"}],
    }


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


# ---- gate: transient falls through to downstream gates, permanent -> L1 ----

def test_transient_418_falls_through_uncorroborated_to_L2(tmp_path, monkeypatch):
    # doi.org 418 (anti-bot) persists through bounded retry -> transient
    # -> ok=False reason=doi_check_unavailable. Post-PR-B the paper falls
    # through to L2; this fixture paper has no corroboration setup so L2
    # quarantines it as uncorroborated -- NOT L1, NOT L1-deferred, and
    # critically NOT doi_unresolved (anti-fabrication: 418 is anti-bot
    # noise, not evidence the DOI is fake).
    monkeypatch.setattr("research_hub.authenticity.requests.head",
                        lambda *a, **k: _Response(418))
    monkeypatch.setattr(
        "research_hub.search.crossref.requests.get",
        lambda *a, **k: _Response(404),  # CrossRef-verify finds nothing
    )
    # Use a DOI with no embedded arxiv-id-looking pattern (the L2b
    # exemption auto-passes papers with arxiv_id / PMID / bioRxiv prefix).
    accepted, quarantined = verify_authenticity(
        [_paper(doi="10.1234/wiley-anti-bot-block")], _cfg(tmp_path),
        cluster_slug="c",
    )
    assert accepted == []                       # uncorroborated -> still held out
    assert len(quarantined) == 1
    q = quarantined[0]
    assert q["layer"] == "L2"
    assert q["reason"] == "uncorroborated"
    assert q["layer"] != DEFERRED_LAYER         # PR-B: bucket empty
    assert q["reason"] != "doi_unresolved"      # anti-fabrication intact


def test_permanent_404_stays_L1_quarantine(tmp_path, monkeypatch):
    # Anti-fabrication regression guard: a genuine 404 is NOT transient
    # and must remain a plain L1 quarantine, exactly as before PR-C/PR-B.
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


def test_mixed_batch_transient_and_permanent_route_distinctly(tmp_path, monkeypatch):
    """One transient (418) + one permanent (404) in the same batch:
    post-PR-B the transient falls through to L2 (uncorroborated for
    these no-backend fixtures) and the permanent stays at L1."""
    def fake_head(url, **kwargs):
        return _Response(418 if "transient" in url else 404)

    monkeypatch.setattr("research_hub.authenticity.requests.head", fake_head)
    monkeypatch.setattr(
        "research_hub.search.crossref.requests.get",
        lambda *a, **k: _Response(404),
    )
    accepted, quarantined = verify_authenticity(
        [_paper(doi="10.1/transient-blocked"),
         _paper(doi="10.9/permanent-missing")],
        _cfg(tmp_path), cluster_slug="c",
    )
    assert accepted == []
    by_reason = {q["reason"]: q["layer"] for q in quarantined}
    # Transient anti-bot routes to L2 uncorroborated (no corroboration);
    # permanent 404 stays at L1 / doi_unresolved.
    assert by_reason["uncorroborated"] == "L2"
    assert by_reason["doi_unresolved"] == "L1"
    assert DEFERRED_LAYER not in by_reason.values()

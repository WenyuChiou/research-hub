"""F7 regression: DOI resolver must send a real User-Agent and must not
fail-closed-quarantine (or cache) a valid paper on a transient
rate-limit / anti-bot block.

Root cause (verified 2026-05-18): the resolver used ``requests.head``
with the default ``python-requests`` UA. doi.org / Cloudflare answer
that bot fingerprint with HTTP 418, which the gate read as
``doi_unresolved`` and fail-closed-quarantined EVERY valid paper. A real
UA makes the same DOI return 200.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import research_hub.authenticity as auth
from research_hub.authenticity import (
    DEFERRED_LAYER,
    DoiResolveCache,
    _resolve_head_with_retry,
    _resolve_identifier,
    verify_authenticity,
)


class _Resp:
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
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry backoff must not slow the suite."""
    monkeypatch.setattr(auth.time, "sleep", lambda *_a, **_k: None)


def test_resolver_sends_real_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    def fake_head(url, **kwargs):
        seen.update(kwargs)
        return _Resp(200)

    monkeypatch.setattr(auth.requests, "head", fake_head)
    status, transient = _resolve_head_with_retry("https://doi.org/10.1/x")
    assert status == 200 and transient is False
    ua = seen.get("headers", {}).get("User-Agent", "")
    assert ua and "python-requests" not in ua  # the whole point of F7


def test_http_418_is_transient_not_unresolved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth.requests, "head", lambda *a, **k: _Resp(418))
    status, transient = _resolve_head_with_retry("https://doi.org/10.1/x", attempts=2)
    assert status == 418 and transient is True


@pytest.mark.parametrize("status_code", [401, 403, 451])
def test_antibot_access_statuses_defer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    monkeypatch.setattr(auth.requests, "head", lambda *a, **k: _Resp(status_code))

    status, transient = _resolve_head_with_retry("https://doi.org/10.1/x", attempts=2)
    assert status == status_code and transient is True

    cache_path = tmp_path / "doi_resolve_cache.json"
    cache = DoiResolveCache.load(cache_path)
    outcome = _resolve_identifier(_paper(), cache, cache_path)
    assert outcome.ok is False
    assert outcome.reason == "doi_check_unavailable"
    assert DoiResolveCache.load(cache_path).get(outcome.key) is None


def test_http_403_verification_is_l1_deferred(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth.requests, "head", lambda *a, **k: _Resp(403))
    accepted, quarantined = verify_authenticity(
        [_paper(doi="10.1111/jfr3.70039")],
        _cfg(tmp_path),
        cluster_slug="c",
    )

    assert accepted == []
    assert len(quarantined) == 1
    assert quarantined[0]["layer"] == DEFERRED_LAYER
    assert quarantined[0]["reason"] == "doi_check_unavailable"


@pytest.mark.parametrize("status_code", [404, 410])
def test_notfound_statuses_stay_permanent_failclosed(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    monkeypatch.setattr(auth.requests, "head", lambda *a, **k: _Resp(status_code))
    status, transient = _resolve_head_with_retry("https://doi.org/10.1/x")
    assert status == status_code and transient is False  # not an anti-bot block


def test_transient_then_success_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = [_Resp(429), _Resp(429), _Resp(200)]
    monkeypatch.setattr(auth.requests, "head", lambda *a, **k: calls.pop(0))
    status, transient = _resolve_head_with_retry("https://doi.org/10.1/x", attempts=3)
    assert status == 200 and transient is False


def test_5xx_stays_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth.requests, "head", lambda *a, **k: _Resp(500))
    status, transient = _resolve_head_with_retry("https://doi.org/10.1/x", attempts=2)
    assert status == 500 and transient is True


def test_request_exception_stays_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_head(*_args, **_kwargs):
        raise auth.requests.RequestException("timeout")

    monkeypatch.setattr(auth.requests, "head", fake_head)
    status, transient = _resolve_head_with_retry("https://doi.org/10.1/x", attempts=2)
    assert status is None and transient is True


def test_transient_outcome_is_not_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A 418 blip must NOT be cached as a permanent miss — a later run
    (e.g. after the UA fix takes effect / rate-limit lifts) must retry."""
    monkeypatch.setattr(auth.requests, "head", lambda *a, **k: _Resp(418))
    cache_path = tmp_path / "doi_resolve_cache.json"
    cache = DoiResolveCache.load(cache_path)
    paper = {"doi": "10.1109/access.2025.3548451", "title": "valid IEEE paper"}
    outcome = _resolve_identifier(paper, cache, cache_path)
    assert outcome.ok is False
    assert outcome.reason == "doi_check_unavailable"  # NOT doi_unresolved
    # nothing persisted: a fresh cache load sees no entry for this key
    assert DoiResolveCache.load(cache_path).get(outcome.key) is None


def test_real_404_is_cached_and_failclosed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Anti-fabrication preserved: a genuine 404 is still ok=False,
    reason=doi_unresolved, and cached."""
    monkeypatch.setattr(auth.requests, "head", lambda *a, **k: _Resp(404))
    cache_path = tmp_path / "doi_resolve_cache.json"
    cache = DoiResolveCache.load(cache_path)
    paper = {"doi": "10.9999/does-not-exist", "title": "fake"}
    outcome = _resolve_identifier(paper, cache, cache_path)
    assert outcome.ok is False
    assert outcome.reason == "doi_unresolved"
    assert DoiResolveCache.load(cache_path).get(outcome.key) is not None


def test_fabricated_404_stays_l1_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth.requests, "head", lambda *a, **k: _Resp(404))
    accepted, quarantined = verify_authenticity(
        [_paper(doi="10.9999/does-not-exist")],
        _cfg(tmp_path),
        cluster_slug="c",
    )

    assert accepted == []
    assert len(quarantined) == 1
    assert quarantined[0]["layer"] == "L1"
    assert quarantined[0]["reason"] == "doi_unresolved"
    assert quarantined[0]["layer"] != DEFERRED_LAYER

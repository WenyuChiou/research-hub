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

import pytest

import research_hub.authenticity as auth
from research_hub.authenticity import (
    DoiResolveCache,
    _resolve_head_with_retry,
    _resolve_identifier,
)


class _Resp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


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


def test_404_stays_permanent_failclosed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth.requests, "head", lambda *a, **k: _Resp(404))
    status, transient = _resolve_head_with_retry("https://doi.org/10.1/x")
    assert status == 404 and transient is False  # 404 != fake-bot block


def test_transient_then_success_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = [_Resp(429), _Resp(429), _Resp(200)]
    monkeypatch.setattr(auth.requests, "head", lambda *a, **k: calls.pop(0))
    status, transient = _resolve_head_with_retry("https://doi.org/10.1/x", attempts=3)
    assert status == 200 and transient is False


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

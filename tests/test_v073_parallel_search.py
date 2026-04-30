from __future__ import annotations

import threading
import time
from concurrent.futures import Future

from research_hub.search.base import SearchResult
from research_hub.search.fallback import search_papers


def _make_result(source: str, suffix: str, *, doi: str = "", arxiv_id: str = "", year: int = 2024) -> SearchResult:
    return SearchResult(
        title=f"{source}-{suffix}",
        doi=doi,
        arxiv_id=arxiv_id,
        year=year,
        source=source,
        citation_count=year - 2020,
    )


def _snapshot(results: list[SearchResult]) -> list[tuple[str, tuple[str, ...], int | None, int]]:
    return sorted(
        (
            result.dedup_key,
            tuple(sorted(result.found_in)),
            result.year,
            result.citation_count,
        )
        for result in results
    )


class _StaticBackend:
    delay = 0.0
    results: list[SearchResult] = []

    def search(self, query: str, **kwargs) -> list[SearchResult]:
        del query, kwargs
        time.sleep(self.delay)
        return list(self.results)


class _SerialExecutor:
    def __init__(self, max_workers: int):
        self.max_workers = max_workers

    def submit(self, fn, *args, **kwargs):
        future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as exc:  # pragma: no cover - exercised via failure path
            future.set_exception(exc)
        return future

    def shutdown(self, wait: bool = True, cancel_futures: bool = False):
        del wait, cancel_futures


def test_parallel_search_returns_same_result_set_as_serial(monkeypatch):
    import research_hub.search.fallback as fallback

    class BackendA(_StaticBackend):
        delay = 0.05
        results = [
            _make_result("alpha", "one", doi="10.1/shared", year=2024),
            _make_result("alpha", "two", doi="10.1/unique-a", year=2023),
        ]

    class BackendB(_StaticBackend):
        delay = 0.01
        results = [
            _make_result("beta", "one", doi="10.1/shared", year=2024),
            _make_result("beta", "two", doi="10.1/unique-b", year=2022),
        ]

    class BackendC(_StaticBackend):
        delay = 0.02
        results = [_make_result("gamma", "one", arxiv_id="2401.12345", year=2025)]

    class BackendD(_StaticBackend):
        delay = 0.03
        results = [_make_result("delta", "one", doi="10.1/unique-a", year=2023)]

    registry = {
        "alpha": BackendA,
        "beta": BackendB,
        "gamma": BackendC,
        "delta": BackendD,
    }
    monkeypatch.setattr(fallback, "_BACKEND_REGISTRY", registry)

    parallel = search_papers("query", backends=tuple(registry), limit=10, rank_by="year")

    with monkeypatch.context() as serial_patch:
        serial_patch.setattr(fallback, "ThreadPoolExecutor", _SerialExecutor)
        serial_patch.setattr(fallback, "as_completed", lambda futures, timeout=None: list(futures))
        serial = search_papers("query", backends=tuple(registry), limit=10, rank_by="year")

    assert _snapshot(parallel) == _snapshot(serial)


def test_parallel_search_one_failing_backend_doesnt_block_others(monkeypatch, caplog):
    import research_hub.search.fallback as fallback

    class OkOne(_StaticBackend):
        results = [_make_result("ok-one", "paper", doi="10.1/ok-one")]

    class BoomBackend:
        def search(self, query: str, **kwargs):
            del query, kwargs
            raise RuntimeError("backend exploded")

    class OkTwo(_StaticBackend):
        results = [_make_result("ok-two", "paper", doi="10.1/ok-two")]

    class OkThree(_StaticBackend):
        results = [_make_result("ok-three", "paper", doi="10.1/ok-three")]

    registry = {
        "ok-one": OkOne,
        "boom": BoomBackend,
        "ok-two": OkTwo,
        "ok-three": OkThree,
    }
    monkeypatch.setattr(fallback, "_BACKEND_REGISTRY", registry)

    caplog.set_level("INFO")
    results = search_papers("query", backends=tuple(registry), limit=10, backend_trace=True, rank_by="year")

    assert {result.doi for result in results} == {"10.1/ok-one", "10.1/ok-two", "10.1/ok-three"}
    assert "search backend boom failed: backend exploded" in caplog.text
    assert "backend boom: 0 hits" in caplog.text


def test_parallel_search_respects_pool_timeout(monkeypatch):
    import research_hub.search.fallback as fallback

    release_event = threading.Event()

    class FastOne(_StaticBackend):
        results = [_make_result("fast-one", "paper", doi="10.1/fast-one")]

    class HangingBackend:
        def search(self, query: str, **kwargs):
            del query, kwargs
            release_event.wait(120)
            return [_make_result("hang", "paper", doi="10.1/hang")]

    class FastTwo(_StaticBackend):
        results = [_make_result("fast-two", "paper", doi="10.1/fast-two")]

    registry = {
        "fast-one": FastOne,
        "hang": HangingBackend,
        "fast-two": FastTwo,
    }
    monkeypatch.setattr(fallback, "_BACKEND_REGISTRY", registry)

    started = time.perf_counter()
    try:
        results = search_papers("query", backends=tuple(registry), limit=10, rank_by="year")
    finally:
        release_event.set()
    elapsed = time.perf_counter() - started

    assert elapsed < 65.0
    assert {result.doi for result in results} == {"10.1/fast-one", "10.1/fast-two"}

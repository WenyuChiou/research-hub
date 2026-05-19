from __future__ import annotations

import json
from pathlib import Path

from research_hub.authenticity import DoiResolveCache, SCHEMA_VERSION


def _entry(
    key: str,
    *,
    ok: bool = False,
    status_code: int | None = None,
    reason: str = "doi_unresolved",
) -> dict:
    return {
        "ok": ok,
        "key": key,
        "resolved_via": "doi.org",
        "checked_at": "2026-05-18T00:00:00Z",
        "status_code": status_code,
        "reason": reason,
        "url": f"https://doi.org/{key.removeprefix('doi:')}",
    }


def _write_cache(path: Path, schema_version: str, results: dict[str, dict]) -> None:
    path.write_text(
        json.dumps({"schema_version": schema_version, "results": results}),
        encoding="utf-8",
    )


def _read_cache(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_pre_11_cache_with_poisoned_entries_is_pruned_and_bumped(
    tmp_path: Path,
    caplog,
) -> None:
    path = tmp_path / "doi_resolve_cache.json"
    _write_cache(
        path,
        "1.0",
        {
            "doi:10.1002/cav.2290": _entry("doi:10.1002/cav.2290", status_code=403),
            "doi:wang2026": _entry("doi:wang2026", status_code=418),
            "doi:fake.404": _entry("doi:fake.404", status_code=404),
            "doi:ok.paper": _entry("doi:ok.paper", ok=True, status_code=200, reason=""),
        },
    )

    with caplog.at_level("WARNING", logger="research_hub.authenticity"):
        cache = DoiResolveCache.load(path)

    assert set(cache.results) == {"doi:fake.404", "doi:ok.paper"}
    assert "pruned 2 stale" in caplog.text
    payload = _read_cache(path)
    assert payload["schema_version"] == SCHEMA_VERSION == "1.1"
    assert set(payload["results"]) == {"doi:fake.404", "doi:ok.paper"}


def test_pre_11_cache_without_poisoned_entries_is_bumped_unchanged(
    tmp_path: Path,
    caplog,
) -> None:
    path = tmp_path / "doi_resolve_cache.json"
    results = {
        "doi:fake.404": _entry("doi:fake.404", status_code=404),
        "doi:ok.paper": _entry("doi:ok.paper", ok=True, status_code=200, reason=""),
    }
    _write_cache(path, "1.0", results)

    with caplog.at_level("WARNING", logger="research_hub.authenticity"):
        cache = DoiResolveCache.load(path)

    assert set(cache.results) == set(results)
    assert "pruned" not in caplog.text
    payload = _read_cache(path)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["results"] == results


def test_already_11_cache_is_not_migrated_or_rewritten(tmp_path: Path) -> None:
    path = tmp_path / "doi_resolve_cache.json"
    results = {
        "doi:blocked.403": _entry("doi:blocked.403", status_code=403),
        "doi:fake.404": _entry("doi:fake.404", status_code=404),
    }
    _write_cache(path, SCHEMA_VERSION, results)
    before_mtime_ns = path.stat().st_mtime_ns

    cache = DoiResolveCache.load(path)

    assert set(cache.results) == set(results)
    assert "doi:blocked.403" in cache.results
    assert path.stat().st_mtime_ns == before_mtime_ns
    assert _read_cache(path)["results"] == results


def test_cache_migration_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "doi_resolve_cache.json"
    _write_cache(
        path,
        "1.0",
        {
            "doi:blocked.403": _entry("doi:blocked.403", status_code=403),
            "doi:fake.404": _entry("doi:fake.404", status_code=404),
            "doi:ok.paper": _entry("doi:ok.paper", ok=True, status_code=200, reason=""),
        },
    )

    first = DoiResolveCache.load(path)
    first_payload = _read_cache(path)
    second = DoiResolveCache.load(path)
    second_payload = _read_cache(path)

    assert set(first.results) == {"doi:fake.404", "doi:ok.paper"}
    assert set(second.results) == set(first.results)
    assert second_payload == first_payload


def test_arxiv_unresolved_entry_is_not_pruned(tmp_path: Path) -> None:
    """S2 regression guard: F7 anti-bot completion targeted ONLY the
    doi.org HEAD path. The `arxiv_unresolved` / `identifier_unresolved`
    reasons come from separate resolvers and were not affected; their
    cache entries must NOT be touched even with anti-bot-class status
    codes attached."""
    path = tmp_path / "doi_resolve_cache.json"
    _write_cache(
        path,
        "1.0",
        {
            "arxiv:2401.00001": _entry(
                "arxiv:2401.00001",
                status_code=403,
                reason="arxiv_unresolved",
            ),
            "other:custom-id": _entry(
                "other:custom-id",
                status_code=403,
                reason="identifier_unresolved",
            ),
        },
    )

    cache = DoiResolveCache.load(path)

    assert set(cache.results) == {"arxiv:2401.00001", "other:custom-id"}
    payload = _read_cache(path)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert set(payload["results"]) == {"arxiv:2401.00001", "other:custom-id"}


def test_statusless_doi_unresolved_entry_is_preserved(tmp_path: Path) -> None:
    path = tmp_path / "doi_resolve_cache.json"
    _write_cache(
        path,
        "1.0",
        {"doi:statusless": _entry("doi:statusless", status_code=None)},
    )

    cache = DoiResolveCache.load(path)

    assert set(cache.results) == {"doi:statusless"}
    payload = _read_cache(path)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["results"]["doi:statusless"]["status_code"] is None


def test_missing_empty_and_corrupt_cache_load_as_empty(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert DoiResolveCache.load(missing).results == {}

    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")
    assert DoiResolveCache.load(empty).results == {}

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    assert DoiResolveCache.load(corrupt).results == {}

    malformed = tmp_path / "malformed.json"
    malformed.write_text("[]", encoding="utf-8")
    assert DoiResolveCache.load(malformed).results == {}

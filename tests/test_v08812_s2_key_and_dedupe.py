"""v0.88.12 — Semantic Scholar API key + frontmatter list dedupe migration.

1. **Semantic Scholar API key (env var pass-through)**. Stage B hit HTTP
   429 from the anonymous shared pool. With ``SEMANTIC_SCHOLAR_API_KEY``
   set, the client sends ``x-api-key`` header and uses a conservative
   ~1 RPS throttle by default.

2. **`vault cleanup-frontmatter --dedupe-lists`** — backfill the
   v0.88.4 list-dedupe across pre-existing notes. W3 found 10/12
   human-water-llm papers still carry 3× repeated cluster_queries
   because they were ingested before v0.88.4 and never re-written
   since. Migration tool walks raw/*.md, dedupes
   `cluster_queries` / `tags` / `collections` / `aliases` in-place.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fix #1 — Semantic Scholar API key plumbing
# ---------------------------------------------------------------------------


def test_s2_client_reads_api_key_from_env(monkeypatch) -> None:
    """When SEMANTIC_SCHOLAR_API_KEY is set, the client picks it up."""
    from research_hub.search.semantic_scholar import SemanticScholarClient

    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-key-abc123")
    client = SemanticScholarClient()
    assert client.api_key == "test-key-abc123"


def test_s2_client_no_key_when_env_unset(monkeypatch) -> None:
    """No env var → no key + default polite throttle."""
    from research_hub.search.semantic_scholar import SemanticScholarClient

    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTIC_SCHOLAR_RPS", raising=False)
    client = SemanticScholarClient()
    assert client.api_key is None
    assert client.delay == 3.0  # default polite delay


def test_s2_client_lifts_throttle_with_api_key(monkeypatch) -> None:
    """Authenticated → default to a conservative ~1 RPS S2 throttle."""
    from research_hub.search.semantic_scholar import (
        DEFAULT_AUTHENTICATED_DELAY_SECONDS,
        SemanticScholarClient,
    )

    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "key")
    monkeypatch.delenv("SEMANTIC_SCHOLAR_RPS", raising=False)
    client = SemanticScholarClient(delay_seconds=10.0)
    assert client.delay == DEFAULT_AUTHENTICATED_DELAY_SECONDS


def test_s2_client_rps_env_overrides_default_delay(monkeypatch) -> None:
    """SEMANTIC_SCHOLAR_RPS lets higher-quota users tune the throttle."""
    from research_hub.search.semantic_scholar import SemanticScholarClient

    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "key")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_RPS", "0.5")

    client = SemanticScholarClient(delay_seconds=10.0)

    assert client.delay == 2.0


def test_s2_client_headers_include_x_api_key_when_authenticated(monkeypatch) -> None:
    """The x-api-key header is sent on every request when key is set."""
    from research_hub.search.semantic_scholar import SemanticScholarClient

    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "secret-456")
    client = SemanticScholarClient()
    headers = client._headers()
    assert headers == {"x-api-key": "secret-456"}


def test_s2_client_no_auth_headers_when_anonymous(monkeypatch) -> None:
    """Without key → no x-api-key header (avoid sending empty value)."""
    from research_hub.search.semantic_scholar import SemanticScholarClient

    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    client = SemanticScholarClient()
    assert client._headers() == {}


def test_s2_explicit_api_key_overrides_env(monkeypatch) -> None:
    """Passing api_key='' explicitly force-disables env lookup (test escape hatch)."""
    from research_hub.search.semantic_scholar import SemanticScholarClient

    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "from-env")
    client = SemanticScholarClient(api_key="")
    # Empty string is treated as anonymous (the env var is for accidental empty)
    assert client.api_key is None or client.api_key == ""


def test_s2_search_sends_api_key_header(monkeypatch) -> None:
    """End-to-end: search() passes headers to requests.get."""
    from research_hub.search import semantic_scholar as s2_mod

    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-key")
    captured_headers: dict = {}

    def fake_get(url, params=None, timeout=None, headers=None, **kwargs):
        captured_headers.update(headers or {})
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"data": []}
        response.raise_for_status = MagicMock()
        return response

    monkeypatch.setattr(s2_mod.requests, "get", fake_get)
    client = s2_mod.SemanticScholarClient()
    client.search("flood forecasting", limit=5)

    assert captured_headers.get("x-api-key") == "test-key"


# ---------------------------------------------------------------------------
# Fix #2 — vault cleanup-frontmatter migration
# ---------------------------------------------------------------------------


def _seed_note_with_dupe_queries(
    vault: Path, cluster: str, slug: str, queries: list[str]
) -> Path:
    """Write a paper note whose cluster_queries frontmatter has duplicates."""
    raw = vault / "raw" / cluster
    raw.mkdir(parents=True, exist_ok=True)
    path = raw / f"{slug}.md"
    queries_yaml = "\n".join(f"  - {q}" for q in queries)
    path.write_text(
        f"""---
title: "T"
authors: A
year: 2025
topic_cluster: "{cluster}"
zotero-key: KEY001
cluster_queries:
{queries_yaml}
tags:
  - topic:{cluster}
  - topic:{cluster}
verified: false
---

# T
""",
        encoding="utf-8",
    )
    return path


def test_migrate_one_note_dedupes_cluster_queries(tmp_path: Path) -> None:
    """The exact W3-flagged shape: 3× repeated 5-element batch → 5 unique."""
    from research_hub.vault.frontmatter_dedupe import migrate_one_note

    five_queries = [
        "LLMs for human-water systems",
        "hydrology",
        "flood risk",
        "sociohydrology",
        "agent-based modeling",
    ]
    accumulated = five_queries * 3  # 15 lines on disk
    note = _seed_note_with_dupe_queries(tmp_path, "demo", "p1", accumulated)

    result = migrate_one_note(note, dry_run=False)

    assert result.action == "deduped"
    assert "cluster_queries" in result.fields_deduped
    assert result.before["cluster_queries"] == 15
    assert result.after["cluster_queries"] == 5

    # Verify on-disk content
    text = note.read_text(encoding="utf-8")
    # Slice out the cluster_queries block exactly (between its header
    # and the next top-level frontmatter key).
    import re as _re
    cq_match = _re.search(
        r"^cluster_queries:\s*\n((?:  - .*\n)+)",
        text,
        _re.MULTILINE,
    )
    assert cq_match, "cluster_queries block missing after migration"
    bullet_lines = [
        line for line in cq_match.group(1).splitlines()
        if line.strip().startswith("- ")
    ]
    assert len(bullet_lines) == 5, f"Expected 5 unique queries, got {len(bullet_lines)}: {bullet_lines}"


def test_migrate_one_note_dedupes_tags(tmp_path: Path) -> None:
    """tags is also a list field that can accumulate dupes."""
    from research_hub.vault.frontmatter_dedupe import migrate_one_note

    note = _seed_note_with_dupe_queries(tmp_path, "demo", "p2", ["q1"])
    # The seed already produces tags with `topic:demo` duplicated 2×
    result = migrate_one_note(note, dry_run=False)
    assert "tags" in result.fields_deduped
    assert result.before["tags"] == 2
    assert result.after["tags"] == 1


def test_migrate_one_note_no_op_when_clean(tmp_path: Path) -> None:
    """A note with no list duplicates returns action='clean'."""
    from research_hub.vault.frontmatter_dedupe import migrate_one_note

    note = _seed_note_with_dupe_queries(tmp_path, "demo", "p3", ["unique-query"])
    # First run dedupes the duplicate `topic:demo` tags. Second run sees
    # everything clean and is a no-op.
    migrate_one_note(note, dry_run=False)
    result = migrate_one_note(note, dry_run=False)
    assert result.action == "clean"
    assert result.fields_deduped == []


def test_migrate_one_note_dry_run_does_not_write(tmp_path: Path) -> None:
    """Dry-run reports what would change without touching disk."""
    from research_hub.vault.frontmatter_dedupe import migrate_one_note

    note = _seed_note_with_dupe_queries(
        tmp_path, "demo", "p4", ["a", "a", "a", "b"]
    )
    before_text = note.read_text(encoding="utf-8")
    result = migrate_one_note(note, dry_run=True)

    assert result.action == "deduped"
    assert "cluster_queries" in result.fields_deduped
    assert result.before["cluster_queries"] == 4
    assert result.after["cluster_queries"] == 2
    # Disk content unchanged
    assert note.read_text(encoding="utf-8") == before_text


def test_migrate_all_walks_cluster_filter(tmp_path: Path) -> None:
    """cluster_slug_filter restricts to a single cluster — same pattern as
    tag_migrate / hub_backlink_migrate."""
    from research_hub.vault.frontmatter_dedupe import migrate_all

    _seed_note_with_dupe_queries(tmp_path, "alpha", "p1", ["x", "x"])
    _seed_note_with_dupe_queries(tmp_path, "beta", "p2", ["y", "y"])
    _seed_note_with_dupe_queries(tmp_path, "gamma", "p3", ["z", "z"])

    results_all = migrate_all(tmp_path, dry_run=True)
    assert len(results_all) == 3

    results_alpha = migrate_all(tmp_path, cluster_slug_filter="alpha", dry_run=True)
    assert len(results_alpha) == 1
    assert "alpha" in str(results_alpha[0].path)


def test_migrate_all_handles_missing_vault(tmp_path: Path) -> None:
    """Calling on a vault with no raw/ dir returns empty list (defensive)."""
    from research_hub.vault.frontmatter_dedupe import migrate_all

    # tmp_path has no `raw/` subdirectory
    results = migrate_all(tmp_path, dry_run=True)
    assert results == []

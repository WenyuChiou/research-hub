"""Tests for the auto abstract-recovery cascade inside summarize_pending.

v1.x: when is_bad_abstract() fires, summarize_pending now calls
recover_abstract() before marking a paper failed_no_abstract.  These
tests verify that cascade + the Semantic Scholar 429-retry backoff.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace


from research_hub.paper import _parse_frontmatter
from research_hub.paper_summarize import summarize_pending
from research_hub.search.abstract_recovery import (
    RecoveredAbstract,
    _recover_from_semantic_scholar,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_BACKEND_RESPONSE = """\
SUMMARY: The study investigates LLM-based agents for flood scheduling.

KEY_FINDINGS: Agents outperform rule-based baselines by 18 %.

METHODOLOGY: Monte Carlo simulation on a 12-node irrigation network.

RELEVANCE: Directly relevant to LLM agents in water resource management.
"""


def _cfg(tmp_path: Path) -> SimpleNamespace:
    raw = tmp_path / "raw"
    raw.mkdir()
    return SimpleNamespace(raw=raw)


def _write_note(
    cfg: SimpleNamespace,
    cluster: str,
    slug: str,
    *,
    status: str = "pending",
    abstract: str = "(no abstract)",
    doi: str = "",
) -> Path:
    path = Path(cfg.raw) / cluster / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    doi_line = f'doi: "{doi}"\n' if doi else ""
    path.write_text(
        f"""---
title: "{slug.title()}"
topic_cluster: "{cluster}"
summarize_status: {status}
{doi_line}---

# {slug.title()}

## Abstract

{abstract}

## Summary

> [!abstract] Summary pending

## Key Findings

> [!warning] Summary pending

## Methodology

> [!info] Summary pending

## Relevance

> [!note] Summary pending
""",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# recovery cascade in summarize_pending
# ---------------------------------------------------------------------------


def test_bad_abstract_with_doi_triggers_recovery_and_succeeds(
    tmp_path: Path, monkeypatch
) -> None:
    """When is_bad_abstract() fires on a note that has a doi, recover_abstract
    is called; if it returns substantive text the note is patched and
    summarization continues to completion.
    """
    cfg = _cfg(tmp_path)
    note = _write_note(cfg, "cluster", "paper-a", doi="10.test/abc")

    recovered_text = "A" * 300  # substantive

    monkeypatch.setattr(
        "research_hub.paper_summarize.recover_abstract",
        lambda doi: RecoveredAbstract(text=recovered_text, source="s2"),
    )
    monkeypatch.setattr(
        "research_hub.paper_summarize._invoke_backend",
        lambda backend, prompt: _BACKEND_RESPONSE,
    )

    results = summarize_pending(cfg, backend="claude")

    assert results[0].action == "done", results
    note_text = note.read_text(encoding="utf-8")
    assert "summarize_status: done" in note_text
    # Recovered abstract must be persisted in the note.
    assert recovered_text in note_text


def test_bad_abstract_with_doi_recovery_fails_marks_failed(
    tmp_path: Path, monkeypatch
) -> None:
    """When recovery returns empty, the paper is still marked failed_no_abstract."""
    cfg = _cfg(tmp_path)
    note = _write_note(cfg, "cluster", "paper-b", doi="10.test/no-abstract-anywhere")

    monkeypatch.setattr(
        "research_hub.paper_summarize.recover_abstract",
        lambda doi: RecoveredAbstract(text="", source=""),
    )

    def fail_backend(backend: str, prompt: str) -> str:
        raise AssertionError("backend must not be called when recovery fails")

    monkeypatch.setattr("research_hub.paper_summarize._invoke_backend", fail_backend)

    results = summarize_pending(cfg, backend="claude")

    assert results[0].action == "failed_no_abstract"
    assert "summarize_status: failed_no_abstract" in note.read_text(encoding="utf-8")


def test_bad_abstract_no_doi_skips_recovery_and_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """When the note has no doi, recovery is skipped entirely (no HTTP call)."""
    cfg = _cfg(tmp_path)
    note = _write_note(cfg, "cluster", "paper-c")  # no doi kwarg

    recover_called = []

    def _should_not_be_called(doi: str) -> RecoveredAbstract:
        recover_called.append(doi)
        return RecoveredAbstract(text="", source="")

    monkeypatch.setattr(
        "research_hub.paper_summarize.recover_abstract",
        _should_not_be_called,
    )

    results = summarize_pending(cfg, backend="claude")

    assert results[0].action == "failed_no_abstract"
    assert recover_called == [], "recover_abstract must not be called when doi is absent"


def test_bad_abstract_recovery_placeholder_treated_as_failure(
    tmp_path: Path, monkeypatch
) -> None:
    """If recovery returns a placeholder string (not substantive), paper still fails."""
    cfg = _cfg(tmp_path)
    _write_note(cfg, "cluster", "paper-d", doi="10.test/placeholder")

    monkeypatch.setattr(
        "research_hub.paper_summarize.recover_abstract",
        lambda doi: RecoveredAbstract(text="(no abstract)", source="crossref"),
    )

    results = summarize_pending(cfg, backend="claude")

    assert results[0].action == "failed_no_abstract"


def test_bad_abstract_recovery_dry_run_does_not_write(
    tmp_path: Path, monkeypatch
) -> None:
    """dry_run=True: even if recovery would succeed, the note is not written to disk."""
    cfg = _cfg(tmp_path)
    note = _write_note(cfg, "cluster", "paper-e", doi="10.test/abc-dry")
    original = note.read_text(encoding="utf-8")

    monkeypatch.setattr(
        "research_hub.paper_summarize.recover_abstract",
        lambda doi: RecoveredAbstract(text="A" * 300, source="s2"),
    )

    def fail_backend(backend: str, prompt: str) -> str:
        raise AssertionError("backend must not be called in dry_run mode")

    monkeypatch.setattr("research_hub.paper_summarize._invoke_backend", fail_backend)

    results = summarize_pending(cfg, backend="claude", dry_run=True)

    # In dry_run the recovery path can proceed but _write_note_text is skipped.
    # The result should be would_summarize (recovery succeeded, so no would_fail).
    assert results[0].action == "would_summarize"
    # Disk state must be unchanged.
    assert note.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# Semantic Scholar 429 retry / backoff
# ---------------------------------------------------------------------------


def test_s2_429_retries_with_backoff(monkeypatch) -> None:
    """_recover_from_semantic_scholar retries up to 2 times on HTTP 429."""
    attempt_count = []
    sleeps: list[float] = []

    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    class Resp429:
        status_code = 429
        def json(self): return {}

    class RespOK:
        status_code = 200
        def json(self):
            return {"abstract": "Recovered after rate limit", "tldr": None}

    def fake_get(*args, **kwargs):
        attempt_count.append(1)
        if len(attempt_count) < 3:
            return Resp429()
        return RespOK()

    monkeypatch.setattr("research_hub.search.abstract_recovery.requests.get", fake_get)

    result = _recover_from_semantic_scholar("10.test/rate-limited")

    assert result.source == "s2"
    assert "Recovered" in result.text
    assert len(attempt_count) == 3, f"Expected 3 attempts, got {len(attempt_count)}"
    assert sleeps == [5.0, 10.0], f"Expected backoff [5, 10], got {sleeps}"


def test_s2_429_exhausted_returns_empty(monkeypatch) -> None:
    """When all retries are exhausted on 429, returns empty RecoveredAbstract."""
    monkeypatch.setattr(time, "sleep", lambda s: None)

    class Resp429:
        status_code = 429
        def json(self): return {}

    monkeypatch.setattr(
        "research_hub.search.abstract_recovery.requests.get",
        lambda *a, **kw: Resp429(),
    )

    result = _recover_from_semantic_scholar("10.test/always-429", _retries=2)

    assert result.text == ""
    assert result.source == ""


def test_s2_200_success_no_sleep(monkeypatch) -> None:
    """Happy path: immediate 200 means no sleep is called."""
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    class RespOK:
        status_code = 200
        def json(self):
            return {"abstract": "Found immediately", "tldr": None}

    monkeypatch.setattr(
        "research_hub.search.abstract_recovery.requests.get",
        lambda *a, **kw: RespOK(),
    )

    result = _recover_from_semantic_scholar("10.test/ok")

    assert result.source == "s2"
    assert sleeps == []

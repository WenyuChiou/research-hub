"""v0.70.0 — auto pipeline LLM-judge fit-check between search and ingest.

Real incident motivating this change: an `auto` run for "post-flood
household relocation" returned 8 papers from search backends, but 2 of
them were off-topic — Llorca 2022 (autonomous vehicles + relocation,
nothing about floods) and Komleva 2025 (Soviet-era reservoir forced
resettlement, not climate adaptation). Both slipped past the
keyword-based fit_check because they shared vocabulary.

This test file pins the v0.70.0 behavior:
  - fit-check runs between search and ingest (not after)
  - LLM-rejected papers never hit Zotero/Obsidian
  - graceful fallback when no LLM CLI on PATH (keep all)
  - graceful fallback when LLM returns malformed JSON (keep all)
  - safety: if EVERY paper is rejected, keep all (better noise than nothing)
  - threshold parameter actually filters
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from research_hub.auto import _run_fit_check_step, AutoReport, auto_pipeline


# -- _run_fit_check_step unit tests -------------------------------------


def _make_papers(*titles_and_dois):
    return [
        {"title": t, "doi": d, "abstract": f"Abstract for {t}", "year": 2024, "authors": []}
        for t, d in titles_and_dois
    ]


def _mock_step_log_capture():
    """Capture _step_log calls so we can assert on the message detail."""
    captured: list[tuple] = []
    def fake(report, name, ok, dur, detail, _print):
        captured.append((name, ok, detail))
    return captured, fake


def test_fit_check_keeps_all_when_no_llm_cli(monkeypatch):
    """Best-effort: no CLI on PATH → skip silently, return all papers."""
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: None)
    cfg = SimpleNamespace(raw=None)
    papers = _make_papers(("A", "10/a"), ("B", "10/b"))
    report = AutoReport(cluster_slug="x", cluster_created=False)

    kept = _run_fit_check_step(cfg, papers, "topic", "x", None, 3, report, 0.0, False)

    assert len(kept) == 2
    assert kept == papers
    assert report.steps[-1].name == "fit_check"
    assert "skipped" in report.steps[-1].detail.lower()


def test_fit_check_filters_by_llm_score(monkeypatch):
    """Happy path: LLM scores 2 papers, threshold drops the low one."""
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: "claude")
    monkeypatch.setattr("research_hub.auto._invoke_llm_cli", lambda cli, prompt: '''
        {"scores": [
            {"doi": "10/a", "score": 5, "reason": "on topic"},
            {"doi": "10/b", "score": 1, "reason": "off topic"}
        ]}
    ''')
    cfg = SimpleNamespace(raw=None, hub=None)
    papers = _make_papers(("Paper A", "10/a"), ("Paper B", "10/b"))
    report = AutoReport(cluster_slug="x", cluster_created=False)

    kept = _run_fit_check_step(cfg, papers, "topic", "x", None, 3, report, 0.0, False)

    assert len(kept) == 1
    assert kept[0]["doi"] == "10/a"
    detail = report.steps[-1].detail
    assert "kept 1/2" in detail


def test_fit_check_keeps_all_on_unparseable_llm_json(monkeypatch):
    """LLM responded but JSON is broken → log failure, keep all (don't drop)."""
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: "claude")
    monkeypatch.setattr("research_hub.auto._invoke_llm_cli", lambda cli, prompt: "not JSON")
    cfg = SimpleNamespace(raw=None, hub=None)
    papers = _make_papers(("A", "10/a"), ("B", "10/b"))
    report = AutoReport(cluster_slug="x", cluster_created=False)

    kept = _run_fit_check_step(cfg, papers, "topic", "x", None, 3, report, 0.0, False)

    assert len(kept) == 2
    assert report.steps[-1].name == "fit_check"
    assert report.steps[-1].ok is False
    assert "unparseable" in report.steps[-1].detail.lower()


def test_fit_check_safety_fallback_when_all_rejected(monkeypatch):
    """If threshold rejects EVERY paper (rubric mismatch / threshold too
    high), fall back to keeping all rather than ingesting nothing."""
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: "claude")
    monkeypatch.setattr("research_hub.auto._invoke_llm_cli", lambda cli, prompt: '''
        {"scores": [
            {"doi": "10/a", "score": 1, "reason": "low"},
            {"doi": "10/b", "score": 0, "reason": "off"}
        ]}
    ''')
    cfg = SimpleNamespace(raw=None, hub=None)
    papers = _make_papers(("A", "10/a"), ("B", "10/b"))
    report = AutoReport(cluster_slug="x", cluster_created=False)

    kept = _run_fit_check_step(cfg, papers, "topic", "x", None, 3, report, 0.0, False)

    # safety fallback: all kept, log says so
    assert len(kept) == 2
    assert "fallback" in report.steps[-1].detail.lower()


def test_fit_check_lower_threshold_keeps_more(monkeypatch):
    """threshold=2 should keep papers scoring 2 that threshold=3 rejects."""
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: "claude")
    monkeypatch.setattr("research_hub.auto._invoke_llm_cli", lambda cli, prompt: '''
        {"scores": [
            {"doi": "10/a", "score": 4, "reason": "ok"},
            {"doi": "10/b", "score": 2, "reason": "borderline"}
        ]}
    ''')
    cfg = SimpleNamespace(raw=None, hub=None)
    papers = _make_papers(("A", "10/a"), ("B", "10/b"))
    report = AutoReport(cluster_slug="x", cluster_created=False)

    kept_low = _run_fit_check_step(cfg, papers, "topic", "x", None, 2, report, 0.0, False)
    assert len(kept_low) == 2  # threshold=2 keeps both

    report2 = AutoReport(cluster_slug="x", cluster_created=False)
    kept_high = _run_fit_check_step(cfg, papers, "topic", "x", None, 3, report2, 0.0, False)
    assert len(kept_high) == 1  # threshold=3 drops "10/b"
    assert kept_high[0]["doi"] == "10/a"


def test_fit_check_returns_empty_when_input_empty(monkeypatch):
    """Edge case: search returned 0 papers → fit-check returns 0 without
    invoking the LLM (would crash on empty prompt)."""
    invoked = []
    monkeypatch.setattr("research_hub.auto._invoke_llm_cli",
                        lambda cli, prompt: invoked.append(prompt) or '{"scores": []}')
    cfg = SimpleNamespace(raw=None, hub=None)
    report = AutoReport(cluster_slug="x", cluster_created=False)

    kept = _run_fit_check_step(cfg, [], "topic", "x", "claude", 3, report, 0.0, False)

    assert kept == []
    assert invoked == []  # short-circuited


def test_fit_check_explicit_cli_overrides_detection(monkeypatch):
    """Passing llm_cli should bypass detect_llm_cli."""
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: None)  # no CLI
    monkeypatch.setattr("research_hub.auto._invoke_llm_cli",
                        lambda cli, prompt: '{"scores": [{"doi": "10/a", "score": 5}]}')
    cfg = SimpleNamespace(raw=None, hub=None)
    papers = _make_papers(("A", "10/a"))
    report = AutoReport(cluster_slug="x", cluster_created=False)

    kept = _run_fit_check_step(cfg, papers, "topic", "x", "codex", 3, report, 0.0, False)

    assert len(kept) == 1
    # detail should mention codex was used
    assert "codex" in report.steps[-1].detail


# -- auto_pipeline integration tests ------------------------------------


@pytest.fixture
def mock_auto_deps():
    """Wire in mocks for cfg, registry, search, ingest, NLM — same shape
    as test_v046_auto.py's mock_deps fixture."""
    with patch("research_hub.auto.get_config") as mock_get_config, \
         patch("research_hub.auto.ClusterRegistry") as mock_cluster_registry, \
         patch("research_hub.auto.run_pipeline") as mock_run_pipeline, \
         patch("research_hub.auto.bundle_cluster") as mock_bundle, \
         patch("research_hub.auto.upload_cluster") as mock_upload, \
         patch("research_hub.auto.generate_artifact") as mock_generate, \
         patch("research_hub.auto.download_briefing_for_cluster") as mock_download, \
         patch("research_hub.auto._run_search") as mock_run_search:

        mock_cfg = MagicMock()
        mock_cfg.root = MagicMock()
        (mock_cfg.root / "papers_input.json").write_text = MagicMock()
        mock_cfg.raw = MagicMock()
        (mock_cfg.raw / "x").exists = lambda: False  # so report.papers_ingested stays from filter
        mock_get_config.return_value = mock_cfg

        registry_instance = MagicMock()
        # `registry.get(slug)` → cluster object with no zotero key
        cluster = MagicMock()
        cluster.zotero_collection_key = "EXISTING"
        registry_instance.get.return_value = cluster
        mock_cluster_registry.return_value = registry_instance

        mock_run_pipeline.return_value = 0

        yield {
            "get_config": mock_get_config,
            "cfg": mock_cfg,
            "registry": registry_instance,
            "run_pipeline": mock_run_pipeline,
            "run_search": mock_run_search,
        }


def test_auto_pipeline_runs_fit_check_by_default(mock_auto_deps, monkeypatch):
    """do_fit_check defaults to True. Search returns 3, LLM keeps 1, ingest
    only sees 1."""
    mock_auto_deps["run_search"].return_value = _make_papers(
        ("On-topic", "10/a"), ("Off-topic AV", "10/b"), ("Off-topic Soviet", "10/c"),
    )
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: "claude")
    monkeypatch.setattr("research_hub.auto._invoke_llm_cli", lambda cli, prompt: '''
        {"scores": [
            {"doi": "10/a", "score": 5},
            {"doi": "10/b", "score": 1},
            {"doi": "10/c", "score": 1}
        ]}
    ''')

    report = auto_pipeline(
        "test topic", do_nlm=False, print_progress=False,
    )

    assert report.ok
    assert report.papers_ingested == 1  # filtered down from 3
    fit_steps = [s for s in report.steps if s.name == "fit_check"]
    assert len(fit_steps) == 1
    assert "kept 1/3" in fit_steps[0].detail


def test_auto_pipeline_skips_fit_check_when_disabled(mock_auto_deps, monkeypatch):
    """do_fit_check=False → no fit_check step, ingest sees all results."""
    mock_auto_deps["run_search"].return_value = _make_papers(
        ("X", "10/x"), ("Y", "10/y"),
    )
    invoked = []
    monkeypatch.setattr("research_hub.auto._invoke_llm_cli",
                        lambda cli, prompt: invoked.append(prompt) or "")

    report = auto_pipeline(
        "test topic", do_nlm=False, do_fit_check=False, print_progress=False,
    )

    assert report.ok
    assert report.papers_ingested == 2
    assert all(s.name != "fit_check" for s in report.steps)
    assert invoked == []  # LLM never invoked


def test_auto_pipeline_dry_run_plan_mentions_fit_check(mock_auto_deps, monkeypatch, capsys):
    """Dry-run plan output should list the fit_check step when enabled."""
    mock_auto_deps["registry"].get.return_value = None  # cluster does not exist
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: "claude")

    auto_pipeline("test topic", dry_run=True, print_progress=True)
    output = capsys.readouterr().out
    assert "fit-check via LLM judge" in output
    assert "claude" in output
    assert "threshold=3" in output


def test_auto_pipeline_fit_check_threshold_param_propagates(mock_auto_deps, monkeypatch):
    """fit_check_threshold=2 should pass through to _run_fit_check_step
    and let borderline (score=2) papers through."""
    mock_auto_deps["run_search"].return_value = _make_papers(
        ("Strong", "10/a"), ("Borderline", "10/b"),
    )
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: "claude")
    monkeypatch.setattr("research_hub.auto._invoke_llm_cli", lambda cli, prompt: '''
        {"scores": [
            {"doi": "10/a", "score": 5},
            {"doi": "10/b", "score": 2}
        ]}
    ''')

    report = auto_pipeline(
        "topic", do_nlm=False, fit_check_threshold=2, print_progress=False,
    )

    assert report.papers_ingested == 2
    fit_step = [s for s in report.steps if s.name == "fit_check"][0]
    assert "threshold=2" in fit_step.detail

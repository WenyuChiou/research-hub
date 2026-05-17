"""Phase C / v1.0 — fail-closed first-run UX contract tests.

Phase A made the relevance gate fail-CLOSED (no LLM judge -> every
paper quarantined). That is correct, but a fresh-clone user with no
`claude`/`codex`/`gemini` on PATH used to discover it only AFTER the
slow multi-backend search, ending with a silent empty vault.

Phase C surfaces it WITHOUT weakening the gate:
  - C1: a pre-flight guard exits BEFORE the search with actionable
        guidance; the only opt-out is the explicit, pre-existing
        --no-fit-check (do_fit_check=False).
  - C2: _print_next_steps emits a quarantine summary + the Phase A
        `research-hub quarantine ...` recovery commands so an
        empty/short vault is auditable, not a mystery.

These lock that contract: the pre-flight must short-circuit before
`_run_search`, the opt-out must still run, the judge-present path
must be unaffected, and the summary must name reasons + recovery.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from research_hub.auto import AutoReport, _print_next_steps, auto_pipeline
from research_hub.authenticity import quarantine_paper


def _make_papers(*titles_and_dois):
    return [
        {"title": t, "doi": d, "abstract": f"Abstract for {t}", "year": 2024, "authors": []}
        for t, d in titles_and_dois
    ]


@pytest.fixture
def mock_auto_deps(tmp_path):
    """Same shape as test_v070_auto_fit_check.py::mock_auto_deps — wires
    cfg/registry/search/ingest so auto_pipeline runs without real I/O."""
    with patch("research_hub.auto.get_config") as mock_get_config, \
         patch("research_hub.auto.ClusterRegistry") as mock_cluster_registry, \
         patch("research_hub.auto.run_pipeline") as mock_run_pipeline, \
         patch("research_hub.auto.bundle_cluster"), \
         patch("research_hub.auto.upload_cluster"), \
         patch("research_hub.auto.generate_artifact"), \
         patch("research_hub.auto.download_briefing_for_cluster"), \
         patch("research_hub.auto._run_search") as mock_run_search:

        root = tmp_path / "vault"
        mock_cfg = MagicMock()
        mock_cfg.root = root
        mock_cfg.raw = root / "raw"
        mock_cfg.hub = root / "hub"
        mock_cfg.research_hub_dir = root / ".research_hub"
        for path in (mock_cfg.raw, mock_cfg.hub, mock_cfg.research_hub_dir):
            path.mkdir(parents=True, exist_ok=True)
        mock_get_config.return_value = mock_cfg

        registry_instance = MagicMock()
        cluster = MagicMock()
        cluster.zotero_collection_key = "EXISTING"
        registry_instance.get.return_value = cluster
        mock_cluster_registry.return_value = registry_instance

        mock_run_pipeline.return_value = 0

        yield {
            "cfg": mock_cfg,
            "registry": registry_instance,
            "run_pipeline": mock_run_pipeline,
            "run_search": mock_run_search,
        }


# --- C1: pre-flight guard --------------------------------------------


def test_preflight_blocks_before_search_when_no_judge(mock_auto_deps, monkeypatch):
    """No judge on PATH + do_fit_check (default) → exit BEFORE the slow
    search, with actionable guidance. The search must never run."""
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: None)

    report = auto_pipeline("test topic", do_nlm=False, print_progress=False)

    assert report.ok is False
    assert "--no-fit-check" in report.error
    assert "fail-closed" in report.error
    # The whole point of Phase C: no time wasted on a doomed search.
    mock_auto_deps["run_search"].assert_not_called()
    mock_auto_deps["run_pipeline"].assert_not_called()
    # No fit_check step ran either — we bailed before it.
    assert all(s.name != "fit_check" for s in report.steps)


def test_preflight_bypassed_by_explicit_no_fit_check(mock_auto_deps, monkeypatch):
    """The ONLY opt-out is the explicit, pre-existing --no-fit-check.
    With it, the run proceeds (papers still get L0/L1/L3 in pipeline);
    Phase C does NOT add a force/weaken path."""
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: None)
    mock_auto_deps["run_search"].return_value = _make_papers(("A", "10/a"))

    report = auto_pipeline(
        "test topic", do_nlm=False, do_fit_check=False, print_progress=False,
    )

    assert report.ok
    mock_auto_deps["run_search"].assert_called_once()
    assert all(s.name != "fit_check" for s in report.steps)


def test_preflight_not_triggered_when_judge_present(mock_auto_deps, monkeypatch):
    """Regression: judge present → normal flow unaffected, search runs,
    fit-check runs. Phase C must not perturb the happy path."""
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: "claude")
    monkeypatch.setattr(
        "research_hub.auto._invoke_llm_cli",
        lambda cli, prompt: '{"scores": [{"doi": "10/a", "score": 5}]}',
    )
    mock_auto_deps["run_search"].return_value = _make_papers(("A", "10/a"))

    report = auto_pipeline("test topic", do_nlm=False, print_progress=False)

    assert report.ok
    mock_auto_deps["run_search"].assert_called_once()
    assert any(s.name == "fit_check" for s in report.steps)


def test_preflight_message_printed_when_progress_on(mock_auto_deps, monkeypatch, capsys):
    """print_progress=True → the 3-option guidance reaches the user."""
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: None)

    auto_pipeline("test topic", do_nlm=False, print_progress=True)
    out = capsys.readouterr().out

    assert "No relevance judge" in out
    assert "--no-fit-check" in out
    assert "research-hub doctor" in out


# --- C2: end-of-run quarantine summary -------------------------------


def _summary_cfg(tmp_path):
    root = tmp_path / "vault"
    rh = root / ".research_hub"
    rh.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(root=root, raw=root / "raw", hub=root / "hub", research_hub_dir=rh)


def test_quarantine_summary_emitted_with_reasons_and_recovery(tmp_path, capsys):
    """A non-empty quarantine for the cluster → _print_next_steps names
    the counts-by-reason AND the Phase A recovery commands."""
    cfg = _summary_cfg(tmp_path)
    slug = "flood-risk"
    quarantine_paper(
        cfg, _make_papers(("Off topic", "10/x"))[0],
        cluster_slug=slug, layer="L4", reason="relevance_unjudged",
    )
    quarantine_paper(
        cfg, _make_papers(("Bad DOI", "10/y"))[0],
        cluster_slug=slug, layer="L1", reason="doi_unresolved",
    )
    report = AutoReport(cluster_slug=slug, cluster_created=False)

    _print_next_steps(report, slug, cfg, do_crystals=True)
    out = capsys.readouterr().out

    assert "[quarantine] 2 paper(s)" in out
    assert "relevance_unjudged: 1" in out
    assert "doi_unresolved: 1" in out
    assert f"research-hub quarantine list --cluster {slug}" in out
    assert f"research-hub quarantine restore <paper-slug> --cluster {slug}" in out


def test_quarantine_summary_silent_when_nothing_quarantined(tmp_path, capsys):
    """No quarantine → no [quarantine] block (don't cry wolf), but the
    normal next-steps still print."""
    cfg = _summary_cfg(tmp_path)
    report = AutoReport(cluster_slug="clean", cluster_created=False)

    _print_next_steps(report, "clean", cfg, do_crystals=True)
    out = capsys.readouterr().out

    assert "[quarantine]" not in out
    assert "Next steps (copy-paste any of these):" in out

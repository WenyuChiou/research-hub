"""PR-B regression: ingest + NLM upload must report honestly.

F6: `auto` printed `[OK] ingest N papers` when EVERY candidate was
quarantined (raw dir never created -> the `exists()` guard skipped ->
the tentative `len(papers)` count survived). Now the count is
authoritative and a 0-written ingest is NOT rendered as a clean step.

F8: `notebooklm upload` returned exit 0 when the NotebookLM source API
drifted and 0 sources were transferred/cached/pruned (notebook created
but empty). Now that is a non-zero error.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from research_hub.auto import auto_pipeline
from research_hub.notebooklm.upload import UploadReport, UploadResult


# --------------------------------------------------------------------------
# F6 — honest ingest count
# --------------------------------------------------------------------------

@pytest.fixture
def auto_env(tmp_path):
    """auto_pipeline with a REAL raw dir so the F6 count logic runs for
    real, and list_quarantine/run_pipeline/_run_search mocked."""
    raw = tmp_path / "raw"
    raw.mkdir()
    cfg = MagicMock()
    cfg.raw = raw
    cfg.root = tmp_path
    cfg.research_hub_dir = tmp_path / ".research_hub"
    with patch("research_hub.auto.get_config", return_value=cfg), \
         patch("research_hub.auto.ClusterRegistry") as reg, \
         patch("research_hub.auto.run_pipeline", return_value=0), \
         patch("research_hub.auto._run_search",
               return_value=[{"title": "P1"}, {"title": "P2"}]), \
         patch("research_hub.auto._run_fit_check_step",
               side_effect=lambda cfg, papers, *a, **k: papers), \
         patch("research_hub.auto.detect_llm_cli", return_value="claude"), \
         patch("research_hub.authenticity.list_quarantine") as lq:
        reg.return_value = MagicMock()
        yield SimpleNamespace(cfg=cfg, raw=raw, list_quarantine=lq, registry=reg)


def _ingest_step(report):
    return next(s for s in report.steps if s.name == "ingest")


def test_f6_all_quarantined_is_not_ok(auto_env):
    # raw dir stays empty (run_pipeline mocked, writes nothing) and both
    # candidates are "quarantined".
    auto_env.list_quarantine.return_value = [{"slug": "p1"}, {"slug": "p2"}]

    report = auto_pipeline(topic="t", do_nlm=False, do_fit_check=False,
                           print_progress=False)

    assert report.papers_ingested == 0          # NOT the tentative 2
    step = _ingest_step(report)
    assert step.ok is False                      # renders [FAIL], not [OK]
    assert "0 written" in step.detail
    assert "2 quarantined" in step.detail
    assert "quarantine list" in (report.error or "")
    # path B: quarantine-of-all is the safety gate working, not an
    # orchestration crash — report.ok is intentionally NOT flipped so
    # the end-of-run quarantine summary still runs.
    assert report.ok is True


def test_f6_partial_write_counts_truthfully(auto_env):
    # one paper actually written, one quarantined
    (auto_env.raw / "t").mkdir(parents=True)
    (auto_env.raw / "t" / "p1.md").write_text("x", encoding="utf-8")
    auto_env.list_quarantine.return_value = [{"slug": "p2"}]

    report = auto_pipeline(topic="t", do_nlm=False, do_fit_check=False,
                           print_progress=False)

    assert report.papers_ingested == 1
    step = _ingest_step(report)
    assert step.ok is True
    assert "1 written" in step.detail
    assert "1 quarantined" in step.detail


# --------------------------------------------------------------------------
# F8 — NLM upload that transfers nothing is not a success
# --------------------------------------------------------------------------

def _run_nlm_upload(monkeypatch, report: UploadReport):
    from research_hub import cli

    monkeypatch.setattr(cli, "get_config", lambda: MagicMock())
    monkeypatch.setattr(cli, "ClusterRegistry", lambda *_a, **_k: MagicMock(
        get=lambda *_: MagicMock()))
    monkeypatch.setattr(
        "research_hub.notebooklm.upload.upload_cluster",
        lambda *a, **k: report,
    )
    monkeypatch.setattr(
        "research_hub.notebooklm.upload.check_cluster_capacity",
        lambda *a, **k: None,
    )
    # bypass the NLM session preflight (F3) — not under test here
    monkeypatch.setattr(cli, "_preflight_nlm_session", lambda *a, **k: None)
    return cli._nlm_upload(
        "c", dry_run=False, headless=True, create_if_missing=True,
    )


def test_f8_nothing_transferred_is_error(monkeypatch, capsys):
    report = UploadReport(cluster_slug="c", notebook_url="http://nb",
                          uploaded=[], skipped_already_uploaded=0)
    rc = _run_nlm_upload(monkeypatch, report)
    assert rc == 1
    assert "0 sources uploaded" in capsys.readouterr().err


def test_f8_real_upload_still_succeeds(monkeypatch):
    report = UploadReport(
        cluster_slug="c",
        uploaded=[UploadResult(success=True, source_kind="url",
                               path_or_url="http://x")],
    )
    assert _run_nlm_upload(monkeypatch, report) == 0


def test_f8_cache_only_upload_is_success(monkeypatch):
    # nothing newly uploaded but everything was already cached -> fine
    report = UploadReport(cluster_slug="c", uploaded=[],
                          skipped_already_uploaded=3)
    assert _run_nlm_upload(monkeypatch, report) == 0

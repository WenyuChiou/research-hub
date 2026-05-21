"""Tests for NLM session pre-flight check in auto_pipeline (v1.1.0).

When check_session_health returns ok=False, auto_pipeline must:
  - set nlm_deferred=True with a "preflight" error string
  - return ok=True (pipeline itself succeeded; NLM is skipped gracefully)
  - NOT attempt bundle/upload/generate/download
  - print a [HINT] pointing at `notebooklm login`

When check_session_health returns ok=True, the preflight passes and the
normal NLM steps run (or raise, which is caught and deferred as before).

When the health check itself raises (e.g. import error), auto_pipeline
must fall through to the normal NLM steps (backward compatibility).
"""
from __future__ import annotations

from pathlib import Path

import json

import pytest

import research_hub.auto as auto_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _paper_input(title: str, slug: str, doi: str) -> dict:
    return {
        "title": title,
        "authors": ["Author A"],
        "year": 2025,
        "doi": doi,
        "abstract": "Abstract text.",
        "source": "test",
        "slug": slug,
        "score": 0.9,
    }


def _setup_auto_pipeline(tmp_path: Path, monkeypatch, *, papers: int = 1):
    """Wire a minimal auto_pipeline that skips real network + file writes."""
    import research_hub.config as cfg_mod

    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    logs = root / "logs"
    research_hub_dir = root / ".research_hub"
    for p in (raw, hub, logs, research_hub_dir):
        p.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({
            "knowledge_base": {
                "root": str(root),
                "raw": str(raw),
                "hub": str(hub),
                "logs": str(logs),
            },
            "clusters_file": str(research_hub_dir / "clusters.yaml"),
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("RESEARCH_HUB_CONFIG", str(config_path))
    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(root))
    cfg_mod._config = None
    cfg_mod._config_path = None
    cfg = cfg_mod.get_config()
    (cfg.research_hub_dir / "dedup_index.json").write_text("{}", encoding="utf-8")

    fake_papers = [_paper_input(f"Paper {i}", f"paper-{i}", f"10.0/{i}") for i in range(papers)]

    monkeypatch.setattr(auto_mod, "_ensure_zotero_collection", lambda *a, **k: None)
    monkeypatch.setattr(auto_mod, "_run_search", lambda *a, **k: fake_papers)
    # run_pipeline must return integer exit code 0 for success.
    monkeypatch.setattr(auto_mod, "run_pipeline", lambda *a, **k: 0)
    # stub populate_all_overviews so vault state is irrelevant
    monkeypatch.setattr(
        "research_hub.vault.hub_overview.populate_all_overviews",
        lambda *a, **k: None,
        raising=False,
    )

    return cfg


# ---------------------------------------------------------------------------
# Preflight: session not valid → graceful skip + HINT
# ---------------------------------------------------------------------------

def test_nlm_preflight_skip_when_session_invalid(tmp_path, monkeypatch, capsys):
    """auto_pipeline defers NLM and prints a HINT when session health = not ok."""
    cfg = _setup_auto_pipeline(tmp_path, monkeypatch)

    # Patch check_session_health inside auto_module's import path.
    import research_hub.notebooklm.auth as auth_mod
    monkeypatch.setattr(
        auth_mod,
        "check_session_health",
        lambda state_file: {"ok": False, "reason": "state.json missing"},
    )

    bundle_called = []
    monkeypatch.setattr(
        "research_hub.notebooklm.bundle.bundle_cluster",
        lambda *a, **k: bundle_called.append(1) or type("R", (), {"pdf_count": 0})(),
    )

    report = auto_mod.auto_pipeline(
        "test query",
        do_nlm=True,
        do_fit_check=False,
        do_cluster_overview=False,
        print_progress=True,
    )

    assert report.ok is True
    assert report.nlm_deferred is True
    assert "preflight" in report.nlm_error
    assert not bundle_called, "bundle_cluster must NOT be called when session is invalid"

    out = capsys.readouterr().out
    assert "HINT" in out
    assert "notebooklm login" in out
    assert "session expired. Fix:" in out
    assert "Resume with:" not in out


def test_nlm_preflight_does_not_skip_when_session_valid(tmp_path, monkeypatch):
    """When session is healthy, preflight passes and the normal NLM steps run."""
    cfg = _setup_auto_pipeline(tmp_path, monkeypatch)

    import research_hub.notebooklm.auth as auth_mod
    monkeypatch.setattr(
        auth_mod,
        "check_session_health",
        lambda state_file: {"ok": True, "reason": "ok"},
    )

    # Stub the actual NLM steps so we don't need a real browser.
    bundle_called = []

    def fake_bundle(cluster, cfg_, **kw):
        bundle_called.append(1)
        return type("R", (), {"pdf_count": 0})()

    monkeypatch.setattr("research_hub.notebooklm.bundle.bundle_cluster", fake_bundle)
    monkeypatch.setattr(
        "research_hub.notebooklm.upload.upload_cluster",
        lambda *a, **k: type("R", (), {"success_count": 0, "notebook_url": None, "notebook_was_reused": False})(),
    )
    monkeypatch.setattr(
        "research_hub.notebooklm.upload.generate_artifact",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "research_hub.notebooklm.upload.download_briefing_for_cluster",
        lambda *a, **k: type("R", (), {"artifact_path": None, "char_count": 0})(),
    )

    report = auto_mod.auto_pipeline(
        "test query",
        do_nlm=True,
        do_fit_check=False,
        do_cluster_overview=False,
        print_progress=False,
    )

    assert bundle_called, "bundle_cluster MUST be called when session is valid"
    assert report.nlm_deferred is False
    assert not report.nlm_error


def test_nlm_preflight_fallthrough_on_health_check_error(tmp_path, monkeypatch):
    """If check_session_health itself raises, auto_pipeline falls through to normal NLM steps."""
    cfg = _setup_auto_pipeline(tmp_path, monkeypatch)

    import research_hub.notebooklm.auth as auth_mod
    monkeypatch.setattr(
        auth_mod,
        "check_session_health",
        lambda state_file: (_ for _ in ()).throw(RuntimeError("import failure")),
    )

    bundle_called = []

    def fake_bundle(cluster, cfg_, **kw):
        bundle_called.append(1)
        raise RuntimeError("browser not available")  # normal NLM deferred path

    monkeypatch.setattr("research_hub.notebooklm.bundle.bundle_cluster", fake_bundle)

    report = auto_mod.auto_pipeline(
        "test query",
        do_nlm=True,
        do_fit_check=False,
        do_cluster_overview=False,
        print_progress=False,
    )

    assert report.ok is True
    # The normal NLM exception path defers without "preflight" in the error.
    assert bundle_called
    assert "preflight" not in (report.nlm_error or "")


def test_nlm_preflight_not_run_when_do_nlm_false(tmp_path, monkeypatch):
    """do_nlm=False must bypass the preflight entirely."""
    cfg = _setup_auto_pipeline(tmp_path, monkeypatch)

    import research_hub.notebooklm.auth as auth_mod
    health_called = []
    monkeypatch.setattr(
        auth_mod,
        "check_session_health",
        lambda state_file: health_called.append(1) or {"ok": False, "reason": "expired"},
    )

    report = auto_mod.auto_pipeline(
        "test query",
        do_nlm=False,
        do_fit_check=False,
        do_cluster_overview=False,
        print_progress=False,
    )

    assert report.ok is True
    assert not health_called, "check_session_health must NOT be called when do_nlm=False"
    assert report.nlm_deferred is False

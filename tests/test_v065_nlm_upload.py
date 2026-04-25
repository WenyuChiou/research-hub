from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from research_hub.notebooklm.client import NotebookLMError, UploadResult
from research_hub.notebooklm import upload as nlm_upload


@pytest.fixture
def fake_page():
    page = MagicMock()
    page.url = "https://notebooklm.google.com/"
    return page


def _cluster() -> SimpleNamespace:
    return SimpleNamespace(slug="alpha", name="Alpha", notebooklm_notebook="")


def _cfg(tmp_path: Path) -> SimpleNamespace:
    hub = tmp_path / ".research_hub"
    hub.mkdir()
    return SimpleNamespace(research_hub_dir=hub, clusters_file=hub / "clusters.yaml")


def _write_bundle(tmp_path: Path, cluster_slug: str, entries: list[dict]) -> Path:
    bundle_dir = tmp_path / "bundles" / f"{cluster_slug}-20260425T000000Z"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "manifest.json").write_text(
        json.dumps({"entries": entries}),
        encoding="utf-8",
    )
    return bundle_dir


def test_check_session_health_accepts_live_notebooklm_page(fake_page):
    ok, detail = nlm_upload._check_session_health(fake_page)

    assert ok is True
    assert detail == "https://notebooklm.google.com/"
    fake_page.goto.assert_called_once()
    fake_page.wait_for_load_state.assert_called_once_with("networkidle")


def test_check_session_health_rejects_auth_redirect(fake_page):
    fake_page.url = "https://accounts.google.com/signin/v2/challenge"

    ok, detail = nlm_upload._check_session_health(fake_page)

    assert ok is False
    assert "expired" in detail
    assert "accounts.google.com" in detail


def test_check_session_health_reports_navigation_failure(fake_page):
    fake_page.goto.side_effect = RuntimeError("boom")

    ok, detail = nlm_upload._check_session_health(fake_page)

    assert ok is False
    assert "Could not reach NotebookLM home" in detail
    assert "boom" in detail


def test_find_latest_bundle_picks_most_recent_directory(tmp_path: Path):
    bundles_root = tmp_path / "bundles"
    older = bundles_root / "alpha-old"
    newer = bundles_root / "alpha-new"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    older.touch()
    newer.touch()

    result = nlm_upload._find_latest_bundle(bundles_root, "alpha")

    assert result == newer


def test_upload_with_retry_retries_until_success(monkeypatch, tmp_path: Path):
    log_path = tmp_path / "upload.jsonl"
    sleeps: list[int] = []
    results = [
        UploadResult(source_kind="url", path_or_url="https://a", success=False, error="try again"),
        UploadResult(source_kind="url", path_or_url="https://a", success=True),
    ]
    client = SimpleNamespace(upload_url=lambda _url: results.pop(0))
    monkeypatch.setattr(nlm_upload.time, "sleep", sleeps.append)

    result = nlm_upload._upload_with_retry(
        client,
        {"action": "url", "url": "https://a"},
        log_path,
    )

    assert result.success is True
    assert sleeps == [1]
    events = log_path.read_text(encoding="utf-8").splitlines()
    assert len(events) == 4


def test_upload_with_retry_skips_unknown_action(tmp_path: Path):
    log_path = tmp_path / "upload.jsonl"
    client = SimpleNamespace(upload_pdf=lambda _path: None, upload_url=lambda _url: None)

    result = nlm_upload._upload_with_retry(
        client,
        {"action": "doi", "doi": "10.1/example"},
        log_path,
    )

    assert result is None
    text = log_path.read_text(encoding="utf-8")
    assert "upload_skip" in text


def test_count_attempts_for_key_ignores_bad_json(tmp_path: Path):
    log_path = tmp_path / "upload.jsonl"
    log_path.write_text(
        "\n".join(
            [
                "not-json",
                json.dumps({"kind": "upload_attempt", "key": "alpha"}),
                json.dumps({"kind": "upload_attempt", "key": "beta"}),
                json.dumps({"kind": "upload_attempt", "key": "alpha"}),
            ]
        ),
        encoding="utf-8",
    )

    assert nlm_upload._count_attempts_for_key(log_path, "alpha") == 2
    assert nlm_upload._count_attempts_for_key(log_path, "missing") == 1


def test_upload_cluster_dry_run_skips_cached_sources_and_caps_rate(tmp_path: Path):
    cfg = _cfg(tmp_path)
    cluster = _cluster()
    bundle_dir = _write_bundle(
        cfg.research_hub_dir,
        cluster.slug,
        [
            {"action": "pdf", "pdf_path": "C:/a.pdf"},
            {"action": "url", "url": "https://example.com/paper"},
            {"action": "url", "url": "https://example.com/second"},
        ],
    )
    (cfg.research_hub_dir / "nlm_cache.json").write_text(
        json.dumps({cluster.slug: {"uploaded_sources": ["C:/a.pdf"]}}),
        encoding="utf-8",
    )

    report = nlm_upload.upload_cluster(cluster, cfg, dry_run=True, rate_limit_cap=1)

    assert bundle_dir.exists()
    assert report.notebook_name == "Alpha"
    assert report.skipped_already_uploaded == 1
    assert len(report.uploaded) == 1
    assert report.uploaded[0].path_or_url == "https://example.com/paper"


def test_upload_cluster_raises_when_bundle_missing(tmp_path: Path):
    cfg = _cfg(tmp_path)

    with pytest.raises(FileNotFoundError, match="No bundle found"):
        nlm_upload.upload_cluster(_cluster(), cfg)


def test_upload_cluster_aborts_when_session_is_expired(monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    cluster = _cluster()
    _write_bundle(
        cfg.research_hub_dir,
        cluster.slug,
        [{"action": "url", "url": "https://example.com/paper"}],
    )
    fake_page = MagicMock()
    fake_page.url = "https://accounts.google.com/signin"

    @contextmanager
    def fake_session(_session_dir, headless=False):
        yield None, fake_page

    monkeypatch.setattr(nlm_upload, "open_cdp_session", fake_session)

    with pytest.raises(NotebookLMError, match="expired"):
        nlm_upload.upload_cluster(cluster, cfg, headless=True)

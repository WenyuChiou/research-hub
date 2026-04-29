from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from research_hub.auto import auto_pipeline
from research_hub.clusters import Cluster
from research_hub.notebooklm import client as nlm_client
from research_hub.notebooklm.client import BriefingArtifact, NotebookHandle, NotebookLMClient
from research_hub.notebooklm import upload as nlm_upload


def _cfg(tmp_path: Path) -> SimpleNamespace:
    research_hub_dir = tmp_path / ".research_hub"
    research_hub_dir.mkdir(parents=True)
    root = tmp_path / "root"
    root.mkdir(parents=True)
    raw = tmp_path / "raw"
    raw.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        raw=raw,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def _write_bundle(cfg: SimpleNamespace, cluster_slug: str, entries: list[dict] | None = None) -> None:
    bundle_dir = cfg.research_hub_dir / "bundles" / f"{cluster_slug}-20260428T000000Z"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "manifest.json").write_text(
        json.dumps({"entries": entries or []}),
        encoding="utf-8",
    )


def test_source_count_falls_back_to_uploaded_doi_count_when_dom_returns_zero(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    cluster = Cluster(slug="alpha", name="Alpha", notebooklm_notebook="Alpha Notebook")
    (cfg.research_hub_dir / "nlm_cache.json").write_text(
        json.dumps({"alpha": {"uploaded_doi_count": 3}}),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, page):
            self.page = page

        def open_notebook_by_name(self, name):
            return NotebookHandle(name=name, url="https://notebooklm.google.com/notebook/abc", notebook_id="abc")

        def download_briefing(self, handle):
            return BriefingArtifact(
                notebook_name=handle.name,
                notebook_url=handle.url,
                notebook_id=handle.notebook_id,
                text="Body",
                titles=["Brief A"],
                source_count=0,
            )

    @contextmanager
    def fake_session(_session_dir, headless=False):
        del headless
        yield object(), MagicMock(spec=["url"])

    monkeypatch.setattr(nlm_upload, "_check_session_health", lambda page: (True, "ok"))
    monkeypatch.setattr(nlm_upload, "open_cdp_session", fake_session)
    monkeypatch.setattr(nlm_upload, "NotebookLMClient", FakeClient)

    report = nlm_upload.download_briefing_for_cluster(cluster, cfg, headless=True)

    saved = report.artifact_path.read_text(encoding="utf-8")
    assert "Sources: 3" in saved


def test_source_count_uses_dom_value_when_nonzero(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    cluster = Cluster(slug="alpha", name="Alpha", notebooklm_notebook="Alpha Notebook")
    (cfg.research_hub_dir / "nlm_cache.json").write_text(
        json.dumps({"alpha": {"uploaded_doi_count": 3}}),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, page):
            self.page = page

        def open_notebook_by_name(self, name):
            return NotebookHandle(name=name, url="https://notebooklm.google.com/notebook/abc", notebook_id="abc")

        def download_briefing(self, handle):
            return BriefingArtifact(
                notebook_name=handle.name,
                notebook_url=handle.url,
                notebook_id=handle.notebook_id,
                text="Body",
                titles=["Brief A"],
                source_count=5,
            )

    @contextmanager
    def fake_session(_session_dir, headless=False):
        del headless
        yield object(), MagicMock(spec=["url"])

    monkeypatch.setattr(nlm_upload, "_check_session_health", lambda page: (True, "ok"))
    monkeypatch.setattr(nlm_upload, "open_cdp_session", fake_session)
    monkeypatch.setattr(nlm_upload, "NotebookLMClient", FakeClient)

    report = nlm_upload.download_briefing_for_cluster(cluster, cfg, headless=True)

    saved = report.artifact_path.read_text(encoding="utf-8")
    assert "Sources: 5" in saved


def test_source_count_falls_back_to_titles_length_in_extract(monkeypatch):
    page = MagicMock(spec=["url", "locator", "evaluate"])
    page.url = "https://notebooklm.google.com/notebook/abc"

    summary = MagicMock(spec=["wait_for", "inner_text"])
    summary.inner_text.return_value = "Brief body"
    summary_locator = MagicMock(spec=["first"])
    summary_locator.first = summary

    title_one = MagicMock(spec=["inner_text"])
    title_one.inner_text.return_value = "Brief A"
    title_two = MagicMock(spec=["inner_text"])
    title_two.inner_text.return_value = "Brief B"
    titles_locator = MagicMock(spec=["all"])
    titles_locator.all.return_value = [title_one, title_two]

    def locator(selector):
        if selector == nlm_client.NOTEBOOK_SUMMARY_CONTENT_CSS:
            return summary_locator
        if selector == nlm_client.ARTIFACT_TITLE_SPAN_CSS:
            return titles_locator
        raise AssertionError(selector)

    page.locator.side_effect = locator
    page.evaluate.return_value = 0
    monkeypatch.setattr("research_hub.notebooklm.client.dismiss_overlay", lambda _page: None)

    artifact = NotebookLMClient(page).download_briefing(
        NotebookHandle(name="Alpha Notebook", url=page.url, notebook_id="abc")
    )

    assert artifact.source_count == 2
    assert artifact.titles == ["Brief A", "Brief B"]


def test_upload_report_signals_notebook_reuse_when_url_matches_registry(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    cluster = Cluster(
        slug="alpha",
        name="Alpha",
        notebooklm_notebook_url="https://notebooklm.google.com/notebook/abc",
    )
    _write_bundle(cfg, cluster.slug)

    class FakeClient:
        def __init__(self, page):
            self.page = page

        def open_or_create_notebook(self, _name):
            return NotebookHandle(
                name="Alpha",
                url="https://notebooklm.google.com/notebook/abc",
                notebook_id="abc",
            )

    class FakeRegistry:
        def __init__(self, _path):
            self.bind = MagicMock()

    @contextmanager
    def fake_session(_session_dir, headless=False):
        del headless
        yield object(), MagicMock(spec=["url"])

    monkeypatch.setattr(nlm_upload, "_check_session_health", lambda page: (True, "ok"))
    monkeypatch.setattr(nlm_upload, "open_cdp_session", fake_session)
    monkeypatch.setattr(nlm_upload, "NotebookLMClient", FakeClient)
    monkeypatch.setattr("research_hub.clusters.ClusterRegistry", FakeRegistry)

    report = nlm_upload.upload_cluster(cluster, cfg, headless=True)

    assert report.notebook_was_reused is True


def test_upload_report_signals_fresh_when_url_differs(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    cluster = Cluster(
        slug="alpha",
        name="Alpha",
        notebooklm_notebook_url="https://notebooklm.google.com/notebook/prior",
    )
    _write_bundle(cfg, cluster.slug)

    class FakeClient:
        def __init__(self, page):
            self.page = page

        def open_or_create_notebook(self, _name):
            return NotebookHandle(
                name="Alpha",
                url="https://notebooklm.google.com/notebook/new",
                notebook_id="new",
            )

    class FakeRegistry:
        def __init__(self, _path):
            self.bind = MagicMock()

    @contextmanager
    def fake_session(_session_dir, headless=False):
        del headless
        yield object(), MagicMock(spec=["url"])

    monkeypatch.setattr(nlm_upload, "_check_session_health", lambda page: (True, "ok"))
    monkeypatch.setattr(nlm_upload, "open_cdp_session", fake_session)
    monkeypatch.setattr(nlm_upload, "NotebookLMClient", FakeClient)
    monkeypatch.setattr("research_hub.clusters.ClusterRegistry", FakeRegistry)

    report = nlm_upload.upload_cluster(cluster, cfg, headless=True)

    assert report.notebook_was_reused is False


def test_auto_pipeline_prints_notebook_reuse_hint(monkeypatch, capsys, tmp_path):
    cfg = _cfg(tmp_path)
    cluster = Cluster(slug="alpha", name="Alpha", zotero_collection_key="Z1")
    (cfg.raw / cluster.slug).mkdir(parents=True)
    ((cfg.raw / cluster.slug) / "paper.md").write_text("x", encoding="utf-8")

    registry = MagicMock()
    registry.get.side_effect = [cluster, cluster]

    monkeypatch.setattr("research_hub.auto.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.auto.ClusterRegistry", lambda _path: registry)
    monkeypatch.setattr("research_hub.auto._run_search", lambda *args, **kwargs: [{"title": "Paper"}])
    monkeypatch.setattr("research_hub.auto.run_pipeline", lambda **kwargs: 0)
    monkeypatch.setattr(
        "research_hub.auto.bundle_cluster",
        lambda *args, **kwargs: SimpleNamespace(pdf_count=1),
    )
    monkeypatch.setattr(
        "research_hub.auto.upload_cluster",
        lambda *args, **kwargs: nlm_upload.UploadReport(
            cluster_slug=cluster.slug,
            notebook_url="https://notebooklm.google.com/notebook/abc",
            notebook_was_reused=True,
        ),
    )
    monkeypatch.setattr("research_hub.auto.generate_artifact", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "research_hub.auto.download_briefing_for_cluster",
        lambda *args, **kwargs: SimpleNamespace(
            artifact_path=cfg.research_hub_dir / "artifacts" / cluster.slug / "brief.txt",
            char_count=4,
        ),
    )
    monkeypatch.setattr("research_hub.auto.refresh_graph_from_vault", lambda _cfg: None)
    monkeypatch.setattr("research_hub.auto._run_cluster_overview_step", lambda *args, **kwargs: None)

    report = auto_pipeline(
        "Alpha",
        do_nlm=True,
        do_fit_check=False,
        do_cluster_overview=False,
        print_progress=True,
    )

    out = capsys.readouterr().out
    assert report.ok is True
    assert "[NLM] Reusing existing notebook (same cluster name)." in out
    assert "To start clean, delete it at https://notebooklm.google.com/ first." in out

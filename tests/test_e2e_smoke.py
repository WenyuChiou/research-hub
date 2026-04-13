"""End-to-end smoke test with mocked external services."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace


def _make_cfg(vault: Path) -> SimpleNamespace:
    return SimpleNamespace(
        root=vault,
        raw=vault / "raw",
        research_hub_dir=vault / ".research_hub",
        clusters_file=vault / ".research_hub" / "clusters.yaml",
    )


def _write_cluster(cfg: SimpleNamespace, cluster) -> None:
    from research_hub.clusters import ClusterRegistry

    registry = ClusterRegistry(cfg.clusters_file)
    registry.clusters[cluster.slug] = cluster
    registry.save()


class _StubPage:
    def __init__(self) -> None:
        self.url = "https://notebooklm.google.com/"


def _setup_smoke_env(tmp_path, monkeypatch) -> SimpleNamespace:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "raw").mkdir()
    (vault / ".research_hub").mkdir()
    (vault / ".research_hub" / "clusters.yaml").write_text("clusters: {}\n", encoding="utf-8")
    (vault / ".research_hub" / "dedup_index.json").write_text(
        json.dumps({"doi_to_hits": {}, "title_to_hits": {}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(vault))
    monkeypatch.setenv("ZOTERO_API_KEY", "test-key")
    monkeypatch.setenv("ZOTERO_LIBRARY_ID", "12345")
    monkeypatch.setenv("RESEARCH_HUB_DEFAULT_COLLECTION", "TEST_COLL")
    cfg = _make_cfg(vault)
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.dashboard.get_config", lambda: cfg, raising=False)
    monkeypatch.setattr(
        "research_hub.dashboard.generate_dashboard",
        lambda open_browser=False: _write_dashboard_file(cfg),
        raising=False,
    )
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: "C:/Chrome/chrome.exe",
    )

    class _Response:
        def __init__(self, status_code: int, url: str, payload: dict | None = None) -> None:
            self.status_code = status_code
            self.url = url
            self.reason = "OK" if status_code == 200 else "Not Found"
            self._payload = payload or {}

        def json(self):
            return self._payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)

    def fake_head(url, *args, **kwargs):
        return _Response(200, url)

    def fake_session_head(self, url, *args, **kwargs):
        del self, args, kwargs
        return _Response(200, url)

    def fake_get(url, params=None, timeout=None, **kwargs):
        del params, timeout, kwargs
        return _Response(
            200,
            url,
            {
                "data": [
                    {
                        "title": "Test Paper",
                        "year": 2025,
                        "authors": [{"name": "Wen-Yu Chang"}],
                        "externalIds": {"DOI": "10.1234/test"},
                        "venue": "Test Journal",
                        "citationCount": 0,
                        "url": "https://example.test/paper",
                        "openAccessPdf": {"url": "https://example.test/paper.pdf"},
                    }
                ]
            },
        )

    monkeypatch.setattr("requests.head", fake_head)
    monkeypatch.setattr("requests.sessions.Session.head", fake_session_head)
    monkeypatch.setattr("requests.get", fake_get)
    return cfg


def _write_dashboard_file(cfg: SimpleNamespace) -> Path:
    cfg.research_hub_dir.mkdir(parents=True, exist_ok=True)
    out_path = cfg.research_hub_dir / "dashboard.html"
    out_path.write_text("<html><body>research-hub</body></html>", encoding="utf-8")
    return out_path


def _seed_bundle_and_download_mocks(cfg: SimpleNamespace, monkeypatch):
    from research_hub.clusters import Cluster
    from research_hub.notebooklm.client import BriefingArtifact

    cluster = Cluster(
        slug="test-cluster",
        name="Test Cluster",
        notebooklm_notebook="Test Notebook",
    )
    _write_cluster(cfg, cluster)

    bundle_dir = cfg.research_hub_dir / "bundles" / "test-cluster-20260412T000000Z"
    pdfs_dir = bundle_dir / "pdfs"
    pdfs_dir.mkdir(parents=True)
    dummy_pdf = pdfs_dir / "test-paper.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4\n")
    (bundle_dir / "manifest.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "action": "pdf",
                        "pdf_path": str(dummy_pdf),
                        "doi": "10.1234/test",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (bundle_dir / "sources.txt").write_text("https://example.test/paper\n", encoding="utf-8")

    class FakeClient:
        def __init__(self, page) -> None:
            self.page = page

        def open_notebook_by_name(self, name):
            return SimpleNamespace(
                name=name,
                url="https://notebooklm.google.com/notebook/test",
                notebook_id="test",
            )

        def download_briefing(self, handle):
            return BriefingArtifact(
                notebook_name=handle.name,
                notebook_url=handle.url,
                notebook_id=handle.notebook_id,
                text="End-to-end briefing body.",
                titles=["Test Brief"],
                source_count=1,
            )

    @contextmanager
    def fake_open_cdp_session(session_dir, headless):
        del session_dir, headless
        yield object(), _StubPage()

    monkeypatch.setattr("research_hub.notebooklm.upload.open_cdp_session", fake_open_cdp_session)
    monkeypatch.setattr(
        "research_hub.notebooklm.upload._check_session_health",
        lambda page: (True, "ok"),
    )
    monkeypatch.setattr("research_hub.notebooklm.upload.NotebookLMClient", FakeClient)
    return cluster


def test_full_pipeline_smoke(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "raw").mkdir()
    (vault / ".research_hub").mkdir()
    (vault / ".research_hub" / "clusters.yaml").write_text("clusters: {}\n", encoding="utf-8")
    (vault / ".research_hub" / "dedup_index.json").write_text(
        json.dumps({"doi_to_hits": {}, "title_to_hits": {}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(vault))
    monkeypatch.setenv("ZOTERO_API_KEY", "test-key")
    monkeypatch.setenv("ZOTERO_LIBRARY_ID", "12345")
    monkeypatch.setenv("RESEARCH_HUB_DEFAULT_COLLECTION", "TEST_COLL")
    cfg = SimpleNamespace(
        root=vault,
        raw=vault / "raw",
        research_hub_dir=vault / ".research_hub",
        clusters_file=vault / ".research_hub" / "clusters.yaml",
    )
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.dashboard.get_config", lambda: cfg, raising=False)
    monkeypatch.setattr(
        "research_hub.dashboard.generate_dashboard",
        lambda open_browser=False: _write_dashboard_file(cfg),
        raising=False,
    )
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: "C:/Chrome/chrome.exe",
    )

    class _Response:
        def __init__(self, status_code: int, url: str, payload: dict | None = None) -> None:
            self.status_code = status_code
            self.url = url
            self.reason = "OK" if status_code == 200 else "Not Found"
            self._payload = payload or {}

        def json(self):
            return self._payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)

    def fake_head(url, *args, **kwargs):
        return _Response(200, url)

    def fake_session_head(self, url, *args, **kwargs):
        del self, args, kwargs
        return _Response(200, url)

    def fake_get(url, params=None, timeout=None, **kwargs):
        del params, timeout, kwargs
        return _Response(
            200,
            url,
            {
                "data": [
                    {
                        "title": "Test Paper",
                        "year": 2025,
                        "authors": [{"name": "Wen-Yu Chang"}],
                        "externalIds": {"DOI": "10.1234/test"},
                        "venue": "Test Journal",
                        "citationCount": 0,
                        "url": "https://example.test/paper",
                        "openAccessPdf": {"url": "https://example.test/paper.pdf"},
                    }
                ]
            },
        )

    monkeypatch.setattr("requests.head", fake_head)
    monkeypatch.setattr("requests.sessions.Session.head", fake_session_head)
    monkeypatch.setattr("requests.get", fake_get)

    from research_hub.dashboard import generate_dashboard
    from research_hub.doctor import run_doctor
    from research_hub.mcp_server import search_papers

    search_results = search_papers("test paper", limit=1, verify=True)
    assert isinstance(search_results, list)
    assert search_results[0]["verified"] is True

    doctor_results = run_doctor()
    assert any(result.name == "vault" for result in doctor_results)
    assert any(result.name == "vault_invariant" for result in doctor_results)
    assert any(result.name == "dedup_consistency" for result in doctor_results)
    assert any(result.name == "config" for result in doctor_results)

    dash_path = generate_dashboard(open_browser=False)
    assert dash_path.exists()
    html = dash_path.read_text(encoding="utf-8")
    assert "research-hub" in html


def test_dedup_normalize_doi_backwards_compat():
    from research_hub.dedup import normalize_doi

    assert normalize_doi("DOI:10.5000/ABC") == "10.5000/abc"


def test_pipeline_extract_arxiv_id_uses_shared_helper():
    from research_hub.pipeline import _extract_arxiv_id_from_url_or_doi

    assert (
        _extract_arxiv_id_from_url_or_doi(
            "https://arxiv.org/abs/2502.10978",
            "10.48550/arxiv.2502.10978",
        )
        == "2502.10978"
    )


def test_full_pipeline_smoke_with_download(tmp_path, monkeypatch):
    from research_hub.doctor import run_doctor
    from research_hub.mcp_server import search_papers
    from research_hub.notebooklm.upload import download_briefing_for_cluster, read_latest_briefing

    cfg = _setup_smoke_env(tmp_path, monkeypatch)
    from research_hub.dashboard import generate_dashboard

    search_results = search_papers("test paper", limit=1, verify=True)
    assert isinstance(search_results, list)
    assert search_results[0]["verified"] is True

    doctor_results = run_doctor()
    assert any(result.name == "vault" for result in doctor_results)
    assert any(result.name == "vault_invariant" for result in doctor_results)
    assert any(result.name == "dedup_consistency" for result in doctor_results)
    assert any(result.name == "config" for result in doctor_results)

    dash_path = generate_dashboard(open_browser=False)
    assert dash_path.exists()

    cluster = _seed_bundle_and_download_mocks(cfg, monkeypatch)
    report = download_briefing_for_cluster(cluster, cfg, headless=True)
    assert report.artifact_path.exists()
    assert "End-to-end briefing body." in report.artifact_path.read_text(encoding="utf-8")

    cache = json.loads((cfg.research_hub_dir / "nlm_cache.json").read_text(encoding="utf-8"))
    assert cache["test-cluster"]["artifacts"]["brief"]["path"] == str(report.artifact_path)

    latest = read_latest_briefing(cluster, cfg)
    assert "End-to-end briefing body." in latest


def test_e2e_mcp_download_artifacts_tool(tmp_path, monkeypatch):
    cfg = _setup_smoke_env(tmp_path, monkeypatch)
    _seed_bundle_and_download_mocks(cfg, monkeypatch)

    from research_hub.mcp_server import mcp
    from tests._mcp_helpers import _get_mcp_tool

    result = _get_mcp_tool(mcp, "download_artifacts").fn(
        cluster_slug="test-cluster",
        artifact_type="brief",
        headless=True,
    )
    assert result["status"] == "ok"
    assert Path(result["path"]).exists()

    briefing = _get_mcp_tool(mcp, "read_briefing").fn(cluster_slug="test-cluster")
    assert briefing["status"] == "ok"
    assert "End-to-end briefing body." in briefing["text"]

    truncated = _get_mcp_tool(mcp, "read_briefing").fn(cluster_slug="test-cluster", max_chars=10)
    assert truncated["status"] == "ok"
    assert truncated["truncated"] is True
    assert truncated["full_chars"] > 10


def test_e2e_read_briefing_missing_returns_remedy(tmp_path, monkeypatch):
    cfg = _setup_smoke_env(tmp_path, monkeypatch)

    from research_hub.clusters import Cluster
    from research_hub.mcp_server import mcp
    from tests._mcp_helpers import _get_mcp_tool

    cluster = Cluster(
        slug="test-cluster",
        name="Test Cluster",
        notebooklm_notebook="Test Notebook",
    )
    _write_cluster(cfg, cluster)

    result = _get_mcp_tool(mcp, "read_briefing").fn(cluster_slug="test-cluster")
    assert result["status"] == "error"
    assert "download_artifacts" in result["remedy"]

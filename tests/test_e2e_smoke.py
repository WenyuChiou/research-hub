"""End-to-end smoke test with mocked external services."""

from __future__ import annotations

import json
from types import SimpleNamespace


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
    monkeypatch.setattr("research_hub.dashboard.get_config", lambda: cfg)
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

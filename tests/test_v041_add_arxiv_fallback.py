from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def stub_config(tmp_path, monkeypatch):
    cfg = SimpleNamespace(root=tmp_path / "vault", raw=tmp_path / "vault" / "raw")
    cfg.raw.mkdir(parents=True)
    monkeypatch.setattr("research_hub.operations.get_config", lambda: cfg)
    return cfg


def _paper(**overrides):
    payload = {
        "title": "Fallback Paper",
        "doi": "10.1000/example",
        "arxiv_id": "",
        "abstract": "Abstract body",
        "year": 2026,
        "authors": ["Jane Doe"],
        "venue": "Venue",
        "url": "https://example.org/paper",
        "pdf_url": "https://example.org/paper.pdf",
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_add_arxiv_fallback_prefers_s2_metadata(stub_config, monkeypatch):
    from research_hub.operations import add_paper

    seen = {"arxiv_called": False}

    class FakeS2:
        def get_paper(self, identifier):
            seen["s2_identifier"] = identifier
            return _paper(doi="10.48550/arxiv.2604.08224", arxiv_id="2604.08224")

    class FakeArxiv:
        def get_paper(self, identifier):
            seen["arxiv_called"] = True
            return _paper(doi="", arxiv_id=identifier)

    monkeypatch.setattr("research_hub.search.SemanticScholarClient", FakeS2)
    monkeypatch.setattr("research_hub.search.ArxivBackend", FakeArxiv)
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: SimpleNamespace(status_code=404))
    monkeypatch.setattr("research_hub.pipeline.run_pipeline", lambda **kwargs: 0)

    result = add_paper("10.48550/arxiv.2604.08224", cluster="agents")

    assert result["status"] == "ok"
    assert seen["s2_identifier"] == "ArXiv:2604.08224"
    assert seen["arxiv_called"] is False


def test_add_arxiv_fallback_uses_arxiv_on_s2_rate_limit(stub_config, monkeypatch):
    from research_hub.operations import add_paper
    from research_hub.search.semantic_scholar import RateLimitError

    captured = {}

    class FakeS2:
        def get_paper(self, identifier):
            raise RateLimitError("429")

    class FakeArxiv:
        def get_paper(self, identifier):
            captured["arxiv_identifier"] = identifier
            return _paper(doi="", arxiv_id=identifier, title="arXiv Fallback Title")

    def fake_pipeline(**kwargs):
        captured["payload"] = json.loads(
            (stub_config.root / "papers_input.json").read_text(encoding="utf-8")
        )
        return 0

    monkeypatch.setattr("research_hub.search.SemanticScholarClient", FakeS2)
    monkeypatch.setattr("research_hub.search.ArxivBackend", FakeArxiv)
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: SimpleNamespace(status_code=404))
    monkeypatch.setattr("research_hub.pipeline.run_pipeline", fake_pipeline)

    result = add_paper("2604.08224")

    assert result["status"] == "ok"
    assert captured["arxiv_identifier"] == "2604.08224"
    assert captured["payload"][0]["title"] == "arXiv Fallback Title"
    assert captured["payload"][0]["doi"] == "10.48550/arxiv.2604.08224"


def test_add_arxiv_fallback_reports_both_backends(stub_config, monkeypatch):
    from research_hub.operations import add_paper

    class FakeS2:
        def get_paper(self, identifier):
            return None

    class FakeArxiv:
        def get_paper(self, identifier):
            return None

    monkeypatch.setattr("research_hub.search.SemanticScholarClient", FakeS2)
    monkeypatch.setattr("research_hub.search.ArxivBackend", FakeArxiv)

    result = add_paper("2604.08224")

    assert result["status"] == "error"
    assert "Semantic Scholar" in result["reason"]
    assert "arXiv" in result["reason"]

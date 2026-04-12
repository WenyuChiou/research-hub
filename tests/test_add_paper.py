"""Tests for one-shot add_paper ingestion."""

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
        "title": "A Useful Paper",
        "doi": "10.1000/example",
        "abstract": "Abstract body",
        "year": 2024,
        "authors": ["Jane Doe", "John Smith"],
        "venue": "Venue",
        "url": "https://example.org/paper",
        "pdf_url": "https://example.org/paper.pdf",
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_add_paper_happy_path(stub_config, monkeypatch):
    from research_hub.operations import add_paper

    seen = {}

    class FakeS2:
        def get_paper(self, identifier):
            seen["s2"] = identifier
            return _paper()

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "message": {
                    "author": [{"given": "Jane", "family": "Doe"}],
                    "container-title": ["Journal Title"],
                    "volume": "12",
                    "issue": "3",
                    "page": "10-20",
                }
            }

    def fake_pipeline(**kwargs):
        seen["pipeline"] = kwargs
        seen["payload"] = json.loads(
            (stub_config.root / "papers_input.json").read_text(encoding="utf-8")
        )
        return 0

    monkeypatch.setattr("research_hub.search.SemanticScholarClient", FakeS2)
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr("research_hub.pipeline.run_pipeline", fake_pipeline)

    result = add_paper("10.1000/example", cluster="topic")

    assert result["status"] == "ok"
    assert seen["s2"] == "10.1000/example"
    assert seen["pipeline"] == {"cluster_slug": "topic", "verify": True}
    entry = seen["payload"][0]
    assert entry["authors"] == [{"creatorType": "author", "firstName": "Jane", "lastName": "Doe"}]
    assert entry["volume"] == "12"
    assert not (stub_config.root / "papers_input.json").exists()


def test_add_paper_doi_not_found(stub_config, monkeypatch):
    from research_hub.operations import add_paper

    class FakeS2:
        def get_paper(self, identifier):
            return None

    monkeypatch.setattr("research_hub.search.SemanticScholarClient", FakeS2)

    result = add_paper("10.1000/missing")

    assert result["status"] == "error"
    assert "Could not resolve" in result["reason"]


def test_add_paper_crossref_failure_falls_back_to_s2(stub_config, monkeypatch):
    from research_hub.operations import add_paper

    captured = {}

    class FakeS2:
        def get_paper(self, identifier):
            return _paper(authors=["Jane Doe"])

    def fake_pipeline(**kwargs):
        captured["payload"] = json.loads(
            (stub_config.root / "papers_input.json").read_text(encoding="utf-8")
        )
        return 0

    monkeypatch.setattr("research_hub.search.SemanticScholarClient", FakeS2)
    monkeypatch.setattr(
        "requests.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr("research_hub.pipeline.run_pipeline", fake_pipeline)

    result = add_paper("10.1000/example")

    assert result["status"] == "ok"
    assert captured["payload"][0]["authors"] == [
        {"creatorType": "author", "firstName": "Jane", "lastName": "Doe"}
    ]


def test_add_paper_arxiv_id_resolves(stub_config, monkeypatch):
    from research_hub.operations import add_paper

    seen = {}

    class FakeS2:
        def get_paper(self, identifier):
            seen["identifier"] = identifier
            return _paper(doi="")

    monkeypatch.setattr("research_hub.search.SemanticScholarClient", FakeS2)
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: SimpleNamespace(status_code=404))
    monkeypatch.setattr("research_hub.pipeline.run_pipeline", lambda **kwargs: 0)

    add_paper("2502.10978")

    assert seen["identifier"] == "ArXiv:2502.10978"


def test_add_paper_no_zotero_sets_env_var(stub_config, monkeypatch):
    from research_hub.operations import add_paper

    seen = {}

    class FakeS2:
        def get_paper(self, identifier):
            return _paper()

    def fake_pipeline(**kwargs):
        import os

        seen["env"] = os.environ.get("RESEARCH_HUB_NO_ZOTERO")
        return 0

    monkeypatch.setattr("research_hub.search.SemanticScholarClient", FakeS2)
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: SimpleNamespace(status_code=404))
    monkeypatch.setattr("research_hub.pipeline.run_pipeline", fake_pipeline)

    add_paper("10.1000/example", no_zotero=True)

    assert seen["env"] == "1"


def test_add_paper_backup_restore(stub_config, monkeypatch):
    from research_hub.operations import add_paper

    papers_path = stub_config.root / "papers_input.json"
    papers_path.write_text('[{"title":"old"}]', encoding="utf-8")

    class FakeS2:
        def get_paper(self, identifier):
            return _paper()

    monkeypatch.setattr("research_hub.search.SemanticScholarClient", FakeS2)
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: SimpleNamespace(status_code=404))
    monkeypatch.setattr("research_hub.pipeline.run_pipeline", lambda **kwargs: 0)

    add_paper("10.1000/example")

    assert papers_path.read_text(encoding="utf-8") == '[{"title":"old"}]'

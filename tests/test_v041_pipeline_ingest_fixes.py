from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.pipeline import run_pipeline


def _cfg(tmp_path: Path, *, default_collection: str | None = None) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    logs = root / "logs"
    hub = root / ".research_hub"
    raw.mkdir(parents=True)
    logs.mkdir(parents=True)
    hub.mkdir(parents=True)
    cfg = SimpleNamespace(
        root=root,
        raw=raw,
        logs=logs,
        research_hub_dir=hub,
        clusters_file=hub / "clusters.yaml",
        zotero_default_collection=default_collection,
        zotero_collections={},
        zotero_library_id="123",
    )
    return cfg


def _minimal_paper() -> list[dict]:
    return [
        {
            "title": "Paper One",
            "doi": "10.1000/example",
            "authors": [{"creatorType": "author", "lastName": "Doe", "firstName": "Jane"}],
            "year": 2026,
            "abstract": "Abstract",
            "journal": "Journal",
            "summary": "Summary",
            "key_findings": ["Finding"],
            "methodology": "Method",
            "relevance": "Relevant",
            "slug": "doe2026-paper-one",
            "sub_category": "agents",
        }
    ]


def test_run_pipeline_accepts_top_level_array(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, default_collection="DEFAULT")
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    (cfg.root / "papers_input.json").write_text(json.dumps(_minimal_paper()), encoding="utf-8")
    monkeypatch.setattr("research_hub.pipeline.get_config", lambda: cfg)

    rc = run_pipeline(dry_run=True, cluster_slug="agents", verify=False)

    assert rc == 0


def test_run_pipeline_accepts_wrapped_papers_object(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, default_collection="DEFAULT")
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    payload = {"papers": _minimal_paper()}
    (cfg.root / "papers_input.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr("research_hub.pipeline.get_config", lambda: cfg)

    rc = run_pipeline(dry_run=True, cluster_slug="agents", verify=False)

    assert rc == 0


def test_run_pipeline_rejects_invalid_papers_shape(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, default_collection="DEFAULT")
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    (cfg.root / "papers_input.json").write_text(json.dumps({"wrong": []}), encoding="utf-8")
    monkeypatch.setattr("research_hub.pipeline.get_config", lambda: cfg)

    with pytest.raises(ValueError, match='top-level JSON array or an object like \\{"papers": \\[\\.\\.\\.\\]\\}'):
        run_pipeline(dry_run=True, cluster_slug="agents", verify=False)


def test_run_pipeline_uses_cluster_collection_without_env_default(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, default_collection=None)
    ClusterRegistry(cfg.clusters_file).create(
        query="agents",
        name="Agents",
        slug="agents",
        zotero_collection_key="WNV9SWVA",
    )
    (cfg.root / "papers_input.json").write_text(json.dumps(_minimal_paper()), encoding="utf-8")
    monkeypatch.setattr("research_hub.pipeline.get_config", lambda: cfg)
    monkeypatch.setattr(
        "research_hub.pipeline._load_or_build_dedup",
        lambda *args, **kwargs: SimpleNamespace(
            doi_to_hits={},
            title_to_hits={},
            check=lambda payload: (False, []),
            add=lambda hit: None,
            save=lambda path: None,
        ),
    )
    monkeypatch.setattr("research_hub.pipeline.check_duplicate", lambda *args, **kwargs: False)
    monkeypatch.setattr("research_hub.pipeline.add_note", lambda *args, **kwargs: True)
    monkeypatch.setattr("research_hub.pipeline.time.sleep", lambda seconds: None)
    monkeypatch.setattr("research_hub.pipeline.update_cluster_links", lambda *args, **kwargs: None)

    captured = {}

    class FakeZotero:
        def item_template(self, kind):
            return {}

        def create_items(self, items):
            captured["collections"] = items[0]["collections"]
            return {"successful": {"0": {"key": "KEY1"}}}

    monkeypatch.setattr("research_hub.pipeline.get_client", lambda: FakeZotero())

    assert run_pipeline(dry_run=False, cluster_slug="agents", verify=False) == 0
    assert captured["collections"] == ["WNV9SWVA"]


def test_run_pipeline_uses_env_default_when_cluster_missing_key(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, default_collection="ENVKEY")
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    (cfg.root / "papers_input.json").write_text(json.dumps(_minimal_paper()), encoding="utf-8")
    monkeypatch.setattr("research_hub.pipeline.get_config", lambda: cfg)
    monkeypatch.setattr(
        "research_hub.pipeline._load_or_build_dedup",
        lambda *args, **kwargs: SimpleNamespace(
            doi_to_hits={},
            title_to_hits={},
            check=lambda payload: (False, []),
            add=lambda hit: None,
            save=lambda path: None,
        ),
    )
    monkeypatch.setattr("research_hub.pipeline.check_duplicate", lambda *args, **kwargs: False)
    monkeypatch.setattr("research_hub.pipeline.add_note", lambda *args, **kwargs: True)
    monkeypatch.setattr("research_hub.pipeline.time.sleep", lambda seconds: None)
    monkeypatch.setattr("research_hub.pipeline.update_cluster_links", lambda *args, **kwargs: None)

    captured = {}

    class FakeZotero:
        def item_template(self, kind):
            return {}

        def create_items(self, items):
            captured["collections"] = items[0]["collections"]
            return {"successful": {"0": {"key": "KEY1"}}}

    monkeypatch.setattr("research_hub.pipeline.get_client", lambda: FakeZotero())

    assert run_pipeline(dry_run=False, cluster_slug="agents", verify=False) == 0
    assert captured["collections"] == ["ENVKEY"]


def test_run_pipeline_errors_when_no_collection_available(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, default_collection=None)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    (cfg.root / "papers_input.json").write_text(json.dumps(_minimal_paper()), encoding="utf-8")
    monkeypatch.setattr("research_hub.pipeline.get_config", lambda: cfg)

    with pytest.raises(RuntimeError, match="cluster.zotero_collection_key.*RESEARCH_HUB_DEFAULT_COLLECTION"):
        run_pipeline(dry_run=False, cluster_slug="agents", verify=False)

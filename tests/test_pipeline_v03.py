"""v0.3.0 pipeline integration tests."""

from __future__ import annotations

import json

from tests.test_pipeline import _configure, _paper


def _create_cluster(cfg, slug: str) -> None:
    cfg.clusters_file.write_text(
        "clusters:\n"
        f"  {slug}:\n"
        f"    name: {slug}\n"
        "    seed_keywords:\n"
        "      - llm\n"
        "      - agents\n"
        f"    obsidian_subfolder: {slug}\n",
        encoding="utf-8",
    )


def test_run_pipeline_no_cluster_behaves_like_v02(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper One", "paper-one", "10.1000/one")]),
        encoding="utf-8",
    )

    class StubClient:
        def item_template(self, item_type: str):
            return {"itemType": item_type}

        def create_items(self, items):
            return {"successful": {"0": {"key": "KEY1"}}}

    monkeypatch.setattr(pipeline, "get_client", lambda: StubClient())
    monkeypatch.setattr(pipeline, "check_duplicate", lambda zot, title, doi="": False)
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    result = pipeline.run_pipeline()

    note = cfg.raw / "survey" / "paper-one.md"
    assert result == 0
    assert note.exists()
    assert 'topic_cluster: ""' in note.read_text(encoding="utf-8")


def test_run_pipeline_with_cluster_writes_manifest(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    _create_cluster(cfg, "cluster-a")
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper One", "paper-one", "10.1000/one")]),
        encoding="utf-8",
    )

    result = pipeline.run_pipeline(dry_run=True, cluster_slug="cluster-a")

    manifest_path = cfg.research_hub_dir / "manifest.jsonl"
    assert result == 0
    assert manifest_path.exists()
    assert '"cluster": "cluster-a"' in manifest_path.read_text(encoding="utf-8")


def test_run_pipeline_dedup_hit_updates_cluster_queries(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    _create_cluster(cfg, "cluster-a")
    existing_dir = cfg.raw / "cluster-a"
    existing_dir.mkdir(parents=True, exist_ok=True)
    existing_note = existing_dir / "paper-one.md"
    existing_note.write_text(
        '---\n'
        'title: "Paper One"\n'
        'doi: "10.1000/one"\n'
        'zotero-key: "KEY1"\n'
        'cluster_queries: ["old query"]\n'
        'topic_cluster: "cluster-a"\n'
        'tags: ["flood risk"]\n'
        '---\n',
        encoding="utf-8",
    )
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper One", "paper-one", "10.1000/one")]),
        encoding="utf-8",
    )

    class StubClient:
        def item_template(self, item_type: str):
            return {"itemType": item_type}

        def create_items(self, items):
            raise AssertionError("Duplicate paper should not be created")

    monkeypatch.setattr(pipeline, "get_client", lambda: StubClient())
    monkeypatch.setattr(pipeline, "check_duplicate", lambda zot, title, doi="": False)
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    result = pipeline.run_pipeline(cluster_slug="cluster-a")

    assert result == 0
    assert '"Paper One"' in existing_note.read_text(encoding="utf-8")


def test_run_pipeline_creates_cluster_subfolder_in_raw(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    _create_cluster(cfg, "cluster-a")
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper One", "paper-one", "10.1000/one")]),
        encoding="utf-8",
    )

    class StubClient:
        def item_template(self, item_type: str):
            return {"itemType": item_type}

        def create_items(self, items):
            return {"successful": {"0": {"key": "KEY1"}}}

    monkeypatch.setattr(pipeline, "get_client", lambda: StubClient())
    monkeypatch.setattr(pipeline, "check_duplicate", lambda zot, title, doi="": False)
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    result = pipeline.run_pipeline(cluster_slug="cluster-a")

    assert result == 0
    assert (cfg.raw / "cluster-a" / "paper-one.md").exists()

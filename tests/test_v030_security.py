from __future__ import annotations

import json

from tests.test_pipeline import _configure, _paper


def _create_cluster(cfg, slug: str, zotero_collection_key: str | None = None) -> None:
    lines = [
        "clusters:",
        f"  {slug}:",
        f"    name: {slug}",
        "    seed_keywords:",
        "      - llm",
        "      - agents",
        f"    obsidian_subfolder: {slug}",
    ]
    if zotero_collection_key:
        lines.append(f"    zotero_collection_key: {zotero_collection_key}")
    cfg.clusters_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_pipeline_routes_to_cluster_collection_when_bound(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    _create_cluster(cfg, "cluster-a", "CLUSTER999")
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper One", "paper-one", "10.1000/one")]),
        encoding="utf-8",
    )

    seen: dict[str, object] = {}

    class StubClient:
        def item_template(self, item_type: str):
            return {"itemType": item_type}

        def create_items(self, items):
            seen["collections"] = items[0]["collections"]
            return {"successful": {"0": {"key": "KEY1"}}}

    monkeypatch.setattr(pipeline, "get_client", lambda: StubClient())
    monkeypatch.setattr(
        pipeline,
        "check_duplicate",
        lambda zot, title, doi="", collection_key=None, **kwargs: (
            seen.setdefault("duplicate_collection", collection_key) and False
        ),
    )
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    result = pipeline.run_pipeline(cluster_slug="cluster-a")

    assert result == 0
    assert seen["duplicate_collection"] == "CLUSTER999"
    assert seen["collections"] == ["CLUSTER999"]
    log_text = (cfg.logs / "pipeline_log.txt").read_text(encoding="utf-8")
    assert "Routing to collection: CLUSTER999 (cluster=cluster-a)" in log_text


def test_pipeline_falls_back_to_default_when_cluster_unbound(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    _create_cluster(cfg, "cluster-a")
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper One", "paper-one", "10.1000/one")]),
        encoding="utf-8",
    )

    seen: dict[str, object] = {}

    class StubClient:
        def item_template(self, item_type: str):
            return {"itemType": item_type}

        def create_items(self, items):
            seen["collections"] = items[0]["collections"]
            return {"successful": {"0": {"key": "KEY1"}}}

    monkeypatch.setattr(pipeline, "get_client", lambda: StubClient())
    monkeypatch.setattr(
        pipeline,
        "check_duplicate",
        lambda zot, title, doi="", collection_key=None, **kwargs: (
            seen.setdefault("duplicate_collection", collection_key) and False
        ),
    )
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    result = pipeline.run_pipeline(cluster_slug="cluster-a")

    assert result == 0
    assert seen["duplicate_collection"] is None
    assert seen["collections"] == ["ABCD1234"]
    log_text = (cfg.logs / "pipeline_log.txt").read_text(encoding="utf-8")
    assert "Routing to collection: ABCD1234 (cluster=cluster-a)" in log_text


def test_pipeline_falls_back_to_default_when_no_cluster_slug(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper One", "paper-one", "10.1000/one")]),
        encoding="utf-8",
    )

    seen: dict[str, object] = {}

    class StubClient:
        def item_template(self, item_type: str):
            return {"itemType": item_type}

        def create_items(self, items):
            seen["collections"] = items[0]["collections"]
            return {"successful": {"0": {"key": "KEY1"}}}

    monkeypatch.setattr(pipeline, "get_client", lambda: StubClient())
    monkeypatch.setattr(
        pipeline,
        "check_duplicate",
        lambda zot, title, doi="", collection_key=None, **kwargs: (
            seen.setdefault("duplicate_collection", collection_key) and False
        ),
    )
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    result = pipeline.run_pipeline()

    assert result == 0
    assert seen["duplicate_collection"] is None
    assert seen["collections"] == ["ABCD1234"]
    log_text = (cfg.logs / "pipeline_log.txt").read_text(encoding="utf-8")
    assert "Routing to collection: ABCD1234 (cluster=none)" in log_text

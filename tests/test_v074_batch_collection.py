from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from unittest.mock import MagicMock

from research_hub.clusters import ClusterRegistry
from research_hub.manifest import Manifest
from tests.test_pipeline import _configure, _paper


def _prepare_cfg(monkeypatch, tmp_path, *, cluster_query: str = "agents"):
    from research_hub import config as hub_config
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query=cluster_query, name="Agents", slug="agents")
    registry.bind("agents", zotero_collection_key="CLUSTER123")
    monkeypatch.setattr(pipeline, "check_duplicate", lambda zot, title, doi="", **kwargs: False)
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(pipeline, "update_cluster_links", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, "_refresh_cluster_base", lambda *args, **kwargs: None)
    return cfg, pipeline, hub_config


def _write_papers(cfg, *papers):
    (cfg.root / "papers_input.json").write_text(json.dumps(list(papers)), encoding="utf-8")


def _make_zotero(existing_subcollections=None):
    zot = MagicMock()
    zot.web = MagicMock()
    zot.web.collections_sub.return_value = list(existing_subcollections or [])
    # _list_subcollections in pipeline.py iterates zot.collections() filtered
    # by parentCollection; mirror that so existing subcollections get found.
    zot.collections.return_value = list(existing_subcollections or [])
    zot.item_template.side_effect = lambda item_type: {"itemType": item_type}

    def _create_items(items):
        return {
            "successful": {
                str(idx): {"key": f"Z{idx}"}
                for idx, _item in enumerate(items)
            }
        }

    zot.create_items.side_effect = _create_items
    # pyzotero.Zotero exposes create_collections(payload_list); the pipeline
    # probes for it first via hasattr.
    zot.create_collections.return_value = {"successful": {"0": {"key": "BATCH123"}}}
    return zot


def test_pipeline_creates_subcollection_per_batch_label(tmp_path, monkeypatch):
    cfg, pipeline, hub_config = _prepare_cfg(monkeypatch, tmp_path)
    _write_papers(cfg, _paper("Paper One", "paper-one", "10.1000/one"))
    zot = _make_zotero()
    monkeypatch.setattr(pipeline, "get_client", lambda: zot)

    try:
        assert pipeline.run_pipeline(
            dry_run=False,
            cluster_slug="agents",
            query="society",
            verify=False,
            batch_label="2026-05-02-society",
        ) == 0
        zot.create_collections.assert_called_once_with(
            [{"name": "2026-05-02-society", "parentCollection": "CLUSTER123"}]
        )
        template = zot.create_items.call_args_list[0].args[0][0]
        assert template["collections"] == ["CLUSTER123", "BATCH123"]
    finally:
        hub_config._config = None
        hub_config._config_path = None


def test_pipeline_reuses_existing_subcollection(tmp_path, monkeypatch):
    cfg, pipeline, hub_config = _prepare_cfg(monkeypatch, tmp_path)
    _write_papers(cfg, _paper("Paper One", "paper-one", "10.1000/one"))
    existing = [{"key": "BATCH123", "data": {"name": "2026-05-02-society", "parentCollection": "CLUSTER123"}}]
    zot = _make_zotero(existing_subcollections=existing)
    monkeypatch.setattr(pipeline, "get_client", lambda: zot)

    try:
        assert pipeline.run_pipeline(
            dry_run=False,
            cluster_slug="agents",
            query="society",
            verify=False,
            batch_label="2026-05-02-society",
        ) == 0
        zot.create_collections.assert_not_called()
        template = zot.create_items.call_args_list[0].args[0][0]
        assert template["collections"] == ["CLUSTER123", "BATCH123"]
    finally:
        hub_config._config = None
        hub_config._config_path = None


def test_pipeline_batch_tag_appended(tmp_path, monkeypatch):
    cfg, pipeline, hub_config = _prepare_cfg(monkeypatch, tmp_path)
    _write_papers(cfg, _paper("Paper One", "paper-one", "10.1000/one"))
    zot = _make_zotero()
    monkeypatch.setattr(pipeline, "get_client", lambda: zot)

    try:
        assert pipeline.run_pipeline(
            dry_run=False,
            cluster_slug="agents",
            query="society",
            verify=False,
            batch_label="2026-05-02-society",
        ) == 0
        template = zot.create_items.call_args_list[0].args[0][0]
        tags = {tag["tag"] for tag in template["tags"]}
        assert "batch:2026-05-02-society" in tags
    finally:
        hub_config._config = None
        hub_config._config_path = None


def test_pipeline_skips_subcollection_when_no_zotero(tmp_path, monkeypatch):
    cfg, pipeline, hub_config = _prepare_cfg(monkeypatch, tmp_path)
    _write_papers(cfg, _paper("Paper One", "paper-one", "10.1000/one"))
    monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")
    monkeypatch.setattr(pipeline, "get_client", lambda: (_ for _ in ()).throw(AssertionError("no client")))

    try:
        assert pipeline.run_pipeline(
            dry_run=False,
            cluster_slug="agents",
            query="society",
            verify=False,
            batch_label="manual-batch",
        ) == 0
        entries = Manifest(cfg.research_hub_dir / "manifest.jsonl").read_all()
        assert entries[-1].batch_label == "manual-batch"
    finally:
        hub_config._config = None
        hub_config._config_path = None


def test_pipeline_default_batch_label_from_query(tmp_path, monkeypatch):
    cfg, pipeline, hub_config = _prepare_cfg(monkeypatch, tmp_path)
    _write_papers(cfg, _paper("Paper One", "paper-one", "10.1000/one"))
    zot = _make_zotero()
    monkeypatch.setattr(pipeline, "get_client", lambda: zot)

    try:
        assert pipeline.run_pipeline(
            dry_run=False,
            cluster_slug="agents",
            query="post-flood",
            verify=False,
        ) == 0
        payload = zot.create_collections.call_args.args[0][0]
        assert re.match(r"^\d{8}-post-flood", payload["name"])
    finally:
        hub_config._config = None
        hub_config._config_path = None


def test_pipeline_default_batch_label_manual(tmp_path, monkeypatch):
    cfg, pipeline, hub_config = _prepare_cfg(monkeypatch, tmp_path, cluster_query="")
    _write_papers(cfg, _paper("Paper One", "paper-one", "10.1000/one"))
    zot = _make_zotero()
    monkeypatch.setattr(pipeline, "get_client", lambda: zot)

    try:
        assert pipeline.run_pipeline(
            dry_run=False,
            cluster_slug="agents",
            query=None,
            verify=False,
        ) == 0
        payload = zot.create_collections.call_args.args[0][0]
        assert re.match(r"^manual-\d{8}-\d{6}$", payload["name"])
    finally:
        hub_config._config = None
        hub_config._config_path = None


def test_same_day_same_query_appends_suffix(tmp_path, monkeypatch):
    cfg, pipeline, hub_config = _prepare_cfg(monkeypatch, tmp_path)
    _write_papers(cfg, _paper("Paper One", "paper-one", "10.1000/one"))
    fixed_now = datetime(2026, 5, 2, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(pipeline, "_utc_now", lambda: fixed_now)
    existing: list[tuple[str, str]] = []
    zot = MagicMock()
    zot.web = MagicMock()
    zot.item_template.side_effect = lambda item_type: {"itemType": item_type}
    zot.create_items.side_effect = lambda items: {"successful": {"0": {"key": "Z0"}}}

    def _existing_payload(_parent=None):
        return [
            {"key": key, "data": {"name": name, "parentCollection": "CLUSTER123"}}
            for key, name in existing
        ]

    def _create_collections(payload_list):
        name = payload_list[0]["name"]
        key = f"B{len(existing) + 1}"
        existing.append((key, name))
        return {"successful": {"0": {"key": key}}}

    zot.web.collections_sub.side_effect = _existing_payload
    zot.collections.side_effect = _existing_payload
    zot.create_collections.side_effect = _create_collections
    monkeypatch.setattr(pipeline, "get_client", lambda: zot)

    try:
        assert pipeline.run_pipeline(dry_run=False, cluster_slug="agents", query="same query", verify=False) == 0
        assert pipeline.run_pipeline(dry_run=False, cluster_slug="agents", query="same query", verify=False) == 0
        labels = [call.args[0][0]["name"] for call in zot.create_collections.call_args_list]
        assert labels == ["20260502-same-query", "20260502-same-query-2"]
    finally:
        hub_config._config = None
        hub_config._config_path = None

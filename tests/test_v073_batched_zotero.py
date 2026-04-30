from __future__ import annotations

import json

from research_hub.clusters import ClusterRegistry
from tests.test_pipeline import _configure, _paper


def _prepare_cfg(monkeypatch, tmp_path):
    from research_hub import config as hub_config
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    monkeypatch.setattr(pipeline, "check_duplicate", lambda zot, title, doi="", **kwargs: False)
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)
    return cfg, pipeline, hub_config


def _write_papers(cfg, count: int = 30) -> None:
    papers = [_paper(f"Paper {i}", f"paper-{i:02d}", f"10.1000/{i:02d}") for i in range(count)]
    (cfg.root / "papers_input.json").write_text(json.dumps(papers), encoding="utf-8")


class _FakeZotero:
    def __init__(self, *, fail_first_batch: bool = False):
        self.fail_first_batch = fail_first_batch
        self.create_calls: list[list[dict]] = []

    def item_template(self, item_type: str):
        return {"itemType": item_type}

    def create_items(self, items: list[dict]):
        self.create_calls.append(items)
        if self.fail_first_batch and len(self.create_calls) == 1:
            raise RuntimeError("batch failed")
        return {
            "successful": {
                str(idx): {"key": f"K{idx}"}
                for idx, _item in enumerate(items)
            }
        }


def test_batched_create_collapses_n_calls_into_one(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg, _pipeline_mod, hub_config = _prepare_cfg(monkeypatch, tmp_path)
    _write_papers(cfg, count=30)
    zot = _FakeZotero()
    monkeypatch.setattr(pipeline, "get_client", lambda: zot)

    try:
        assert pipeline.run_pipeline(dry_run=False, cluster_slug="agents", verify=False) == 0
        assert len(zot.create_calls) == 1
        output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
        assert all(paper["zotero_key"] for paper in output["papers"])
    finally:
        hub_config._config = None


def test_batched_falls_back_to_per_paper_on_batch_exception(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg, _pipeline_mod, hub_config = _prepare_cfg(monkeypatch, tmp_path)
    _write_papers(cfg, count=30)
    zot = _FakeZotero(fail_first_batch=True)
    monkeypatch.setattr(pipeline, "get_client", lambda: zot)

    try:
        assert pipeline.run_pipeline(dry_run=False, cluster_slug="agents", verify=False) == 0
        assert len(zot.create_calls) == 31
        output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
        assert all(paper["zotero_key"] == "K0" for paper in output["papers"])
    finally:
        hub_config._config = None


def test_batch_response_keys_map_back_to_papers_correctly(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg, _pipeline_mod, hub_config = _prepare_cfg(monkeypatch, tmp_path)
    _write_papers(cfg, count=30)
    zot = _FakeZotero()
    monkeypatch.setattr(pipeline, "get_client", lambda: zot)

    try:
        assert pipeline.run_pipeline(dry_run=False, cluster_slug="agents", verify=False) == 0
        output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
        assert [paper["zotero_key"] for paper in output["papers"]] == [f"K{i}" for i in range(30)]
    finally:
        hub_config._config = None

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
        self._single_calls = 0

    def item_template(self, item_type: str):
        return {"itemType": item_type}

    def create_items(self, items: list[dict]):
        self.create_calls.append(items)
        if self.fail_first_batch and len(self.create_calls) == 1:
            raise RuntimeError("batch failed")
        if len(items) == 1:
            # single-item (per-paper retry): a real Zotero hands out a fresh,
            # DISTINCT key per call — not a collapsed "K0" for every retry. This
            # keeps the exception-fallback test honest about key-uniqueness.
            key = f"R{self._single_calls}"
            self._single_calls += 1
            return {"successful": {"0": {"key": key}}}
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
        keys = [paper["zotero_key"] for paper in output["papers"]]
        # every paper got a key, and each is DISTINCT — the exception-fallback
        # path must never collapse distinct papers onto one key (STAB-1).
        assert all(keys)
        assert len(set(keys)) == 30
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


class _SparseZotero:
    """Batch create returns ``successful`` for EVEN indexes only; odd indexes are
    absent from BOTH ``successful`` and ``failed`` — the sparse-response shape
    behind STAB-1. Single-item retries hand out fresh, distinct keys (a realistic
    Zotero, unlike _FakeZotero which returns "K0" for every single-item call)."""

    def __init__(self):
        self.create_calls: list[list[dict]] = []
        self._retry = 0

    def item_template(self, item_type: str):
        return {"itemType": item_type}

    def create_items(self, items: list[dict]):
        self.create_calls.append(items)
        if len(items) > 1:
            return {
                "successful": {
                    str(idx): {"key": f"K{idx}"}
                    for idx, _item in enumerate(items)
                    if idx % 2 == 0
                }
            }
        key = f"R{self._retry}"
        self._retry += 1
        return {"successful": {"0": {"key": key}}}


def test_batch_sparse_response_retries_missing_indexes_for_own_key(tmp_path, monkeypatch):
    """STAB-1 regression: when Zotero's batch ``successful`` map omits indexes that
    are also absent from ``failed``, each missing paper must be retried for its OWN
    key — never stamped with another paper's key, which would silently cross-link
    two distinct papers onto one Zotero item (and write a note onto the wrong one)."""
    from research_hub import pipeline

    cfg, _pipeline_mod, hub_config = _prepare_cfg(monkeypatch, tmp_path)
    _write_papers(cfg, count=4)
    zot = _SparseZotero()
    monkeypatch.setattr(pipeline, "get_client", lambda: zot)

    try:
        assert pipeline.run_pipeline(dry_run=False, cluster_slug="agents", verify=False) == 0
        output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
        keys = {paper["title"]: paper["zotero_key"] for paper in output["papers"]}
        # even indexes keep their batch key
        assert keys["Paper 0"] == "K0"
        assert keys["Paper 2"] == "K2"
        # odd indexes were retried individually -> their OWN distinct keys, NOT
        # the last successful batch key (K2 under the old fallback_key bug)
        assert keys["Paper 1"] not in ("K0", "K2")
        assert keys["Paper 3"] not in ("K0", "K2")
        assert keys["Paper 1"] != keys["Paper 3"]
        # no two papers share a Zotero key
        assert len(set(keys.values())) == len(keys)
        # one batch call + one retry per missing (odd) index
        assert len(zot.create_calls) == 3
    finally:
        hub_config._config = None


def test_run_pipeline_reads_passed_papers_json_not_shared_default(tmp_path, monkeypatch):
    """WF-2 regression: when an explicit papers_json is passed, run_pipeline reads
    THAT file and ignores the shared cfg.root/papers_input.json — so a concurrent
    run clobbering the default path cannot contaminate this run's cluster."""
    from research_hub import pipeline

    cfg, _pipeline_mod, hub_config = _prepare_cfg(monkeypatch, tmp_path)
    # this run's OWN input, written to a per-run path
    run_dir = cfg.root / ".runs" / "agents-1234"
    run_dir.mkdir(parents=True)
    own = [_paper("Own A", "own-a", "10.1000/aa"), _paper("Own B", "own-b", "10.1000/bb")]
    (run_dir / "papers_input.json").write_text(json.dumps({"papers": own}), encoding="utf-8")
    # a "concurrent run B" clobbers the SHARED default path with different papers
    other = [_paper("Other X", "other-x", "10.1000/xx")]
    (cfg.root / "papers_input.json").write_text(json.dumps({"papers": other}), encoding="utf-8")

    zot = _FakeZotero()
    monkeypatch.setattr(pipeline, "get_client", lambda: zot)
    try:
        rc = pipeline.run_pipeline(
            dry_run=False,
            cluster_slug="agents",
            verify=False,
            papers_json=run_dir / "papers_input.json",
        )
        assert rc == 0
        output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
        titles = sorted(paper["title"] for paper in output["papers"])
        # ingested THIS run's papers, never the clobbered default ("Other X")
        assert titles == ["Own A", "Own B"]
    finally:
        hub_config._config = None

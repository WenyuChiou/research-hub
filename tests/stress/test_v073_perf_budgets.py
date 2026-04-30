from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.search.base import SearchResult
from research_hub.search.fallback import search_papers
from research_hub.summarize import apply_summaries
from tests.stress._helpers import make_stress_cfg
from tests.test_pipeline import _configure, _paper


class _SleepBackend:
    delay = 5.0
    name = "sleep"

    def __init__(self, source: str):
        self.source = source

    def search(self, query: str, **kwargs):
        del query, kwargs
        time.sleep(self.delay)
        return [SearchResult(title=f"{self.source} paper", doi=f"10.1/{self.source}", year=2024, source=self.source)]


@pytest.mark.stress
def test_parallel_search_under_8s_for_4_mocked_backends_with_5s_latency(monkeypatch):
    import research_hub.search.fallback as fallback

    registry = {
        "a": type("BackendA", (), {"search": lambda self, query, **kwargs: _SleepBackend("a").search(query, **kwargs)}),
        "b": type("BackendB", (), {"search": lambda self, query, **kwargs: _SleepBackend("b").search(query, **kwargs)}),
        "c": type("BackendC", (), {"search": lambda self, query, **kwargs: _SleepBackend("c").search(query, **kwargs)}),
        "d": type("BackendD", (), {"search": lambda self, query, **kwargs: _SleepBackend("d").search(query, **kwargs)}),
    }
    monkeypatch.setattr(fallback, "_BACKEND_REGISTRY", registry)

    start = time.perf_counter()
    results = search_papers("query", backends=tuple(registry), limit=10, rank_by="year")
    elapsed = time.perf_counter() - start

    assert len(results) == 4
    assert elapsed < 8.0


@pytest.mark.stress
def test_batched_zotero_ingest_under_3s_for_30_papers(tmp_path, monkeypatch):
    from research_hub import config as hub_config
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    ClusterRegistry(cfg.clusters_file).create(query="stress", name="Stress", slug="stress")
    papers = [_paper(f"Paper {i}", f"paper-{i:02d}", f"10.1000/{i:02d}") for i in range(30)]
    (cfg.root / "papers_input.json").write_text(json.dumps(papers), encoding="utf-8")

    class _FastZotero:
        def item_template(self, item_type: str):
            return {"itemType": item_type}

        def create_items(self, items):
            return {"successful": {str(idx): {"key": f"K{idx}"} for idx, _item in enumerate(items)}}

    monkeypatch.setattr(pipeline, "get_client", lambda: _FastZotero())
    monkeypatch.setattr(pipeline, "check_duplicate", lambda zot, title, doi="", **kwargs: False)
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)

    start = time.perf_counter()
    try:
        assert pipeline.run_pipeline(dry_run=False, cluster_slug="stress", verify=False) == 0
    finally:
        hub_config._config = None
    elapsed = time.perf_counter() - start

    assert elapsed < 3.0


def _write_summary_note(path, slug: str, idx: int) -> None:
    path.write_text(
        f"""---
title: "Paper {idx}"
year: 2024
doi: "10.1/{slug}"
zotero-key: ZK{idx}
---

## Abstract

Abstract for paper {idx}.

---

## Summary

> [!abstract]
> [TODO]
^summary

## Key Findings

> [!success]
> - [TODO: fill from abstract]
^findings

## Methodology

> [!info]
> [TODO: fill from abstract]
^methodology

## Relevance

> [!note]
> [TODO: fill relevance to cluster]
^relevance
""",
        encoding="utf-8",
    )


@pytest.mark.stress
def test_parallel_summarize_writes_under_5s_for_30_papers(tmp_path, monkeypatch):
    import research_hub.summarize as summarize

    cfg = make_stress_cfg(tmp_path)
    cluster_dir = cfg.raw / "stress"
    cluster_dir.mkdir(parents=True, exist_ok=True)
    for idx in range(30):
        slug = f"paper-{idx:02d}"
        _write_summary_note(cluster_dir / f"{slug}.md", slug, idx)

    payload = {
        "summaries": [
            {
                "paper_slug": f"paper-{idx:02d}",
                "key_findings": [f"Finding {idx}A.", f"Finding {idx}B."],
                "methodology": f"Method {idx}.",
                "relevance": f"Relevance {idx}.",
            }
            for idx in range(30)
        ]
    }

    def slow_zotero_write(zot, parent_key: str, html: str):
        del zot, parent_key, html
        time.sleep(0.1)

    monkeypatch.setattr(summarize, "_write_zotero_child_note", slow_zotero_write)

    start = time.perf_counter()
    result = apply_summaries(
        SimpleNamespace(raw=cfg.raw, research_hub_dir=cfg.research_hub_dir),
        "stress",
        payload,
        zot=object(),
    )
    elapsed = time.perf_counter() - start

    assert len(result.applied) == 30
    assert elapsed < 5.0

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

from research_hub.summarize import apply_summaries


def _write_paper(path: Path, slug: str, title: str, zotero_key: str) -> None:
    path.write_text(
        f"""---
title: "{title}"
year: 2024
doi: "10.1/{slug}"
zotero-key: {zotero_key}
---

# {title}

## Abstract

Abstract for {title}.

---

## Summary

> [!abstract]
> [TODO] {title}
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


def _build_cfg(tmp_path: Path, root_name: str, count: int) -> SimpleNamespace:
    root = tmp_path / root_name
    raw = root / "raw" / "test-cluster"
    raw.mkdir(parents=True)
    research_hub_dir = root / ".research_hub"
    research_hub_dir.mkdir()
    for idx in range(1, count + 1):
        slug = f"paper-{idx:02d}"
        _write_paper(raw / f"{slug}.md", slug, f"Paper {idx}", f"ZK{idx}")
    return SimpleNamespace(raw=raw.parent, research_hub_dir=research_hub_dir)


def _payload(count: int) -> dict:
    return {
        "summaries": [
            {
                "paper_slug": f"paper-{idx:02d}",
                "key_findings": [f"Finding {idx}A.", f"Finding {idx}B.", f"Finding {idx}C."],
                "methodology": f"Method {idx}.",
                "relevance": f"Relevance {idx}.",
            }
            for idx in range(1, count + 1)
        ]
    }


class _SerialExecutor:
    def __init__(self, max_workers: int):
        self.max_workers = max_workers

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def map(self, fn, iterable):
        return [fn(item) for item in iterable]


class _ZoteroStub:
    def children(self, parent_key: str):
        return [{"data": {"key": f"N-{parent_key}", "itemType": "note", "note": "old", "parentItem": parent_key}}]

    def update_item(self, data):
        return {"ok": True, "data": data}

    def item_template(self, item_type: str):
        return {"itemType": item_type}

    def create_items(self, items):
        return {"successful": {"0": {"key": "NEW_NOTE"}}}


def test_parallel_writes_produce_same_apply_result_as_sequential(tmp_path, monkeypatch):
    import research_hub.summarize as summarize

    serial_cfg = _build_cfg(tmp_path, "serial", 5)
    parallel_cfg = _build_cfg(tmp_path, "parallel", 5)
    payload = _payload(5)
    zot = _ZoteroStub()

    with monkeypatch.context() as serial_patch:
        serial_patch.setattr(summarize, "ThreadPoolExecutor", _SerialExecutor)
        serial_result = apply_summaries(serial_cfg, "test-cluster", payload, zot=zot)

    parallel_result = apply_summaries(parallel_cfg, "test-cluster", payload, zot=zot)

    assert serial_result.applied == [f"paper-{idx:02d}" for idx in range(1, 6)]
    assert parallel_result.applied == serial_result.applied
    assert parallel_result.obsidian_writes == 5
    assert parallel_result.zotero_writes == 5
    for idx in range(1, 6):
        slug = f"paper-{idx:02d}"
        serial_text = (serial_cfg.raw / "test-cluster" / f"{slug}.md").read_text(encoding="utf-8")
        parallel_text = (parallel_cfg.raw / "test-cluster" / f"{slug}.md").read_text(encoding="utf-8")
        assert parallel_text == serial_text


def test_parallel_writes_preserve_per_paper_rollback_invariant(tmp_path, monkeypatch):
    import research_hub.summarize as summarize

    cfg = _build_cfg(tmp_path, "rollback", 5)
    originals = {
        idx: (cfg.raw / "test-cluster" / f"paper-{idx:02d}.md").read_text(encoding="utf-8")
        for idx in range(1, 6)
    }

    def fail_one(zot, parent_key: str, html: str):
        del zot, html
        if parent_key == "ZK2":
            raise RuntimeError("boom")

    monkeypatch.setattr(summarize, "_write_zotero_child_note", fail_one)
    result = apply_summaries(cfg, "test-cluster", _payload(5), zot=object())

    assert len(result.errors) == 1
    assert "paper-02" in result.errors[0]
    for idx in range(1, 6):
        path = cfg.raw / "test-cluster" / f"paper-{idx:02d}.md"
        text = path.read_text(encoding="utf-8")
        if idx == 2:
            assert text == originals[idx]
        else:
            assert text != originals[idx]
            assert f"Finding {idx}A." in text
            assert f"Method {idx}." in text
            assert f"Relevance {idx}." in text


def test_parallel_writes_use_4_workers_default(tmp_path, monkeypatch):
    import research_hub.summarize as summarize

    cfg = _build_cfg(tmp_path, "workers", 2)
    seen: dict[str, int] = {}

    class _SpyExecutor(_SerialExecutor):
        def __init__(self, max_workers: int):
            seen["max_workers"] = max_workers
            super().__init__(max_workers)

    monkeypatch.setattr(summarize, "ThreadPoolExecutor", _SpyExecutor)
    result = apply_summaries(cfg, "test-cluster", _payload(2), zot=_ZoteroStub())

    assert seen["max_workers"] == 4
    assert result.applied == ["paper-01", "paper-02"]

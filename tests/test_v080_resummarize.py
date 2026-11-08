from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from research_hub.clusters import ClusterRegistry
from research_hub.summarize import SummaryApplyResult, SummaryReport, summarize_cluster
from research_hub.zotero.enrich import EnrichPlan, apply_enrichment


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    research_hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    research_hub_dir.mkdir()
    return SimpleNamespace(
        root=root,
        raw=raw,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def _bind_cluster(cfg, slug: str, key: str = "COLL1") -> None:
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query=slug, name=slug.title(), slug=slug)
    registry.bind(slug, zotero_collection_key=key, sync_zotero=False)


def _write_note(path: Path, *, title: str, zotero_key: str, abstract: str, summary: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
title: "{title}"
year: 2026
doi: "10.1/{zotero_key.lower()}"
zotero-key: {zotero_key}
---

# {title}

## Abstract

{abstract}

---

## Summary

> [!abstract]
> {summary}
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


def test_summarize_cluster_filters_prompt_to_requested_paper_keys(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    cluster_dir = cfg.raw / "agents"
    _write_note(cluster_dir / "paper-one.md", title="Paper One", zotero_key="ZK1", abstract="Abstract one.", summary="[TODO] Paper One")
    _write_note(cluster_dir / "paper-two.md", title="Paper Two", zotero_key="ZK2", abstract="Abstract two.", summary="[TODO] Paper Two")
    monkeypatch.setattr("research_hub.llm_cli.detect_llm_cli", lambda: None)

    report = summarize_cluster(cfg, "agents", paper_keys=["ZK2"])

    assert report.ok is True
    assert report.prompt_path is not None
    prompt = report.prompt_path.read_text(encoding="utf-8")
    assert "Paper Two" in prompt
    assert "Paper One" not in prompt


def test_apply_enrichment_updates_note_and_chains_resummarize(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _bind_cluster(cfg, "agents")
    note_path = cfg.raw / "agents" / "paper-one.md"
    _write_note(
        note_path,
        title="Paper One",
        zotero_key="K1",
        abstract="(no abstract)",
        summary="[TODO] Paper One",
    )

    captured: dict[str, object] = {}

    def fake_summarize_cluster(cfg_arg, slug, *, apply=False, paper_keys=None, **kwargs):
        captured["cfg"] = cfg_arg
        captured["slug"] = slug
        captured["apply"] = apply
        captured["paper_keys"] = list(paper_keys or [])
        return SummaryReport(
            cluster_slug=slug,
            ok=True,
            cli_used="codex",
            apply_result=SummaryApplyResult(cluster_slug=slug, applied=["paper-one"]),
        )

    monkeypatch.setattr("research_hub.summarize.summarize_cluster", fake_summarize_cluster)

    class _Zot:
        def __init__(self) -> None:
            self.updated: list[dict] = []

        def item(self, key: str) -> dict:
            return {"data": {"key": key, "title": "Paper One", "abstractNote": ""}}

        def update_item(self, data: dict) -> dict:
            self.updated.append(data.copy())
            return {}

    zot = _Zot()
    results = apply_enrichment(
        zot,
        [
            EnrichPlan(
                item_key="K1",
                title="Paper One",
                doi="10.1/k1",
                fields_to_fill={"abstractNote": "Recovered abstract text."},
                abstract_source="s2",
            )
        ],
        rate_limit_rps=999.0,
        cfg=cfg,
        cluster_slug="agents",
    )

    assert results == {"K1": "ok"}
    assert captured["slug"] == "agents"
    assert captured["apply"] is True
    assert captured["paper_keys"] == ["K1"]
    text = note_path.read_text(encoding="utf-8")
    assert "Recovered abstract text." in text
    assert 'abstract_source: "s2"' in text


def test_cli_paper_resummarize_targets_only_todo_notes(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    _bind_cluster(cfg, "agents")
    cluster_dir = cfg.raw / "agents"
    _write_note(cluster_dir / "todo-note.md", title="Todo Note", zotero_key="KTODO", abstract="Abstract one.", summary="[TODO] Todo Note")
    _write_note(cluster_dir / "done-note.md", title="Done Note", zotero_key="KDONE", abstract="Abstract two.", summary="Completed summary.")
    monkeypatch.setattr(cli, "get_config", lambda: cfg)

    captured: dict[str, object] = {}

    def fake_summarize_cluster(cfg_arg, slug, *, apply=False, paper_keys=None, **kwargs):
        captured["cfg"] = cfg_arg
        captured["slug"] = slug
        captured["apply"] = apply
        captured["paper_keys"] = list(paper_keys or [])
        return SummaryReport(
            cluster_slug=slug,
            ok=True,
            cli_used="codex",
            apply_result=SummaryApplyResult(cluster_slug=slug, applied=["todo-note"]),
        )

    monkeypatch.setattr("research_hub.summarize.summarize_cluster", fake_summarize_cluster)

    rc = cli.main(["paper", "resummarize", "--cluster", "agents", "--apply"])

    assert rc == 0
    assert captured["slug"] == "agents"
    assert captured["apply"] is True
    assert captured["paper_keys"] == ["KTODO"]

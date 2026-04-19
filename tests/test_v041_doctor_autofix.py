from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from research_hub.clusters import ClusterRegistry
from research_hub.paper import _parse_frontmatter
from research_hub.vault_autofix import run_autofix


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir(parents=True)
    return SimpleNamespace(root=root, raw=raw, research_hub_dir=hub, clusters_file=hub / "clusters.yaml")


def _write_note(path: Path, frontmatter: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\n{frontmatter}\n---\n\n## Summary\nx\n\n## Key Findings\n- x\n\n## Methodology\nx\n\n## Relevance\nx\n",
        encoding="utf-8",
    )


def test_autofix_backfills_topic_cluster_from_folder_mapping(tmp_path):
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    note = cfg.raw / "agents" / "paper-one.md"
    _write_note(note, 'title: "Paper"\ndoi: "10.1/x"\nauthors: "Doe"\nyear: "2026"\ntopic_cluster: ""')

    summary = run_autofix(cfg)
    meta = _parse_frontmatter(note.read_text(encoding="utf-8"))

    assert summary["topic_cluster"] == 1
    assert meta["topic_cluster"] == "agents"


def test_autofix_is_idempotent(tmp_path):
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    note = cfg.raw / "agents" / "2604.08224-paper.md"
    _write_note(note, 'title: "Paper"\nauthors: "Doe"\nyear: "2026"')

    first = run_autofix(cfg)
    second = run_autofix(cfg)

    assert first["topic_cluster"] == 1
    assert first["ingested_at"] == 1
    assert first["doi_derived"] == 1
    assert second == {
        "topic_cluster": 0,
        "ingested_at": 0,
        "doi_derived": 0,
        "skipped_no_cluster": 0,
    }


def test_autofix_skips_orphan_folders_without_cluster_mapping(tmp_path):
    cfg = _cfg(tmp_path)
    note = cfg.raw / "orphan-folder" / "paper-one.md"
    _write_note(note, 'title: "Paper"\ndoi: "10.1/x"\nauthors: "Doe"\nyear: "2026"')

    summary = run_autofix(cfg)
    meta = _parse_frontmatter(note.read_text(encoding="utf-8"))

    assert summary["skipped_no_cluster"] == 1
    assert meta.get("topic_cluster", "") == ""


def test_autofix_adds_ingested_at_from_mtime(tmp_path):
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    note = cfg.raw / "agents" / "paper-one.md"
    _write_note(note, 'title: "Paper"\ndoi: "10.1/x"\nauthors: "Doe"\nyear: "2026"\ntopic_cluster: "agents"')
    note.touch()

    summary = run_autofix(cfg)
    meta = _parse_frontmatter(note.read_text(encoding="utf-8"))

    assert summary["ingested_at"] == 1
    assert str(meta["ingested_at"]).endswith("Z")

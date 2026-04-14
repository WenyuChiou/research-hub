from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    research_hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        raw=raw,
        hub=hub,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def _write_note(cfg, cluster: str, slug: str, labels: str = "deprecated") -> Path:
    note_dir = cfg.raw / cluster
    note_dir.mkdir(parents=True, exist_ok=True)
    path = note_dir / f"{slug}.md"
    path.write_text(
        (
            "---\n"
            f'title: "{slug}"\n'
            f'doi: "10.1/{slug}"\n'
            f'topic_cluster: "{cluster}"\n'
            f"labels: [{labels}]\n"
            "---\n"
            "Body\n"
        ),
        encoding="utf-8",
    )
    return path


def _seed_dedup(cfg, path: Path, doi: str) -> None:
    payload = {
        "doi_to_hits": {doi: [{"source": "obsidian", "doi": doi, "title": path.stem, "zotero_key": None, "obsidian_path": str(path)}]},
        "title_to_hits": {},
    }
    (cfg.research_hub_dir / "dedup_index.json").write_text(json.dumps(payload), encoding="utf-8")


def test_prune_dry_run_changes_nothing(tmp_path):
    from research_hub.paper import prune_cluster

    cfg = _cfg(tmp_path)
    path = _write_note(cfg, "agents", "paper")

    result = prune_cluster(cfg, "agents", dry_run=True)

    assert result["mode"] == "dry_run"
    assert path.exists()


def test_prune_archive_moves_to_archive_dir(tmp_path):
    from research_hub.paper import archive_dir, prune_cluster

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper")

    prune_cluster(cfg, "agents", dry_run=False)

    assert (archive_dir(cfg, "agents") / "paper.md").exists()


def test_prune_archive_adds_archived_label(tmp_path):
    from research_hub.paper import archive_dir, prune_cluster, read_labels

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper")

    prune_cluster(cfg, "agents", dry_run=False)

    assert read_labels(cfg, "paper") is None
    archived_text = (archive_dir(cfg, "agents") / "paper.md").read_text(encoding="utf-8")
    assert "archived" in archived_text


def test_prune_archive_updates_topic_cluster_field(tmp_path):
    from research_hub.paper import archive_dir, prune_cluster

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper")

    prune_cluster(cfg, "agents", dry_run=False)

    text = (archive_dir(cfg, "agents") / "paper.md").read_text(encoding="utf-8")
    assert 'topic_cluster: "_archive/agents"' in text


def test_prune_archive_removes_from_dedup_index(tmp_path):
    from research_hub.paper import prune_cluster

    cfg = _cfg(tmp_path)
    path = _write_note(cfg, "agents", "paper")
    _seed_dedup(cfg, path, "10.1/paper")

    prune_cluster(cfg, "agents", dry_run=False)

    payload = json.loads((cfg.research_hub_dir / "dedup_index.json").read_text(encoding="utf-8"))
    assert payload["doi_to_hits"] == {}


def test_prune_delete_removes_file(tmp_path):
    from research_hub.paper import prune_cluster

    cfg = _cfg(tmp_path)
    path = _write_note(cfg, "agents", "paper")

    result = prune_cluster(cfg, "agents", delete=True, archive=False, dry_run=False)

    assert result["deleted"] == ["paper"]
    assert not path.exists()


def test_prune_custom_label(tmp_path):
    from research_hub.paper import prune_cluster

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper", labels="tangential")

    result = prune_cluster(cfg, "agents", label="tangential", dry_run=False)

    assert result["moved"] == ["paper"]


def test_prune_returns_empty_when_no_matches(tmp_path):
    from research_hub.paper import prune_cluster

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper", labels="seed")

    result = prune_cluster(cfg, "agents", dry_run=False)

    assert result["moved"] == []
    assert result["would_affect"] == []


def test_unarchive_restores_paper_to_active_dir(tmp_path):
    from research_hub.paper import prune_cluster, unarchive

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper")
    prune_cluster(cfg, "agents", dry_run=False)

    result = unarchive(cfg, "agents", "paper")

    assert result["restored"] == "paper"
    assert (cfg.raw / "agents" / "paper.md").exists()


def test_unarchive_removes_archived_label(tmp_path):
    from research_hub.paper import prune_cluster, unarchive

    cfg = _cfg(tmp_path)
    _write_note(cfg, "agents", "paper")
    prune_cluster(cfg, "agents", dry_run=False)

    unarchive(cfg, "agents", "paper")

    text = (cfg.raw / "agents" / "paper.md").read_text(encoding="utf-8")
    assert "archived" not in text

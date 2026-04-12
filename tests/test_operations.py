from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config
from research_hub.dedup import DedupHit, DedupIndex
from research_hub.operations import mark_paper, move_paper, remove_paper


def _make_config(tmp_path: Path, monkeypatch):
    root = tmp_path / "vault"
    raw = root / "raw"
    hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    hub_dir.mkdir(parents=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"knowledge_base": {"root": str(root), "raw": str(raw)}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("RESEARCH_HUB_CONFIG", str(config_path))
    return get_config()


def _write_note(
    path: Path,
    *,
    title: str,
    doi: str = "",
    cluster: str = "",
    status: str = "unread",
    zotero_key: str = "",
):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f'title: "{title}"\n'
        f'doi: "{doi}"\n'
        f'zotero-key: "{zotero_key}"\n'
        f'topic_cluster: "{cluster}"\n'
        f"status: {status}\n"
        "---\n"
        f"# {title}\n",
        encoding="utf-8",
    )
    return path


def test_remove_paper_removes_matching_note(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    note = _write_note(cfg.raw / "alpha" / "paper-one.md", title="Paper One")

    result = remove_paper("paper-one")

    assert result["removed_files"] == [str(note)]
    assert not note.exists()


def test_remove_paper_dry_run_keeps_file(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    note = _write_note(cfg.raw / "alpha" / "paper-one.md", title="Paper One")

    result = remove_paper("paper-one", dry_run=True)

    assert result["removed_files"] == [str(note)]
    assert note.exists()


def test_remove_paper_resolves_doi_from_dedup_index(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    note = _write_note(cfg.raw / "alpha" / "paper-one.md", title="Paper One", doi="10.1000/example")
    index = DedupIndex()
    index.add(
        DedupHit(
            source="obsidian",
            doi="10.1000/example",
            title="Paper One",
            obsidian_path=str(note),
        )
    )
    index.save(cfg.research_hub_dir / "dedup_index.json")

    result = remove_paper("10.1000/example")

    assert result["removed_files"] == [str(note)]
    assert not note.exists()


def test_remove_paper_deletes_zotero_item_when_requested(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    _write_note(
        cfg.raw / "alpha" / "paper-one.md",
        title="Paper One",
        zotero_key="ABCD1234",
    )
    calls: list[str] = []

    class FakeDual:
        def delete_item(self, key):
            calls.append(key)

    monkeypatch.setattr("research_hub.zotero.client.ZoteroDualClient", lambda: FakeDual())

    result = remove_paper("paper-one", include_zotero=True)

    assert result["zotero_deleted"] is True
    assert calls == ["ABCD1234"]


def test_mark_paper_updates_status(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    note = _write_note(cfg.raw / "alpha" / "paper-one.md", title="Paper One", status="unread")

    result = mark_paper("paper-one", "reading")

    assert result["updated"] == [str(note)]
    assert "status: reading" in note.read_text(encoding="utf-8")


def test_mark_paper_bulk_marks_cluster(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    note1 = _write_note(cfg.raw / "alpha" / "one.md", title="One", cluster="alpha")
    note2 = _write_note(cfg.raw / "alpha" / "two.md", title="Two", cluster="alpha")

    result = mark_paper(None, "deep-read", cluster="alpha")

    assert result["updated"] == [str(note1), str(note2)]
    assert "status: deep-read" in note1.read_text(encoding="utf-8")
    assert "status: deep-read" in note2.read_text(encoding="utf-8")


def test_mark_paper_rejects_invalid_status(tmp_path, monkeypatch):
    _make_config(tmp_path, monkeypatch)

    with pytest.raises(ValueError):
        mark_paper("paper-one", "skim")


def test_move_paper_moves_file_and_updates_cluster(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    source = _write_note(cfg.raw / "alpha" / "paper-one.md", title="Paper One", cluster="alpha")

    result = move_paper("paper-one", "beta")
    target = cfg.raw / "beta" / "paper-one.md"

    assert result == {"from": str(source), "to": str(target), "cluster": "beta"}
    assert not source.exists()
    assert target.exists()
    assert "topic_cluster: beta" in target.read_text(encoding="utf-8")


def test_move_paper_creates_target_directory(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    _write_note(cfg.raw / "alpha" / "paper-one.md", title="Paper One", cluster="alpha")

    move_paper("paper-one", "new-cluster")

    assert (cfg.raw / "new-cluster").exists()


def test_move_paper_raises_when_source_missing(tmp_path, monkeypatch):
    _make_config(tmp_path, monkeypatch)

    with pytest.raises(FileNotFoundError):
        move_paper("missing", "beta")


def test_move_paper_noop_when_already_in_target(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    note = _write_note(cfg.raw / "beta" / "paper-one.md", title="Paper One", cluster="beta")

    result = move_paper("paper-one", "beta")

    assert result == {"from": str(note), "to": str(note), "cluster": "beta"}
    assert note.exists()


def test_cluster_rename_updates_registry(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create("flood risk", name="Flood Risk", slug="flood-risk")

    updated = registry.rename("flood-risk", "Flood Perception")

    assert updated.name == "Flood Perception"
    assert ClusterRegistry(cfg.clusters_file).get("flood-risk").name == "Flood Perception"


def test_cluster_rename_updates_display_name_only(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create("my-query", name="Old Name", slug="my-slug")

    registry.rename("my-slug", "New Name")

    fresh = ClusterRegistry(cfg.clusters_file)
    assert fresh.clusters["my-slug"].name == "New Name"


def test_cluster_delete_removes_registry_entry_and_unbinds_notes(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create("flood risk", name="Flood Risk", slug="flood-risk")
    note = _write_note(cfg.raw / "flood-risk" / "paper-one.md", title="Paper One", cluster="flood-risk")

    result = registry.delete("flood-risk")

    assert result["notes_unbound"] == 1
    assert ClusterRegistry(cfg.clusters_file).get("flood-risk") is None
    assert 'topic_cluster: ""' in note.read_text(encoding="utf-8")


def test_cluster_delete_dry_run_preserves_registry(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create("flood risk", name="Flood Risk", slug="flood-risk")

    result = registry.delete("flood-risk", dry_run=True)

    assert result["dry_run"] is True
    assert ClusterRegistry(cfg.clusters_file).get("flood-risk") is not None


def test_cluster_merge_moves_files_and_updates_notes(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create("source", name="Source", slug="source")
    registry.create("target", name="Target", slug="target")
    note = _write_note(cfg.raw / "source" / "paper-one.md", title="Paper One", cluster="source")

    result = registry.merge("source", "target", vault_raw=cfg.raw)
    moved = cfg.raw / "target" / "paper-one.md"

    assert result == {"source": "source", "target": "target", "moved": 1}
    assert ClusterRegistry(cfg.clusters_file).get("source") is None
    assert moved.exists()
    assert "topic_cluster: target" in moved.read_text(encoding="utf-8")
    assert not note.exists()


def test_cluster_merge_raises_for_missing_target(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create("source", name="Source", slug="source")

    with pytest.raises(ValueError):
        registry.merge("source", "missing", vault_raw=cfg.raw)


def test_cluster_merge_with_no_notes_returns_zero(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create("source", name="Source", slug="source")
    registry.create("target", name="Target", slug="target")

    result = registry.merge("source", "target", vault_raw=cfg.raw)

    assert result["moved"] == 0


def test_cluster_split_creates_new_cluster_and_moves_matches(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create("flood risk", name="Flood Risk", slug="flood-risk")
    _write_note(
        cfg.raw / "flood-risk" / "flood-agents.md",
        title="Flood Risk Agents",
        cluster="flood-risk",
    )
    _write_note(
        cfg.raw / "flood-risk" / "coastal-insurance.md",
        title="Coastal Insurance Pricing",
        cluster="flood-risk",
    )

    result = registry.split("flood-risk", "flood agents", "Flood Agents", vault_raw=cfg.raw)

    assert result["new_cluster"] == "flood-agents"
    assert result["moved"] == 1
    assert (cfg.raw / "flood-agents" / "flood-agents.md").exists()
    assert (cfg.raw / "flood-risk" / "coastal-insurance.md").exists()


def test_cluster_split_keeps_non_matching_notes(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create("flood risk", name="Flood Risk", slug="flood-risk")
    _write_note(
        cfg.raw / "flood-risk" / "coastal-insurance.md",
        title="Coastal Insurance Pricing",
        cluster="flood-risk",
    )

    result = registry.split("flood-risk", "flood agents", "Flood Agents", vault_raw=cfg.raw)

    assert result["moved"] == 0
    assert result["remaining"] == 1

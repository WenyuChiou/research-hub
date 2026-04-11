from __future__ import annotations

from research_hub.manifest import Manifest, new_entry


def test_manifest_append_creates_parent_dir(tmp_path):
    manifest = Manifest(tmp_path / "nested" / "manifest.jsonl")

    manifest.append(new_entry("cluster-a", "query", "new"))

    assert manifest.path.exists()


def test_manifest_read_all_returns_empty_for_missing_file(tmp_path):
    manifest = Manifest(tmp_path / "missing.jsonl")

    assert manifest.read_all() == []


def test_manifest_append_and_read_roundtrip(tmp_path):
    manifest = Manifest(tmp_path / "manifest.jsonl")
    entry = new_entry("cluster-a", "query", "new", title="Paper")

    manifest.append(entry)
    loaded = manifest.read_all()

    assert len(loaded) == 1
    assert loaded[0].title == "Paper"


def test_manifest_get_ingested_keys_filters_by_cluster_and_new(tmp_path):
    manifest = Manifest(tmp_path / "manifest.jsonl")
    manifest.append(new_entry("cluster-a", "q1", "new", zotero_key="A"))
    manifest.append(new_entry("cluster-a", "q2", "dup-zotero", zotero_key="B"))
    manifest.append(new_entry("cluster-b", "q3", "new", zotero_key="C"))

    assert manifest.get_ingested_keys("cluster-a") == {"A"}


def test_manifest_count_by_action(tmp_path):
    manifest = Manifest(tmp_path / "manifest.jsonl")
    manifest.append(new_entry("cluster-a", "q1", "new"))
    manifest.append(new_entry("cluster-a", "q2", "new"))
    manifest.append(new_entry("cluster-a", "q3", "dup-zotero"))

    assert manifest.count_by_action("cluster-a") == {"new": 2, "dup-zotero": 1}


def test_new_entry_includes_timestamp():
    entry = new_entry("cluster-a", "query", "new")

    assert entry.timestamp.endswith("Z")

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_hub.manifest import Manifest, new_entry


def test_manifest_append_only_not_overwritten(tmp_path):
    path = tmp_path / "manifest.jsonl"
    manifest = Manifest(path)
    for idx in range(3):
        manifest.append(new_entry("cluster-a", f"q{idx}", "new", title=str(idx)))

    reopened = Manifest(path)
    reopened.append(new_entry("cluster-a", "q3", "updated", title="3"))
    reopened.append(new_entry("cluster-a", "q4", "discover", title="4"))

    loaded = reopened.read_all()
    assert len(loaded) == 5
    assert [entry.title for entry in loaded] == ["0", "1", "2", "3", "4"]


def test_manifest_read_skips_malformed_json_lines(tmp_path):
    path = tmp_path / "manifest.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(new_entry("cluster-a", "q1", "new").__dict__),
                "{not-json",
                json.dumps(new_entry("cluster-b", "q2", "updated").__dict__),
            ]
        ),
        encoding="utf-8",
    )

    entries = Manifest(path).read_all()

    assert [entry.cluster for entry in entries] == ["cluster-a", "cluster-b"]


def test_manifest_action_vocabulary_respected():
    allow = {
        "new",
        "duplicate",
        "dup-obsidian",
        "dup-zotero",
        "error",
        "updated",
        "archived",
        "move",
        "label",
        "repair_created_note",
        "repair_pruned_dedup",
        "rebuild",
        "discover",
    }
    manifest_path = Path.home() / "knowledge-base" / ".research_hub" / "manifest.jsonl"
    if not manifest_path.exists():
        pytest.skip("live manifest not present")
    unknown = {entry.action for entry in Manifest(manifest_path).read_all() if entry.action not in allow}
    assert not unknown, f"Unknown action values in manifest: {unknown}"

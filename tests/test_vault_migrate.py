"""Tests for vault YAML migration helpers."""

from __future__ import annotations

from pathlib import Path

from research_hub.vault.migrate import (
    migrate_note,
    migrate_vault,
    needs_migration,
    patch_frontmatter,
)


def _write_note(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_needs_migration_detects_missing_status_field():
    text = "---\ntitle: Test\ntopic_cluster: \"\"\nverified: false\n---\n"
    assert "status" in needs_migration(text)


def test_needs_migration_returns_empty_when_all_present():
    text = (
        "---\n"
        "title: Test\n"
        "topic_cluster: \"\"\n"
        "verified: false\n"
        "status: unread\n"
        "ingested_at: \"2026-04-11T00:00:00Z\"\n"
        "ingestion_source: \"research-hub\"\n"
        "---\n"
    )
    assert needs_migration(text) == []


def test_patch_frontmatter_inserts_before_closing_dashes():
    text = "---\ntitle: Test\n---\nBody\n"
    patched = patch_frontmatter(text, {"status": "unread"})
    assert "status: unread\n---" in patched


def test_patch_frontmatter_preserves_existing_fields():
    text = "---\ntitle: Test\nyear: 2024\n---\nBody\n"
    patched = patch_frontmatter(text, {"status": "unread"})
    assert patched.index("title: Test") < patched.index("year: 2024") < patched.index("status: unread")


def test_migrate_note_skips_when_status_already_present(tmp_path: Path):
    note = tmp_path / "note.md"
    _write_note(note, "---\ntitle: Test\nstatus: unread\n---\nBody\n")

    assert migrate_note(note) is None


def test_migrate_note_bulk_assign_cluster_without_force_skips_existing(tmp_path: Path):
    note = tmp_path / "note.md"
    _write_note(
        note,
        "---\ntitle: Test\nstatus: unread\ntopic_cluster: existing\n---\nBody\n",
    )

    report = migrate_note(note, cluster_override="alpha", force=False)

    assert report is not None
    assert report["skipped"] == "topic_cluster already set"
    assert 'topic_cluster: existing' in note.read_text(encoding="utf-8")


def test_migrate_vault_dry_run_does_not_write(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    note = raw_dir / "legacy.md"
    original = "---\ntitle: Legacy\n---\nBody\n"
    _write_note(note, original)

    report = migrate_vault(raw_dir, dry_run=True)

    assert report["changed"] == 1
    assert note.read_text(encoding="utf-8") == original

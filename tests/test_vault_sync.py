"""Tests for vault.sync cluster status and Zotero-to-Obsidian reconcile."""

from __future__ import annotations

import json
from pathlib import Path

from research_hub.clusters import Cluster
from research_hub.vault.sync import (
    compute_sync_status,
    list_cluster_notes,
    reconcile_zotero_to_obsidian,
)


def _write_note(path: Path, *, doi: str, topic_cluster: str, title: str = "Test") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'---\ntitle: "{title}"\ndoi: "{doi}"\ntopic_cluster: "{topic_cluster}"\n---\n\n# {title}\n',
        encoding="utf-8",
    )
    return path


class FakeZotero:
    def __init__(self, items_by_collection: dict[str, list[dict]]):
        self.items_by_collection = items_by_collection

    def collection_items(self, key: str, start: int = 0, limit: int = 100, itemType: str = ""):
        items = self.items_by_collection.get(key, [])
        return items[start : start + limit]


def test_list_cluster_notes_filters_by_topic_cluster(tmp_path):
    raw = tmp_path / "raw"
    _write_note(raw / "llm" / "a.md", doi="10.1/a", topic_cluster="llm-agents")
    _write_note(raw / "llm" / "b.md", doi="10.1/b", topic_cluster="llm-agents")
    _write_note(raw / "survey" / "c.md", doi="10.1/c", topic_cluster="flood-risk")
    notes = list_cluster_notes("llm-agents", raw)
    assert len(notes) == 2
    assert [path.name for path in notes] == ["a.md", "b.md"]


def test_compute_sync_status_reports_zero_when_no_cluster_bound(tmp_path):
    raw = tmp_path / "raw"
    _write_note(raw / "a.md", doi="10.1/a", topic_cluster="llm-agents")
    cluster = Cluster(slug="llm-agents", name="LLM Agents")
    status = compute_sync_status(cluster, None, raw)
    assert status.cluster_slug == "llm-agents"
    assert status.obsidian_count == 1
    assert status.zotero_count == 0
    assert status.zotero_only == []


def test_compute_sync_status_detects_drift(tmp_path):
    raw = tmp_path / "raw"
    _write_note(raw / "a.md", doi="10.1/a", topic_cluster="llm-agents")
    _write_note(raw / "b.md", doi="10.1/b", topic_cluster="llm-agents")
    cluster = Cluster(slug="llm-agents", name="LLM Agents", zotero_collection_key="COLL1")
    fake = FakeZotero(
        {
            "COLL1": [
                {"key": "Z1", "data": {"DOI": "10.1/a", "itemType": "journalArticle"}},
                {"key": "Z2", "data": {"DOI": "10.1/c", "itemType": "journalArticle"}},
            ]
        }
    )
    status = compute_sync_status(cluster, fake, raw)
    assert status.zotero_count == 2
    assert status.obsidian_count == 2
    assert status.in_both == 1
    assert status.zotero_only == ["Z2"]
    assert len(status.obsidian_only) == 1


def test_compute_sync_status_reads_nlm_cache_when_present(tmp_path):
    raw = tmp_path / "raw"
    cache_path = tmp_path / "nlm_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "llm-agents": {
                    "uploaded_doi_count": 42,
                    "notebook_url": "https://notebooklm.google.com/notebook/abc",
                    "last_synced": "2026-04-11T10:00:00Z",
                }
            }
        ),
        encoding="utf-8",
    )
    cluster = Cluster(slug="llm-agents", name="LLM Agents")
    status = compute_sync_status(cluster, None, raw, nlm_cache_path=cache_path)
    assert status.nlm_cached_count == 42
    assert "notebooklm.google.com" in status.notebook_url


def test_reconcile_dry_run_does_not_write(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    cluster = Cluster(
        slug="llm-agents",
        name="LLM",
        zotero_collection_key="COLL1",
        obsidian_subfolder="llm-agents",
    )

    class StubCfg:
        root = tmp_path
        raw = tmp_path / "raw"
        logs = tmp_path / "logs"
        research_hub_dir = tmp_path / ".research_hub"

    fake = FakeZotero(
        {
            "COLL1": [
                {
                    "key": "Z1",
                    "data": {
                        "DOI": "10.1/a",
                        "title": "Sample",
                        "creators": [{"creatorType": "author", "lastName": "Smith", "firstName": "J"}],
                        "date": "2024",
                        "itemType": "journalArticle",
                        "publicationTitle": "J",
                        "abstractNote": "...",
                        "tags": [],
                    },
                }
            ]
        }
    )

    report = reconcile_zotero_to_obsidian(cluster, fake, StubCfg(), dry_run=True)
    assert len(report.created_notes) == 1
    assert report.dry_run is True
    assert not any((raw / "llm-agents").rglob("*.md"))


def test_reconcile_skips_existing_by_doi(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    _write_note(raw / "llm-agents" / "already.md", doi="10.1/a", topic_cluster="llm-agents")

    cluster = Cluster(
        slug="llm-agents",
        name="LLM",
        zotero_collection_key="COLL1",
        obsidian_subfolder="llm-agents",
    )

    class StubCfg:
        root = tmp_path
        raw = tmp_path / "raw"
        logs = tmp_path / "logs"
        research_hub_dir = tmp_path / ".research_hub"

    fake = FakeZotero(
        {
            "COLL1": [
                {
                    "key": "Z1",
                    "data": {
                        "DOI": "10.1/a",
                        "title": "Sample",
                        "creators": [{"creatorType": "author", "lastName": "Smith", "firstName": "J"}],
                        "date": "2024",
                        "itemType": "journalArticle",
                        "publicationTitle": "J",
                        "abstractNote": "",
                        "tags": [],
                    },
                }
            ]
        }
    )

    report = reconcile_zotero_to_obsidian(cluster, fake, StubCfg(), dry_run=False)
    assert report.skipped_existing == 1
    assert len(report.created_notes) == 0

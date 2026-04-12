"""Tests for DedupIndex invalidation API."""

from __future__ import annotations

from research_hub.dedup import DedupHit, DedupIndex


def test_invalidate_doi_removes_entries():
    idx = DedupIndex.empty()
    idx.add(DedupHit(source="zotero", doi="10.1234/x", title="A", zotero_key="K1"))

    assert len(idx.doi_to_hits) == 1

    removed = idx.invalidate_doi("10.1234/x")

    assert removed == 1
    assert len(idx.doi_to_hits) == 0


def test_invalidate_doi_normalizes_input():
    idx = DedupIndex.empty()
    idx.add(DedupHit(source="zotero", doi="10.1234/X", title="A", zotero_key="K1"))

    removed = idx.invalidate_doi("https://doi.org/10.1234/x")

    assert removed == 1


def test_invalidate_obsidian_path_removes_entries(tmp_path):
    idx = DedupIndex.empty()
    p1 = str(tmp_path / "raw" / "a.md")
    p2 = str(tmp_path / "raw" / "b.md")
    idx.add(DedupHit(source="obsidian", doi="10.1/a", title="A", obsidian_path=p1))
    idx.add(DedupHit(source="obsidian", doi="10.1/b", title="B", obsidian_path=p2))

    removed = idx.invalidate_obsidian_path(p1)

    assert removed >= 1
    assert "10.1/a" not in idx.doi_to_hits
    assert "10.1/b" in idx.doi_to_hits

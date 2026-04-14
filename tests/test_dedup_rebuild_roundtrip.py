from __future__ import annotations

import logging

from research_hub.dedup import DedupHit, DedupIndex


def _write_note(path, title: str, doi: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "---\n"
            f'title: "{title}"\n'
            f'doi: "{doi}"\n'
            "---\n"
        ),
        encoding="utf-8",
    )


def test_rebuild_from_obsidian_recovers_all_known_dois(tmp_path):
    raw = tmp_path / "raw"
    for idx in range(5):
        _write_note(raw / "alpha" / f"paper-{idx}.md", f"Paper {idx}", f"10.1/{idx}")

    rebuilt = DedupIndex.empty().rebuild_from_obsidian(raw)

    assert set(rebuilt.doi_to_hits) == {f"10.1/{idx}" for idx in range(5)}


def test_rebuild_preserves_zotero_hits(tmp_path):
    raw = tmp_path / "raw"
    _write_note(raw / "alpha" / "paper-a.md", "Paper A", "10.1/a")
    _write_note(raw / "alpha" / "paper-b.md", "Paper B", "10.1/b")
    index = DedupIndex.empty()
    index.add(DedupHit(source="obsidian", doi="10.1/old", title="Old Obsidian Title"))
    index.add(DedupHit(source="obsidian", doi="10.1/older", title="Older Obsidian Title"))
    index.add(DedupHit(source="zotero", doi="10.1/z1", title="Zotero One", zotero_key="Z1"))
    index.add(DedupHit(source="zotero", doi="10.1/z2", title="Zotero Two", zotero_key="Z2"))

    rebuilt = index.rebuild_from_obsidian(raw)

    assert {hit.zotero_key for hit in rebuilt.doi_to_hits["10.1/z1"]} == {"Z1"}
    assert {hit.zotero_key for hit in rebuilt.doi_to_hits["10.1/z2"]} == {"Z2"}
    assert "10.1/a" in rebuilt.doi_to_hits
    assert "10.1/b" in rebuilt.doi_to_hits
    assert "10.1/old" not in rebuilt.doi_to_hits


def test_rebuild_handles_malformed_frontmatter_gracefully(tmp_path, caplog):
    raw = tmp_path / "raw"
    _write_note(raw / "alpha" / "good-a.md", "Good A", "10.1/a")
    _write_note(raw / "alpha" / "good-b.md", "Good B", "10.1/b")
    bad = raw / "alpha" / "bad.md"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text('---\ntitle: "unterminated\ndoi: "10.1/bad"\n---\n', encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        rebuilt = DedupIndex.empty().rebuild_from_obsidian(raw)

    assert "10.1/a" in rebuilt.doi_to_hits
    assert "10.1/b" in rebuilt.doi_to_hits
    assert "10.1/bad" not in rebuilt.doi_to_hits
    assert any("Skipping malformed frontmatter" in message for message in caplog.messages)


def test_rebuild_normalizes_dois_consistently(tmp_path):
    raw = tmp_path / "raw"
    _write_note(raw / "alpha" / "one.md", "One", "10.1/x")
    _write_note(raw / "alpha" / "two.md", "Two", "https://doi.org/10.1/x")
    _write_note(raw / "alpha" / "three.md", "Three", "DOI:10.1/X")

    rebuilt = DedupIndex.empty().rebuild_from_obsidian(raw)

    assert list(rebuilt.doi_to_hits) == ["10.1/x"]
    assert len(rebuilt.doi_to_hits["10.1/x"]) == 3

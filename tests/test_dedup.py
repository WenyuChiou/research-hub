from __future__ import annotations

from research_hub.dedup import (
    DedupHit,
    DedupIndex,
    build_from_obsidian,
    normalize_doi,
    normalize_title,
)


def test_normalize_doi_strips_prefix_and_case():
    assert normalize_doi("https://doi.org/10.1234/ABC") == "10.1234/abc"
    assert normalize_doi("DOI:10.5/XYZ") == "10.5/xyz"
    assert normalize_doi("  http://doi.org/10.1/Test  ") == "10.1/test"


def test_normalize_title_strips_accents_and_punct():
    assert normalize_title("Flóòd Risk?") == "flood risk"


def test_normalize_title_empty_on_none_or_empty():
    assert normalize_title(None) == ""
    assert normalize_title("") == ""


def test_dedup_index_add_and_lookup_by_doi():
    index = DedupIndex()
    hit = DedupHit(source="zotero", doi="10.1000/example", title="Example Paper")

    index.add(hit)

    assert index.lookup(doi="10.1000/example") == [hit]


def test_dedup_index_lookup_falls_back_to_title_when_no_doi():
    index = DedupIndex()
    hit = DedupHit(source="obsidian", title="A Long Enough Title For Lookup")
    index.add(hit)

    matches = index.lookup(title="A long enough title for lookup")

    assert matches == [hit]


def test_dedup_index_save_and_load_roundtrip(tmp_path):
    index = DedupIndex()
    index.add(DedupHit(source="zotero", doi="10.1/x", title="Roundtrip Title"))
    path = tmp_path / "dedup_index.json"

    index.save(path)
    loaded = DedupIndex.load(path)

    assert loaded.lookup(doi="10.1/x")[0].title == "Roundtrip Title"


def test_dedup_check_returns_hits_for_matching_doi():
    index = DedupIndex()
    index.add(DedupHit(source="zotero", doi="10.1/check", title="Check Title"))

    is_duplicate, hits = index.check({"doi": "10.1/check", "title": "Other"})

    assert is_duplicate is True
    assert hits[0].source == "zotero"


def test_dedup_check_returns_empty_for_new_paper():
    index = DedupIndex()

    is_duplicate, hits = index.check({"doi": "10.9/new", "title": "Brand New Paper"})

    assert is_duplicate is False
    assert hits == []


def test_build_from_obsidian_parses_yaml_frontmatter(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "one.md").write_text(
        '---\n'
        'title: "Paper One"\n'
        'doi: "10.1/one"\n'
        'zotero-key: "KEY1"\n'
        '---\n',
        encoding="utf-8",
    )
    (raw_dir / "two.md").write_text(
        '---\n'
        'title: "Paper Two"\n'
        'doi: ""\n'
        'zotero-key: null\n'
        '---\n',
        encoding="utf-8",
    )

    hits = build_from_obsidian(raw_dir)

    assert len(hits) == 2
    assert hits[0].source == "obsidian"
    assert hits[1].zotero_key is None


def test_rebuild_from_obsidian_drops_stale_paths_regardless_of_source(tmp_path):
    """v0.49.3 regression: rebuild must clear hits whose obsidian_path is gone,
    even when source != 'obsidian' (e.g., 'importer' from import-folder).
    The previous filter only purged source='obsidian', leaving dead paths
    in the index forever.
    """
    raw = tmp_path / "raw"
    raw.mkdir()
    surviving = raw / "alive.md"
    surviving.write_text(
        '---\ntitle: "Alive paper"\ndoi: "10.1/alive"\nzotero-key: "K1"\n---\n',
        encoding="utf-8",
    )

    index = DedupIndex()
    # Pre-existing importer-source hit pointing at a file that no longer exists
    index.add(DedupHit(
        source="importer",
        doi="10.1/dead",
        title="Stale paper",
        obsidian_path=str(tmp_path / "deleted-by-user.md"),  # never created
    ))
    # Pre-existing zotero-source hit with no obsidian_path (must survive)
    index.add(DedupHit(
        source="zotero",
        doi="10.1/zotero-only",
        title="Pure-Zotero paper",
        zotero_key="K2",
    ))

    index.rebuild_from_obsidian(raw)

    # The stale importer hit should be GONE
    assert not index.lookup(doi="10.1/dead"), "stale importer hit not purged"
    # The pure-Zotero hit (no obsidian_path) must be preserved
    assert index.lookup(doi="10.1/zotero-only"), "pure-Zotero hit was wrongly dropped"
    # The new alive paper should be indexed
    assert index.lookup(doi="10.1/alive"), "rebuild did not pick up the alive paper"

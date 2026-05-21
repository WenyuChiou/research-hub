from __future__ import annotations

from pathlib import Path

from research_hub.vault.link_updater import (
    NoteMeta,
    add_wikilinks_to_note,
    find_related_in_cluster,
    parse_frontmatter,
    remove_paper_links,
)


def test_parse_frontmatter_extracts_title_tags_cluster(tmp_path):
    note = tmp_path / "paper.md"
    note.write_text(
        '---\n'
        'title: "Paper"\n'
        'tags: ["llm", "agents"]\n'
        'topic_cluster: "cluster-a"\n'
        '---\n',
        encoding="utf-8",
    )

    meta = parse_frontmatter(note)

    assert meta is not None
    assert meta.title == "Paper"
    assert meta.tags == ["llm", "agents"]
    assert meta.topic_cluster == "cluster-a"


def test_parse_frontmatter_returns_none_for_no_yaml(tmp_path):
    note = tmp_path / "paper.md"
    note.write_text("# No YAML", encoding="utf-8")

    assert parse_frontmatter(note) is None


def test_find_related_in_cluster_filters_by_cluster():
    new_note = NoteMeta(Path("new.md"), "New", ["llm"], "cluster-a")
    notes = [
        NoteMeta(Path("one.md"), "One", ["llm"], "cluster-a"),
        NoteMeta(Path("two.md"), "Two", ["llm"], "cluster-b"),
    ]

    related = find_related_in_cluster(new_note, notes)

    assert [item.slug for item in related] == ["one"]


def test_find_related_in_cluster_ranks_by_tag_overlap():
    new_note = NoteMeta(Path("new.md"), "New", ["llm", "agents"], "cluster-a")
    notes = [
        NoteMeta(Path("one.md"), "One", ["llm"], "cluster-a"),
        NoteMeta(Path("two.md"), "Two", ["llm", "agents"], "cluster-a"),
    ]

    related = find_related_in_cluster(new_note, notes)

    assert [item.slug for item in related] == ["two", "one"]


def test_add_wikilinks_to_note_creates_section(tmp_path):
    note = tmp_path / "paper.md"
    note.write_text("---\ntitle: \"Paper\"\n---\n", encoding="utf-8")

    changed = add_wikilinks_to_note(note, ["other-paper"])

    assert changed is True
    assert "## Related Papers in This Cluster" in note.read_text(encoding="utf-8")


def test_add_wikilinks_to_note_idempotent_update(tmp_path):
    note = tmp_path / "paper.md"
    note.write_text("---\ntitle: \"Paper\"\n---\n", encoding="utf-8")

    add_wikilinks_to_note(note, ["other-paper"])
    changed = add_wikilinks_to_note(note, ["other-paper"])

    assert changed is False


def test_add_wikilinks_filters_nonexistent_slugs(tmp_path):
    """v0.84.0 regression test: when existing_stems is provided, broken
    wikilinks (target file doesn't exist) must not be written. This is
    the safety net against the 2026-05-11 graph-hygiene incident where
    1,199 broken cross-refs were left in the vault after historical slug
    formula divergence between safe_filename and slugify(title)[:60].
    """
    note = tmp_path / "paper.md"
    note.write_text("---\ntitle: \"Paper\"\n---\n", encoding="utf-8")

    # Mix of real (exist in vault) and broken (don't exist) slugs
    existing = {"real-paper-2024", "another-real-2025"}
    add_wikilinks_to_note(
        note,
        ["real-paper-2024", "broken-phantom-2023", "another-real-2025", "ghost-paper-2022"],
        existing_stems=existing,
    )

    content = note.read_text(encoding="utf-8")
    assert "[[real-paper-2024]]" in content
    assert "[[another-real-2025]]" in content
    assert "[[broken-phantom-2023]]" not in content
    assert "[[ghost-paper-2022]]" not in content


def test_add_wikilinks_without_existing_stems_writes_all(tmp_path):
    """Backward compat: when existing_stems is None, write all slugs
    (legacy behavior preserved for callers that don't yet pass the set).
    """
    note = tmp_path / "paper.md"
    note.write_text("---\ntitle: \"Paper\"\n---\n", encoding="utf-8")

    add_wikilinks_to_note(note, ["slug-a", "slug-b"], existing_stems=None)

    content = note.read_text(encoding="utf-8")
    assert "[[slug-a]]" in content
    assert "[[slug-b]]" in content


# ---------------------------------------------------------------------------
# top-10 cap (v1.1.0 quality improvement)
# ---------------------------------------------------------------------------

def test_find_related_caps_at_ten_results():
    """find_related_in_cluster returns at most 10 notes even for large clusters."""
    new_note = NoteMeta(Path("new.md"), "New", ["llm"], "cluster-a")
    # Build 15 sibling notes all in the same cluster.
    siblings = [
        NoteMeta(Path(f"p{i}.md"), f"Paper {i}", ["llm"], "cluster-a")
        for i in range(15)
    ]

    related = find_related_in_cluster(new_note, siblings)

    assert len(related) <= 10


# ---------------------------------------------------------------------------
# remove_paper_links (v1.1.0)
# ---------------------------------------------------------------------------

def _make_cluster_note(path: Path, cluster: str, related_slugs: list[str]) -> None:
    """Write a minimal vault note with a Related Papers section."""
    links = "\n".join(f"- [[{slug}]]" for slug in related_slugs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'---\ntitle: "{path.stem}"\ntopic_cluster: "{cluster}"\n---\n\n'
        f"## Related Papers in This Cluster\n{links}\n",
        encoding="utf-8",
    )


def test_remove_paper_links_scrubs_slug_from_siblings(tmp_path):
    """remove_paper_links must remove the target slug from sibling Related sections."""
    raw = tmp_path / "raw"
    (raw / "cluster-a").mkdir(parents=True)
    _make_cluster_note(raw / "cluster-a" / "paper-a.md", "cluster-a", ["paper-b", "paper-c"])
    _make_cluster_note(raw / "cluster-a" / "paper-c.md", "cluster-a", ["paper-b"])

    modified = remove_paper_links("paper-b", raw, "cluster-a")

    assert modified == 2
    for note_path in [raw / "cluster-a" / "paper-a.md", raw / "cluster-a" / "paper-c.md"]:
        text = note_path.read_text(encoding="utf-8")
        assert "[[paper-b]]" not in text


def test_remove_paper_links_leaves_other_slugs_intact(tmp_path):
    """Only the removed slug is scrubbed; other wikilinks must survive.

    paper-c.md must exist on disk so the v0.84.0 existing_stems safety
    net does not filter it out as a broken wikilink.
    """
    raw = tmp_path / "raw"
    (raw / "cluster-a").mkdir(parents=True)
    _make_cluster_note(raw / "cluster-a" / "paper-a.md", "cluster-a", ["paper-b", "paper-c"])
    # Create the sibling note so its slug survives the existing_stems filter.
    _make_cluster_note(raw / "cluster-a" / "paper-c.md", "cluster-a", [])

    remove_paper_links("paper-b", raw, "cluster-a")

    text = (raw / "cluster-a" / "paper-a.md").read_text(encoding="utf-8")
    assert "[[paper-c]]" in text


def test_remove_paper_links_ignores_other_clusters(tmp_path):
    """Notes in a different cluster must not be modified."""
    raw = tmp_path / "raw"
    (raw / "cluster-a").mkdir(parents=True)
    (raw / "cluster-b").mkdir(parents=True)
    _make_cluster_note(raw / "cluster-a" / "paper-a.md", "cluster-a", ["paper-b"])
    _make_cluster_note(raw / "cluster-b" / "paper-x.md", "cluster-b", ["paper-b"])

    modified = remove_paper_links("paper-b", raw, "cluster-a")

    assert modified == 1
    # cluster-b note untouched
    assert "[[paper-b]]" in (raw / "cluster-b" / "paper-x.md").read_text(encoding="utf-8")


def test_remove_paper_links_returns_zero_when_slug_absent(tmp_path):
    """Returns 0 when no notes reference the given slug."""
    raw = tmp_path / "raw"
    (raw / "cluster-a").mkdir(parents=True)
    _make_cluster_note(raw / "cluster-a" / "paper-a.md", "cluster-a", ["paper-c"])

    modified = remove_paper_links("nonexistent-slug", raw, "cluster-a")

    assert modified == 0


def test_remove_paper_links_removes_entire_section_when_last_slug(tmp_path):
    """When the removed slug was the only entry, the whole Related section is deleted."""
    raw = tmp_path / "raw"
    (raw / "cluster-a").mkdir(parents=True)
    _make_cluster_note(raw / "cluster-a" / "paper-a.md", "cluster-a", ["paper-b"])

    remove_paper_links("paper-b", raw, "cluster-a")

    text = (raw / "cluster-a" / "paper-a.md").read_text(encoding="utf-8")
    assert "## Related Papers in This Cluster" not in text

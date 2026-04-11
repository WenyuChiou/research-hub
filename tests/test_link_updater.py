from __future__ import annotations

from pathlib import Path

from research_hub.vault.link_updater import (
    NoteMeta,
    add_wikilinks_to_note,
    find_related_in_cluster,
    parse_frontmatter,
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

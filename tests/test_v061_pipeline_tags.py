from research_hub.pipeline import _compose_hub_tags


def test_compose_hub_tags_minimum_includes_research_hub():
    # v0.68.4: type/journalArticle is now a default; pipeline always
    # creates that Zotero item type so the tag now matches reality.
    assert _compose_hub_tags({}, None) == ["research-hub", "type/journalArticle"]


def test_compose_hub_tags_with_cluster():
    assert _compose_hub_tags({}, "my-slug") == [
        "research-hub",
        "cluster/my-slug",
        "type/journalArticle",
    ]


def test_compose_hub_tags_full_decoration():
    tags = _compose_hub_tags(
        {"tags": ["existing", "research-hub"], "doc_type": "article", "source": "openalex"},
        "my-slug",
    )

    assert tags == ["existing", "research-hub", "cluster/my-slug", "type/article", "src/openalex"]


def test_compose_hub_tags_dedupes_when_called_twice():
    tags = _compose_hub_tags({"doc_type": "article", "found_in": "crossref"}, "my-slug")
    second = _compose_hub_tags(
        {"tags": tags, "doc_type": "article", "found_in": "crossref"},
        "my-slug",
    )

    assert second == tags

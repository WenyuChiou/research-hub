"""v0.65 Track D3: _compose_hub_tags must not emit cluster/None tags."""

from __future__ import annotations

import pytest

from research_hub.pipeline import _compose_hub_tags


@pytest.mark.parametrize("cluster_slug", [None, "", "   ", "None", "none", "null", "NULL"])
def test_compose_hub_tags_skips_bogus_cluster_slug(cluster_slug):
    """None / empty / whitespace / literal None-strings must NOT produce
    a cluster/<slug> tag. (v0.68.4: type/journalArticle default still
    appears since the pipeline always creates that Zotero item type.)"""
    tags = _compose_hub_tags({}, cluster_slug)
    assert "research-hub" in tags
    assert not any(t.startswith("cluster/") for t in tags), (
        f"cluster_slug={cluster_slug!r} produced a cluster/ tag: {tags}"
    )


def test_compose_hub_tags_real_slug_still_emitted():
    """Regression guard: real slugs must still emit cluster/<slug>."""
    tags = _compose_hub_tags({}, "llm-agents-software-engineering")
    assert "cluster/llm-agents-software-engineering" in tags
    assert "research-hub" in tags


def test_compose_hub_tags_strips_surrounding_whitespace():
    tags = _compose_hub_tags({}, "  my-cluster  ")
    assert "cluster/my-cluster" in tags

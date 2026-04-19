"""v0.39 rebind heuristic chain tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from research_hub.cluster_rebind import _propose_cluster


def _make_cluster(slug, name="", seed_keywords=None, zotero_collection_key=None):
    c = MagicMock()
    c.slug = slug
    c.name = name or slug
    c.seed_keywords = seed_keywords or []
    c.zotero_collection_key = zotero_collection_key
    c.obsidian_subfolder = slug
    return c


def test_h2_topic_cluster_field_matches():
    c = _make_cluster("llm-se")
    by_slug = {"llm-se": c}
    fm = {"topic_cluster": "llm-se"}
    result = _propose_cluster(fm, by_slug, {}, "")
    assert result is not None
    cluster, reason, confidence = result
    assert cluster.slug == "llm-se"
    assert "topic_cluster" in reason
    assert confidence == "high"


def test_h2_topic_cluster_empty_string_does_not_match():
    c = _make_cluster("llm-se")
    by_slug = {"llm-se": c}
    fm = {"topic_cluster": ""}
    result = _propose_cluster(fm, by_slug, {}, "")
    assert result is None


def test_h4_zotero_collection_name_exact_match():
    c = _make_cluster("llm-agents", name="LLM AI Agent")
    by_slug = {"llm-agents": c}
    fm = {"collections": ["LLM AI agent"]}
    result = _propose_cluster(fm, by_slug, {}, "")
    assert result is not None
    cluster, reason, confidence = result
    assert cluster.slug == "llm-agents"
    assert "matches cluster name" in reason
    assert confidence == "high"


def test_h4_zotero_collection_substring_seed_keyword():
    c = _make_cluster("flood-abm", name="Flood ABM", seed_keywords=["flood", "abm", "simulation"])
    by_slug = {"flood-abm": c}
    fm = {"collections": ["Flood-Simulation"]}
    result = _propose_cluster(fm, by_slug, {}, "")
    assert result is not None
    cluster, reason, confidence = result
    assert cluster.slug == "flood-abm"
    assert "shares keyword" in reason
    assert confidence == "medium"


def test_h5_tag_seed_keyword_jaccard_overlap():
    c = _make_cluster("llm-soc", seed_keywords=["llm", "agent", "social", "simulation"])
    by_slug = {"llm-soc": c}
    fm = {"tags": ["research/llm-agent", "research/social"]}
    result = _propose_cluster(fm, by_slug, {}, "")
    assert result is not None
    cluster, reason, confidence = result
    assert cluster.slug == "llm-soc"
    assert "Jaccard" in reason
    assert confidence == "medium"


def test_h5_tag_overlap_below_threshold_returns_none():
    c = _make_cluster("flood-abm", seed_keywords=["flood", "household", "adaptation"])
    by_slug = {"flood-abm": c}
    fm = {"tags": ["research/quantum-computing"]}
    result = _propose_cluster(fm, by_slug, {}, "")
    assert result is None


def test_priority_chain_explicit_wins_over_overlap():
    c1 = _make_cluster("llm-se", seed_keywords=["software", "engineering"])
    c2 = _make_cluster("llm-soc", seed_keywords=["llm", "agent"])
    by_slug = {"llm-se": c1, "llm-soc": c2}
    fm = {"cluster": "llm-se", "tags": ["research/llm-agent"]}
    result = _propose_cluster(fm, by_slug, {}, "")
    assert result is not None
    cluster, reason, confidence = result
    assert cluster.slug == "llm-se"
    assert "cluster" in reason
    assert confidence == "high"


def test_empty_seed_keywords_does_not_crash():
    c = _make_cluster("empty", seed_keywords=[])
    by_slug = {"empty": c}
    fm = {"tags": ["something"]}
    result = _propose_cluster(fm, by_slug, {}, "")
    assert result is None

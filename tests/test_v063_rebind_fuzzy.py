from __future__ import annotations

from unittest.mock import MagicMock

from research_hub.cluster_rebind import _propose_cluster


def _cluster(slug: str, *, seed_keywords: list[str]) -> MagicMock:
    item = MagicMock()
    item.slug = slug
    item.name = slug
    item.seed_keywords = seed_keywords
    item.obsidian_subfolder = slug
    return item


def test_rebind_fuzzy_matches_deleted_slug_to_survivor():
    survivor = _cluster("llm-software-engineering", seed_keywords=["llm", "software", "engineering"])
    result = _propose_cluster({"topic_cluster": "llm-software-engineering-legacy"}, {"llm-software-engineering": survivor}, {}, "")
    assert result is not None
    cluster, reason, confidence = result
    assert cluster.slug == "llm-software-engineering"
    assert reason == "fuzzy(from=llm-software-engineering-legacy)"
    assert confidence == "high"


def test_rebind_fuzzy_requires_min_overlap_of_2():
    survivor = _cluster("llm-software-engineering", seed_keywords=["llm", "software", "engineering"])
    result = _propose_cluster({"topic_cluster": "llm-random"}, {"llm-software-engineering": survivor}, {}, "")
    assert result is None


def test_rebind_fuzzy_bind_logs_reason():
    survivor = _cluster("llm-software-engineering", seed_keywords=["llm", "software", "engineering"])
    result = _propose_cluster({"topic_cluster": "llm-software-engineering-ish"}, {"llm-software-engineering": survivor}, {}, "")
    assert result is not None
    assert result[1] == "fuzzy(from=llm-software-engineering-ish)"


def test_rebind_exact_match_takes_priority_over_fuzzy():
    exact = _cluster("llm-ssweng", seed_keywords=["llm", "software"])
    fuzzy = _cluster("llm-software-engineering", seed_keywords=["llm", "software", "engineering"])
    result = _propose_cluster(
        {"topic_cluster": "llm-ssweng"},
        {"llm-ssweng": exact, "llm-software-engineering": fuzzy},
        {},
        "",
    )
    assert result is not None
    assert result[0].slug == "llm-ssweng"
    assert "topic_cluster" in result[1]

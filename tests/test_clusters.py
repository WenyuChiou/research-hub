from __future__ import annotations

import pytest

pytest.importorskip("yaml")

from research_hub.clusters import ClusterRegistry, slugify


def test_slugify_basic():
    assert slugify("LLM agents in behavioral science") == "llm-agents-behavioral-science"


def test_slugify_strips_stopwords():
    assert slugify("The role of agents in the model") == "role-agents-model"


def test_slugify_caps_at_6_words():
    result = slugify("one two three four five six seven eight")

    assert result == "one-two-three-four-five-six"


def test_cluster_registry_empty_file(tmp_path):
    registry = ClusterRegistry(tmp_path / "clusters.yaml")

    assert registry.list() == []


def test_cluster_registry_create_and_save_roundtrip(tmp_path):
    path = tmp_path / "clusters.yaml"
    registry = ClusterRegistry(path)
    created = registry.create(query="behavioral llm agents", name="Behavioral LLM")

    loaded = ClusterRegistry(path)

    assert loaded.get(created.slug) is not None
    assert loaded.get(created.slug).name == "Behavioral LLM"


def test_cluster_registry_create_returns_existing_on_collision(tmp_path):
    registry = ClusterRegistry(tmp_path / "clusters.yaml")
    first = registry.create(query="same query", slug="same-slug")
    second = registry.create(query="different query", slug="same-slug")

    assert first is second


def test_cluster_registry_match_by_query_overlap(tmp_path):
    registry = ClusterRegistry(tmp_path / "clusters.yaml")
    cluster = registry.create(
        query="llm agents behavioral science",
        seed_keywords=["llm", "agents", "behavioral", "science"],
    )

    match = registry.match_by_query("agents and llm in behavioral economics")

    assert match is not None
    assert match.slug == cluster.slug


def test_cluster_registry_match_by_query_returns_none_on_no_overlap(tmp_path):
    registry = ClusterRegistry(tmp_path / "clusters.yaml")
    registry.create(query="llm agents behavioral science")

    assert registry.match_by_query("coastal flooding insurance premiums") is None

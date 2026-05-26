from __future__ import annotations

from research_hub.vault.hub_overview import derive_moc_links, ensure_moc


def test_ensure_moc_creates_file_when_missing(tmp_path):
    path = ensure_moc(tmp_path, "LLM-Agents", description="LLM agent notes.")

    assert path == tmp_path / "hub" / "_moc" / "LLM-Agents.md"
    text = path.read_text(encoding="utf-8")
    assert "type: moc" in text
    assert "name: LLM-Agents" in text
    assert 'tags: ["topic:llm-agents", "type:moc"]' in text
    assert "# LLM-Agents" in text
    assert "LLM agent notes." in text


def test_ensure_moc_is_idempotent(tmp_path):
    path = ensure_moc(tmp_path, "Water-Resources")
    path.write_text("USER EDIT\n", encoding="utf-8")

    second = ensure_moc(tmp_path, "Water-Resources", description="ignored")

    assert second == path
    assert path.read_text(encoding="utf-8") == "USER EDIT\n"


def test_moc_links_from_llm_and_water_slugs():
    """Each LLM/water cluster gets BOTH a parent MOC (`LLM-Agents`,
    `Water-Resources`) and a per-cluster sub-MOC (e.g.
    `LLM-Agents-Human`). Two-level hub-and-spoke graph view."""
    assert derive_moc_links("human-water-llm") == [
        "LLM-Agents", "LLM-Agents-Human",
        "Water-Resources", "Water-Resources-Human",
    ]
    assert derive_moc_links("flood-water-supply") == [
        "Water-Resources", "Water-Resources-Supply",
    ]
    assert derive_moc_links("social-llm-agents") == [
        "LLM-Agents", "LLM-Agents-Social",
    ]


def test_moc_links_v0885_broader_water_keywords():
    """v0.88.5: clusters about flood / hydrology / rainfall / drought etc.
    surface Water-Resources. Each also gets a per-cluster sub-MOC."""
    assert derive_moc_links("ml-flood-forecasting") == [
        "Water-Resources", "Water-Resources-MlForecasting",
    ]
    assert derive_moc_links("hydrology-data-pipeline") == [
        "Water-Resources", "Water-Resources-DataPipeline",
    ]
    assert derive_moc_links("rainfall-radar-deep-learning") == [
        "Water-Resources", "Water-Resources-DeepLearning",
    ]
    assert derive_moc_links("drought-monitoring") == [
        "Water-Resources", "Water-Resources-Monitoring",
    ]
    assert derive_moc_links("urban-stormwater-modeling") == [
        "Water-Resources", "Water-Resources-UrbanModeling",
    ]
    assert derive_moc_links("reservoir-operation-rl") == [
        "Water-Resources", "Water-Resources-OperationRl",
    ]
    # query text triggers Water-Resources; sub-MOC is derived from SLUG only
    # (so `smart-cities` slug + `drainage` query → Water-Resources-SmartCities)
    assert derive_moc_links(
        "smart-cities", cluster_queries=["urban drainage simulation"]
    ) == ["Water-Resources", "Water-Resources-SmartCities"]


def test_moc_links_v0885_agent_keyword_for_llm_agents():
    """v0.88.5: `agent` as a standalone keyword routes to LLM-Agents."""
    assert "LLM-Agents" in derive_moc_links("multi-agent-systems")
    assert "LLM-Agents" in derive_moc_links(
        "social-simulation", cluster_queries=["generative agent persona modelling"]
    )


def test_sub_moc_per_cluster_creates_visible_sub_hub():
    """Two-level hub-and-spoke: parent MOC + per-cluster sub-MOC.

    Without this, every LLM cluster collapses onto the single `LLM-Agents`
    MOC in Obsidian graph view; with it, each cluster has a distinct
    sub-hub node BETWEEN the parent and the paper notes."""
    # Realistic slugs from production clusters
    flood = derive_moc_links("generative-ai-chatgpt-llm-agents-flood")
    assert flood == ["LLM-Agents", "LLM-Agents-Flood",
                     "Water-Resources", "Water-Resources-Flood"]

    consumer = derive_moc_links("large-language-models-consumer-behavior")
    assert consumer == ["LLM-Agents", "LLM-Agents-ConsumerBehavior"]

    human_nature = derive_moc_links(
        "generative-ai-large-language-models-coupled-human-nature-systems"
    )
    # last 2 distinctive (post-stopword: coupled, human, nature) = HumanNature
    assert human_nature == ["LLM-Agents", "LLM-Agents-HumanNature"]


def test_sub_moc_fallback_when_all_tokens_are_stopwords():
    """If every slug token is a stopword (very LLM/water-heavy slug),
    fall back to the LAST original token so the sub-MOC isn't empty.
    Better to have `LLM-Agents-Llms` than to collapse the cluster onto
    the parent MOC alone."""
    assert derive_moc_links("llm-agents-llms") == [
        "LLM-Agents", "LLM-Agents-Llms",
    ]


def test_sub_moc_explicit_moc_links_pass_through_untouched():
    """Existing `cluster.moc_links` (set by hand in clusters.yaml) flow
    through unchanged — sub-MOC derivation only adds, never strips."""
    out = derive_moc_links(
        "my-cluster",
        moc_links=["MyCustomMOC"],
        cluster_queries=["large language model X"],
    )
    assert "MyCustomMOC" in out
    assert "LLM-Agents" in out
    assert "LLM-Agents-Cluster" in out  # sub from slug "my-cluster" (last non-stopword)

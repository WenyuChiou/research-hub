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
    through unchanged — sub-MOC derivation only adds, never strips.

    Caveat: an explicit name that does NOT match a family prefix
    (`LLM-Agents-*` / `Water-Resources-*`) is treated as an unrelated
    extra MOC; the family's auto sub-MOC still gets added. See
    `test_explicit_sub_moc_suppresses_auto_for_same_family` for the
    suppression rule when the prefix DOES match."""
    out = derive_moc_links(
        "my-cluster",
        moc_links=["MyCustomMOC"],
        cluster_queries=["large language model X"],
    )
    assert "MyCustomMOC" in out
    assert "LLM-Agents" in out
    assert "LLM-Agents-Cluster" in out  # sub from slug "my-cluster" (last non-stopword)


def test_explicit_sub_moc_suppresses_auto_for_same_family():
    """When `cluster.moc_links` contains a name with the parent's
    prefix (`LLM-Agents-*`), the auto-derived slug-based sub-MOC for
    that family is SUPPRESSED. The user-provided name wins.

    Use case: slug like `generative-ai-large-language-models-coupled`
    auto-derives `LLM-Agents-Coupled`, but the actual topic is
    Human-Nature Systems. User sets
    `moc_links: [LLM-Agents-HumanNature]` in clusters.yaml; result
    should be the user's choice + parent, NOT both."""
    out = derive_moc_links(
        "generative-ai-large-language-models-coupled",
        moc_links=["LLM-Agents-HumanNature"],
    )
    assert out == ["LLM-Agents-HumanNature", "LLM-Agents"]
    # Slug-derived `LLM-Agents-Coupled` must NOT appear.
    assert "LLM-Agents-Coupled" not in out


def test_explicit_water_sub_moc_suppresses_auto_for_same_family():
    """Same suppression rule for the Water-Resources family."""
    out = derive_moc_links(
        "ml-flood-forecasting",
        moc_links=["Water-Resources-Floods"],
    )
    assert out == ["Water-Resources-Floods", "Water-Resources"]
    assert "Water-Resources-MlForecasting" not in out


def test_explicit_override_only_suppresses_matching_family():
    """An explicit `LLM-Agents-*` override should NOT suppress the
    auto water sub-MOC, and vice-versa. Each family is independent."""
    # Slug triggers BOTH families; user overrides only LLM.
    out = derive_moc_links(
        "human-water-llm",
        moc_links=["LLM-Agents-Custom"],
    )
    # LLM family: user override wins, no auto sub.
    assert "LLM-Agents-Custom" in out
    assert "LLM-Agents-Human" not in out
    # Water family: auto sub-MOC still derived.
    assert "Water-Resources" in out
    assert "Water-Resources-Human" in out


def test_explicit_override_propagates_to_paper_note_hub_section(tmp_path):
    """Regression: the per-paper Obsidian-note `## Hub` block (written
    by `pipeline._render_obsidian_note`) MUST also honour
    `cluster.moc_links`. Before this test existed, the pipeline call
    site at `pipeline.py:700` only passed `cluster_slug` +
    `cluster_queries` — the override took effect on the cluster
    `00_overview.md` and MOC pages but NOT on the paper notes, so the
    overview said `LLM-Agents-HumanNature` while every paper wikilinked
    to `LLM-Agents-Coupled`. This test pins the fix."""
    from research_hub.pipeline import _render_obsidian_note

    pp = {
        "title": "Test paper on coupled human-nature systems",
        "authors": ["Doe, J."],
        "year": "2026",
        "journal": "Nat. HumanNature",
        "doi": "10.1234/test",
        "abstract": "Coupled human-nature systems are studied with LLMs.",
        "slug": "doe2026-test-paper",
        "tags": [],
        "summary": "",
        "key_findings": [],
        "methodology": "",
        "relevance": "",
    }
    out = _render_obsidian_note(
        pp,
        collection_name="generative-ai-large-language-models-coupled",
        cluster_slug="generative-ai-large-language-models-coupled",
        query="LLM human-nature systems",
        cluster_moc_links=["LLM-Agents-HumanNature"],
    )
    # The override should be wikilinked from the `## Hub` block.
    assert "[[LLM-Agents-HumanNature]]" in out
    # The slug-derived auto sub-MOC must NOT appear.
    assert "[[LLM-Agents-Coupled]]" not in out
    # Parent MOC still present.
    assert "[[LLM-Agents]]" in out

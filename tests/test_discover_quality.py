from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub.search import SearchResult


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    research_hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        raw=raw,
        hub=hub,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def _result(
    title: str,
    doi: str,
    *,
    source: str = "openalex",
    confidence: float = 0.5,
    citation_count: int = 0,
    year: int = 2024,
) -> SearchResult:
    return SearchResult(
        title=title,
        doi=doi,
        authors=["Jane Doe"],
        year=year,
        venue="Venue",
        abstract=f"Abstract for {title}",
        source=source,
        confidence=confidence,
        citation_count=citation_count,
    )


def _write_overview(cfg, cluster: str, definition: str) -> None:
    cluster_dir = cfg.hub / cluster
    cluster_dir.mkdir(parents=True, exist_ok=True)
    (cluster_dir / "00_overview.md").write_text(
        f"# {cluster}\n\n## Definition\n\n{definition}\n",
        encoding="utf-8",
    )


def _write_note(cluster_dir: Path, name: str, doi: str) -> None:
    cluster_dir.mkdir(parents=True, exist_ok=True)
    (cluster_dir / name).write_text(
        f"---\ndoi: {doi}\n---\n\nBody\n",
        encoding="utf-8",
    )


def _read_candidates(cfg, cluster: str) -> list[dict]:
    from research_hub.discover import CANDIDATES_FILENAME, stash_dir

    return json.loads((stash_dir(cfg, cluster) / CANDIDATES_FILENAME).read_text(encoding="utf-8"))


def test_emit_variation_prompt_includes_original_query(tmp_path):
    from research_hub.discover import emit_variation_prompt

    cfg = _cfg(tmp_path)
    prompt = emit_variation_prompt(cfg, "agents", "LLM agent software engineering benchmark")

    assert "LLM agent software engineering benchmark" in prompt


def test_emit_variation_prompt_includes_definition_when_overview_present(tmp_path):
    from research_hub.discover import emit_variation_prompt

    cfg = _cfg(tmp_path)
    _write_overview(cfg, "agents", "Benchmarks and frameworks for LLM agents in software engineering.")

    prompt = emit_variation_prompt(cfg, "agents", "LLM agent software engineering benchmark")

    assert "Benchmarks and frameworks for LLM agents in software engineering." in prompt


def test_emit_variation_prompt_respects_count_parameter(tmp_path):
    from research_hub.discover import emit_variation_prompt

    cfg = _cfg(tmp_path)
    prompt = emit_variation_prompt(cfg, "agents", "query", target_count=2)

    assert "Generate 2 query variations" in prompt


def test_apply_variations_runs_search_for_each(tmp_path, monkeypatch):
    from research_hub.discover import QueryVariation, apply_variations

    cfg = _cfg(tmp_path)
    calls = []

    def fake_search(query, **kwargs):
        calls.append(query)
        return [_result(f"{query} paper", f"10.1/{query.replace(' ', '-')}")]

    monkeypatch.setattr("research_hub.search.search_papers", fake_search)

    apply_variations(
        cfg,
        "agents",
        [QueryVariation("first facet"), QueryVariation("second facet")],
    )

    assert calls == ["first facet", "second facet"]


def test_apply_variations_merges_by_doi_with_confidence_boost(tmp_path, monkeypatch):
    from research_hub.discover import QueryVariation, apply_variations

    cfg = _cfg(tmp_path)

    def fake_search(query, **kwargs):
        return [_result("Shared Paper", "10.1/shared")]

    monkeypatch.setattr("research_hub.search.search_papers", fake_search)

    payload = apply_variations(
        cfg,
        "agents",
        [QueryVariation("facet one"), QueryVariation("facet two")],
    )

    assert len(payload) == 1
    assert payload[0]["confidence"] == pytest.approx(0.6)


def test_apply_variations_tags_matched_variations(tmp_path, monkeypatch):
    from research_hub.discover import QueryVariation, apply_variations

    cfg = _cfg(tmp_path)

    def fake_search(query, **kwargs):
        return [_result("Shared Paper", "10.1/shared")]

    monkeypatch.setattr("research_hub.search.search_papers", fake_search)

    payload = apply_variations(
        cfg,
        "agents",
        [QueryVariation("facet one"), QueryVariation("facet two")],
    )

    assert payload[0]["_discover_meta"]["matched_variations"] == ["facet one", "facet two"]


def test_discover_new_from_variants_file_loads_and_runs_all(tmp_path, monkeypatch):
    from research_hub.discover import discover_new

    cfg = _cfg(tmp_path)
    calls = []
    variations_path = tmp_path / "variations.json"
    variations_path.write_text(
        json.dumps({"variations": [{"query": "facet one"}, {"query": "facet two"}]}),
        encoding="utf-8",
    )

    def fake_search(query, **kwargs):
        calls.append(query)
        return [_result(f"{query} paper", f"10.1/{query.replace(' ', '-')}")]

    monkeypatch.setattr("research_hub.search.search_papers", fake_search)
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "prompt")

    state, _ = discover_new(cfg, "agents", "base query", from_variants=variations_path)

    assert calls == ["base query", "facet one", "facet two"]
    assert state.variations_used == ["facet one", "facet two"]


def test_cli_discover_variants_subcommand_emits_prompt(tmp_path, monkeypatch, capsys):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr(
        "research_hub.discover.emit_variation_prompt",
        lambda cfg, cluster_slug, original_query, target_count=4: f"prompt for {cluster_slug} {original_query} {target_count}",
    )

    assert cli.main(["discover", "variants", "--cluster", "agents", "--query", "base", "--count", "4"]) == 0

    assert "prompt for agents base 4" in capsys.readouterr().out


def test_expand_citations_from_seed_doi_adds_to_pool(tmp_path, monkeypatch):
    from research_hub.discover import discover_new

    cfg = _cfg(tmp_path)

    class FakeClient:
        def get_references(self, seed, limit=30):
            return [SimpleNamespace(title="Ref", doi="10.1/ref", year=2020, authors=["A"], venue="V", citation_count=2, url="u", pdf_url="p")]

        def get_citations(self, seed, limit=30):
            return []

    monkeypatch.setattr("research_hub.search.search_papers", lambda *args, **kwargs: [_result("Base", "10.1/base")])
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "prompt")
    monkeypatch.setattr("research_hub.citation_graph.CitationGraphClient", FakeClient)

    state, _ = discover_new(cfg, "agents", "base", expand_from=("10.1/base",))

    assert state.expanded_from == ["10.1/base"]
    assert {item["doi"] for item in _read_candidates(cfg, "agents")} == {"10.1/base", "10.1/ref"}


def test_expand_auto_picks_top_3_by_confidence_and_citations():
    from research_hub.discover import _pick_auto_seeds

    seeds = _pick_auto_seeds(
        [
            {"doi": "10.1/a", "confidence": 0.5, "citation_count": 50},
            {"doi": "10.1/b", "confidence": 0.9, "citation_count": 10},
            {"doi": "10.1/c", "confidence": 0.9, "citation_count": 40},
            {"doi": "10.1/d", "confidence": 0.7, "citation_count": 100},
        ]
    )

    assert seeds == ["10.1/c", "10.1/b", "10.1/d"]


def test_expand_citations_handles_s2_rate_limit_gracefully(tmp_path, monkeypatch):
    from research_hub.discover import _expand_citations

    class FakeClient:
        def get_references(self, seed, limit=30):
            raise RuntimeError("429")

        def get_citations(self, seed, limit=30):
            raise RuntimeError("429")

    monkeypatch.setattr("research_hub.citation_graph.CitationGraphClient", FakeClient)

    assert _expand_citations(["10.1/base"]) == []


def test_expand_citations_bounded_by_hops_parameter(tmp_path, monkeypatch):
    from research_hub.discover import _expand_citations

    class FakeClient:
        def get_references(self, seed, limit=30):
            return [SimpleNamespace(title="Ref", doi="10.1/ref", year=2020, authors=[], venue="", citation_count=0, url="", pdf_url="")]

        def get_citations(self, seed, limit=30):
            return []

    monkeypatch.setattr("research_hub.citation_graph.CitationGraphClient", FakeClient)

    assert _expand_citations(["10.1/base"], hops=0) == []
    assert len(_expand_citations(["10.1/base"], hops=1)) == 1


def test_expand_citations_dedup_with_keyword_results(tmp_path, monkeypatch):
    from research_hub.discover import discover_new

    cfg = _cfg(tmp_path)

    class FakeClient:
        def get_references(self, seed, limit=30):
            return [SimpleNamespace(title="Base", doi="10.1/base", year=2024, authors=["A"], venue="V", citation_count=5, url="u", pdf_url="p")]

        def get_citations(self, seed, limit=30):
            return []

    monkeypatch.setattr("research_hub.search.search_papers", lambda *args, **kwargs: [_result("Base", "10.1/base", confidence=0.5)])
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "prompt")
    monkeypatch.setattr("research_hub.citation_graph.CitationGraphClient", FakeClient)

    discover_new(cfg, "agents", "base", expand_from=("10.1/base",))
    candidates = _read_candidates(cfg, "agents")

    assert len(candidates) == 1
    assert candidates[0]["confidence"] == pytest.approx(0.6)


def test_expand_citations_tags_source_as_citation_graph(tmp_path, monkeypatch):
    from research_hub.discover import discover_new

    cfg = _cfg(tmp_path)

    class FakeClient:
        def get_references(self, seed, limit=30):
            return [SimpleNamespace(title="Ref", doi="10.1/ref", year=2020, authors=["A"], venue="V", citation_count=2, url="u", pdf_url="p")]

        def get_citations(self, seed, limit=30):
            return []

    monkeypatch.setattr("research_hub.search.search_papers", lambda *args, **kwargs: [_result("Base", "10.1/base")])
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "prompt")
    monkeypatch.setattr("research_hub.citation_graph.CitationGraphClient", FakeClient)

    discover_new(cfg, "agents", "base", expand_from=("10.1/base",))
    extra = [item for item in _read_candidates(cfg, "agents") if item["doi"] == "10.1/ref"][0]

    assert "citation-graph" in extra["_discover_meta"]["source_tags"]


def test_citation_node_to_search_result_conversion():
    from research_hub.discover import _citation_node_to_search_result

    node = SimpleNamespace(
        title="Node",
        doi="10.1/NODE",
        year=2021,
        authors=["A"],
        venue="Venue",
        citation_count=7,
        url="url",
        pdf_url="pdf",
    )
    result = _citation_node_to_search_result(node)

    assert result.doi == "10.1/node"
    assert result.source == "citation-graph"
    assert result.citation_count == 7


def test_discover_new_expand_from_flag_accepts_comma_list(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    captured = {}
    monkeypatch.setattr(cli, "get_config", lambda: cfg)

    def fake_discover_new(cfg, cluster_slug, query, **kwargs):
        captured["expand_from"] = kwargs["expand_from"]
        from research_hub.discover import DiscoverState

        return DiscoverState(cluster_slug=cluster_slug, stage="scored_pending", query=query), "prompt"

    monkeypatch.setattr("research_hub.discover.discover_new", fake_discover_new)

    assert cli.main(
        ["discover", "new", "--cluster", "agents", "--query", "base", "--expand-from", "10.1/a,10.1/b", "--prompt-out", str(tmp_path / "prompt.md")]
    ) == 0

    assert captured["expand_from"] == ("10.1/a", "10.1/b")


def test_load_cluster_doi_set_reads_paper_frontmatter(tmp_path):
    from research_hub.discover import _load_cluster_doi_set

    cfg = _cfg(tmp_path)
    _write_note(cfg.raw / "agents", "paper.md", "10.1/abc")

    assert _load_cluster_doi_set(cfg, "agents") == {"10.1/abc"}


def test_load_cluster_doi_set_normalizes_dois(tmp_path):
    from research_hub.discover import _load_cluster_doi_set

    cfg = _cfg(tmp_path)
    _write_note(cfg.raw / "agents", "paper.md", "10.1/AbC")

    assert _load_cluster_doi_set(cfg, "agents") == {"10.1/abc"}


def test_cluster_dedup_removes_existing_papers_from_candidates(tmp_path, monkeypatch):
    from research_hub.discover import discover_new

    cfg = _cfg(tmp_path)
    _write_note(cfg.raw / "agents", "paper.md", "10.1/base")
    monkeypatch.setattr("research_hub.search.search_papers", lambda *args, **kwargs: [_result("Base", "10.1/base"), _result("New", "10.1/new")])
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "prompt")

    state, _ = discover_new(cfg, "agents", "base")

    assert state.candidate_count == 1
    assert _read_candidates(cfg, "agents")[0]["doi"] == "10.1/new"


def test_cluster_dedup_count_tracked_in_state(tmp_path, monkeypatch):
    from research_hub.discover import discover_new

    cfg = _cfg(tmp_path)
    _write_note(cfg.raw / "agents", "paper.md", "10.1/base")
    monkeypatch.setattr("research_hub.search.search_papers", lambda *args, **kwargs: [_result("Base", "10.1/base"), _result("New", "10.1/new")])
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "prompt")

    state, _ = discover_new(cfg, "agents", "base")

    assert state.deduped_against_cluster == 1


def test_include_existing_flag_bypasses_dedup(tmp_path, monkeypatch):
    from research_hub.discover import discover_new

    cfg = _cfg(tmp_path)
    _write_note(cfg.raw / "agents", "paper.md", "10.1/base")
    monkeypatch.setattr("research_hub.search.search_papers", lambda *args, **kwargs: [_result("Base", "10.1/base")])
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "prompt")

    state, _ = discover_new(cfg, "agents", "base", include_existing=True)

    assert state.candidate_count == 1
    assert state.deduped_against_cluster == 0


def test_cluster_dedup_empty_cluster_keeps_all_candidates(tmp_path, monkeypatch):
    from research_hub.discover import discover_new

    cfg = _cfg(tmp_path)
    monkeypatch.setattr("research_hub.search.search_papers", lambda *args, **kwargs: [_result("Base", "10.1/base"), _result("New", "10.1/new")])
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "prompt")

    state, _ = discover_new(cfg, "agents", "base")

    assert state.candidate_count == 2


def test_resolve_seed_dois_via_enrich_candidates(tmp_path, monkeypatch):
    from research_hub.discover import _resolve_seed_dois

    calls = {}

    def fake_enrich(candidates, backends=()):
        calls["candidates"] = list(candidates)
        return [_result("Seed", "10.1/seed")]

    monkeypatch.setattr("research_hub.search.enrich_candidates", fake_enrich)
    payload = _resolve_seed_dois(["10.1/seed"], [])

    assert calls["candidates"] == ["10.1/seed"]
    assert payload[0]["doi"] == "10.1/seed"


def test_resolve_seed_dois_boosts_confidence_when_already_in_results():
    from research_hub.discover import _resolve_seed_dois

    existing = [{"title": "Seed", "doi": "10.1/seed", "confidence": 0.5, "_discover_meta": {"matched_variations": [], "source_tags": [], "is_seed": False}}]
    payload = _resolve_seed_dois(["10.1/seed"], existing)

    assert payload[0]["confidence"] == pytest.approx(0.75)
    assert payload[0]["_discover_meta"]["is_seed"] is True


def test_resolve_seed_dois_adds_missing_papers(tmp_path, monkeypatch):
    from research_hub.discover import _resolve_seed_dois

    monkeypatch.setattr("research_hub.search.enrich_candidates", lambda *args, **kwargs: [_result("Seed", "10.1/seed")])
    payload = _resolve_seed_dois(["10.1/seed"], [])

    assert payload[0]["confidence"] == 1.0


def test_seed_dois_file_reads_one_per_line(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    seed_file = tmp_path / "seeds.txt"
    seed_file.write_text("# comment\n10.1/a\n10.1/b\n", encoding="utf-8")
    captured = {}
    monkeypatch.setattr(cli, "get_config", lambda: cfg)

    def fake_discover_new(cfg, cluster_slug, query, **kwargs):
        captured["seed_dois"] = kwargs["seed_dois"]
        from research_hub.discover import DiscoverState

        return DiscoverState(cluster_slug=cluster_slug, stage="scored_pending", query=query), "prompt"

    monkeypatch.setattr("research_hub.discover.discover_new", fake_discover_new)

    assert cli.main(
        ["discover", "new", "--cluster", "agents", "--query", "base", "--seed-dois-file", str(seed_file), "--prompt-out", str(tmp_path / "prompt.md")]
    ) == 0

    assert captured["seed_dois"] == ("10.1/a", "10.1/b")


def test_seed_dois_tags_source_as_seed(tmp_path, monkeypatch):
    from research_hub.discover import _resolve_seed_dois

    monkeypatch.setattr("research_hub.search.enrich_candidates", lambda *args, **kwargs: [_result("Seed", "10.1/seed")])
    payload = _resolve_seed_dois(["10.1/seed"], [])

    assert payload[0]["_discover_meta"]["source_tags"] == ["seed"]


def test_seed_dois_skip_invalid_dois_gracefully(tmp_path, monkeypatch):
    from research_hub.discover import _resolve_seed_dois

    monkeypatch.setattr("research_hub.search.enrich_candidates", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not fetch")))

    assert _resolve_seed_dois(["not-a-doi"], []) == []


def test_seed_dois_state_tracks_list(tmp_path, monkeypatch):
    from research_hub.discover import discover_new

    cfg = _cfg(tmp_path)
    monkeypatch.setattr("research_hub.search.search_papers", lambda *args, **kwargs: [])
    monkeypatch.setattr("research_hub.search.enrich_candidates", lambda *args, **kwargs: [_result("Seed", "10.1/seed")])
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "prompt")

    state, _ = discover_new(cfg, "agents", "base", seed_dois=("10.1/seed",))

    assert state.seed_dois == ["10.1/seed"]


def test_default_limit_is_50():
    from research_hub import discover

    assert discover._DEFAULT_LIMIT == 50


def test_over_fetch_limit_is_max_limit_times_3_or_40(tmp_path, monkeypatch):
    from research_hub.discover import discover_new

    cfg = _cfg(tmp_path)
    captured = {}

    def fake_search(query, **kwargs):
        captured["per_backend_limit"] = kwargs["per_backend_limit"]
        return []

    monkeypatch.setattr("research_hub.search.search_papers", fake_search)
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "prompt")

    discover_new(cfg, "agents", "base", limit=10)

    assert captured["per_backend_limit"] == 40


def test_discover_new_limit_flag_overrides_default(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    captured = {}
    monkeypatch.setattr(cli, "get_config", lambda: cfg)

    def fake_discover_new(cfg, cluster_slug, query, **kwargs):
        captured["limit"] = kwargs["limit"]
        from research_hub.discover import DiscoverState

        return DiscoverState(cluster_slug=cluster_slug, stage="scored_pending", query=query), "prompt"

    monkeypatch.setattr("research_hub.discover.discover_new", fake_discover_new)

    assert cli.main(
        ["discover", "new", "--cluster", "agents", "--query", "base", "--limit", "100", "--prompt-out", str(tmp_path / "prompt.md")]
    ) == 0

    assert captured["limit"] == 100


def test_state_tracks_all_new_v021_counts(tmp_path, monkeypatch):
    from research_hub.discover import discover_new

    cfg = _cfg(tmp_path)
    _write_note(cfg.raw / "agents", "paper.md", "10.1/base")

    class FakeClient:
        def get_references(self, seed, limit=30):
            return [SimpleNamespace(title="Ref", doi="10.1/ref", year=2020, authors=["A"], venue="V", citation_count=1, url="u", pdf_url="p")]

        def get_citations(self, seed, limit=30):
            return []

    def fake_search(query, **kwargs):
        if query == "base":
            return [_result("Base", "10.1/base", confidence=0.9, citation_count=10), _result("Other", "10.1/other")]
        return [_result("Var", "10.1/var")]

    variations_path = tmp_path / "variations.json"
    variations_path.write_text(json.dumps({"variations": [{"query": "facet"}]}), encoding="utf-8")
    monkeypatch.setattr("research_hub.search.search_papers", fake_search)
    monkeypatch.setattr("research_hub.search.enrich_candidates", lambda *args, **kwargs: [_result("Seed", "10.1/seed")])
    monkeypatch.setattr("research_hub.citation_graph.CitationGraphClient", FakeClient)
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "prompt")

    state, _ = discover_new(
        cfg,
        "agents",
        "base",
        from_variants=variations_path,
        expand_auto=True,
        seed_dois=("10.1/seed",),
    )

    assert state.variations_used == ["facet"]
    assert state.expanded_from == ["10.1/base", "10.1/other", "10.1/var"][: len(state.expanded_from)]
    assert state.seed_dois == ["10.1/seed"]
    assert state.deduped_against_cluster == 1


def test_full_flow_multi_query_plus_expansion_plus_seed(tmp_path, monkeypatch):
    from research_hub.discover import discover_new

    cfg = _cfg(tmp_path)

    class FakeClient:
        def get_references(self, seed, limit=30):
            return [SimpleNamespace(title="Ref", doi="10.1/ref", year=2020, authors=["A"], venue="V", citation_count=1, url="u", pdf_url="p")]

        def get_citations(self, seed, limit=30):
            return []

    def fake_search(query, **kwargs):
        if query == "base":
            return [_result("Base", "10.1/base", confidence=0.9, citation_count=5)]
        return [_result("Variant", "10.1/variant")]

    variations_path = tmp_path / "variations.json"
    variations_path.write_text(json.dumps({"variations": [{"query": "facet"}]}), encoding="utf-8")
    monkeypatch.setattr("research_hub.search.search_papers", fake_search)
    monkeypatch.setattr("research_hub.search.enrich_candidates", lambda *args, **kwargs: [_result("Seed", "10.1/seed")])
    monkeypatch.setattr("research_hub.citation_graph.CitationGraphClient", FakeClient)
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "prompt")

    state, _ = discover_new(
        cfg,
        "agents",
        "base",
        from_variants=variations_path,
        expand_auto=True,
        seed_dois=("10.1/seed",),
    )
    dois = {item["doi"] for item in _read_candidates(cfg, "agents")}

    assert state.candidate_count == 4
    assert dois == {"10.1/base", "10.1/variant", "10.1/ref", "10.1/seed"}


def test_from_json_tolerates_old_state_missing_v021_fields():
    from research_hub.discover import DiscoverState

    state = DiscoverState.from_json(
        json.dumps(
            {
                "cluster_slug": "agents",
                "stage": "scored_pending",
                "query": "base",
            }
        )
    )

    assert state.variations_used == []
    assert state.expanded_from == []
    assert state.seed_dois == []
    assert state.deduped_against_cluster == 0

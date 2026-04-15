from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from research_hub.cli import main
from research_hub.clusters import ClusterRegistry
from tests._mcp_helpers import _get_mcp_tool


@dataclass
class _Cfg:
    root: Path
    raw: Path
    research_hub_dir: Path
    clusters_file: Path


def _make_cfg(tmp_path: Path) -> _Cfg:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub_dir = root / ".research_hub"
    raw.mkdir(parents=True, exist_ok=True)
    hub_dir.mkdir(parents=True, exist_ok=True)
    return _Cfg(root=root, raw=raw, research_hub_dir=hub_dir, clusters_file=hub_dir / "clusters.yaml")


def _seed_cluster(tmp_path: Path, slug: str, papers: list[tuple[str, str, str]]) -> _Cfg:
    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query=slug, name=slug.title(), slug=slug)
    cluster_dir = cfg.raw / slug
    cluster_dir.mkdir(parents=True, exist_ok=True)
    for paper_slug, doi, title in papers:
        (cluster_dir / f"{paper_slug}.md").write_text(
            f'---\ntitle: "{title}"\ndoi: "{doi}"\ntopic_cluster: {slug}\n---\n\n## Abstract\nFake\n',
            encoding="utf-8",
        )
    return cfg


def test_build_graph_with_mocked_references(tmp_path, monkeypatch):
    cfg = _seed_cluster(
        tmp_path,
        "my-cluster",
        [
            ("paper-a", "10.1/a", "Paper A"),
            ("paper-b", "10.1/b", "Paper B"),
            ("paper-c", "10.1/c", "Paper C"),
        ],
    )

    def fake_refs(_cfg, _cluster_slug, paper):
        return {
            "paper-a": ["10.1/r1", "10.1/r2"],
            "paper-b": ["10.1/r1", "10.1/r2", "10.1/r3"],
            "paper-c": ["10.1/r3", "10.1/r4"],
        }[paper["slug"]]

    monkeypatch.setattr("research_hub.analyze._fetch_references", fake_refs)

    from research_hub.analyze import build_intra_cluster_citation_graph

    graph = build_intra_cluster_citation_graph(cfg, "my-cluster")
    assert len(graph.nodes) == 3
    assert graph.has_edge("paper-a", "paper-b")
    assert graph.has_edge("paper-b", "paper-c")
    assert not graph.has_edge("paper-a", "paper-c")
    assert graph.edges["paper-a", "paper-b"]["weight"] == 2


def test_suggest_split_produces_communities(tmp_path, monkeypatch):
    cfg = _seed_cluster(
        tmp_path,
        "agents",
        [
            ("paper-a", "10.1/a", "Agent Planning Systems"),
            ("paper-b", "10.1/b", "Agent Planning Benchmarks"),
            ("paper-c", "10.1/c", "Coding Agent Tool Use"),
            ("paper-d", "10.1/d", "Coding Agent Repositories"),
        ],
    )

    def fake_refs(_cfg, _cluster_slug, paper):
        return {
            "paper-a": ["10.1/r1", "10.1/r2"],
            "paper-b": ["10.1/r1", "10.1/r3"],
            "paper-c": ["10.1/r8", "10.1/r9"],
            "paper-d": ["10.1/r8", "10.1/r10"],
        }[paper["slug"]]

    monkeypatch.setattr("research_hub.analyze._fetch_references", fake_refs)

    from research_hub.analyze import suggest_split

    suggestion = suggest_split(cfg, "agents", min_community_size=2, max_communities=8)
    assert suggestion.community_count == 2
    assert suggestion.paper_count == 4
    assert suggestion.modularity_score > 0
    member_sets = {frozenset(item.member_slugs) for item in suggestion.communities}
    assert member_sets == {frozenset({"paper-a", "paper-b"}), frozenset({"paper-c", "paper-d"})}


def test_suggest_split_min_community_size_respected(tmp_path, monkeypatch):
    cfg = _seed_cluster(
        tmp_path,
        "agents",
        [
            ("paper-a", "10.1/a", "Agent Planning Systems"),
            ("paper-b", "10.1/b", "Agent Planning Benchmarks"),
            ("paper-c", "10.1/c", "Coding Agent Tool Use"),
        ],
    )

    def fake_refs(_cfg, _cluster_slug, paper):
        return {
            "paper-a": ["10.1/r1"],
            "paper-b": ["10.1/r1"],
            "paper-c": ["10.1/r9"],
        }[paper["slug"]]

    monkeypatch.setattr("research_hub.analyze._fetch_references", fake_refs)

    from research_hub.analyze import suggest_split

    suggestion = suggest_split(cfg, "agents", min_community_size=2, max_communities=8)
    assert suggestion.community_count == 1
    assert suggestion.communities[0].member_slugs == ["paper-a", "paper-b"]


def test_suggest_split_empty_citation_graph_returns_single_community(tmp_path, monkeypatch):
    cfg = _seed_cluster(
        tmp_path,
        "agents",
        [
            ("paper-a", "10.1/a", "Paper A"),
            ("paper-b", "10.1/b", "Paper B"),
        ],
    )
    monkeypatch.setattr("research_hub.analyze._fetch_references", lambda *_args, **_kwargs: [])

    from research_hub.analyze import suggest_split

    suggestion = suggest_split(cfg, "agents")
    assert suggestion.community_count == 1
    assert suggestion.communities[0].slug == "cluster"
    assert suggestion.communities[0].member_slugs == ["paper-a", "paper-b"]


def test_citation_cache_prevents_double_fetch(tmp_path, monkeypatch):
    cfg = _seed_cluster(tmp_path, "agents", [("paper-a", "10.1/a", "Paper A")])
    calls: list[str] = []

    class _Node:
        def __init__(self, doi: str) -> None:
            self.doi = doi

    class _Client:
        def get_references(self, doi: str):
            calls.append(doi)
            return [_Node("10.1/r1")]

    monkeypatch.setattr("research_hub.citation_graph.CitationGraphClient", lambda: _Client())

    from research_hub.analyze import _fetch_references

    assert _fetch_references(cfg, "agents", {"slug": "paper-a", "doi": "10.1/a"}) == ["10.1/r1"]
    assert _fetch_references(cfg, "agents", {"slug": "paper-a", "doi": "10.1/a"}) == ["10.1/r1"]
    assert calls == ["10.1/a"]


def test_compute_subtopic_name_picks_distinctive_terms():
    from research_hub.analyze import _compute_subtopic_name

    slug, title = _compute_subtopic_name(
        ["Agent Planning for Software Tasks", "Interactive Agent Planning Systems"],
        [
            "Agent Planning for Software Tasks",
            "Interactive Agent Planning Systems",
            "Robot Navigation Learning",
        ],
    )
    assert slug == "agent-planning"
    assert title == "Agent Planning"


def test_render_split_suggestion_markdown_contains_all_communities():
    from research_hub.analyze import CommunityProposal, SplitSuggestion, render_split_suggestion_markdown

    suggestion = SplitSuggestion(
        cluster_slug="agents",
        paper_count=4,
        community_count=2,
        modularity_score=0.42,
        coverage_fraction=0.75,
        rate_limited=False,
        communities=[
            CommunityProposal("planning", "Planning", ["paper-a", "paper-b"], ["10.1/r1"], 0.0),
            CommunityProposal("coding", "Coding", ["paper-c", "paper-d"], ["10.1/r8"], 0.0),
        ],
    )

    rendered = render_split_suggestion_markdown(suggestion)
    assert "### 01. Planning (`planning`)" in rendered
    assert "### 02. Coding (`coding`)" in rendered
    payload = json.loads(rendered.split("```json\n", 1)[1].split("\n```", 1)[0])
    assert payload["assignments"]["paper-a"] == ["planning"]
    assert payload["assignments"]["paper-d"] == ["coding"]


def test_cli_clusters_analyze_writes_markdown_report(tmp_path, monkeypatch, capsys):
    cfg = _seed_cluster(tmp_path, "agents", [("paper-a", "10.1/a", "Paper A")])

    from research_hub.analyze import CommunityProposal, SplitSuggestion

    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    monkeypatch.setattr(
        "research_hub.analyze.suggest_split",
        lambda *_args, **_kwargs: SplitSuggestion(
            cluster_slug="agents",
            paper_count=1,
            community_count=1,
            modularity_score=0.0,
            coverage_fraction=1.0,
            rate_limited=False,
            communities=[CommunityProposal("cluster", "Cluster", ["paper-a"], [], 0.0)],
        ),
    )

    out = tmp_path / "report.md"
    assert main(["clusters", "analyze", "--cluster", "agents", "--split-suggestion", "--out", str(out)]) == 0
    stdout = capsys.readouterr().out
    assert "Analyzed 1 papers -> 1 communities" in stdout
    assert out.exists()
    assert "# Cluster split suggestion - agents" in out.read_text(encoding="utf-8")


def test_cli_clusters_analyze_requires_analysis_flag(tmp_path, monkeypatch, capsys):
    cfg = _seed_cluster(tmp_path, "agents", [("paper-a", "10.1/a", "Paper A")])
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    assert main(["clusters", "analyze", "--cluster", "agents"]) == 0
    assert "--split-suggestion" in capsys.readouterr().out


def test_mcp_suggest_cluster_split_returns_dict(tmp_path, monkeypatch):
    cfg = _seed_cluster(tmp_path, "agents", [("paper-a", "10.1/a", "Paper A")])
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)

    from research_hub.analyze import CommunityProposal, SplitSuggestion
    from research_hub.mcp_server import mcp

    monkeypatch.setattr(
        "research_hub.analyze.suggest_split",
        lambda *_args, **_kwargs: SplitSuggestion(
            cluster_slug="agents",
            paper_count=1,
            community_count=1,
            modularity_score=0.0,
            coverage_fraction=1.0,
            rate_limited=False,
            communities=[CommunityProposal("cluster", "Cluster", ["paper-a"], [], 0.0)],
        ),
    )

    tool = _get_mcp_tool(mcp, "suggest_cluster_split")
    result = tool.fn("agents")
    assert result["cluster_slug"] == "agents"
    assert result["communities"][0]["member_slugs"] == ["paper-a"]


def test_rate_limited_warning_emitted_below_50pct_coverage():
    from research_hub.analyze import CommunityProposal, SplitSuggestion, render_split_suggestion_markdown

    rendered = render_split_suggestion_markdown(
        SplitSuggestion(
            cluster_slug="agents",
            paper_count=4,
            community_count=1,
            modularity_score=0.0,
            coverage_fraction=0.25,
            rate_limited=True,
            communities=[CommunityProposal("cluster", "Cluster", ["paper-a"], [], 0.0)],
        )
    )
    assert "**Warning:** citation data coverage below 50%" in rendered


def test_read_cluster_papers_skips_non_markdown_and_uses_frontmatter(tmp_path):
    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    cluster_dir = cfg.raw / "agents"
    cluster_dir.mkdir(parents=True, exist_ok=True)
    (cluster_dir / "00_overview.md").write_text(
        "---\ntitle: Overview\ntopic_cluster: agents\n---\n",
        encoding="utf-8",
    )
    (cluster_dir / "paper-a.md").write_text(
        '---\ntitle: "Paper A"\ndoi: "10.1/A"\ntopic_cluster: agents\n---\n',
        encoding="utf-8",
    )

    from research_hub.analyze import _read_cluster_papers

    assert _read_cluster_papers(cfg, "agents") == [
        {"slug": "paper-a", "doi": "10.1/a", "title": "Paper A"}
    ]

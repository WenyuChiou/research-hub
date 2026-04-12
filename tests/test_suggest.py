from __future__ import annotations

from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.dedup import DedupHit, DedupIndex, normalize_doi, normalize_title
from research_hub.suggest import PaperInput, suggest_cluster_for_paper, suggest_related_papers


def make_dedup_with(hits: list[dict]) -> DedupIndex:
    """Build a DedupIndex from a list of hit dictionaries."""
    index = DedupIndex()
    for item in hits:
        hit = DedupHit(
            source=item["source"],
            doi=item.get("doi", ""),
            title=item.get("title", ""),
            zotero_key=item.get("zotero_key"),
            obsidian_path=item.get("obsidian_path"),
        )
        if hit.doi:
            index.doi_to_hits.setdefault(normalize_doi(hit.doi), []).append(hit)
        if hit.title:
            index.title_to_hits.setdefault(normalize_title(hit.title), []).append(hit)
    return index


def write_note(
    path: Path,
    *,
    title: str,
    doi: str = "",
    tags: list[str] | None = None,
    authors: list[str] | None = None,
    topic_cluster: str = "",
    journal: str = "",
) -> Path:
    tags = tags or []
    authors = authors or []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                f'title: "{title}"',
                f'doi: "{doi}"',
                "tags: [" + ", ".join(f'"{tag}"' for tag in tags) + "]",
                "authors: [" + ", ".join(f'"{author}"' for author in authors) + "]",
                f'topic_cluster: "{topic_cluster}"',
                f'journal: "{journal}"',
                "---",
                "",
                "body",
            ]
        ),
        encoding="utf-8",
    )
    return path


def make_registry(tmp_path: Path, clusters: dict[str, dict]) -> ClusterRegistry:
    import yaml

    clusters_file = tmp_path / "clusters.yaml"
    clusters_file.write_text(yaml.safe_dump({"clusters": clusters}, sort_keys=False), encoding="utf-8")
    return ClusterRegistry(clusters_file)


def test_suggest_cluster_empty_registry(tmp_path: Path):
    registry = make_registry(tmp_path, {})
    result = suggest_cluster_for_paper(PaperInput(title="llm agent flood decision"), registry, DedupIndex())
    assert result == []


def test_suggest_cluster_single_seed_match(tmp_path: Path):
    registry = make_registry(
        tmp_path,
        {
            "agents": {"name": "Agents", "seed_keywords": ["agent", "simulation"]},
        },
    )
    result = suggest_cluster_for_paper(PaperInput(title="Agent approaches for flood response"), registry, DedupIndex())
    assert result[0].score > 0
    assert any("matches seed keyword" in reason for reason in result[0].reasons)


def test_suggest_cluster_multi_signal(tmp_path: Path):
    note = write_note(
        tmp_path / "raw" / "paper-a.md",
        title="LLM agent planning for rivers",
        doi="10.1000/a",
        tags=["flood", "llm", "adaptation"],
        authors=["Wen-Yu Chang", "A. Smith"],
        topic_cluster="flood-agents",
        journal="Nature Climate Change",
    )
    registry = make_registry(
        tmp_path,
        {
            "flood-agents": {"name": "Flood Agents", "seed_keywords": ["llm", "agent", "flood"]},
        },
    )
    dedup = make_dedup_with(
        [{"source": "obsidian", "doi": "10.1000/a", "title": "LLM agent planning for rivers", "obsidian_path": str(note)}]
    )
    paper = PaperInput(
        title="LLM agent support for flood adaptation",
        authors=["W. Chang"],
        venue="Nature Climate Change",
        tags=["llm", "flood"],
    )
    result = suggest_cluster_for_paper(paper, registry, dedup)
    assert result[0].cluster_slug == "flood-agents"
    assert result[0].score > 50


def test_suggest_cluster_top_n_limit(tmp_path: Path):
    registry = make_registry(
        tmp_path,
        {
            f"cluster-{idx}": {"name": f"Cluster {idx}", "seed_keywords": [f"term{idx}"]}
            for idx in range(5)
        },
    )
    result = suggest_cluster_for_paper(PaperInput(title="term1 term2 term3"), registry, DedupIndex(), top_n=2)
    assert len(result) == 2


def test_suggest_cluster_deterministic_ties(tmp_path: Path):
    registry = make_registry(
        tmp_path,
        {
            "alpha": {"name": "Alpha", "seed_keywords": ["agent"]},
            "beta": {"name": "Beta", "seed_keywords": ["agent"]},
        },
    )
    result = suggest_cluster_for_paper(PaperInput(title="agent systems"), registry, DedupIndex(), top_n=2)
    assert [item.cluster_slug for item in result] == ["alpha", "beta"]


def test_suggest_related_papers_filters_self(tmp_path: Path):
    note = write_note(tmp_path / "raw" / "same.md", title="Same", doi="10.1000/self")
    registry = make_registry(tmp_path, {})
    dedup = make_dedup_with(
        [{"source": "obsidian", "doi": "10.1000/self", "title": "Same", "obsidian_path": str(note)}]
    )
    result = suggest_related_papers(PaperInput(title="Same", doi="10.1000/self"), dedup, registry)
    assert result == []


def test_suggest_related_papers_same_cluster_scores_high(tmp_path: Path):
    note_a = write_note(
        tmp_path / "raw" / "a.md",
        title="LLM flood planning systems",
        doi="10.1000/a",
        tags=["flood"],
        authors=["Jane Chang"],
        topic_cluster="flood-agents",
    )
    note_b = write_note(
        tmp_path / "raw" / "b.md",
        title="Coastal erosion monitoring",
        doi="10.1000/b",
        tags=["coast"],
        authors=["Pat Lee"],
        topic_cluster="coast",
    )
    registry = make_registry(
        tmp_path,
        {
            "flood-agents": {"name": "Flood Agents", "seed_keywords": ["llm", "flood"]},
            "coast": {"name": "Coast", "seed_keywords": ["coastal"]},
        },
    )
    dedup = make_dedup_with(
        [
            {"source": "obsidian", "doi": "10.1000/a", "title": "LLM flood planning systems", "obsidian_path": str(note_a)},
            {"source": "obsidian", "doi": "10.1000/b", "title": "Coastal erosion monitoring", "obsidian_path": str(note_b)},
        ]
    )
    result = suggest_related_papers(
        PaperInput(title="LLM tools for flood adaptation", tags=["flood"]),
        dedup,
        registry,
        top_n=2,
    )
    assert result[0].doi == "10.1000/a"
    assert result[0].score > result[1].score


def test_suggest_related_papers_author_surname_overlap(tmp_path: Path):
    note = write_note(
        tmp_path / "raw" / "author.md",
        title="Adaptive flood systems",
        doi="10.1000/a",
        authors=["Wen-Yu Chang"],
    )
    registry = make_registry(tmp_path, {})
    dedup = make_dedup_with(
        [{"source": "obsidian", "doi": "10.1000/a", "title": "Adaptive flood systems", "obsidian_path": str(note)}]
    )
    result = suggest_related_papers(
        PaperInput(title="Decision support", authors=["W. Chang"]),
        dedup,
        registry,
    )
    assert any("shared author" in reason for reason in result[0].reasons)


def test_suggest_related_papers_venue_match(tmp_path: Path):
    note = write_note(
        tmp_path / "raw" / "venue.md",
        title="Adaptive flood systems",
        doi="10.1000/a",
        journal="Nature Climate Change",
    )
    registry = make_registry(tmp_path, {})
    dedup = make_dedup_with(
        [{"source": "obsidian", "doi": "10.1000/a", "title": "Adaptive flood systems", "obsidian_path": str(note)}]
    )
    result = suggest_related_papers(
        PaperInput(title="Decision support", venue="Nature Climate Change"),
        dedup,
        registry,
    )
    assert result[0].score >= 10


def test_suggest_related_papers_title_keyword_overlap(tmp_path: Path):
    note = write_note(
        tmp_path / "raw" / "title.md",
        title="Flood adaptation with agent systems",
        doi="10.1000/a",
    )
    registry = make_registry(tmp_path, {})
    dedup = make_dedup_with(
        [{"source": "obsidian", "doi": "10.1000/a", "title": "Flood adaptation with agent systems", "obsidian_path": str(note)}]
    )
    result = suggest_related_papers(
        PaperInput(title="Agent systems for flood response"),
        dedup,
        registry,
    )
    assert result[0].score > 0
    assert any("title overlap" in reason for reason in result[0].reasons)


def test_suggest_related_papers_top_n_limit(tmp_path: Path):
    registry = make_registry(tmp_path, {})
    hits = []
    for idx in range(20):
        note = write_note(tmp_path / "raw" / f"note-{idx}.md", title=f"Flood agent {idx}", doi=f"10.1000/{idx}")
        hits.append({"source": "obsidian", "doi": f"10.1000/{idx}", "title": f"Flood agent {idx}", "obsidian_path": str(note)})
    dedup = make_dedup_with(hits)
    result = suggest_related_papers(PaperInput(title="Flood agent systems"), dedup, registry, top_n=5)
    assert len(result) == 5


def test_suggest_reasons_are_non_empty(tmp_path: Path):
    cluster_note = write_note(
        tmp_path / "raw" / "cluster.md",
        title="LLM agent flood planning",
        doi="10.1000/a",
        tags=["llm"],
        authors=["Jane Chang"],
        topic_cluster="flood-agents",
        journal="Nature Climate Change",
    )
    registry = make_registry(
        tmp_path,
        {
            "flood-agents": {"name": "Flood Agents", "seed_keywords": ["llm", "agent", "flood"]},
        },
    )
    dedup = make_dedup_with(
        [{"source": "obsidian", "doi": "10.1000/a", "title": "LLM agent flood planning", "obsidian_path": str(cluster_note)}]
    )
    paper = PaperInput(
        title="LLM agent support for flood adaptation",
        authors=["W. Chang"],
        venue="Nature Climate Change",
        tags=["llm"],
    )
    cluster_result = suggest_cluster_for_paper(paper, registry, dedup)
    related_result = suggest_related_papers(paper, dedup, registry)
    assert all(item.reasons for item in cluster_result)
    assert all(item.reasons for item in related_result)

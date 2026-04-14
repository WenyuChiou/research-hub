from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from research_hub.clusters import ClusterRegistry


@dataclass
class StressCfg:
    root: Path
    raw: Path
    hub: Path
    research_hub_dir: Path
    clusters_file: Path
    logs: Path
    no_zotero: bool = True
    zotero_default_collection: str | None = None
    zotero_collections: dict[str, dict[str, str]] | None = None
    zotero_library_id: str | None = None


def make_stress_cfg(tmp_path: Path) -> StressCfg:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "research_hub" / "hub"
    research_hub_dir = root / ".research_hub"
    logs = root / ".research_hub_logs"
    raw.mkdir(parents=True, exist_ok=True)
    hub.mkdir(parents=True, exist_ok=True)
    research_hub_dir.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    clusters_file = research_hub_dir / "clusters.yaml"
    clusters_file.write_text("clusters: {}\n", encoding="utf-8")
    return StressCfg(
        root=root,
        raw=raw,
        hub=hub,
        research_hub_dir=research_hub_dir,
        clusters_file=clusters_file,
        logs=logs,
        zotero_collections={},
    )


def synthetic_paper_note(
    slug: str,
    *,
    title: str | None = None,
    year: int = 2024,
    doi: str | None = None,
    cluster_slug: str = "stress",
    labels: list[str] | None = None,
) -> str:
    title = title or f"Synthetic paper {slug}"
    doi = doi or f"10.9999/{slug}"
    labels_json = json.dumps(labels or [], ensure_ascii=False)
    return (
        "---\n"
        f'title: "{title}"\n'
        'authors: "Stress, Test"\n'
        f'year: "{year}"\n'
        f'doi: "{doi}"\n'
        f'topic_cluster: "{cluster_slug}"\n'
        f"labels: {labels_json}\n"
        "status: unread\n"
        "---\n\n"
        f"# {title}\n\n"
        "## Abstract\n\n"
        "Synthetic abstract for stress testing.\n"
    )


def build_synthetic_cluster(
    cfg: StressCfg,
    cluster_slug: str,
    paper_count: int,
    *,
    labels_per_paper: list[str] | None = None,
) -> None:
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query=cluster_slug, name=f"Stress cluster {cluster_slug}", slug=cluster_slug)
    cluster_dir = cfg.raw / cluster_slug
    cluster_dir.mkdir(parents=True, exist_ok=True)
    for i in range(paper_count):
        slug = f"stress-{cluster_slug}-{i:04d}"
        note = synthetic_paper_note(
            slug,
            title=f"Paper {i}",
            year=2024 + (i % 2),
            cluster_slug=cluster_slug,
            labels=labels_per_paper,
        )
        (cluster_dir / f"{slug}.md").write_text(note, encoding="utf-8")


def build_synthetic_vault(
    tmp_path: Path,
    *,
    clusters: int = 5,
    papers_per_cluster: int = 100,
) -> StressCfg:
    cfg = make_stress_cfg(tmp_path)
    for idx in range(clusters):
        build_synthetic_cluster(cfg, f"cluster-{idx:02d}", papers_per_cluster)
    return cfg

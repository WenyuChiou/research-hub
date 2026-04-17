from __future__ import annotations

import time
from pathlib import Path

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.dashboard.data import collect_dashboard_data
from research_hub.dedup import DedupIndex

pytestmark = pytest.mark.stress


class _StubConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.hub = root / "hub"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"
        self.no_zotero = False
        self.raw.mkdir(parents=True, exist_ok=True)
        self.hub.mkdir(parents=True, exist_ok=True)
        self.research_hub_dir.mkdir(parents=True, exist_ok=True)


def _make_large_vault(tmp_path: Path, n_papers: int, n_clusters: int) -> _StubConfig:
    cfg = _StubConfig(tmp_path / "vault")
    registry = ClusterRegistry(cfg.clusters_file)

    papers_per_cluster = n_papers // n_clusters
    for c in range(n_clusters):
        slug = f"c{c:03d}"
        registry.create(query=slug, name=f"Cluster {c}", slug=slug)
        cluster_dir = cfg.raw / slug
        cluster_dir.mkdir(parents=True, exist_ok=True)
        for p in range(papers_per_cluster):
            (cluster_dir / f"p{p:04d}.md").write_text(
                "---\n"
                f'title: "Paper {c}-{p}"\n'
                f'authors: "Auth{p}"\n'
                'year: "2020"\n'
                f'doi: "10.1/c{c}p{p}"\n'
                f'topic_cluster: "{slug}"\n'
                'labels: ["core"]\n'
                'status: "unread"\n'
                f'ingested_at: "2026-04-16T{c % 24:02d}:{p % 60:02d}:00Z"\n'
                "---\n"
                f"# Paper {c}-{p}\n",
                encoding="utf-8",
            )
    return cfg


def test_dashboard_render_1000_papers_under_5s(tmp_path, monkeypatch):
    cfg = _make_large_vault(tmp_path, n_papers=1000, n_clusters=10)
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])
    monkeypatch.setattr("research_hub.dashboard.data.load_all_quotes", lambda cfg: [], raising=False)

    start = time.monotonic()
    data = collect_dashboard_data(cfg)
    elapsed = time.monotonic() - start

    assert data.total_papers == 1000
    assert elapsed < 5.0, f"render took {elapsed:.2f}s for 1000 papers"


@pytest.mark.xfail(reason="dashboard data has no cache layer yet", strict=False)
def test_dashboard_render_1000_papers_lru_cached(tmp_path, monkeypatch):
    cfg = _make_large_vault(tmp_path, n_papers=500, n_clusters=5)
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])
    monkeypatch.setattr("research_hub.dashboard.data.load_all_quotes", lambda cfg: [], raising=False)

    start = time.monotonic()
    collect_dashboard_data(cfg)
    first_elapsed = time.monotonic() - start

    start = time.monotonic()
    collect_dashboard_data(cfg)
    second_elapsed = time.monotonic() - start

    assert second_elapsed < min(1.0, first_elapsed * 0.5)


def test_dedup_index_500_papers(tmp_path):
    cfg = _make_large_vault(tmp_path, n_papers=500, n_clusters=5)

    start = time.monotonic()
    index = DedupIndex.empty().rebuild_from_obsidian(cfg.raw)
    elapsed = time.monotonic() - start

    assert len(index.doi_to_hits) == 500
    assert elapsed < 3.0, f"dedup rebuild took {elapsed:.2f}s for 500 papers"


def test_clusters_save_load_roundtrip_50(tmp_path):
    reg = ClusterRegistry(tmp_path / "clusters.yaml")
    for i in range(50):
        reg.create(query=f"cluster {i}", slug=f"c{i:03d}", name=f"Cluster {i}")

    reloaded = ClusterRegistry(tmp_path / "clusters.yaml")
    assert len(reloaded.list()) == 50

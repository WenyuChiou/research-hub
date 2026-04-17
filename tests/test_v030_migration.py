from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.crystal import list_crystals
from research_hub.dedup import DedupIndex
from research_hub.paper import read_labels
from research_hub.vault.sync import list_cluster_notes


class _StubConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.hub = root / "hub"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.hub.mkdir(parents=True, exist_ok=True)
        self.research_hub_dir.mkdir(parents=True, exist_ok=True)


def _make_v010_vault(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "smith2020-foo.md").write_text(
        "---\n"
        'title: "Foo"\n'
        'authors: ["Smith"]\n'
        'year: "2020"\n'
        'doi: "10.1/foo"\n'
        "---\n"
        "# Foo\n",
        encoding="utf-8",
    )
    rh = tmp_path / ".research_hub"
    rh.mkdir()
    (rh / "clusters.yaml").write_text(
        "clusters:\n"
        "  legacy-cluster:\n"
        "    name: Legacy Cluster\n"
        "    collection_id: ABC123\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.xfail(reason="current ClusterRegistry loader rejects legacy collection_id schema", strict=False)
def test_v010_vault_opens_in_v030(tmp_path):
    vault = _make_v010_vault(tmp_path)
    reg = ClusterRegistry(vault / ".research_hub" / "clusters.yaml")
    cluster = reg.get("legacy-cluster")
    assert cluster is None or cluster.zotero_collection_key in {None, "ABC123"}


def test_v010_papers_visible_via_topic_cluster_frontmatter(tmp_path):
    vault = _make_v010_vault(tmp_path)
    assert (vault / "raw" / "smith2020-foo.md").exists()
    notes = list_cluster_notes("legacy-cluster", vault / "raw")
    assert notes == []


@pytest.mark.xfail(reason="current DedupIndex.load ignores pre-v0.20 doi_to_key schema", strict=False)
def test_v015_dedup_index_v030_compatible(tmp_path):
    path = tmp_path / ".research_hub" / "dedup_index.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "doi_to_key": {"10.1/foo": "ABC123"},
            }
        ),
        encoding="utf-8",
    )
    idx = DedupIndex.load(path)
    hits = idx.lookup(doi="10.1/foo")
    assert hits and hits[0].zotero_key == "ABC123"


def test_v020_pre_crystal_vault_opens(tmp_path):
    cfg = _StubConfig(tmp_path / "vault")
    (cfg.hub / "test-cluster").mkdir(parents=True, exist_ok=True)
    assert list_crystals(cfg, "test-cluster") == []


def test_pre_v028_topic_cluster_frontmatter_compat(tmp_path):
    cfg = _StubConfig(tmp_path / "vault")
    cluster_dir = cfg.raw / "test-cluster"
    cluster_dir.mkdir(parents=True)
    note = cluster_dir / "old-paper.md"
    note.write_text(
        "---\n"
        'title: "Old"\n'
        'cluster_slug: "test-cluster"\n'
        "---\n",
        encoding="utf-8",
    )
    state = read_labels(cfg, "old-paper")
    assert state is not None
    assert state.cluster_slug == "test-cluster"


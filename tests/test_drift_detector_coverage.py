from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from research_hub.clusters import ClusterRegistry
from research_hub.dedup import DedupIndex
from research_hub.dashboard.drift import detect_drift


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir(parents=True)
    return SimpleNamespace(root=root, raw=raw, research_hub_dir=hub, clusters_file=hub / "clusters.yaml")


def _write_note(path: Path, *, title: str, doi: str, topic_cluster: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'---\ntitle: "{title}"\ndoi: "{doi}"\ntopic_cluster: "{topic_cluster}"\n---\n',
        encoding="utf-8",
    )


class _FakeZot:
    def __init__(self, items_by_collection: dict[str, list[dict]]):
        self.items_by_collection = items_by_collection

    def collection_items(self, collection_key: str, limit: int = 500, start: int = 0, itemType: str = ""):
        del limit, start, itemType
        return self.items_by_collection.get(collection_key, [])


def test_drift_detects_zotero_orphan(tmp_path):
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="agents", name="Agents", slug="agents", zotero_collection_key="COLL1"
    )
    _write_note(cfg.raw / "agents" / "matched.md", title="Matched", doi="10.1/a", topic_cluster="agents")
    zot = _FakeZot({"COLL1": [{"data": {"DOI": "10.1/a", "title": "Matched"}}, {"data": {"DOI": "10.1/b", "title": "Missing"}}]})

    alerts = detect_drift(cfg, DedupIndex.empty(), zot=zot)

    assert any(alert.kind == "zotero_orphan" for alert in alerts)


def test_drift_detects_subtopic_file_paper_mismatch(tmp_path):
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    topics = cfg.raw / "agents" / "topics"
    topics.mkdir(parents=True)
    (topics / "01_foo.md").write_text(
        "---\npapers: 5\n---\n# Foo\n\n## Papers\n- [[A]]\n- [[B]]\n- [[C]]\n",
        encoding="utf-8",
    )

    alerts = detect_drift(cfg, DedupIndex.empty(), zot=None)

    assert any(alert.kind == "subtopic_paper_mismatch" for alert in alerts)


def test_drift_detects_stale_manifest_cluster(tmp_path):
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    (cfg.research_hub_dir / "manifest.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-04-14T00:00:00Z",
                "cluster": "old-slug",
                "query": "old",
                "action": "new",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    alerts = detect_drift(cfg, DedupIndex.empty(), zot=None)

    assert any(alert.kind == "stale_manifest_cluster" for alert in alerts)

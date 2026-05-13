from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub.clusters import Cluster, ClusterRegistry, NotebookShard
from research_hub.notebooklm import upload as upload_mod  # for module-ref monkeypatching
from research_hub.notebooklm.client import NotebookHandle, UploadResult
from research_hub.notebooklm.upload import NotebookLMCapacityError, upload_cluster


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    research_hub_dir = root / ".research_hub"
    for path in (raw, hub, research_hub_dir):
        path.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        root=root,
        raw=raw,
        hub=hub,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def _cluster(cfg, slug: str = "alpha") -> Cluster:
    cluster = Cluster(slug=slug, name="Alpha Cluster")
    registry = ClusterRegistry(cfg.clusters_file)
    registry.clusters[slug] = cluster
    registry.save()
    return cluster


def _entry(index: int, **extra) -> dict:
    payload = {
        "action": "url",
        "url": f"https://example.com/paper-{index:03d}",
        "doi": f"10.1000/{index:03d}",
        "title": f"Paper {index:03d}",
        "ingested_at": f"2026-01-{(index // 24) + 1:02d}T{index % 24:02d}:00:00Z",
        "citation_count": index,
    }
    payload.update(extra)
    return payload


def _write_bundle(cfg, cluster_slug: str, entries: list[dict]) -> Path:
    bundle_dir = cfg.research_hub_dir / "bundles" / f"{cluster_slug}-20260513T000000Z"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "manifest.json").write_text(
        json.dumps({"entries": entries}, ensure_ascii=False),
        encoding="utf-8",
    )
    return bundle_dir


def _dois(entries: list[dict]) -> list[str]:
    return [entry["doi"] for entry in entries]


def test_cluster_with_50_sources_has_no_overflow(tmp_path):
    cfg = _cfg(tmp_path)
    cluster = _cluster(cfg)
    _write_bundle(cfg, cluster.slug, [_entry(i) for i in range(50)])

    report = upload_cluster(cluster, cfg, dry_run=True)

    assert report.success_count == 50
    assert report.over_cap_skipped == []
    assert report.over_cap_strategy == "fail"


def test_cluster_with_51_sources_default_raises_capacity_error(tmp_path):
    cfg = _cfg(tmp_path)
    cluster = _cluster(cfg)
    _write_bundle(cfg, cluster.slug, [_entry(i) for i in range(51)])

    with pytest.raises(NotebookLMCapacityError) as excinfo:
        upload_cluster(cluster, cfg, dry_run=True)

    message = str(excinfo.value)
    assert "Alpha Cluster" in message
    assert "1 source over" in message
    assert "--over-cap-strategy shard" in message


def test_top_n_recent_uploads_50_newest_and_records_10_skipped(tmp_path):
    cfg = _cfg(tmp_path)
    cluster = _cluster(cfg)
    _write_bundle(cfg, cluster.slug, [_entry(i) for i in range(60)])

    report = upload_cluster(cluster, cfg, dry_run=True, over_cap_strategy="top-n-recent")

    assert report.success_count == 50
    assert len(report.over_cap_skipped) == 10
    assert report.uploaded[0].path_or_url == "https://example.com/paper-059"
    assert set(_dois(report.over_cap_skipped)) == {f"10.1000/{i:03d}" for i in range(10)}


def test_top_n_cited_uploads_50_highest_cited_and_records_10_skipped(tmp_path):
    cfg = _cfg(tmp_path)
    cluster = _cluster(cfg)
    entries = [_entry(i, citation_count=1000 - i) for i in range(60)]
    _write_bundle(cfg, cluster.slug, entries)

    report = upload_cluster(cluster, cfg, dry_run=True, over_cap_strategy="top-n-cited")

    assert report.success_count == 50
    assert len(report.over_cap_skipped) == 10
    assert report.uploaded[0].path_or_url == "https://example.com/paper-000"
    assert set(_dois(report.over_cap_skipped)) == {f"10.1000/{i:03d}" for i in range(50, 60)}


def test_fit_score_uploads_50_highest_fit_scores_and_records_10_skipped(tmp_path):
    cfg = _cfg(tmp_path)
    cluster = _cluster(cfg)
    _write_bundle(cfg, cluster.slug, [_entry(i) for i in range(60)])
    fit_dir = cfg.hub / cluster.slug
    fit_dir.mkdir(parents=True)
    (fit_dir / ".fit_check_accepted.json").write_text(
        json.dumps({"accepted": [{"doi": f"10.1000/{i:03d}", "score": i} for i in range(60)]}),
        encoding="utf-8",
    )

    report = upload_cluster(cluster, cfg, dry_run=True, over_cap_strategy="fit-score")

    assert report.success_count == 50
    assert len(report.over_cap_skipped) == 10
    assert report.uploaded[0].path_or_url == "https://example.com/paper-059"
    assert set(_dois(report.over_cap_skipped)) == {f"10.1000/{i:03d}" for i in range(10)}


class FakeNotebookLMClient:
    def __init__(self) -> None:
        self.active_notebook_id = ""
        self.handles: list[NotebookHandle] = []
        self.uploads: list[tuple[str, str]] = []

    def find_or_create_notebook(self, name: str) -> NotebookHandle:
        notebook_id = f"nb-{len(self.handles) + 1}"
        handle = NotebookHandle(
            name=name,
            url=f"https://notebooklm.google.com/notebook/{notebook_id}",
            notebook_id=notebook_id,
        )
        self.handles.append(handle)
        return handle

    def set_active_notebook(self, notebook_id: str) -> None:
        self.active_notebook_id = notebook_id

    def upload_url(self, url: str) -> UploadResult:
        self.uploads.append((self.active_notebook_id, url))
        return UploadResult(source_kind="url", path_or_url=url, success=True)

    def list_sources(self, _notebook_id: str) -> list:
        return []

    def close(self) -> None:
        return None


def test_shard_strategy_materializes_three_notebooks_for_110_sources(tmp_path, monkeypatch):
    """v0.88.1 fix: switched from `monkeypatch.setattr("research_hub...string", ...)`
    to `monkeypatch.setattr(upload_mod, ...)` with the real module reference.
    The string-path form caused pytest to resolve the module path via
    importlib at fixture time, and in some test orderings the resolved
    module object was a different instance than the one held by
    `_upload_cluster_shards`'s globals — so the patch landed on a stale
    sys.modules entry while the live function kept the original
    _make_client. Resolving the module ourselves removes that ambiguity."""
    cfg = _cfg(tmp_path)
    cluster = _cluster(cfg)
    _write_bundle(cfg, cluster.slug, [_entry(i) for i in range(110)])
    fake_client = FakeNotebookLMClient()
    monkeypatch.setattr(upload_mod, "_make_client", lambda *_args, **_kwargs: fake_client)
    monkeypatch.setattr(upload_mod, "NotebookLMClient", lambda *_args, **_kwargs: fake_client)
    monkeypatch.setattr(upload_mod.time, "sleep", lambda _seconds: None)
    # Sanity assertion: confirm patches landed on the SAME module instance
    # _upload_cluster_shards reads from. If sys.modules has drifted, this
    # fires immediately rather than silently constructing a real client.
    assert upload_mod._make_client is not None
    assert upload_mod._make_client(None, headless=True) is fake_client

    report = upload_cluster(cluster, cfg, over_cap_strategy="shard", shard_size=50)

    loaded = ClusterRegistry(cfg.clusters_file).get(cluster.slug)
    assert report.success_count == 110
    assert [shard.source_count for shard in loaded.notebooklm_shards] == [50, 50, 10]
    assert [shard.notebook_name for shard in loaded.notebooklm_shards] == [
        "Alpha Cluster [1/3]",
        "Alpha Cluster [2/3]",
        "Alpha Cluster [3/3]",
    ]


def test_sharding_preserves_doi_uniqueness_across_shards(tmp_path, monkeypatch):
    """v0.88.1 fix: same module-reference monkeypatch pattern as the
    sibling shard test — bypasses the string-path import-resolution
    ambiguity that caused full-suite flakes."""
    cfg = _cfg(tmp_path)
    cluster = _cluster(cfg)
    _write_bundle(cfg, cluster.slug, [_entry(i) for i in range(110)])
    fake_client = FakeNotebookLMClient()
    monkeypatch.setattr(upload_mod, "_make_client", lambda *_args, **_kwargs: fake_client)
    monkeypatch.setattr(upload_mod, "NotebookLMClient", lambda *_args, **_kwargs: fake_client)
    monkeypatch.setattr(upload_mod.time, "sleep", lambda _seconds: None)

    upload_cluster(cluster, cfg, over_cap_strategy="shard", shard_size=50)

    loaded = ClusterRegistry(cfg.clusters_file).get(cluster.slug)
    doi_list = [doi for shard in loaded.notebooklm_shards for doi in shard.source_doi_list]
    assert len(doi_list) == 110
    assert len(set(doi_list)) == 110


def test_notebook_shard_round_trips_through_clusters_yaml(tmp_path):
    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.clusters["alpha"] = Cluster(
        slug="alpha",
        name="Alpha",
        notebooklm_shards=[
            NotebookShard(
                notebook_id="nb-1",
                notebook_url="https://notebooklm.google.com/notebook/nb-1",
                notebook_name="Alpha [1/1]",
                source_count=2,
                source_doi_list=["10.1000/a", "10.1000/b"],
                created_at="2026-05-13T00:00:00Z",
            )
        ],
    )
    registry.save()

    loaded = ClusterRegistry(cfg.clusters_file).get("alpha")

    assert isinstance(loaded.notebooklm_shards[0], NotebookShard)
    assert loaded.notebooklm_shards[0].source_doi_list == ["10.1000/a", "10.1000/b"]


@pytest.mark.parametrize("strategy", ["fail", "top-n-recent", "shard"])
def test_cli_parses_upload_over_cap_strategies(strategy):
    from research_hub.cli import build_parser

    args = build_parser().parse_args(
        ["notebooklm", "upload", "--cluster", "alpha", "--over-cap-strategy", strategy]
    )

    assert args.notebooklm_command == "upload"
    assert args.over_cap_strategy == strategy


def test_cli_default_upload_over_cap_strategy_is_fail():
    from research_hub.cli import build_parser

    args = build_parser().parse_args(["notebooklm", "upload", "--cluster", "alpha"])

    assert args.over_cap_strategy == "fail"
    assert args.shard_size == 50


def test_cli_parses_notebooklm_shard_command():
    from research_hub.cli import build_parser

    args = build_parser().parse_args(
        ["notebooklm", "shard", "--cluster", "alpha", "--strategy", "recent", "--shard-size", "25"]
    )

    assert args.notebooklm_command == "shard"
    assert args.strategy == "recent"
    assert args.shard_size == 25

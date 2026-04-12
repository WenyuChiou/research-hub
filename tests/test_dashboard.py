from __future__ import annotations

import json
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.dedup import DedupHit, DedupIndex
from research_hub.dashboard import (
    ClusterStats,
    collect_vault_state,
    generate_dashboard,
    render_dashboard_html,
)


class StubConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"


def make_config(tmp_path: Path) -> StubConfig:
    root = tmp_path / "vault"
    cfg = StubConfig(root)
    cfg.raw.mkdir(parents=True)
    cfg.research_hub_dir.mkdir(parents=True)
    return cfg


def write_note(
    cfg: StubConfig,
    cluster_slug: str,
    filename: str,
    *,
    status: str = "unread",
    ingested_at: str = "2026-04-12T10:00:00Z",
    title: str | None = None,
) -> Path:
    note_dir = cfg.raw / cluster_slug
    note_dir.mkdir(parents=True, exist_ok=True)
    note_path = note_dir / filename
    note_path.write_text(
        f"""---
title: "{title or filename}"
status: "{status}"
ingested_at: "{ingested_at}"
---
Body
""",
        encoding="utf-8",
    )
    return note_path


def test_collect_vault_state_returns_clusters(tmp_path):
    cfg = make_config(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    write_note(cfg, "agents", "paper-1.md")
    write_note(cfg, "agents", "paper-2.md")

    state = collect_vault_state(cfg)

    assert state["total_clusters"] == 1
    assert state["total_papers"] == 2
    assert state["clusters"]["agents"].paper_count == 2


def test_collect_vault_state_status_breakdown(tmp_path):
    cfg = make_config(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    write_note(cfg, "agents", "paper-1.md", status="reading")
    write_note(cfg, "agents", "paper-2.md", status="deep-read")
    write_note(cfg, "agents", "paper-3.md", status="reading")

    state = collect_vault_state(cfg)

    assert state["clusters"]["agents"].status_breakdown == {"reading": 2, "deep-read": 1}


def test_render_dashboard_html_includes_cluster_name():
    state = {
        "vault_root": "/vault",
        "generated_at": "2026-04-12 12:00 UTC",
        "total_papers": 1,
        "total_clusters": 1,
        "dedup_doi_count": 0,
        "dedup_title_count": 0,
        "clusters": {"agents": ClusterStats(slug="agents", name="Agents", paper_count=1)},
        "nlm_cache": {},
    }

    html = render_dashboard_html(state)

    assert "Agents" in html


def test_render_dashboard_html_no_clusters_shows_empty():
    state = {
        "vault_root": "/vault",
        "generated_at": "2026-04-12 12:00 UTC",
        "total_papers": 0,
        "total_clusters": 0,
        "dedup_doi_count": 0,
        "dedup_title_count": 0,
        "clusters": {},
        "nlm_cache": {},
    }

    html = render_dashboard_html(state)

    assert "No clusters yet" in html


def test_render_dashboard_html_includes_stats():
    state = {
        "vault_root": "/vault",
        "generated_at": "2026-04-12 12:00 UTC",
        "total_papers": 12,
        "total_clusters": 3,
        "dedup_doi_count": 5,
        "dedup_title_count": 7,
        "clusters": {},
        "nlm_cache": {},
    }

    html = render_dashboard_html(state)

    for value in ("12", "3", "5", "7"):
        assert value in html


def test_render_dashboard_html_escapes_user_data():
    state = {
        "vault_root": "/vault",
        "generated_at": "2026-04-12 12:00 UTC",
        "total_papers": 1,
        "total_clusters": 1,
        "dedup_doi_count": 0,
        "dedup_title_count": 0,
        "clusters": {
            "unsafe": ClusterStats(slug="unsafe", name="<script>alert(1)</script>", paper_count=1)
        },
        "nlm_cache": {},
    }

    html = render_dashboard_html(state)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_render_dashboard_html_includes_notebooklm_link():
    state = {
        "vault_root": "/vault",
        "generated_at": "2026-04-12 12:00 UTC",
        "total_papers": 1,
        "total_clusters": 1,
        "dedup_doi_count": 0,
        "dedup_title_count": 0,
        "clusters": {
            "agents": ClusterStats(
                slug="agents",
                name="Agents",
                paper_count=1,
                notebooklm_notebook_url="https://notebooklm.google.com/test",
            )
        },
        "nlm_cache": {},
    }

    html = render_dashboard_html(state)

    assert "https://notebooklm.google.com/test" in html
    assert 'target="_blank"' in html


def test_render_dashboard_html_self_contained():
    state = {
        "vault_root": "/vault",
        "generated_at": "2026-04-12 12:00 UTC",
        "total_papers": 0,
        "total_clusters": 0,
        "dedup_doi_count": 0,
        "dedup_title_count": 0,
        "clusters": {},
        "nlm_cache": {},
    }

    html = render_dashboard_html(state)

    assert "<link " not in html
    assert "<script src=" not in html


def test_generate_dashboard_writes_file(tmp_path, monkeypatch):
    cfg = make_config(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="agents", name="Agents", slug="agents")
    write_note(cfg, "agents", "paper-1.md")
    monkeypatch.setattr("research_hub.dashboard.get_config", lambda: cfg)

    out_path = generate_dashboard()

    assert out_path.exists()
    assert out_path.name == "dashboard.html"
    assert "research-hub" in out_path.read_text(encoding="utf-8")


def test_generate_dashboard_creates_research_hub_dir(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    raw = root / "raw"
    raw.mkdir(parents=True)
    cfg = StubConfig(root)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="agents", name="Agents", slug="agents")
    write_note(cfg, "agents", "paper-1.md")
    if cfg.research_hub_dir.exists():
        for item in cfg.research_hub_dir.iterdir():
            item.unlink()
        cfg.research_hub_dir.rmdir()
    monkeypatch.setattr("research_hub.dashboard.get_config", lambda: cfg)

    out_path = generate_dashboard()

    assert cfg.research_hub_dir.exists()
    assert out_path.exists()


def test_collect_vault_state_reads_dedup_and_nlm_cache(tmp_path):
    cfg = make_config(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="agents", name="Agents", slug="agents", notebooklm_notebook="Notebook")
    write_note(cfg, "agents", "paper-1.md", ingested_at="2026-04-10T10:00:00Z")
    write_note(cfg, "agents", "paper-2.md", ingested_at="2026-04-12T10:00:00Z")
    index = DedupIndex()
    index.add(DedupHit(source="obsidian", doi="10.1000/test", title="Paper One"))
    index.add(DedupHit(source="obsidian", title="A long enough title for indexing"))
    index.save(cfg.research_hub_dir / "dedup_index.json")
    (cfg.research_hub_dir / "nlm_cache.json").write_text(
        json.dumps({"agents": {"notebook_url": "https://example.com/notebook"}}),
        encoding="utf-8",
    )

    state = collect_vault_state(cfg)

    assert state["dedup_doi_count"] == 1
    assert state["dedup_title_count"] == 1
    assert state["clusters"]["agents"].latest_ingested_at == "2026-04-12T10:00:00Z"
    assert state["clusters"]["agents"].notebooklm_notebook_url == "https://example.com/notebook"

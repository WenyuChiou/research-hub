from __future__ import annotations

from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.dashboard import render_dashboard_from_config
from research_hub.dashboard.data import _detect_persona


class _Cfg:
    def __init__(self, root: Path, *, no_zotero: bool = False) -> None:
        self.root = root
        self.raw = root / "raw"
        self.hub = root / "hub"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"
        self.no_zotero = no_zotero
        self.raw.mkdir(parents=True, exist_ok=True)
        self.hub.mkdir(parents=True, exist_ok=True)
        self.research_hub_dir.mkdir(parents=True, exist_ok=True)


def _make_cfg(tmp_path: Path, *, no_zotero: bool = False) -> _Cfg:
    return _Cfg(tmp_path / "vault", no_zotero=no_zotero)


def _write_note(cfg: _Cfg, cluster_slug: str) -> None:
    note_dir = cfg.raw / cluster_slug
    note_dir.mkdir(parents=True, exist_ok=True)
    (note_dir / "paper-one.md").write_text(
        "---\n"
        'title: "Paper One"\n'
        'authors: "Doe, Jane"\n'
        'year: "2025"\n'
        'doi: "10.1000/one"\n'
        f'topic_cluster: "{cluster_slug}"\n'
        "zotero-key: ABC123\n"
        "---\nBody\n",
        encoding="utf-8",
    )


def test_analyst_persona_hides_zotero_column(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path, no_zotero=True)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    _write_note(cfg, "agents")
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])

    html = render_dashboard_from_config(cfg)

    assert "<th scope=\"col\">Zotero</th>" not in html


def test_analyst_persona_omits_bibtex_buttons(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path, no_zotero=True)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    _write_note(cfg, "agents")
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])

    html = render_dashboard_from_config(cfg)

    assert 'class="cite-btn"' not in html
    assert "Download cluster .bib" not in html


def test_researcher_persona_default_when_zotero_configured(tmp_path):
    cfg = _make_cfg(tmp_path, no_zotero=False)
    assert _detect_persona(cfg, zot=None) == "researcher"

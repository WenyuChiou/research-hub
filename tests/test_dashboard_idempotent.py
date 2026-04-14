from __future__ import annotations

import hashlib
import re
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.dashboard import render_dashboard_from_config


class _Cfg:
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


def _make_cfg(tmp_path: Path) -> _Cfg:
    return _Cfg(tmp_path / "vault")


def _write_note(cfg: _Cfg, cluster_slug: str, slug: str) -> None:
    note_dir = cfg.raw / cluster_slug
    note_dir.mkdir(parents=True, exist_ok=True)
    (note_dir / f"{slug}.md").write_text(
        "---\n"
        f'title: "{slug}"\n'
        'authors: "Doe, Jane"\n'
        'year: "2025"\n'
        'doi: "10.1000/example"\n'
        f'topic_cluster: "{cluster_slug}"\n'
        "---\nBody\n",
        encoding="utf-8",
    )


def _strip_timestamp(html: str) -> str:
    html = re.sub(r"Generated [^<]+", "Generated <TS>", html)
    html = re.sub(r'"generated_at":\s*"[^"]+"', '"generated_at":"<TS>"', html)
    return html


def test_running_dashboard_twice_produces_identical_html(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    _write_note(cfg, "agents", "paper-one")
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])

    html1 = render_dashboard_from_config(cfg)
    html2 = render_dashboard_from_config(cfg)

    digest1 = hashlib.sha256(_strip_timestamp(html1).encode("utf-8")).hexdigest()
    digest2 = hashlib.sha256(_strip_timestamp(html2).encode("utf-8")).hexdigest()
    assert digest1 == digest2


def test_dashboard_handles_empty_vault_without_crash(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])

    html = render_dashboard_from_config(cfg)

    for tab_id in ("tab-overview", "tab-library", "tab-briefings", "tab-writing", "tab-diagnostics", "tab-manage"):
        assert f'id="{tab_id}"' in html
    assert "No clusters yet" in html


def test_dashboard_handles_missing_bindings_gracefully(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    _write_note(cfg, "agents", "paper-one")
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])

    html = render_dashboard_from_config(cfg)

    assert "NotebookLM" in html
    assert "Zotero" in html
    assert "unbound" in html

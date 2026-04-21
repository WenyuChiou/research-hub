from __future__ import annotations

from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.dashboard.render import render_dashboard_from_config
from research_hub.sample_vault import copy_sample_vault, generate_sample_dashboard


class SampleConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.hub = root / "hub"
        self.logs = root / "logs"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"
        self.no_zotero = True
        self.persona = "researcher"
        self.zotero_library_id = ""
        self.zotero_library_type = "user"
        self.zotero_default_collection = ""
        self.zotero_collections = {}


def test_sample_vault_structure_loads(tmp_path):
    root = copy_sample_vault(tmp_path / "sample")
    registry = ClusterRegistry(root / ".research_hub" / "clusters.yaml")

    assert registry.get("llm-evaluation-harness") is not None
    assert registry.get("agent-based-modeling") is not None
    assert len(list((root / "raw" / "llm-evaluation-harness").glob("*.md"))) == 3
    assert len(list((root / "raw" / "agent-based-modeling").glob("*.md"))) == 2
    assert len(list((root / "hub").glob("*/crystals/*.md"))) == 3
    assert (root / "hub" / "llm-evaluation-harness" / "llm-evaluation-harness.base").exists()
    assert (root / ".research_hub" / "artifacts" / "llm-evaluation-harness").exists()


def test_sample_vault_dashboard_render_returns_html(tmp_path):
    root = copy_sample_vault(tmp_path / "sample")
    cfg = SampleConfig(root)

    html = render_dashboard_from_config(cfg)

    assert "<!DOCTYPE html>" in html
    assert "research-hub dashboard" in html
    assert "LLM Evaluation Harness" in html
    assert "Agent-Based Modeling" in html


def test_generate_sample_dashboard_adds_preview_banner(tmp_path, monkeypatch):
    monkeypatch.delenv("RESEARCH_HUB_CONFIG", raising=False)
    monkeypatch.setattr(
        "research_hub.sample_vault.copy_sample_vault",
        lambda destination=None: copy_sample_vault(tmp_path / "sample-run"),
    )
    out_path = generate_sample_dashboard(open_browser=False)
    html = out_path.read_text(encoding="utf-8")

    assert out_path.name == "dashboard.html"
    assert "SAMPLE PREVIEW - this vault is read-only and temporary." in html
    assert "research-hub init" in html

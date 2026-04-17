"""v0.31 Track D: NotebookLM MCP tool wrappers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from research_hub.clusters import ClusterRegistry
from tests._mcp_helpers import _get_mcp_tool


@dataclass
class _Cfg:
    root: Path
    raw: Path
    hub: Path
    research_hub_dir: Path
    clusters_file: Path
    no_zotero: bool = False


def _make_cfg(tmp_path: Path) -> _Cfg:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    rh = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir(parents=True)
    rh.mkdir(parents=True)
    return _Cfg(root=root, raw=raw, hub=hub, research_hub_dir=rh, clusters_file=rh / "clusters.yaml")


def _call_tool(name: str, *args, **kwargs):
    from research_hub.mcp_server import mcp

    return _get_mcp_tool(mcp, name).fn(*args, **kwargs)


def test_notebooklm_bundle_validates_slug():
    from research_hub.security import ValidationError

    with pytest.raises(ValidationError):
        _call_tool("notebooklm_bundle", "../../etc")


def test_notebooklm_upload_handles_missing_cluster(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)

    result = _call_tool("notebooklm_upload", "nonexistent-cluster")

    assert isinstance(result, dict)
    assert result["status"] == "error"
    assert "cluster not found" in result["error"].lower()


def test_notebooklm_generate_validates_artifact_type(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)

    result = _call_tool("notebooklm_generate", "agents", artifact_type="not-a-valid-type")

    assert isinstance(result, dict)
    assert result["status"] == "error"
    assert "artifact_type" in result["error"].lower()

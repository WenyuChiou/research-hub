from __future__ import annotations

import json
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config
from research_hub.mcp_server import merge_clusters, remove_paper, search_vault


def _make_config(tmp_path: Path, monkeypatch):
    root = tmp_path / "vault"
    raw = root / "raw"
    hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    hub_dir.mkdir(parents=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"knowledge_base": {"root": str(root), "raw": str(raw)}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("RESEARCH_HUB_CONFIG", str(config_path))
    return get_config()


def _write_note(path: Path, *, title: str, cluster: str, status: str = "unread"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f'title: "{title}"\n'
        f'topic_cluster: "{cluster}"\n'
        f"status: {status}\n"
        "---\n",
        encoding="utf-8",
    )


def test_remove_paper_tool_returns_expected_dict(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    note = cfg.raw / "alpha" / "paper-one.md"
    _write_note(note, title="Paper One", cluster="alpha")

    result = remove_paper("paper-one")

    assert result["removed_files"] == [str(note)]


def test_search_vault_tool_returns_list(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    _write_note(cfg.raw / "alpha" / "paper-one.md", title="Flood Risk Agents", cluster="alpha")

    result = search_vault("flood")

    assert isinstance(result, list)
    assert result[0]["slug"] == "paper-one"


def test_merge_clusters_tool_returns_expected_dict(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path, monkeypatch)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create("alpha", name="Alpha", slug="alpha")
    registry.create("beta", name="Beta", slug="beta")
    _write_note(cfg.raw / "alpha" / "paper-one.md", title="Paper One", cluster="alpha")

    result = merge_clusters("alpha", "beta")

    assert result == {"source": "alpha", "target": "beta", "moved": 1}

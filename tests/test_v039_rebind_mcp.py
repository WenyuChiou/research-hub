"""v0.39 rebind MCP tool tests."""

from __future__ import annotations

from pathlib import Path

from tests._mcp_helpers import _get_mcp_tool
from tests._persona_factory import make_persona_vault


def _seed_orphans(cfg, folder, count, *, frontmatter="", tag="research/topic-x"):
    subdir = cfg.raw / folder
    subdir.mkdir(exist_ok=True)
    for i in range(count):
        lines = ["---", f"title: Orphan {i}"]
        if frontmatter:
            lines.append(frontmatter)
        else:
            lines.append(f"tags: [{tag}]")
        lines.extend(["---", "body"])
        (subdir / f"orphan-{i}.md").write_text("\n".join(lines), encoding="utf-8")


def test_propose_cluster_rebind_returns_moves(tmp_path, monkeypatch):
    from research_hub import mcp_server

    cfg, info = make_persona_vault(tmp_path, persona="A")
    _seed_orphans(cfg, "stranded", 1, frontmatter=f"cluster: {info['cluster_slug']}")
    monkeypatch.setattr("research_hub.mcp_server.get_config", lambda: cfg)
    result = _get_mcp_tool(mcp_server.mcp, "propose_cluster_rebind").fn()
    assert result["count"] == 1
    assert result["moves"][0]["confidence"] == "high"


def test_apply_cluster_rebind_dry_run_returns_counts(tmp_path, monkeypatch):
    from research_hub import mcp_server
    from research_hub.cluster_rebind import emit_rebind_prompt

    cfg, info = make_persona_vault(tmp_path, persona="A")
    _seed_orphans(cfg, "stranded", 1, frontmatter=f"cluster: {info['cluster_slug']}")
    report_path = tmp_path / "rebind.md"
    report_path.write_text(emit_rebind_prompt(cfg), encoding="utf-8")
    monkeypatch.setattr("research_hub.mcp_server.get_config", lambda: cfg)
    result = _get_mcp_tool(mcp_server.mcp, "apply_cluster_rebind").fn(str(report_path), dry_run=True)
    assert result["moved"] == 0
    assert result["skipped"] == 1
    assert result["dry_run"] is True


def test_list_orphan_papers_filters_by_folder(tmp_path, monkeypatch):
    from research_hub import mcp_server

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    _seed_orphans(cfg, "folder-a", 2)
    _seed_orphans(cfg, "folder-b", 3)
    monkeypatch.setattr("research_hub.mcp_server.get_config", lambda: cfg)
    result = _get_mcp_tool(mcp_server.mcp, "list_orphan_papers").fn("folder-b")
    assert result["folder"] == "folder-b"
    assert result["count"] == 3
    assert all(path.startswith("folder-b/") for path in result["papers"])


def test_summarize_rebind_status_counts_new_cluster_proposals(tmp_path, monkeypatch):
    from research_hub import mcp_server

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    _seed_orphans(cfg, "Behavioral-Theory", 6, tag="research/behavior")
    monkeypatch.setattr("research_hub.mcp_server.get_config", lambda: cfg)
    result = _get_mcp_tool(mcp_server.mcp, "summarize_rebind_status").fn()
    assert result["total_orphans"] == 6
    assert result["proposed_to_existing_clusters"] == 0
    assert result["new_clusters_proposed"] == 1
    assert result["stuck"] == 6


def test_apply_cluster_rebind_auto_create_new_moves_files(tmp_path, monkeypatch):
    from research_hub import mcp_server
    from research_hub.cluster_rebind import emit_rebind_prompt

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    _seed_orphans(cfg, "Behavioral-Theory", 6, tag="research/behavior")
    report_path = tmp_path / "rebind.md"
    report_path.write_text(emit_rebind_prompt(cfg), encoding="utf-8")
    monkeypatch.setattr("research_hub.mcp_server.get_config", lambda: cfg)
    result = _get_mcp_tool(mcp_server.mcp, "apply_cluster_rebind").fn(
        str(report_path),
        dry_run=False,
        auto_create_new=True,
    )
    assert result["moved"] == 6
    assert Path(cfg.raw / "behavioral-theory" / "orphan-0.md").exists()

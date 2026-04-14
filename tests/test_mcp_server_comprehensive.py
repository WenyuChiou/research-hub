from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path

from research_hub import mcp_server
from research_hub.clusters import ClusterRegistry
from tests._mcp_helpers import _get_mcp_tool, _list_mcp_tool_names


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


def _write_note(cfg: _Cfg, cluster_slug: str, slug: str, *, doi: str = "10.1000/example") -> Path:
    note_dir = cfg.raw / cluster_slug
    note_dir.mkdir(parents=True, exist_ok=True)
    path = note_dir / f"{slug}.md"
    path.write_text(
        "---\n"
        f'title: "{slug.title()}"\n'
        'authors: ["Doe, Jane"]\n'
        'year: "2025"\n'
        f'doi: "{doi}"\n'
        f'topic_cluster: "{cluster_slug}"\n'
        'zotero-key: ABC123\n'
        "---\n"
        "## Abstract\n"
        "A note body.\n",
        encoding="utf-8",
    )
    return path


def _all_mcp_tools():
    names = sorted(_list_mcp_tool_names(mcp_server.mcp))
    return [(name, _get_mcp_tool(mcp_server.mcp, name)) for name in names]


def _call_tool(name: str, *args, **kwargs):
    return _get_mcp_tool(mcp_server.mcp, name).fn(*args, **kwargs)


def test_all_mcp_tool_functions_are_callable():
    tools = _all_mcp_tools()
    assert len(tools) >= 9
    assert all(tool is not None for _, tool in tools)


def test_mcp_tools_have_docstrings():
    for name, tool in _all_mcp_tools():
        assert tool.fn.__doc__, f"MCP tool {name} missing docstring"


def test_mcp_tools_have_typed_parameters():
    for name, tool in _all_mcp_tools():
        sig = inspect.signature(tool.fn)
        for param_name, param in sig.parameters.items():
            assert param.annotation is not inspect.Parameter.empty, f"{name}.{param_name} missing annotation"


def test_build_citation_tool_returns_expected_shape(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    _write_note(cfg, "agents", "paper-one", doi="10.1000/one")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)

    result = _call_tool("build_citation", "paper-one")

    assert result["status"] == "ok"
    assert set(result) >= {"status", "inline", "markdown"}
    assert "(Doe" in result["inline"]
    assert "https://doi.org/10.1000/one" in result["markdown"]


def test_list_quotes_tool_returns_list(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)

    result = _call_tool("list_quotes")

    assert result["status"] == "ok"
    assert result["count"] == 0
    assert result["quotes"] == []


def test_capture_quote_tool_writes_to_disk(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    _write_note(cfg, "agents", "paper-one")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)

    result = _call_tool("capture_quote", "paper-one", page="12", text="Useful passage", context="Methods")

    assert result["status"] == "ok"
    saved = Path(result["path"])
    assert saved.exists()
    assert "Useful passage" in saved.read_text(encoding="utf-8")


def test_compose_draft_tool_empty_cluster_returns_error(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)

    result = _call_tool("compose_draft", "agents")

    assert "error" in result
    assert "No captured quotes found" in result["error"]


def test_compose_draft_tool_produces_draft(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    _write_note(cfg, "agents", "paper-one")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    capture = _call_tool("capture_quote", "paper-one", page="3", text="Quoted text", context="Intro")
    assert capture["status"] == "ok"

    result = _call_tool("compose_draft", "agents", outline=["Intro"], quote_slugs=["paper-one"])

    assert result["status"] == "ok"
    assert Path(result["path"]).exists()
    assert result["quote_count"] == 1
    assert result["section_count"] == 1


def test_generate_dashboard_tool_writes_html(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.dashboard.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])

    result = _call_tool("generate_dashboard")

    assert result["status"] == "ok"
    path = Path(result["path"])
    assert path.exists()
    assert path.suffix == ".html"


def test_read_briefing_tool_truncates_long_briefing(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    artifacts = cfg.research_hub_dir / "artifacts" / "agents"
    artifacts.mkdir(parents=True)
    (artifacts / "brief-20260412.txt").write_text("x" * 120, encoding="utf-8")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)

    result = _call_tool("read_briefing", "agents", max_chars=50)

    assert result["status"] == "ok"
    assert result["truncated"] is True
    assert len(result["text"]) == 50
    assert result["full_chars"] == 120


def test_propose_research_setup_tool_returns_suggestions():
    result = _call_tool("propose_research_setup", "AI agents in geopolitics")

    assert result["topic"] == "AI agents in geopolitics"
    assert result["suggestions"]["cluster_slug"]
    assert result["suggestions"]["cluster_name"]
    assert result["next_steps"]


def test_add_paper_tool_validates_identifier_format(monkeypatch):
    monkeypatch.setattr(
        "research_hub.operations.add_paper",
        lambda *args, **kwargs: {"status": "error", "reason": "invalid identifier format"},
    )

    result = _call_tool("add_paper", "not-an-id")

    assert result["status"] == "error"
    assert "invalid identifier format" in result["reason"]

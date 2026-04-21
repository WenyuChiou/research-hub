"""Tests for v0.29 onboarding UX improvements."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub.config import get_config


class _StubConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.hub = root / "hub"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.hub.mkdir(parents=True, exist_ok=True)
        self.research_hub_dir.mkdir(parents=True, exist_ok=True)


def _reset_config_cache() -> None:
    import research_hub.config as config_mod

    config_mod._config = None
    config_mod._config_path = None


def test_init_prints_next_steps_with_vault_and_config_paths(tmp_path, capsys):
    from research_hub.init_wizard import _print_completion_banner

    vault = tmp_path / "my-vault"
    config = tmp_path / "config.json"
    _print_completion_banner(vault, config, persona="researcher")
    out = capsys.readouterr().out
    assert "Setup complete" in out
    assert str(vault) in out
    assert str(config) in out
    assert "research-hub doctor" in out
    assert 'research-hub plan "your research topic"' in out
    assert 'research-hub auto "your research topic"' in out
    assert "research-hub serve --dashboard" in out
    assert "research-hub install --mcp" not in out


def test_init_prints_analyst_next_steps(tmp_path, capsys):
    from research_hub.init_wizard import _print_completion_banner

    _print_completion_banner(tmp_path / "vault", tmp_path / "config.json", persona="analyst")
    out = capsys.readouterr().out
    assert "research-hub import-folder <folder> --cluster <slug>" in out
    assert 'research-hub auto "your topic" --no-nlm' in out
    assert "research-hub serve --dashboard" in out
    assert "research-hub install --mcp" not in out


def test_init_detects_existing_obsidian_vault(tmp_path, capsys):
    from research_hub.init_wizard import _detect_existing_obsidian_vault

    vault = tmp_path / "my-vault"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    (vault / "note1.md").write_text("# Note", encoding="utf-8")
    (vault / "note2.md").write_text("# Note", encoding="utf-8")

    _detect_existing_obsidian_vault(vault)
    out = capsys.readouterr().out
    assert "Found existing Obsidian vault" in out
    assert "2 .md files detected" in out
    assert "Nothing is overwritten" in out


def test_init_skips_existing_vault_message_for_fresh_path(tmp_path, capsys):
    from research_hub.init_wizard import _detect_existing_obsidian_vault

    vault = tmp_path / "fresh-vault"
    vault.mkdir()
    _detect_existing_obsidian_vault(vault)
    assert capsys.readouterr().out == ""


def test_require_config_raises_when_no_config(monkeypatch, capsys):
    monkeypatch.setattr("research_hub.config._resolve_config_path", lambda: None)
    from research_hub.config import require_config

    with pytest.raises(SystemExit) as exc:
        require_config()
    err = capsys.readouterr().err
    assert exc.value.code == 1
    assert "not initialized" in err.lower()
    assert "research-hub init" in err


def test_require_config_succeeds_when_config_exists(tmp_path, monkeypatch):
    _reset_config_cache()
    config = tmp_path / "config.json"
    vault = tmp_path / "vault"
    (vault / "raw").mkdir(parents=True)
    (vault / "hub").mkdir(parents=True)
    (vault / ".research_hub").mkdir(parents=True)
    config.write_text(json.dumps({"knowledge_base": {"root": str(vault)}}), encoding="utf-8")
    monkeypatch.setattr("research_hub.config._resolve_config_path", lambda: config)

    from research_hub.config import require_config

    cfg = require_config()
    assert cfg.root == vault


def test_get_config_still_works_as_fallback(tmp_path, monkeypatch):
    _reset_config_cache()
    monkeypatch.setattr("research_hub.config._resolve_config_path", lambda: None)
    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(tmp_path / "fallback-vault"))
    cfg = get_config()
    assert cfg is not None
    assert cfg.root == tmp_path / "fallback-vault"


def test_cli_add_before_init_shows_error(monkeypatch, capsys):
    monkeypatch.setattr("research_hub.config._resolve_config_path", lambda: None)
    from research_hub import cli

    with pytest.raises(SystemExit):
        cli.main(["add", "10.1234/test", "--cluster", "test"])
    err = capsys.readouterr().err
    assert "not initialized" in err.lower()
    assert "research-hub init" in err


def test_cli_init_exempt_from_require_config(monkeypatch):
    monkeypatch.setattr("research_hub.config.require_config", lambda: (_ for _ in ()).throw(AssertionError))
    from research_hub.cli import build_parser

    args = build_parser().parse_args(["init"])
    assert args.command == "init"


def test_cli_doctor_exempt_from_require_config(monkeypatch):
    monkeypatch.setattr("research_hub.config.require_config", lambda: (_ for _ in ()).throw(AssertionError))
    from research_hub.cli import build_parser

    args = build_parser().parse_args(["doctor"])
    assert args.command == "doctor"


def test_build_parser_accepts_install_mcp_and_where():
    from research_hub.cli import build_parser

    args = build_parser().parse_args(["install", "--mcp"])
    assert args.command == "install"
    assert args.mcp is True

    args = build_parser().parse_args(["where"])
    assert args.command == "where"


def test_install_mcp_writes_claude_config(tmp_path, capsys):
    from research_hub.cli import _install_mcp

    config_path = tmp_path / "Claude" / "claude_desktop_config.json"
    rc = _install_mcp(config_path)
    out = capsys.readouterr().out
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert rc == 0
    assert data["mcpServers"]["research-hub"]["command"] == "research-hub"
    assert data["mcpServers"]["research-hub"]["args"] == ["serve"]
    assert "MCP server added" in out


def test_install_mcp_preserves_existing_servers(tmp_path):
    from research_hub.cli import _install_mcp

    config_path = tmp_path / "Claude" / "claude_desktop_config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps({"mcpServers": {"other-tool": {"command": "other"}}}),
        encoding="utf-8",
    )

    _install_mcp(config_path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "other-tool" in data["mcpServers"]
    assert "research-hub" in data["mcpServers"]


def test_install_mcp_skips_if_already_configured(tmp_path, capsys):
    from research_hub.cli import _install_mcp

    config_path = tmp_path / "Claude" / "claude_desktop_config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps({"mcpServers": {"research-hub": {"command": "research-hub", "args": ["serve"]}}}),
        encoding="utf-8",
    )

    before = config_path.read_text(encoding="utf-8")
    _install_mcp(config_path)
    out = capsys.readouterr().out
    after = config_path.read_text(encoding="utf-8")
    assert "already configured" in out
    assert before == after


def test_doctor_header_shows_config_and_vault_paths(tmp_path, capsys, monkeypatch):
    from research_hub.doctor import run_doctor

    config = tmp_path / "config.json"
    vault = tmp_path / "vault"
    (vault / "raw").mkdir(parents=True)
    (vault / "hub").mkdir(parents=True)
    (vault / ".research_hub").mkdir(parents=True)
    config.write_text(
        json.dumps({"knowledge_base": {"root": str(vault)}, "no_zotero": True}),
        encoding="utf-8",
    )
    monkeypatch.setattr("research_hub.config._resolve_config_path", lambda: config)
    _reset_config_cache()
    monkeypatch.setitem(
        sys.modules,
        "research_hub.doctor_field",
        SimpleNamespace(field_inference_check=lambda cfg: []),
    )
    monkeypatch.setitem(
        sys.modules,
        "research_hub.notebooklm.cdp_launcher",
        SimpleNamespace(find_chrome_binary=lambda: None),
    )
    monkeypatch.setattr(
        "research_hub.doctor.check_frontmatter_completeness",
        lambda cfg: SimpleNamespace(name="frontmatter", status="OK", message="ok", remedy=""),
    )

    run_doctor()
    out = capsys.readouterr().out
    assert "research-hub health check" in out
    assert f"Config:  {config}" in out
    assert f"Vault:   {vault}" in out


def test_doctor_header_shows_not_found_when_no_config(capsys, monkeypatch):
    from research_hub.doctor import run_doctor

    monkeypatch.setattr("research_hub.config._resolve_config_path", lambda: None)
    _reset_config_cache()
    monkeypatch.setitem(
        sys.modules,
        "research_hub.doctor_field",
        SimpleNamespace(field_inference_check=lambda cfg: []),
    )
    monkeypatch.setitem(
        sys.modules,
        "research_hub.notebooklm.cdp_launcher",
        SimpleNamespace(find_chrome_binary=lambda: None),
    )
    monkeypatch.setattr(
        "research_hub.doctor.check_frontmatter_completeness",
        lambda cfg: SimpleNamespace(name="frontmatter", status="OK", message="ok", remedy=""),
    )

    run_doctor()
    out = capsys.readouterr().out
    assert "Config:  (not found - run: research-hub init)" in out
    assert "Vault:   (unknown)" in out


def test_where_command_shows_vault_path(tmp_path, capsys, monkeypatch):
    cfg = _StubConfig(tmp_path / "vault")
    monkeypatch.setattr("research_hub.config._resolve_config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.cli._get_claude_desktop_config_path", lambda: tmp_path / "claude.json")

    from research_hub import cli

    result = cli.main(["where"])
    out = capsys.readouterr().out
    assert result == 0
    assert str(cfg.root) in out


def test_where_command_shows_note_count(tmp_path, capsys, monkeypatch):
    cfg = _StubConfig(tmp_path / "vault")
    cluster_dir = cfg.raw / "my-cluster"
    cluster_dir.mkdir(parents=True)
    (cluster_dir / "paper1.md").write_text("---\ntitle: P1\n---\n", encoding="utf-8")
    (cluster_dir / "paper2.md").write_text("---\ntitle: P2\n---\n", encoding="utf-8")
    monkeypatch.setattr("research_hub.config._resolve_config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.cli._get_claude_desktop_config_path", lambda: tmp_path / "claude.json")

    from research_hub import cli

    cli.main(["where"])
    out = capsys.readouterr().out
    assert "2 papers" in out


def test_where_command_works_without_init(capsys, monkeypatch):
    monkeypatch.setattr("research_hub.config._resolve_config_path", lambda: None)
    from research_hub import cli

    result = cli.main(["where"])
    out = capsys.readouterr().out
    assert "not found" in out.lower() or "not configured" in out.lower()
    assert result == 1


def test_where_shows_mcp_status(tmp_path, capsys, monkeypatch):
    cfg = _StubConfig(tmp_path / "vault")
    mcp_config = tmp_path / "Claude" / "claude_desktop_config.json"
    mcp_config.parent.mkdir(parents=True)
    mcp_config.write_text(
        json.dumps({"mcpServers": {"research-hub": {"command": "research-hub", "args": ["serve"]}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("research_hub.config._resolve_config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.cli._get_claude_desktop_config_path", lambda: mcp_config)

    from research_hub import cli

    cli.main(["where"])
    out = capsys.readouterr().out
    assert "MCP:" in out
    assert "configured" in out


def test_where_shows_dashboard_and_cluster_folders(tmp_path, capsys, monkeypatch):
    cfg = _StubConfig(tmp_path / "vault")
    dashboard = cfg.research_hub_dir / "dashboard.html"
    dashboard.write_text("<html></html>", encoding="utf-8")
    cluster_dir = cfg.raw / "cluster-a"
    topics_dir = cluster_dir / "topics"
    topics_dir.mkdir(parents=True)
    (cluster_dir / "paper.md").write_text("# Paper", encoding="utf-8")
    (topics_dir / "topic.md").write_text("# Topic", encoding="utf-8")
    monkeypatch.setattr("research_hub.config._resolve_config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.cli._get_claude_desktop_config_path", lambda: tmp_path / "claude.json")

    from research_hub import cli

    cli.main(["where"])
    out = capsys.readouterr().out
    assert "Dashboard:" in out
    assert "raw/cluster-a/" in out
    assert "+ 1 sub-topics" in out

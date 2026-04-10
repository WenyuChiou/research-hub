"""Tests for hub_config.py - path loading, env var override, defaults."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_config_loads_from_file(tmp_path, monkeypatch):
    """get_config() reads knowledge_base.root from config.json."""
    import hub_config

    hub_config._config = None

    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps(
            {
                "knowledge_base": {
                    "root": str(tmp_path / "kb"),
                    "raw": str(tmp_path / "kb" / "raw"),
                    "hub": str(tmp_path / "kb" / "hub"),
                    "projects": str(tmp_path / "kb" / "projects"),
                    "logs": str(tmp_path / "kb" / "logs"),
                    "obsidian_graph": str(tmp_path / "kb" / ".obsidian" / "graph.json"),
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(hub_config, "CONFIG_PATH", cfg_file)
    cfg = hub_config.get_config()

    assert cfg.root == tmp_path / "kb"
    assert cfg.raw == tmp_path / "kb" / "raw"
    assert cfg.hub == tmp_path / "kb" / "hub"


def test_config_env_var_override(tmp_path, monkeypatch):
    """RESEARCH_HUB_ROOT env var overrides config file."""
    import hub_config

    hub_config._config = None

    monkeypatch.setattr(hub_config, "CONFIG_PATH", tmp_path / "nonexistent.json")
    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(tmp_path / "env-kb"))
    monkeypatch.delenv("RESEARCH_HUB_RAW", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_HUB", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_PROJECTS", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_LOGS", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_GRAPH", raising=False)

    cfg = hub_config.get_config()
    assert cfg.root == tmp_path / "env-kb"
    assert cfg.raw == tmp_path / "env-kb" / "raw"


def test_config_tilde_expansion(tmp_path, monkeypatch):
    """Paths with ~ are expanded to absolute paths."""
    import hub_config

    hub_config._config = None

    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps({"knowledge_base": {"root": "~/knowledge-base"}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(hub_config, "CONFIG_PATH", cfg_file)
    cfg = hub_config.get_config()

    assert not str(cfg.root).startswith("~")
    assert cfg.root.is_absolute()


def test_config_logs_dir_created(tmp_path, monkeypatch):
    """logs directory is auto-created on config load."""
    import hub_config

    hub_config._config = None

    cfg_file = tmp_path / "config.json"
    logs_dir = tmp_path / "mylogs"
    cfg_file.write_text(
        json.dumps(
            {
                "knowledge_base": {
                    "root": str(tmp_path / "kb"),
                    "logs": str(logs_dir),
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(hub_config, "CONFIG_PATH", cfg_file)
    hub_config.get_config()

    assert logs_dir.exists()
    assert logs_dir.is_dir()

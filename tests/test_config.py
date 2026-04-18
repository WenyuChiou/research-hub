"""Tests for hub_config.py - path loading, env var override, defaults."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_config_resolution(tmp_path, monkeypatch):
    from research_hub import config as hub_config

    hub_config._config = None
    hub_config._config_path = None
    monkeypatch.delenv("RESEARCH_HUB_CONFIG", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_ROOT", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_RAW", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_HUB", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_PROJECTS", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_LOGS", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_GRAPH", raising=False)
    monkeypatch.delenv("ZOTERO_LIBRARY_ID", raising=False)
    monkeypatch.delenv("ZOTERO_LIBRARY_TYPE", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_DEFAULT_COLLECTION", raising=False)
    monkeypatch.setattr(hub_config, "CONFIG_PATH", tmp_path / "missing-legacy-config.json")
    monkeypatch.setattr(hub_config.platformdirs, "user_config_dir", lambda *args, **kwargs: str(tmp_path / "missing-platformdirs"))


def test_config_loads_from_file(tmp_path, monkeypatch):
    """get_config() reads knowledge_base.root from config.json."""
    from research_hub import config as hub_config

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
    from research_hub import config as hub_config

    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(tmp_path / "env-kb"))

    cfg = hub_config.get_config()
    assert cfg.root == tmp_path / "env-kb"
    assert cfg.raw == tmp_path / "env-kb" / "raw"


def test_config_tilde_expansion(tmp_path, monkeypatch):
    """Paths with ~ are expanded to absolute paths."""
    from research_hub import config as hub_config

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
    from research_hub import config as hub_config

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


def test_zotero_config_from_json(tmp_path, monkeypatch):
    """Zotero settings load from config.json."""
    from research_hub import config as hub_config

    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps(
            {
                "knowledge_base": {"root": str(tmp_path / "kb")},
                "zotero": {
                    "library_id": "12345678",
                    "library_type": "user",
                    "default_collection": "ABCD1234",
                    "collections": {
                        "ABCD1234": {
                            "name": "Survey Papers",
                            "parent": None,
                            "section": "survey",
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(hub_config, "CONFIG_PATH", cfg_file)
    cfg = hub_config.get_config()

    assert cfg.zotero_library_id == "12345678"
    assert cfg.zotero_default_collection == "ABCD1234"
    assert cfg.zotero_collections == {
        "ABCD1234": {
            "name": "Survey Papers",
            "parent": None,
            "section": "survey",
        }
    }


def test_zotero_library_id_from_env(tmp_path, monkeypatch):
    """ZOTERO_LIBRARY_ID env var is used when config.json has no zotero section."""
    from research_hub import config as hub_config

    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps({"knowledge_base": {"root": str(tmp_path / "kb")}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(hub_config, "CONFIG_PATH", cfg_file)
    monkeypatch.setenv("ZOTERO_LIBRARY_ID", "env-library-id")
    cfg = hub_config.get_config()

    assert cfg.zotero_library_id == "env-library-id"


def test_zotero_collections_default_empty(tmp_path, monkeypatch):
    """Zotero config defaults to empty collections and no library ID."""
    from research_hub import config as hub_config

    monkeypatch.setattr(hub_config, "CONFIG_PATH", tmp_path / "nonexistent.json")

    cfg = hub_config.get_config()

    assert cfg.zotero_collections == {}
    assert cfg.zotero_library_id is None


def test_resolve_config_path_env_override(tmp_path, monkeypatch):
    from research_hub import config as hub_config

    cfg_file = tmp_path / "env-config.json"
    cfg_file.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("RESEARCH_HUB_CONFIG", str(cfg_file))

    assert hub_config._resolve_config_path() == cfg_file


def test_resolve_config_path_platformdirs_fallback(tmp_path, monkeypatch):
    from research_hub import config as hub_config

    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(hub_config.platformdirs, "user_config_dir", lambda *args, **kwargs: str(tmp_path))

    assert hub_config._resolve_config_path() == cfg_file


def test_resolve_config_path_legacy_claude_path(tmp_path, monkeypatch):
    from research_hub import config as hub_config

    legacy_home = tmp_path / "home"
    legacy_config = legacy_home / ".claude" / "skills" / "knowledge-base" / "config.json"
    legacy_config.parent.mkdir(parents=True)
    legacy_config.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: legacy_home))
    monkeypatch.setattr(
        hub_config,
        "CONFIG_PATH",
        Path.home() / ".claude" / "skills" / "knowledge-base" / "config.json",
    )

    assert hub_config._resolve_config_path() == legacy_config


def test_resolve_config_path_returns_none_when_nothing_exists(tmp_path, monkeypatch):
    from research_hub import config as hub_config

    monkeypatch.setattr(hub_config, "CONFIG_PATH", tmp_path / "missing.json")

    assert hub_config._resolve_config_path() is None


def test_get_config_works_with_no_config_file(tmp_path, monkeypatch):
    from research_hub import config as hub_config

    monkeypatch.setattr(hub_config, "CONFIG_PATH", tmp_path / "missing.json")

    cfg = hub_config.get_config()

    assert cfg.root == Path.home() / "knowledge-base"
    assert cfg.raw == cfg.root / "raw"
    assert cfg.hub == cfg.root / "hub"


def test_require_config_accepts_research_hub_root_env_var(tmp_path, monkeypatch):
    """REGRESSION (v0.37): require_config must treat RESEARCH_HUB_ROOT as a valid
    init signal, not just config.json existence. Without this, headless / CI
    / test environments that bootstrap via env vars hit a misleading
    'not initialized' SystemExit even though HubConfig honors the env var fully.
    Originally surfaced via test_v032_screenshot.py CI failure on GitHub Actions.
    """
    from research_hub import config as hub_config

    monkeypatch.setattr(hub_config, "CONFIG_PATH", tmp_path / "no-config.json")
    monkeypatch.delenv("RESEARCH_HUB_CONFIG", raising=False)
    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(tmp_path))
    monkeypatch.setenv("RESEARCH_HUB_ALLOW_EXTERNAL_ROOT", "1")
    hub_config._config = None
    hub_config._config_path = None

    cfg = hub_config.require_config()
    assert cfg.root == tmp_path


def test_require_config_still_fails_when_root_dir_missing(tmp_path, monkeypatch):
    """RESEARCH_HUB_ROOT must point to an existing directory; bogus paths still fail."""
    import pytest
    from research_hub import config as hub_config

    monkeypatch.setattr(hub_config, "CONFIG_PATH", tmp_path / "no-config.json")
    monkeypatch.delenv("RESEARCH_HUB_CONFIG", raising=False)
    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(tmp_path / "nonexistent-vault"))
    hub_config._config = None
    hub_config._config_path = None

    with pytest.raises(SystemExit):
        hub_config.require_config()


def test_require_config_fails_when_no_config_and_no_env(tmp_path, monkeypatch):
    """Neither config.json nor RESEARCH_HUB_ROOT -> SystemExit (original guard preserved)."""
    import pytest
    from research_hub import config as hub_config

    monkeypatch.setattr(hub_config, "CONFIG_PATH", tmp_path / "no-config.json")
    monkeypatch.delenv("RESEARCH_HUB_CONFIG", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_ROOT", raising=False)
    hub_config._config = None
    hub_config._config_path = None

    with pytest.raises(SystemExit):
        hub_config.require_config()

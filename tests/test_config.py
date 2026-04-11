"""Tests for hub_config.py - path loading, env var override, defaults."""

import json


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
    from research_hub import config as hub_config

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
    from research_hub import config as hub_config

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


def test_zotero_config_from_json(tmp_path, monkeypatch):
    """Zotero settings load from config.json."""
    from research_hub import config as hub_config

    hub_config._config = None

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
    monkeypatch.delenv("ZOTERO_LIBRARY_ID", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_DEFAULT_COLLECTION", raising=False)

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

    hub_config._config = None

    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps({"knowledge_base": {"root": str(tmp_path / "kb")}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(hub_config, "CONFIG_PATH", cfg_file)
    monkeypatch.setenv("ZOTERO_LIBRARY_ID", "env-library-id")
    monkeypatch.delenv("RESEARCH_HUB_DEFAULT_COLLECTION", raising=False)

    cfg = hub_config.get_config()

    assert cfg.zotero_library_id == "env-library-id"


def test_zotero_collections_default_empty(tmp_path, monkeypatch):
    """Zotero config defaults to empty collections and no library ID."""
    from research_hub import config as hub_config

    hub_config._config = None

    monkeypatch.setattr(hub_config, "CONFIG_PATH", tmp_path / "nonexistent.json")
    monkeypatch.delenv("ZOTERO_LIBRARY_ID", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_DEFAULT_COLLECTION", raising=False)

    cfg = hub_config.get_config()

    assert cfg.zotero_collections == {}
    assert cfg.zotero_library_id is None

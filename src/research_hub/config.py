"""Portable config loader for the Research Hub pipeline."""

from __future__ import annotations

import json
import os
from pathlib import Path

# Config search order: (1) repo-local config.json, (2) ~/.claude skill config, (3) env vars, (4) HOME defaults
_REPO_CONFIG = Path(__file__).resolve().parents[2] / "config.json"
# CONFIG_PATH kept for backward-compat (tests monkeypatch this attribute directly)
CONFIG_PATH = Path.home() / ".claude" / "skills" / "knowledge-base" / "config.json"


def _resolve_config_path() -> Path | None:
    """Return the first config.json that exists: repo-local first, then skill config."""
    if _REPO_CONFIG.exists():
        return _REPO_CONFIG
    if CONFIG_PATH.exists():
        return CONFIG_PATH
    return None


class HubConfig:
    """Resolve Research Hub paths from config, env vars, or HOME defaults."""

    def __init__(self) -> None:
        config_root: str | None = None
        config_raw: str | None = None
        config_hub: str | None = None
        config_projects: str | None = None
        config_logs: str | None = None
        config_graph: str | None = None

        config_path = _resolve_config_path()
        if config_path is not None:
            with config_path.open(encoding="utf-8") as file_obj:
                data = json.load(file_obj)
            knowledge_base = data.get("knowledge_base", {})
            config_root = knowledge_base.get("root")
            config_raw = knowledge_base.get("raw")
            config_hub = knowledge_base.get("hub")
            config_projects = knowledge_base.get("projects")
            config_logs = knowledge_base.get("logs")
            config_graph = knowledge_base.get("obsidian_graph")

        raw_root = config_root or os.environ.get("RESEARCH_HUB_ROOT")
        raw_path = config_raw or os.environ.get("RESEARCH_HUB_RAW")
        hub_path = config_hub or os.environ.get("RESEARCH_HUB_HUB")
        projects_path = config_projects or os.environ.get("RESEARCH_HUB_PROJECTS")
        logs_path = config_logs or os.environ.get("RESEARCH_HUB_LOGS")
        graph_path = config_graph or os.environ.get("RESEARCH_HUB_GRAPH")

        if not raw_root:
            raw_root = str(Path.home() / "knowledge-base")

        self.root = Path(raw_root).expanduser()
        self.raw = Path(raw_path).expanduser() if raw_path else self.root / "raw"
        self.hub = Path(hub_path).expanduser() if hub_path else self.root / "hub"
        self.projects = (
            Path(projects_path).expanduser() if projects_path else self.root / "projects"
        )
        self.logs = Path(logs_path).expanduser() if logs_path else self.root / "logs"
        self.graph_json = (
            Path(graph_path).expanduser()
            if graph_path
            else self.root / ".obsidian" / "graph.json"
        )

        self.logs.mkdir(parents=True, exist_ok=True)


_config: HubConfig | None = None


def get_config() -> HubConfig:
    """Return a cached HubConfig instance."""

    global _config
    if _config is None:
        _config = HubConfig()
    return _config

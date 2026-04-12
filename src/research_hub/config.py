"""Portable config loader for the Research Hub pipeline."""

from __future__ import annotations

import json
import os
from pathlib import Path
import platformdirs

CONFIG_PATH = Path.home() / ".claude" / "skills" / "knowledge-base" / "config.json"


def _resolve_config_path() -> Path | None:
    """Find the config file in priority order."""

    env = os.environ.get("RESEARCH_HUB_CONFIG")
    if env:
        env_path = Path(env).expanduser()
        if env_path.exists():
            return env_path

    platformdirs_path = (
        Path(platformdirs.user_config_dir("research-hub", ensure_exists=False)) / "config.json"
    )
    if platformdirs_path.exists():
        return platformdirs_path

    legacy_path = CONFIG_PATH
    if legacy_path.exists():
        return legacy_path

    repo_candidate = Path(__file__).resolve().parents[2] / "config.json"
    if repo_candidate.exists() and (repo_candidate.parent / "pyproject.toml").exists():
        return repo_candidate

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
        config_clusters_file: str | None = None
        config_zotero_library_id: str | None = None
        config_zotero_library_type: str | None = None
        config_zotero_default_collection: str | None = None
        config_zotero_collections: dict[str, dict] = {}

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
            config_clusters_file = data.get("clusters_file")
            zotero = data.get("zotero", {})
            config_zotero_library_id = zotero.get("library_id")
            config_zotero_library_type = zotero.get("library_type")
            config_zotero_default_collection = zotero.get("default_collection")
            config_zotero_collections = zotero.get("collections", {})

        raw_root = config_root or os.environ.get("RESEARCH_HUB_ROOT")
        raw_path = config_raw or os.environ.get("RESEARCH_HUB_RAW")
        hub_path = config_hub or os.environ.get("RESEARCH_HUB_HUB")
        projects_path = config_projects or os.environ.get("RESEARCH_HUB_PROJECTS")
        logs_path = config_logs or os.environ.get("RESEARCH_HUB_LOGS")
        graph_path = config_graph or os.environ.get("RESEARCH_HUB_GRAPH")
        zotero_library_id = config_zotero_library_id or os.environ.get("ZOTERO_LIBRARY_ID")
        zotero_default_collection = config_zotero_default_collection or os.environ.get(
            "RESEARCH_HUB_DEFAULT_COLLECTION"
        )

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
        self.research_hub_dir = self.root / ".research_hub"
        self.clusters_file = (
            Path(config_clusters_file).expanduser()
            if config_clusters_file
            else self.research_hub_dir / "clusters.yaml"
        )
        self.zotero_library_id = zotero_library_id
        self.zotero_library_type = config_zotero_library_type or os.environ.get(
            "ZOTERO_LIBRARY_TYPE", "user"
        )
        self.zotero_default_collection = zotero_default_collection
        self.zotero_collections = config_zotero_collections if isinstance(
            config_zotero_collections, dict
        ) else {}

        self.logs.mkdir(parents=True, exist_ok=True)
        try:
            self.research_hub_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            pass


_config: HubConfig | None = None
_config_path: Path | None = None


def get_config() -> HubConfig:
    """Return a cached HubConfig instance."""

    global _config, _config_path
    resolved_path = _resolve_config_path()
    if _config is None or _config_path != resolved_path:
        _config = HubConfig()
        _config_path = resolved_path
    return _config

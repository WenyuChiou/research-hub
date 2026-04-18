"""Build a .dxt archive for Claude Desktop one-click install."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path


def _manifest(version: str) -> dict[str, object]:
    return {
        "dxt_version": "0.1",
        "name": "research-hub",
        "display_name": "Research Hub",
        "version": version,
        "description": "Zotero + Obsidian + NotebookLM pipeline for AI agents",
        "author": {"name": "Wenyu Chiou"},
        "server": {
            "type": "python",
            "entry_point": "research_hub.mcp_server",
            "mcp_config": {"command": "python", "args": ["-m", "research_hub.mcp_server"]},
        },
    }


def build_dxt(out_path: Path, version: str) -> Path:
    """Build research-hub.dxt at out_path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(_manifest(version), indent=2))
    return out_path.resolve()

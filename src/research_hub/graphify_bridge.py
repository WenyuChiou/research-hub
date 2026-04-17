"""graphify_bridge: parse graphify-out/graph.json for sub-topic assignment.

graphify is an external coding-skill (https://github.com/safishamsi/graphify)
that runs inside Claude Code / Codex / etc. It cannot be invoked as a
standalone CLI for first-time extraction.

v0.32 redesign: instead of trying to subprocess graphify, accept a pre-built
graph.json path. Workflow:

  Step 1 (user, via Claude Code): /graphify ./project
                                  (produces ./graphify-out/graph.json)
  Step 2 (research-hub):
    research-hub import-folder ./project --cluster X \
                  --graphify-graph ./graphify-out/graph.json
"""
from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path

logger = logging.getLogger(__name__)


class GraphifyNotInstalled(RuntimeError):
    """DEPRECATED in v0.32. Kept for backward compat with v0.31 imports.

    v0.31 used this when subprocess invocation of `graphify` failed. v0.32+
    no longer attempts subprocess invocation because graphify is a coding-skill,
    not a standalone CLI. Users supply pre-built graph.json paths instead.
    """


def find_graphify_binary() -> str | None:
    """DEPRECATED in v0.32. Always returns None now.

    Kept for backward-compat imports. Use `--graphify-graph PATH` instead.
    """
    warnings.warn(
        "find_graphify_binary() is deprecated in v0.32. graphify is a coding-skill, "
        "not a standalone CLI. Provide a pre-built graph.json via --graphify-graph.",
        DeprecationWarning,
        stacklevel=2,
    )
    return None


def run_graphify(
    folder: Path,
    *,
    output_dir: Path | None = None,
    timeout: float = 600.0,
) -> Path:
    """DEPRECATED in v0.32. Always raises GraphifyNotInstalled.

    graphify cannot be invoked as a standalone CLI. Users must run /graphify
    in Claude Code (or equivalent) to produce graph.json, then pass that path
    to research-hub via --graphify-graph.
    """
    del folder, output_dir, timeout
    warnings.warn(
        "run_graphify() is deprecated in v0.32. Use --graphify-graph PATH "
        "with a pre-built graph.json from `/graphify` in Claude Code.",
        DeprecationWarning,
        stacklevel=2,
    )
    raise GraphifyNotInstalled(
        "graphify cannot be invoked as a standalone CLI. To use graphify "
        "with research-hub:\n"
        "  1. Inside Claude Code (or any AI assistant where graphify is installed):\n"
        "     /graphify ./project\n"
        "     (produces ./graphify-out/graph.json)\n"
        "  2. Then run:\n"
        "     research-hub import-folder ./project --cluster X "
        "--graphify-graph ./graphify-out/graph.json"
    )


def parse_graphify_communities(graph_json: Path) -> dict[str, list[str]]:
    """Parse graphify's graph.json. Return {community_label: [file_path, ...]}."""
    data = json.loads(Path(graph_json).read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])
    community_names = data.get("communities", {}) or {}

    by_community: dict[str, list[str]] = {}
    for node in nodes:
        community_id = node.get("community")
        source_file = (
            node.get("source_file")
            or node.get("file")
            or node.get("path")
        )
        if community_id is None or not source_file:
            continue
        label = community_names.get(str(community_id)) or f"community-{community_id}"
        by_community.setdefault(label, [])
        if source_file not in by_community[label]:
            by_community[label].append(source_file)

    return by_community


def map_to_subtopics(
    communities: dict[str, list[str]],
    imported_files: list[Path],
) -> dict[str, list[str]]:
    """Match graphify's communities to research-hub's imported files."""
    imported_strs = {str(Path(path).resolve()): str(path) for path in imported_files}
    assignments: dict[str, list[str]] = {original: [] for original in imported_strs.values()}

    for community_label, source_files in communities.items():
        for src in source_files:
            src_resolved = str(Path(src).resolve())
            if src_resolved in imported_strs:
                original = imported_strs[src_resolved]
                if community_label not in assignments[original]:
                    assignments[original].append(community_label)

    return assignments


__all__ = [
    "GraphifyNotInstalled",
    "find_graphify_binary",
    "run_graphify",
    "parse_graphify_communities",
    "map_to_subtopics",
]

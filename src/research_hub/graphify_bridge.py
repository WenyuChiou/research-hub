"""Invoke external graphify CLI and parse its output.

graphify (safishamsi/graphify) is an external multi-modal extraction +
community detection tool. We invoke it via subprocess when the user passes
--use-graphify to research-hub import-folder, then parse its graph.json
output to suggest sub-topic assignments.

graphify is NOT a pyproject.toml dep; user installs separately:
    pip install graphifyy && graphify install
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class GraphifyNotInstalled(RuntimeError):
    """graphify CLI binary not on PATH."""


def find_graphify_binary() -> str | None:
    """Return path to graphify binary or None if not installed."""
    return shutil.which("graphify")


def run_graphify(
    folder: Path,
    *,
    output_dir: Path | None = None,
    timeout: float = 600.0,
) -> Path:
    """Invoke `graphify <folder>` and return path to graphify-out/graph.json.

    Raises:
        GraphifyNotInstalled: if `graphify` is not on PATH
        subprocess.CalledProcessError: if graphify exits non-zero
        FileNotFoundError: if expected graph.json is missing after the run
    """
    binary = find_graphify_binary()
    if not binary:
        raise GraphifyNotInstalled(
            "graphify CLI not found on PATH.\n"
            "  Install: pip install graphifyy && graphify install\n"
            "  Or omit --use-graphify to use lightweight extractors only."
        )

    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise ValueError(f"folder not a directory: {folder}")

    cwd = Path(output_dir).resolve() if output_dir is not None else folder
    cmd = [binary, str(folder)]
    logger.info("running graphify: %s", " ".join(cmd))

    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode,
            cmd,
            output=proc.stdout,
            stderr=proc.stderr,
        )

    graph_json = cwd / "graphify-out" / "graph.json"
    if not graph_json.exists():
        raise FileNotFoundError(
            f"expected {graph_json} after graphify run; "
            f"stdout: {proc.stdout[-500:]}\nstderr: {proc.stderr[-500:]}"
        )
    return graph_json


def parse_graphify_communities(graph_json: Path) -> dict[str, list[str]]:
    """Parse graphify graph.json as {community_label: [file_path, ...]}."""
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
    """Match graphify's communities to imported files.

    Returns {imported_file_str: [subtopic_label, ...]}.
    """
    imported_strs = {str(Path(path).resolve()): str(path) for path in imported_files}
    assignments: dict[str, list[str]] = {
        original: [] for original in imported_strs.values()
    }

    for community_label, source_files in communities.items():
        for source_file in source_files:
            resolved_source = str(Path(source_file).resolve())
            if resolved_source not in imported_strs:
                continue
            original = imported_strs[resolved_source]
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

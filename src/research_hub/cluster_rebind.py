"""Cluster rebind: detect orphan papers and propose cluster bindings."""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from research_hub.security import safe_join

logger = logging.getLogger(__name__)


@dataclass
class RebindProposal:
    """A proposed move: paper file -> target cluster's obsidian_subfolder."""

    src: str
    dst: str
    reason: str
    confidence: str

    def to_dict(self) -> dict:
        return {
            "src": self.src,
            "dst": self.dst,
            "reason": self.reason,
            "confidence": self.confidence,
        }


@dataclass
class RebindResult:
    moved: list[RebindProposal] = field(default_factory=list)
    skipped: list[tuple[RebindProposal, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    log_path: str = ""


def emit_rebind_prompt(cfg) -> str:
    """Walk raw/, propose cluster bindings using frontmatter heuristics."""
    from research_hub.clusters import ClusterRegistry

    registry = ClusterRegistry(cfg.clusters_file)
    clusters = registry.list()

    bound_dirs = {(cluster.obsidian_subfolder or cluster.slug): cluster for cluster in clusters}
    by_zot_key = {cluster.zotero_collection_key: cluster for cluster in clusters if cluster.zotero_collection_key}
    by_slug = {cluster.slug: cluster for cluster in clusters}

    proposals: list[RebindProposal] = []
    raw_dir = Path(cfg.raw)
    for sub in raw_dir.iterdir() if raw_dir.exists() else []:
        if not sub.is_dir() or sub.name.startswith(".") or sub.name in {"pdfs", "attachments"}:
            continue
        if sub.name in bound_dirs:
            continue
        for md in sorted(sub.glob("*.md")):
            try:
                text = md.read_text(encoding="utf-8")
            except Exception:
                continue
            frontmatter = _parse_frontmatter(text)
            target = _propose_cluster(frontmatter, by_slug, by_zot_key, sub.name)
            if target is None:
                continue
            cluster, reason, confidence = target
            dst_dir = safe_join(Path(cfg.raw), cluster.obsidian_subfolder or cluster.slug)
            proposals.append(
                RebindProposal(
                    src=str(md.resolve()),
                    dst=str(safe_join(dst_dir, md.name)),
                    reason=reason,
                    confidence=confidence,
                )
            )

    return _render_report(cfg, clusters, proposals)


def apply_rebind(cfg, report_path: Path, *, dry_run: bool = True) -> RebindResult:
    """Read JSON moves from report and execute file moves."""
    result = RebindResult()
    moves = _parse_proposals(report_path)

    log_dir = safe_join(Path(cfg.root), ".research_hub")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"rebind-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"

    for prop in moves:
        src = Path(prop.src)
        dst = Path(prop.dst)
        if not src.exists():
            result.skipped.append((prop, "src does not exist"))
            _append_log(log_path, f"SKIP: {src} -> {dst} [src does not exist]")
            continue
        if dst.exists():
            result.skipped.append((prop, "dst already exists"))
            _append_log(log_path, f"SKIP: {src} -> {dst} [dst already exists]")
            continue
        if dry_run:
            result.skipped.append((prop, "dry-run"))
            _append_log(log_path, f"DRY: {src} -> {dst} [{prop.confidence}: {prop.reason}]")
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            result.moved.append(prop)
            _append_log(log_path, f"MOVED: {src} -> {dst} [{prop.confidence}: {prop.reason}]")
        except Exception as exc:
            result.errors.append(f"{src}: {exc}")
            _append_log(log_path, f"ERROR: {src}: {exc}")

    if log_path.exists():
        result.log_path = str(log_path)
    return result


def _append_log(log_path: Path, line: str) -> None:
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _propose_cluster(fm: dict, by_slug: dict, by_zot_key: dict, folder_hint: str):
    """Heuristic priority: cluster/topic_cluster > collections > tags > category > folder name."""
    explicit = str(fm.get("cluster", "") or fm.get("topic_cluster", "") or "").strip()
    if explicit and explicit in by_slug:
        return (by_slug[explicit], "explicit cluster frontmatter field", "high")

    collections = fm.get("collections")
    if isinstance(collections, list):
        for coll in collections:
            coll_str = str(coll).strip()
            if coll_str in by_zot_key:
                return (by_zot_key[coll_str], f"collections includes Zotero key {coll_str}", "high")

    tags = fm.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            tag_str = str(tag).strip()
            for slug in by_slug:
                if tag_str == slug or tag_str.endswith(f"/{slug}"):
                    return (by_slug[slug], f"tag matches cluster slug: {tag_str}", "medium")

    category = str(fm.get("category", "") or "").strip().lower()
    for slug, cluster in by_slug.items():
        if category and (category in slug or slug in category):
            return (cluster, f"category={category!r} matches cluster slug", "low")

    normalized_hint = folder_hint.replace("-", "").lower()
    for slug, cluster in by_slug.items():
        if folder_hint == slug or normalized_hint == slug.replace("-", "").lower():
            return (cluster, "folder name matches cluster slug", "low")

    return None


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    try:
        end = text.index("\n---", 3)
    except ValueError:
        return {}
    body = text[4:end]
    out: dict = {}
    for line in body.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            items = [item.strip().strip('"').strip("'") for item in inner.split(",") if item.strip()]
            out[key] = items
        elif val.startswith('"') and val.endswith('"'):
            out[key] = val[1:-1]
        else:
            out[key] = val
    return out


def _render_report(cfg, clusters: list, proposals: list[RebindProposal]) -> str:
    lines = [
        "# Cluster rebind proposal",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Vault: {cfg.root}",
        "",
        "## Summary",
        "",
        f"- Clusters: {len(clusters)}",
        f"- Proposed moves: {len(proposals)}",
        "",
    ]
    if proposals:
        lines.extend(
            [
                "## Proposed moves (review before applying)",
                "",
                "Apply with: `research-hub clusters rebind --apply <this-file> [--no-dry-run]`",
                "",
                "```json",
                json.dumps([proposal.to_dict() for proposal in proposals], indent=2, ensure_ascii=False),
                "```",
            ]
        )
    else:
        lines.append("No moves proposed. All papers are already bound or no heuristic matches were found.")
    return "\n".join(lines)


def _parse_proposals(report_path: Path) -> list[RebindProposal]:
    text = Path(report_path).read_text(encoding="utf-8")
    match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    if not match:
        return []
    data = json.loads(match.group(1))
    return [RebindProposal(**item) for item in data]

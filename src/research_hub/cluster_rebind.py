"""Cluster rebind: detect orphan papers and propose cluster bindings."""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from research_hub.clusters import score_cluster_match, slugify
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


@dataclass
class NewClusterProposal:
    """A proposed NEW cluster derived from a topic folder of orphan papers."""

    slug: str
    name: str
    seed_keywords: list[str]
    obsidian_subfolder: str
    paper_count: int
    source_folder: str

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "name": self.name,
            "seed_keywords": list(self.seed_keywords),
            "obsidian_subfolder": self.obsidian_subfolder,
            "paper_count": self.paper_count,
            "source_folder": self.source_folder,
        }


_AUTO_CREATE_THRESHOLD = 5


def emit_rebind_prompt(cfg) -> str:
    """Walk raw/, propose cluster bindings using frontmatter heuristics."""
    from research_hub.clusters import ClusterRegistry

    registry = ClusterRegistry(cfg.clusters_file)
    clusters = registry.list()

    bound_dirs = {(cluster.obsidian_subfolder or cluster.slug): cluster for cluster in clusters}
    by_zot_key = {cluster.zotero_collection_key: cluster for cluster in clusters if cluster.zotero_collection_key}
    by_slug = {cluster.slug: cluster for cluster in clusters}

    proposals: list[RebindProposal] = []
    unmatched_by_folder: dict[str, list[Path]] = {}
    orphan_count = 0
    raw_dir = Path(cfg.raw)
    for sub in raw_dir.iterdir() if raw_dir.exists() else []:
        if not sub.is_dir() or sub.name.startswith(".") or sub.name in {"pdfs", "attachments"}:
            continue
        if sub.name in bound_dirs:
            continue
        for md in sorted(sub.glob("*.md")):
            orphan_count += 1
            try:
                text = md.read_text(encoding="utf-8")
            except Exception:
                unmatched_by_folder.setdefault(sub.name, []).append(md)
                continue
            frontmatter = _parse_frontmatter(text)
            target = _propose_cluster(frontmatter, by_slug, by_zot_key, sub.name)
            if target is None:
                unmatched_by_folder.setdefault(sub.name, []).append(md)
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

    new_cluster_proposals = _propose_new_clusters_from_orphans(cfg, registry, unmatched_by_folder)
    return _render_report(cfg, clusters, proposals, new_cluster_proposals, orphan_count)


def apply_rebind(cfg, report_path: Path, *, dry_run: bool = True, auto_create_new: bool = False) -> RebindResult:
    """Read JSON moves from report and execute file moves."""
    from research_hub.clusters import ClusterRegistry

    result = RebindResult()
    moves = _parse_proposals(report_path)
    new_clusters = _parse_new_cluster_proposals(report_path) if auto_create_new else []

    log_dir = safe_join(Path(cfg.root), ".research_hub")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"rebind-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"

    if new_clusters:
        registry = ClusterRegistry(cfg.clusters_file)
        _apply_new_cluster_proposals(
            cfg,
            registry,
            new_clusters,
            result,
            log_path,
            dry_run=dry_run,
        )

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
    """Heuristic priority chain. Returns (cluster, reason, confidence) or None.

    Order is important: HIGH-confidence signals checked first, weak signals last.
    Each heuristic is a no-side-effect, pure function of frontmatter + cluster registry.
    """
    explicit = str(fm.get("cluster", "") or "").strip()
    if explicit and explicit in by_slug:
        return (by_slug[explicit], "explicit `cluster:` frontmatter field", "high")

    topic_cluster = str(fm.get("topic_cluster", "") or "").strip()
    desired_topic_cluster = topic_cluster.lower()
    if desired_topic_cluster:
        if desired_topic_cluster in by_slug:
            return (
                by_slug[desired_topic_cluster],
                "explicit `topic_cluster:` frontmatter field",
                "high",
            )
        tokens = {token for token in slugify(desired_topic_cluster).split("-") if token}
        best_cluster = None
        best_score = 0
        for cluster in by_slug.values():
            score = score_cluster_match(tokens, cluster)
            if score > best_score:
                best_score = score
                best_cluster = cluster
        if best_cluster is not None and best_score >= 2:
            return (best_cluster, f"fuzzy(from={desired_topic_cluster})", "high")

    collections = fm.get("collections")
    if isinstance(collections, list):
        for coll in collections:
            coll_str = str(coll).strip()
            if coll_str in by_zot_key:
                return (by_zot_key[coll_str], f"collections includes Zotero key {coll_str}", "high")

    if isinstance(collections, list):
        for coll in collections:
            coll_str = str(coll).strip()
            if not coll_str:
                continue
            coll_lower = coll_str.lower()
            for slug, cluster in by_slug.items():
                cluster_name = str(getattr(cluster, "name", "") or "").lower()
                if coll_lower == cluster_name:
                    return (cluster, f"collections name '{coll_str}' matches cluster name", "high")
                if cluster_name and (coll_lower in cluster_name or cluster_name in coll_lower):
                    return (cluster, f"collections name '{coll_str}' substring-matches cluster name", "medium")
                seed_keywords = list(getattr(cluster, "seed_keywords", []) or [])
                for kw in seed_keywords:
                    kw_lower = str(kw).strip().lower()
                    if kw_lower and len(kw_lower) >= 3 and (kw_lower in coll_lower or coll_lower in kw_lower):
                        return (cluster, f"collections name '{coll_str}' shares keyword '{kw_lower}'", "medium")

    tags = fm.get("tags")
    if isinstance(tags, list) and tags:
        tag_tokens: set[str] = set()
        for tag in tags:
            token = str(tag).strip().lower()
            if not token:
                continue
            token = token.split("/")[-1]
            for piece in re.split(r"[-_\s]+", token):
                if piece and len(piece) >= 2:
                    tag_tokens.add(piece)

        best_match = None
        best_score = 0.0
        for slug, cluster in by_slug.items():
            seeds = {str(k).strip().lower() for k in getattr(cluster, "seed_keywords", []) or [] if str(k).strip()}
            if not seeds or not tag_tokens:
                continue
            intersect = tag_tokens & seeds
            union = tag_tokens | seeds
            if not union:
                continue
            score = len(intersect) / len(union)
            if score > best_score:
                best_score = score
                best_match = (cluster, f"tag->seed_keywords Jaccard={score:.2f}")
        if best_match and best_score >= 0.5:
            cluster, reason = best_match
            return (cluster, reason, "medium")
        if best_match and best_score >= 0.3:
            cluster, reason = best_match
            return (cluster, reason, "low")

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

    for slug, cluster in by_slug.items():
        if folder_hint == slug or folder_hint.replace("-", "").lower() == slug.replace("-", "").lower():
            return (cluster, f"folder name matches cluster slug", "low")

    return None


def _propose_new_clusters_from_orphans(cfg, registry, unmatched_by_folder: dict[str, list[Path]]) -> list[NewClusterProposal]:
    """For each topic folder with >= threshold unmatched papers, propose a new cluster."""
    from collections import Counter

    proposals: list[NewClusterProposal] = []
    existing_slugs = {c.slug for c in registry.list()}
    for folder_name, paper_paths in unmatched_by_folder.items():
        if len(paper_paths) < _AUTO_CREATE_THRESHOLD:
            continue
        slug = re.sub(r"[^a-z0-9-]+", "-", folder_name.lower()).strip("-")
        if not slug or slug in existing_slugs:
            continue
        name = " ".join(part.capitalize() for part in folder_name.replace("-", " ").replace("_", " ").split())
        token_counts: Counter[str] = Counter()
        for paper_path in paper_paths:
            try:
                fm = _parse_frontmatter(paper_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for tag in (fm.get("tags") or []):
                token = str(tag).strip().lower()
                token = token.split("/")[-1]
                for piece in re.split(r"[-_\s]+", token):
                    if piece and len(piece) >= 3 and not piece.isdigit():
                        token_counts[piece] += 1
        seed_keywords = [tok for tok, _ in token_counts.most_common(5)] or [slug]
        proposals.append(
            NewClusterProposal(
                slug=slug,
                name=name,
                seed_keywords=seed_keywords,
                obsidian_subfolder=slug,
                paper_count=len(paper_paths),
                source_folder=folder_name,
            )
        )
    return proposals


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


def _render_report(
    cfg,
    clusters: list,
    proposals: list[RebindProposal],
    new_cluster_proposals: list[NewClusterProposal],
    orphan_count: int,
) -> str:
    lines = [
        "# Cluster rebind proposal",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Vault: {cfg.root}",
        "",
        "## Summary",
        "",
        f"- Clusters: {len(clusters)}",
        f"- Orphan papers scanned: {orphan_count}",
        f"- Proposed moves: {len(proposals)}",
        f"- New clusters proposed: {len(new_cluster_proposals)}",
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
    if new_cluster_proposals:
        lines.extend(
            [
                "",
                "## Proposed new clusters (opt-in; only applied with `--auto-create-new`)",
                "",
                "Apply with: `research-hub clusters rebind --apply <this-file> [--no-dry-run] --auto-create-new`",
                "",
                "new_cluster_proposals",
                "```json",
                json.dumps([proposal.to_dict() for proposal in new_cluster_proposals], indent=2, ensure_ascii=False),
                "```",
            ]
        )
    return "\n".join(lines)


def _parse_proposals(report_path: Path) -> list[RebindProposal]:
    text = Path(report_path).read_text(encoding="utf-8")
    match = re.search(r"## Proposed moves .*?```json\s*\n(.*?)\n```", text, re.DOTALL)
    if not match:
        return []
    data = json.loads(match.group(1))
    return [RebindProposal(**item) for item in data]


def _parse_new_cluster_proposals(report_path: Path) -> list[NewClusterProposal]:
    text = Path(report_path).read_text(encoding="utf-8")
    match = re.search(r"new_cluster_proposals\s*```json\s*\n(.*?)\n```", text, re.DOTALL)
    if not match:
        return []
    data = json.loads(match.group(1))
    return [NewClusterProposal(**item) for item in data]


def _apply_new_cluster_proposals(cfg, registry, proposals, result, log_path: Path, *, dry_run: bool) -> None:
    from research_hub.topic import scaffold_cluster_hub

    for proposal in proposals:
        cluster = registry.get(proposal.slug)
        if cluster is None:
            if dry_run:
                _append_log(log_path, f"DRY: create cluster {proposal.slug} from folder {proposal.source_folder}")
            else:
                cluster = registry.create(
                    query=proposal.name,
                    name=proposal.name,
                    slug=proposal.slug,
                    seed_keywords=proposal.seed_keywords,
                )
                try:
                    scaffold_cluster_hub(cfg, proposal.slug)
                except Exception as exc:
                    logger.warning("hub scaffold failed for new cluster %s: %s", proposal.slug, exc)
                _append_log(log_path, f"CREATED: cluster {proposal.slug} from folder {proposal.source_folder}")
        source_dir = safe_join(Path(cfg.raw), proposal.source_folder)
        target_dir_hint = Path(cfg.raw) / proposal.obsidian_subfolder
        target_dir = safe_join(Path(cfg.raw), proposal.obsidian_subfolder)
        source_files = sorted(source_dir.glob("*.md")) if source_dir.exists() else []

        if (
            source_dir.exists()
            and source_dir.name != proposal.obsidian_subfolder
            and source_dir.name.lower() == proposal.obsidian_subfolder.lower()
        ):
            if dry_run:
                for src in source_files:
                    prop = RebindProposal(
                        src=str(src.resolve()),
                        dst=str(target_dir_hint / src.name),
                        reason=f"auto-created cluster '{proposal.slug}' from folder '{proposal.source_folder}'",
                        confidence="medium",
                    )
                    result.skipped.append((prop, "dry-run"))
                    _append_log(log_path, f"DRY: {prop.src} -> {prop.dst} [{prop.confidence}: {prop.reason}]")
                continue
            temp_dir = source_dir.with_name(f"{source_dir.name}.__rebind_tmp__")
            try:
                shutil.move(str(source_dir), str(temp_dir))
                shutil.move(str(temp_dir), str(target_dir_hint))
                for dst in sorted(target_dir_hint.glob("*.md")):
                    result.moved.append(
                        RebindProposal(
                            src=str(safe_join(source_dir, dst.name)),
                            dst=str(dst.resolve()),
                            reason=f"auto-created cluster '{proposal.slug}' from folder '{proposal.source_folder}'",
                            confidence="medium",
                        )
                    )
                _append_log(log_path, f"MOVED: folder {source_dir} -> {target_dir_hint} [medium: auto-created cluster]")
            except Exception as exc:
                result.errors.append(f"{source_dir}: {exc}")
                _append_log(log_path, f"ERROR: {source_dir}: {exc}")
            continue

        for src in source_files:
            prop = RebindProposal(
                src=str(src.resolve()),
                dst=str(safe_join(target_dir, src.name)),
                reason=f"auto-created cluster '{proposal.slug}' from folder '{proposal.source_folder}'",
                confidence="medium",
            )
            if Path(prop.dst).exists():
                result.skipped.append((prop, "dst already exists"))
                _append_log(log_path, f"SKIP: {prop.src} -> {prop.dst} [dst already exists]")
                continue
            if dry_run:
                result.skipped.append((prop, "dry-run"))
                _append_log(log_path, f"DRY: {prop.src} -> {prop.dst} [{prop.confidence}: {prop.reason}]")
                continue
            try:
                Path(prop.dst).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(prop.src, prop.dst)
                result.moved.append(prop)
                _append_log(log_path, f"MOVED: {prop.src} -> {prop.dst} [{prop.confidence}: {prop.reason}]")
            except Exception as exc:
                result.errors.append(f"{prop.src}: {exc}")
                _append_log(log_path, f"ERROR: {prop.src}: {exc}")

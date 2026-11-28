"""Per-paper labels, curation, and archive management."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from research_hub.fsops import robust_move
from research_hub.security import atomic_write_text

logger = logging.getLogger(__name__)

CANONICAL_LABELS: frozenset[str] = frozenset(
    {
        "seed",
        "core",
        "method",
        "benchmark",
        "survey",
        "application",
        "tangential",
        "deprecated",
        "archived",
    }
)

ARCHIVE_DIRNAME = "_archive"
LABEL_TAGS_START = "<!-- research-hub tags start -->"
LABEL_TAGS_END = "<!-- research-hub tags end -->"


@dataclass
class PaperLabel:
    slug: str
    cluster_slug: str
    path: Path
    labels: list[str] = field(default_factory=list)
    fit_score: int | None = None
    fit_reason: str = ""
    labeled_at: str = ""
    tags: list[str] = field(default_factory=list)
    zotero_key: str = ""


def read_labels(cfg, slug: str) -> PaperLabel | None:
    note_path = _find_note_path(cfg, slug)
    if note_path is None:
        return None
    if _is_archived_path(note_path):
        return None
    return _parse_paper_label(note_path, slug=slug)


def set_labels(
    cfg,
    slug: str,
    *,
    labels: list[str] | None = None,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    fit_score: int | None = None,
    fit_reason: str | None = None,
) -> PaperLabel:
    if not slug or not slug.strip():
        raise ValueError("slug is required")
    note_path = _find_note_path(cfg, slug)
    if note_path is None:
        raise FileNotFoundError(f"paper not found: {slug}")

    _validate_note_frontmatter_for_write(note_path)
    current = _parse_paper_label(note_path, slug=slug)
    new_labels = list(current.labels)
    if labels is not None:
        new_labels = _clean_labels(labels)
    if add:
        for label in _clean_labels(add):
            if label not in new_labels:
                new_labels.append(label)
    if remove:
        remove_set = set(_clean_labels(remove))
        new_labels = [label for label in new_labels if label not in remove_set]

    updates: dict[str, object] = {
        "labels": new_labels,
        "labeled_at": _utc_now(),
    }
    if fit_score is not None:
        updates["fit_score"] = fit_score
    if fit_reason is not None:
        updates["fit_reason"] = fit_reason

    _rewrite_paper_frontmatter(note_path, updates)
    ensure_label_tags_in_body(note_path, new_labels)
    return _parse_paper_label(note_path, slug=slug)


def list_papers_by_label(
    cfg,
    cluster_slug: str,
    *,
    label: str | None = None,
    label_not: str | None = None,
) -> list[PaperLabel]:
    results: list[PaperLabel] = []
    for note_path in _iter_cluster_notes(cfg, cluster_slug, include_archive=True):
        state = _parse_paper_label(note_path, slug=note_path.stem)
        if label is not None and label not in state.labels:
            continue
        if label_not is not None and label_not in state.labels:
            continue
        results.append(state)
    return results


def apply_fit_check_to_labels(cfg, cluster_slug: str) -> dict[str, list[str]]:
    from research_hub.dedup import normalize_doi

    cluster_dir = _hub_cluster_dir(cfg, cluster_slug)
    rejected_sidecar = cluster_dir / ".fit_check_rejected.json"
    accepted_sidecar = cluster_dir / ".fit_check_accepted.json"
    if not rejected_sidecar.exists() and not accepted_sidecar.exists():
        return {"tagged": [], "already": [], "missing": []}

    rejected_payload = (
        json.loads(rejected_sidecar.read_text(encoding="utf-8")) if rejected_sidecar.exists() else {}
    )
    accepted_payload = (
        json.loads(accepted_sidecar.read_text(encoding="utf-8")) if accepted_sidecar.exists() else {}
    )
    rejected = rejected_payload.get("rejected") or []
    accepted = accepted_payload.get("accepted") or []

    doi_to_note: dict[str, Path] = {}
    for note_path in _iter_cluster_notes(cfg, cluster_slug, include_archive=False):
        meta = _parse_frontmatter(note_path.read_text(encoding="utf-8"))
        doi = str(meta.get("doi", "") or "").strip()
        if doi:
            doi_to_note[normalize_doi(doi)] = note_path

    tagged: list[str] = []
    already: list[str] = []
    missing: list[str] = []

    accepted_top_tier = _pick_top_tier_indices(accepted)
    entries: list[tuple[dict, bool, int | None]] = []
    entries.extend((entry, False, index) for index, entry in enumerate(accepted))
    entries.extend((entry, True, None) for entry in rejected)

    for entry, from_rejected, accepted_index in entries:
        norm = normalize_doi(str(entry.get("doi", "") or ""))
        if not norm:
            continue
        note_path = doi_to_note.get(norm)
        if note_path is None:
            missing.append(str(entry.get("doi", "") or ""))
            continue
        state = _parse_paper_label(note_path, slug=note_path.stem)
        existing = state.labels
        entry_score = int(entry.get("score", 0))
        labels_to_add = label_from_fit_score(
            entry_score,
            is_top_tier=not from_rejected and accepted_index in accepted_top_tier,
        )
        if not labels_to_add:
            set_labels(
                cfg,
                note_path.stem,
                fit_score=entry_score,
                fit_reason=str(entry.get("reason", "") or ""),
            )
            continue
        if all(label in existing for label in labels_to_add):
            already.append(note_path.stem)
            continue
        set_labels(
            cfg,
            note_path.stem,
            add=labels_to_add,
            fit_score=entry_score,
            fit_reason=str(entry.get("reason", "") or ""),
        )
        tagged.append(note_path.stem)
    return {"tagged": tagged, "already": already, "missing": missing}


def prune_cluster(
    cfg,
    cluster_slug: str,
    *,
    label: str = "deprecated",
    archive: bool = True,
    delete: bool = False,
    dry_run: bool = True,
    include_zotero: bool = False,
) -> dict:
    del include_zotero
    if archive and delete:
        raise ValueError("--archive and --delete are mutually exclusive")

    candidates = [state for state in list_papers_by_label(cfg, cluster_slug, label=label) if not _is_archived_path(state.path)]
    would_affect = [state.slug for state in candidates]
    if dry_run:
        return {
            "mode": "dry_run",
            "cluster_slug": cluster_slug,
            "label": label,
            "moved": [],
            "deleted": [],
            "would_affect": would_affect,
        }

    moved: list[str] = []
    deleted: list[str] = []

    if delete:
        for state in candidates:
            try:
                state.path.unlink()
            except OSError as exc:
                logger.warning("prune: failed to delete %s: %s", state.path, exc)
                continue
            deleted.append(state.slug)
    else:
        target_dir = archive_dir(cfg, cluster_slug)
        target_dir.mkdir(parents=True, exist_ok=True)
        for state in candidates:
            dest = target_dir / state.path.name
            try:
                robust_move(str(state.path), str(dest))
            except OSError as exc:
                logger.warning("prune: failed to archive %s: %s", state.path, exc)
                continue
            _rewrite_paper_frontmatter(
                dest,
                {
                    "topic_cluster": f"{ARCHIVE_DIRNAME}/{cluster_slug}",
                    "labels": _merge_labels(state.labels, ["archived"]),
                    "labeled_at": _utc_now(),
                },
            )
            moved.append(state.slug)

    _rebuild_dedup_index(cfg)
    return {
        "mode": "delete" if delete else "archive",
        "cluster_slug": cluster_slug,
        "label": label,
        "moved": moved,
        "deleted": deleted,
        "would_affect": would_affect,
    }


def unarchive(cfg, cluster_slug: str, slug: str) -> dict:
    source = archive_dir(cfg, cluster_slug) / f"{slug}.md"
    if not source.exists():
        raise FileNotFoundError(f"archived paper not found: {slug}")

    dest_dir = Path(cfg.raw) / cluster_slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{slug}.md"
    robust_move(str(source), str(dest))

    state = _parse_paper_label(dest, slug=slug)
    _rewrite_paper_frontmatter(
        dest,
        {
            "topic_cluster": cluster_slug,
            "labels": [label for label in state.labels if label != "archived"],
            "labeled_at": _utc_now(),
        },
    )
    ensure_label_tags_in_body(dest, [label for label in state.labels if label != "archived"])
    _rebuild_dedup_index(cfg)
    return {"restored": slug, "path": str(dest)}


def bulk_relabel(
    cfg,
    from_label: str,
    to_label: str,
    *,
    cluster_slug: str | None = None,
    dry_run: bool = True,
) -> dict:
    """Replace a frontmatter label across paper notes and mirror Zotero tags."""

    from_label = from_label.strip()
    to_label = to_label.strip()
    if not from_label or not to_label:
        raise ValueError("--from and --to labels are required")

    changes: list[dict] = []
    for note_path in _iter_candidate_notes(cfg, cluster_slug):
        state = _parse_paper_label(note_path, slug=note_path.stem)
        if from_label not in state.labels:
            continue
        new_labels = [to_label if label == from_label else label for label in state.labels]
        new_labels = _clean_labels(new_labels)
        changes.append(
            {
                "slug": state.slug,
                "cluster": state.cluster_slug,
                "path": str(state.path),
                "labels": state.labels,
                "new_labels": new_labels,
                "zotero_key": state.zotero_key,
            }
        )

    report = {
        "mode": "dry_run" if dry_run else "apply",
        "from": from_label,
        "to": to_label,
        "cluster": cluster_slug or "",
        "changed": changes,
        "zotero_updated": [],
        "zotero_errors": [],
    }
    if dry_run or not changes:
        return report

    zot = _maybe_get_zotero_client([change.get("zotero_key", "") for change in changes], report)
    replacements = _label_tag_replacements(from_label, to_label)
    for change in changes:
        path = Path(str(change["path"]))
        _rewrite_paper_frontmatter(
            path,
            {
                "labels": change["new_labels"],
                "labeled_at": _utc_now(),
            },
        )
        ensure_label_tags_in_body(path, list(change["new_labels"]))
        zotero_key = str(change.get("zotero_key") or "")
        if zot is not None and zotero_key:
            try:
                if _replace_zotero_tags(zot, zotero_key, replacements):
                    report["zotero_updated"].append(zotero_key)
            except Exception as exc:
                report["zotero_errors"].append({"key": zotero_key, "error": str(exc)})

    return report


def bulk_move(
    cfg,
    slugs: list[str],
    to_cluster: str,
    *,
    dry_run: bool = True,
) -> dict:
    """Move selected notes to another cluster and rebind their Zotero collection."""

    clean_slugs = _clean_labels(slugs)
    to_cluster = to_cluster.strip()
    if not clean_slugs:
        raise ValueError("at least one slug is required")
    if not to_cluster:
        raise ValueError("--to-cluster is required")

    from research_hub.clusters import ClusterRegistry

    registry = ClusterRegistry(cfg.clusters_file)
    target_cluster = registry.get(to_cluster)
    if target_cluster is None:
        raise ValueError(f"target cluster not found: {to_cluster}")
    target_dirname = target_cluster.obsidian_subfolder or target_cluster.slug
    target_dir = Path(cfg.raw) / target_dirname
    target_collection = (target_cluster.zotero_collection_key or "").strip()

    would_move: list[dict] = []
    missing: list[str] = []
    skipped: list[dict] = []
    for slug in clean_slugs:
        source_path = _find_note_path(cfg, slug)
        if source_path is None or _is_archived_path(source_path):
            missing.append(slug)
            continue
        state = _parse_paper_label(source_path, slug=slug)
        target_path = target_dir / f"{slug}.md"
        if source_path.resolve() == target_path.resolve():
            skipped.append({"slug": slug, "reason": "already in target cluster"})
            continue
        if target_path.exists():
            skipped.append({"slug": slug, "reason": f"target exists: {target_path}"})
            continue
        would_move.append(
            {
                "slug": slug,
                "from_cluster": state.cluster_slug,
                "to_cluster": to_cluster,
                "from": str(source_path),
                "to": str(target_path),
                "zotero_key": state.zotero_key,
            }
        )

    report = {
        "mode": "dry_run" if dry_run else "apply",
        "to_cluster": to_cluster,
        "would_move": would_move,
        "moved": [],
        "missing": missing,
        "skipped": skipped,
        "zotero_updated": [],
        "zotero_errors": [],
    }
    if dry_run or not would_move:
        return report

    zot = _maybe_get_zotero_client([move.get("zotero_key", "") for move in would_move], report)
    for move in would_move:
        source_path = Path(str(move["from"]))
        target_path = Path(str(move["to"]))
        source_cluster = str(move["from_cluster"])
        source_cluster_obj = registry.get(source_cluster)
        source_collection = (
            (source_cluster_obj.zotero_collection_key or "").strip()
            if source_cluster_obj is not None
            else ""
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        robust_move(str(source_path), str(target_path))

        meta = _parse_frontmatter(target_path.read_text(encoding="utf-8"))
        updates: dict[str, object] = {"topic_cluster": to_cluster}
        frontmatter_tags = _frontmatter_list(meta, "tags")
        if frontmatter_tags:
            updates["tags"] = _replace_cluster_tags(frontmatter_tags, source_cluster, to_cluster)
        frontmatter_collections = _frontmatter_list(meta, "collections")
        if frontmatter_collections and target_collection:
            updates["collections"] = _replace_collection_binding(
                frontmatter_collections,
                source_collection,
                target_collection,
            )
        _rewrite_paper_frontmatter(target_path, updates)
        report["moved"].append(move["slug"])

        zotero_key = str(move.get("zotero_key") or "")
        if zot is not None and zotero_key and target_collection:
            try:
                if _rebind_zotero_collection(
                    zot,
                    zotero_key,
                    target_collection,
                    remove_collection=source_collection,
                    tag_from_cluster=source_cluster,
                    tag_to_cluster=to_cluster,
                ):
                    report["zotero_updated"].append(zotero_key)
            except Exception as exc:
                report["zotero_errors"].append({"key": zotero_key, "error": str(exc)})

    _rebuild_dedup_index(cfg)
    return report


def bulk_delete_by_tag(
    cfg,
    by_tag: str,
    *,
    dry_run: bool = True,
) -> dict:
    """Remove notes whose frontmatter tags include a tag, trashing Zotero items."""

    by_tag = by_tag.strip()
    if not by_tag:
        raise ValueError("--by-tag is required")

    candidates: list[dict] = []
    for note_path in _iter_candidate_notes(cfg, None):
        state = _parse_paper_label(note_path, slug=note_path.stem)
        if by_tag not in state.tags:
            continue
        candidates.append(
            {
                "slug": state.slug,
                "cluster": state.cluster_slug,
                "path": str(state.path),
                "zotero_key": state.zotero_key,
            }
        )

    report = {
        "mode": "dry_run" if dry_run else "apply",
        "tag": by_tag,
        "would_delete": candidates,
        "deleted": [],
        "zotero_trashed": [],
        "zotero_errors": [],
    }
    if dry_run or not candidates:
        return report

    zot = _maybe_get_zotero_client([item.get("zotero_key", "") for item in candidates], report)
    for candidate in candidates:
        zotero_key = str(candidate.get("zotero_key") or "")
        if zot is not None and zotero_key:
            try:
                if _trash_zotero_item(zot, zotero_key):
                    report["zotero_trashed"].append(zotero_key)
            except Exception as exc:
                report["zotero_errors"].append({"key": zotero_key, "error": str(exc)})
        path = Path(str(candidate["path"]))
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("bulk-delete: failed to delete %s: %s", path, exc)
            continue
        report["deleted"].append(candidate["slug"])

    _rebuild_dedup_index(cfg)
    return report


def ensure_label_tags_in_body(path: Path, labels: list[str]) -> bool:
    """Ensure the note body ends with an idempotent label-tag sentinel block."""

    text = _read_text_preserve_newlines(path)
    split = _split_frontmatter(text)
    if split is None:
        return False
    opening, frontmatter, body, newline = split
    rendered_labels = " ".join(f"#label/{label}" for label in sorted(_clean_labels(labels)))
    block = (
        f"{LABEL_TAGS_START}{newline}"
        f"{rendered_labels}{newline}"
        f"{LABEL_TAGS_END}"
    )
    pattern = re.compile(
        rf"(?:\r?\n)*{re.escape(LABEL_TAGS_START)}\r?\n.*?\r?\n{re.escape(LABEL_TAGS_END)}\s*$",
        re.DOTALL,
    )
    body_without_block = re.sub(pattern, "", body).rstrip("\r\n")
    if body_without_block:
        new_body = f"{body_without_block}{newline}{newline}{block}{newline}"
    else:
        new_body = f"{block}{newline}"
    frontmatter_out = (
        frontmatter
        if not frontmatter or frontmatter.endswith(("\n", "\r\n"))
        else f"{frontmatter}{newline}"
    )
    updated = f"{opening}{frontmatter_out}---{newline}{new_body}"
    if updated == text:
        return False
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(updated)
    return True


def archive_dir(cfg, cluster_slug: str) -> Path:
    return Path(cfg.raw) / ARCHIVE_DIRNAME / cluster_slug


def label_from_fit_score(score: int, is_top_tier: bool = False) -> list[str]:
    if score >= 5:
        return ["seed", "core"] if is_top_tier else ["core"]
    if score == 4:
        return ["core"]
    if score <= 1:
        return ["deprecated"]
    if score == 2:
        return ["tangential"]
    return []


def _pick_top_tier_indices(accepted: list[dict], top_fraction: float = 0.2) -> set[int]:
    score_five = [(index, entry) for index, entry in enumerate(accepted) if int(entry.get("score", 0)) >= 5]
    if not score_five:
        return set()
    top_n = max(1, math.ceil(len(score_five) * top_fraction))
    return {index for index, _ in score_five[:top_n]}


def _find_note_path(cfg, slug: str) -> Path | None:
    raw_root = Path(cfg.raw)
    if not raw_root.exists():
        return None
    direct = list(raw_root.glob(f"*/{slug}.md"))
    if direct:
        return direct[0]
    archived = list((raw_root / ARCHIVE_DIRNAME).glob(f"*/{slug}.md"))
    if archived:
        return archived[0]
    return None


def _iter_cluster_notes(cfg, cluster_slug: str, *, include_archive: bool):
    cluster_dir = Path(cfg.raw) / cluster_slug
    if cluster_dir.exists():
        for note in sorted(cluster_dir.glob("*.md")):
            if note.name in {"00_overview.md", "index.md"}:
                continue
            yield note
    if include_archive:
        arch = archive_dir(cfg, cluster_slug)
        if arch.exists():
            for note in sorted(arch.glob("*.md")):
                if note.name in {"00_overview.md", "index.md"}:
                    continue
                yield note


def _hub_cluster_dir(cfg, cluster_slug: str) -> Path:
    hub_root = getattr(cfg, "hub", None)
    if hub_root is None:
        root = getattr(cfg, "root", None)
        if root is None:
            raise AttributeError("config must define either 'hub' or 'root'")
        hub_root = Path(root) / "research_hub" / "hub"
    return Path(hub_root) / cluster_slug


def _parse_frontmatter_legacy(frontmatter: str) -> dict[str, object]:
    meta: dict[str, object] = {}
    lines = frontmatter.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$", line)
        if not match:
            i += 1
            continue
        key, value = match.group(1), match.group(2).strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key] = _parse_inline_list(value)
            i += 1
            continue
        if value == "":
            items: list[str] = []
            j = i + 1
            while j < len(lines) and re.match(r"^[ \t]+-\s+", lines[j]):
                items.append(re.sub(r"^[ \t]+-\s+", "", lines[j]).strip().strip('"').strip("'"))
                j += 1
            meta[key] = items if items else ""
            i = j
            continue
        meta[key] = value.strip('"').strip("'")
        i += 1
    return meta


class _NoTimestampSafeLoader(yaml.SafeLoader):
    """YAML SafeLoader that keeps unquoted ISO-8601 timestamps/dates as str."""


_NoTimestampSafeLoader.yaml_implicit_resolvers = {
    first_char: [
        (tag, regexp)
        for tag, regexp in resolvers
        if tag != "tag:yaml.org,2002:timestamp"
    ]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


class _UniqueMappingSafeLoader(_NoTimestampSafeLoader):
    """Strict YAML SafeLoader rejecting duplicate or non-string keys at any level."""

    def __init__(self, stream: object) -> None:
        super().__init__(stream)
        self._validated_unique_nodes: dict[int, yaml.Node] = {}


def _validate_node_unique_mappings(
    loader: _UniqueMappingSafeLoader,
    node: yaml.Node,
    *,
    deep: bool = False,
    _seen_nodes: dict[int, yaml.Node] | None = None,
) -> None:
    if _seen_nodes is None:
        _seen_nodes = getattr(loader, "_validated_unique_nodes", None)
        if _seen_nodes is None:
            _seen_nodes = {}
            setattr(loader, "_validated_unique_nodes", _seen_nodes)
    if isinstance(node, yaml.MappingNode):
        _validate_mapping_node_unique_keys(
            loader, node, deep=deep, _seen_nodes=_seen_nodes
        )
    elif isinstance(node, yaml.SequenceNode):
        node_id = id(node)
        if node_id in _seen_nodes:
            return
        _seen_nodes[node_id] = node
        for item in node.value:
            _validate_node_unique_mappings(
                loader, item, deep=deep, _seen_nodes=_seen_nodes
            )


def _validate_mapping_node_unique_keys(
    loader: _UniqueMappingSafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
    _seen_nodes: dict[int, yaml.Node] | None = None,
) -> None:
    if _seen_nodes is None:
        _seen_nodes = getattr(loader, "_validated_unique_nodes", None)
        if _seen_nodes is None:
            _seen_nodes = {}
            setattr(loader, "_validated_unique_nodes", _seen_nodes)
    node_id = id(node)
    if node_id in _seen_nodes:
        return
    _seen_nodes[node_id] = node

    explicit_keys: set[str] = set()
    seen_merge = False
    for key_node, value_node in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            if seen_merge:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found duplicate key '<<'",
                    key_node.start_mark,
                )
            seen_merge = True
            _validate_node_unique_mappings(
                loader, value_node, deep=deep, _seen_nodes=_seen_nodes
            )
            continue
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found non-string key {key!r}",
                key_node.start_mark,
            )
        if key in explicit_keys:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        explicit_keys.add(key)
        _validate_node_unique_mappings(
            loader, value_node, deep=deep, _seen_nodes=_seen_nodes
        )


def _construct_unique_mapping(
    loader: _UniqueMappingSafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[str, object]:
    _validate_mapping_node_unique_keys(loader, node, deep=deep)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_UniqueMappingSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _parse_frontmatter(text: str) -> dict[str, object]:
    frontmatter = _extract_frontmatter(text)
    if frontmatter is None or not frontmatter.strip():
        return {}
    try:
        loaded = yaml.load(frontmatter, Loader=_NoTimestampSafeLoader)
    except (yaml.YAMLError, ValueError):
        return _parse_frontmatter_legacy(frontmatter)
    if loaded is None:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return _parse_frontmatter_legacy(frontmatter)


_read_paper_frontmatter = _parse_frontmatter


def _parse_paper_label(note_path: Path, *, slug: str) -> PaperLabel:
    text = note_path.read_text(encoding="utf-8")
    meta = _parse_frontmatter(text)
    labels_raw = meta.get("labels", [])
    if isinstance(labels_raw, str):
        labels = [labels_raw] if labels_raw else []
    elif isinstance(labels_raw, list):
        labels = [str(item) for item in labels_raw if str(item).strip()]
    else:
        labels = []
    tags = _frontmatter_list(meta, "tags")

    fit_score_raw = meta.get("fit_score")
    fit_score: int | None = None
    if isinstance(fit_score_raw, int) and not isinstance(fit_score_raw, bool):
        fit_score = fit_score_raw
    elif isinstance(fit_score_raw, str) and fit_score_raw.lstrip("-").isdigit():
        fit_score = int(fit_score_raw)

    cluster_slug = str(meta.get("topic_cluster", "") or note_path.parent.name)
    return PaperLabel(
        slug=slug,
        cluster_slug=cluster_slug,
        path=note_path,
        labels=labels,
        fit_score=fit_score,
        fit_reason=str(meta.get("fit_reason", "") or ""),
        labeled_at=str(meta.get("labeled_at", "") or ""),
        tags=tags,
        zotero_key=str(meta.get("zotero-key", meta.get("zotero_key", "")) or ""),
    )


_SAFE_BARE_YAML_ITEM_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_YAML_RESERVED_WORDS = frozenset({"true", "false", "yes", "no", "on", "off", "null", "y", "n"})


def _render_list_item(item: object) -> str:
    """Render a scalar YAML list item safely without type or comment corruption."""
    if (
        isinstance(item, str)
        and _SAFE_BARE_YAML_ITEM_RE.fullmatch(item)
        and item.casefold() not in _YAML_RESERVED_WORDS
    ):
        return item
    return json.dumps(item, ensure_ascii=False)


def _dedupe_list_items(value: list[object]) -> list[object]:
    """Dedupe list values order-preservingly while distinguishing distinct scalar types."""
    seen: set[str] = set()
    deduped: list[object] = []
    for item in value:
        try:
            sig = json.dumps(item, sort_keys=True, ensure_ascii=False)
        except TypeError:
            sig = f"{type(item).__name__}:{item}"
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append(item)
    return deduped


def _values_and_types_match(actual: object, expected: object) -> bool:
    """Compare reloaded YAML values and types strictly (e.g. int 1 != bool True)."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _values_and_types_match(a, e) for a, e in zip(actual, expected)
        )
    if isinstance(expected, dict):
        return set(actual.keys()) == set(expected.keys()) and all(
            _values_and_types_match(actual[k], expected[k]) for k in expected
        )
    return actual == expected


def _render_patch_field(key: str, value: object, newline: str) -> str:
    if isinstance(value, list):
        can_use_simple_list = all(
            item is None or isinstance(item, (str, int, float, bool))
            for item in value
        )
        if not value or can_use_simple_list:
            return newline.join(_render_field(key, value))
        dumped = yaml.safe_dump(
            {key: value},
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        ).rstrip("\r\n")
        return dumped.replace("\n", newline)
    if isinstance(value, dict):
        dumped = yaml.safe_dump(
            {key: value},
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        ).rstrip("\r\n")
        return dumped.replace("\n", newline)
    if isinstance(value, bool):
        return f"{key}: {'true' if value else 'false'}"
    if isinstance(value, (int, float)):
        return f"{key}: {value}"
    return f"{key}: {json.dumps(str(value), ensure_ascii=False)}"


def _append_patch_field(frontmatter_lf: str, key: str, value: object) -> str:
    if value is None:
        return frontmatter_lf
    rendered = _render_patch_field(key, value, "\n")
    if not frontmatter_lf:
        return f"{rendered}\n"
    sep = "" if frontmatter_lf.endswith("\n") else "\n"
    return f"{frontmatter_lf}{sep}{rendered}\n"


def _patch_yaml_frontmatter_field(frontmatter_lf: str, key: str, value: object) -> str:
    if not frontmatter_lf.strip():
        return _append_patch_field(frontmatter_lf, key, value)

    document = yaml.compose(frontmatter_lf, Loader=yaml.SafeLoader)
    if document is None:
        return _append_patch_field(frontmatter_lf, key, value)
    if not isinstance(document, yaml.MappingNode):
        raise ValueError("Paper note frontmatter must be a mapping")

    matches = [(k_node, v_node) for k_node, v_node in document.value if k_node.value == key]
    if len(matches) > 1:
        raise ValueError(f"Paper note has duplicate '{key}' fields")

    if not matches:
        return _append_patch_field(frontmatter_lf, key, value)

    k_node, v_node = matches[0]
    start, end = k_node.start_mark.index, v_node.end_mark.index
    if v_node.start_mark.index < k_node.end_mark.index:
        raise ValueError(f"Cannot safely update aliased '{key}' metadata")
    tokens = list(yaml.scan(frontmatter_lf, Loader=yaml.SafeLoader))
    if any(
        isinstance(token, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken))
        and start <= token.start_mark.index < end
        for token in tokens
    ):
        raise ValueError(f"Cannot safely update anchored or aliased '{key}' metadata")

    content_ends = [
        token.end_mark.index
        for token in tokens
        if isinstance(
            token,
            (
                yaml.tokens.ScalarToken,
                yaml.tokens.FlowSequenceEndToken,
                yaml.tokens.FlowMappingEndToken,
                yaml.tokens.ValueToken,
                yaml.tokens.BlockEntryToken,
            ),
        )
        and v_node.start_mark.index <= token.start_mark.index < end
    ]
    if content_ends:
        end = max(content_ends)

    if value is None:
        if frontmatter_lf[start:end].endswith("\n"):
            return frontmatter_lf[:start] + frontmatter_lf[end:]
        tail_match = re.match(r"[ \t]*(?:#[^\n]*)?(\n?)", frontmatter_lf[end:])
        after = end + (tail_match.end() if tail_match else 0)
        if tail_match and tail_match.group(1) == "\n":
            return frontmatter_lf[:start] + frontmatter_lf[after:]
        if start > 0 and frontmatter_lf[start - 1] == "\n":
            return frontmatter_lf[: start - 1] + frontmatter_lf[after:]
        return frontmatter_lf[:start] + frontmatter_lf[after:]

    rendered = _render_patch_field(key, value, "\n")
    if frontmatter_lf[start:end].endswith("\n"):
        rendered += "\n"
    return frontmatter_lf[:start] + rendered + frontmatter_lf[end:]


def _atomic_write_preserving_newlines(path: Path, content: str) -> None:
    if os.name != "nt" and "\r" not in content:
        atomic_write_text(path, content, encoding="utf-8")
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        with tmp.open("w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        os.replace(str(tmp), str(path))
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def _validate_frontmatter_mapping_lf(frontmatter_lf: str) -> None:
    if not frontmatter_lf.strip():
        return
    try:
        initial = yaml.load(frontmatter_lf, Loader=_UniqueMappingSafeLoader)
        if initial is not None and not isinstance(initial, dict):
            raise ValueError("Paper note frontmatter must be a valid YAML mapping")
    except (yaml.YAMLError, ValueError) as exc:
        raise ValueError("Paper note frontmatter must be a valid YAML mapping") from exc


def _validate_note_frontmatter_for_write(note_path: Path) -> None:
    text = _read_text_preserve_newlines(note_path)
    split = _split_frontmatter(text)
    if split is None:
        return
    _opening, frontmatter, _body, newline = split
    frontmatter_lf = frontmatter.replace("\r\n", "\n") if newline == "\r\n" else frontmatter
    _validate_frontmatter_mapping_lf(frontmatter_lf)


def _rewrite_paper_frontmatter(note_path: Path, updates: dict) -> None:
    text = _read_text_preserve_newlines(note_path)
    split = _split_frontmatter(text)
    if split is None:
        logger.warning("paper labels: malformed or missing frontmatter in %s", note_path)
        return
    opening, frontmatter, body, newline = split
    if not updates:
        return

    frontmatter_lf = frontmatter.replace("\r\n", "\n") if newline == "\r\n" else frontmatter
    _validate_frontmatter_mapping_lf(frontmatter_lf)

    patched_lf = frontmatter_lf
    for key, value in updates.items():
        patched_lf = _patch_yaml_frontmatter_field(patched_lf, key, value)

    if patched_lf.strip():
        try:
            verified = yaml.load(patched_lf, Loader=_UniqueMappingSafeLoader)
        except (yaml.YAMLError, ValueError) as exc:
            raise ValueError("Patched frontmatter must remain a valid YAML mapping") from exc
        if verified is None:
            verified = {}
        if not isinstance(verified, dict):
            raise ValueError("Patched frontmatter must remain a YAML mapping")
    else:
        verified = {}

    for key, expected in updates.items():
        if expected is None:
            if key in verified:
                raise ValueError(f"Failed to delete frontmatter field '{key}'")
            continue
        if key not in verified:
            raise ValueError(f"Missing updated frontmatter field '{key}'")
        expected_checked = (
            _dedupe_list_items(expected)
            if isinstance(expected, list)
            and all(item is None or isinstance(item, (str, int, float, bool)) for item in expected)
            else expected
        )
        if not _values_and_types_match(verified[key], expected_checked):
            raise ValueError(f"Patched frontmatter field '{key}' failed round-trip verification")

    patched = patched_lf.replace("\n", newline) if newline != "\n" else patched_lf
    if patched and not patched.endswith(newline):
        patched += newline
    content = f"{opening}{patched}---{newline}{body}"
    _atomic_write_preserving_newlines(note_path, content)


def _split_frontmatter(text: str) -> tuple[str, str, str, str] | None:
    if text.startswith("---\r\n"):
        newline = "\r\n"
    elif text.startswith("---\n"):
        newline = "\n"
    else:
        return None
    opening = f"---{newline}"
    pos = len(opening)
    text_len = len(text)
    while pos < text_len:
        nl_idx = text.find("\n", pos)
        if nl_idx == -1:
            line = text[pos:]
            after_line = text_len
        else:
            line_end = nl_idx - 1 if nl_idx > pos and text[nl_idx - 1] == "\r" else nl_idx
            line = text[pos:line_end]
            after_line = nl_idx + 1
        if line == "---":
            frontmatter = text[len(opening):pos]
            body = text[after_line:]
            return opening, frontmatter, body, newline
        if nl_idx == -1:
            break
        pos = after_line
    return None


def _extract_frontmatter(text: str) -> str | None:
    split = _split_frontmatter(text)
    if split is None:
        return None
    return split[1]


def _frontmatter_key_order(frontmatter: str) -> list[str]:
    keys: list[str] = []
    for line in frontmatter.splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:", line)
        if match and match.group(1) not in keys:
            keys.append(match.group(1))
    return keys


def _render_frontmatter(meta: dict[str, object], ordered_keys: list[str], newline: str) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for key in ordered_keys:
        if key not in meta:
            continue
        lines.extend(_render_field(key, meta[key]))
        seen.add(key)
    for key in meta:
        if key in seen:
            continue
        lines.extend(_render_field(key, meta[key]))
    return newline.join(lines)


def _render_field(key: str, value: object) -> list[str]:
    if isinstance(value, list):
        if not value:
            return [f"{key}: []"]
        # v0.88.4 #2: dedupe list values (order-preserving) before writing to
        # disk. Upstream enrich-existing / paper-relabel flows can accumulate
        # duplicates in cluster_queries / tags / collections / aliases when
        # they re-run on an already-tagged note; we want the rendered
        # frontmatter to stay clean regardless.
        deduped = _dedupe_list_items(value)
        return [f"{key}:"] + [f"  - {_render_list_item(item)}" for item in deduped]
    if value is None:
        return [f"{key}: "]
    if isinstance(value, bool):
        return [f"{key}: {'true' if value else 'false'}"]
    if isinstance(value, (int, float)):
        return [f"{key}: {value}"]
    return [f"{key}: {json.dumps(str(value), ensure_ascii=False)}"]


def _escape_scalar(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _clean_labels(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def _merge_labels(current: list[str], extra: list[str]) -> list[str]:
    merged = list(current)
    for label in extra:
        if label not in merged:
            merged.append(label)
    return merged


def _frontmatter_list(meta: dict[str, object], key: str) -> list[str]:
    value = meta.get(key, [])
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _iter_candidate_notes(cfg, cluster_slug: str | None):
    raw_root = Path(cfg.raw)
    if not raw_root.exists():
        return
    if cluster_slug:
        yield from _iter_cluster_notes(cfg, cluster_slug, include_archive=False)
        return
    for folder in sorted(raw_root.iterdir()):
        if not folder.is_dir():
            continue
        if folder.name in {ARCHIVE_DIRNAME, "pdfs", "attachments"} or folder.name.startswith("_deleted_"):
            continue
        for note in sorted(folder.glob("*.md")):
            if note.name in {"00_overview.md", "index.md"}:
                continue
            yield note


def _label_tag_replacements(from_label: str, to_label: str) -> dict[str, str]:
    return {
        from_label: to_label,
        f"label/{from_label}": f"label/{to_label}",
        f"cluster/{from_label}": f"cluster/{to_label}",
        f"topic:{from_label}": f"topic:{to_label}",
    }


def _replace_cluster_tags(tags: list[str], from_cluster: str, to_cluster: str) -> list[str]:
    replacements = {
        f"cluster/{from_cluster}": f"cluster/{to_cluster}",
        f"topic:{from_cluster}": f"topic:{to_cluster}",
    }
    return _replace_tag_values(tags, replacements)


def _replace_tag_values(tags: list[str], replacements: dict[str, str]) -> list[str]:
    updated: list[str] = []
    for tag in tags:
        replacement = replacements.get(tag, tag)
        if replacement not in updated:
            updated.append(replacement)
    return updated


def _replace_collection_binding(
    collections: list[str],
    source_collection: str,
    target_collection: str,
) -> list[str]:
    updated = [key for key in collections if not source_collection or key != source_collection]
    if target_collection not in updated:
        updated.append(target_collection)
    return updated


def retype_paper(
    cfg,
    slug: str,
    *,
    target_type: str,
    dry_run: bool = True,
) -> dict:
    """v0.88.2 §B: change a paper's Zotero itemType.

    Background: pyzotero / the Zotero web API rejects PATCH requests
    that try to change `itemType` on an existing item. The work-around
    is "create new item with the target type + copy shared fields +
    delete (trash) the old item + update the Obsidian frontmatter's
    `zotero-key` to point at the new item". This function wraps that
    flow.

    Live use cases (V088_PLAN.md): goldshtein2025 should be
    `conferencePaper` not `journalArticle`; arnold2026 Zenodo deposit
    should be `dataset` not `journalArticle`.

    Returns a report dict:
      {
        "mode": "dry_run" | "apply",
        "slug": <slug>,
        "from_type": <current itemType>,
        "to_type": <target_type>,
        "old_zotero_key": <key>,
        "new_zotero_key": <key | "">,  # populated on --apply
        "fields_copied": [<field>...],
        "fields_dropped": [<field>...],  # target template lacks them
        "errors": [<msg>...],
      }
    """
    target_type = (target_type or "").strip()
    if not target_type:
        raise ValueError("--to-type is required")

    note_path = _find_note_path(cfg, slug)
    if note_path is None:
        return {
            "mode": "dry_run" if dry_run else "apply",
            "slug": slug,
            "errors": [f"note not found for slug: {slug}"],
        }
    state = _parse_paper_label(note_path, slug=slug)
    zotero_key = (state.zotero_key or "").strip()
    if not zotero_key:
        return {
            "mode": "dry_run" if dry_run else "apply",
            "slug": slug,
            "errors": ["note has no zotero-key in frontmatter"],
        }

    report: dict = {
        "mode": "dry_run" if dry_run else "apply",
        "slug": slug,
        "from_type": "",
        "to_type": target_type,
        "old_zotero_key": zotero_key,
        "new_zotero_key": "",
        "fields_copied": [],
        "fields_dropped": [],
        "errors": [],
    }

    zot = _maybe_get_zotero_client([zotero_key], report)
    if zot is None:
        report["errors"].append("zotero client unavailable")
        return report

    try:
        item = zot.item(zotero_key)
    except Exception as exc:
        report["errors"].append(f"fetch item {zotero_key}: {exc}")
        return report
    data = item.get("data", {})
    report["from_type"] = data.get("itemType", "")

    if report["from_type"] == target_type:
        report["errors"].append("paper is already the target itemType (no-op)")
        return report

    try:
        new_template = zot.item_template(target_type)
    except Exception as exc:
        report["errors"].append(f"unknown itemType '{target_type}': {exc}")
        return report

    # Map shared fields from old data → new template.
    # Common bibliographic fields are named the same across types; venue
    # field has type-specific names (publicationTitle / proceedingsTitle /
    # bookTitle / archive) handled below.
    NEVER_COPY = {"itemType", "key", "version", "dateAdded", "dateModified",
                  "tags", "collections", "relations", "creators"}
    venue_field_map = {
        "journalArticle": "publicationTitle",
        "conferencePaper": "proceedingsTitle",
        "bookSection": "bookTitle",
        "manuscript": "publicationTitle",
        "report": "reportType",
        "dataset": "",   # datasets have no canonical venue field
    }
    source_venue_field = venue_field_map.get(report["from_type"], "publicationTitle")
    target_venue_field = venue_field_map.get(target_type, "publicationTitle")

    new_data = dict(new_template)
    fields_copied: list[str] = []
    fields_dropped: list[str] = []

    for key, value in data.items():
        if key in NEVER_COPY:
            continue
        if key == source_venue_field and target_venue_field and target_venue_field != source_venue_field:
            # Cross-type venue translation: publicationTitle → proceedingsTitle
            if target_venue_field in new_data:
                new_data[target_venue_field] = value
                fields_copied.append(f"{source_venue_field}->{target_venue_field}")
            else:
                fields_dropped.append(key)
            continue
        if key in new_data:
            new_data[key] = value
            fields_copied.append(key)
        elif value not in ("", [], None):
            # Substantive value but target template doesn't have this field
            fields_dropped.append(key)

    # Carry creators + tags + collections explicitly
    new_data["creators"] = data.get("creators", [])
    new_data["tags"] = data.get("tags", [])
    new_data["collections"] = data.get("collections", [])
    report["fields_copied"] = sorted(set(fields_copied))
    report["fields_dropped"] = sorted(set(fields_dropped))

    if dry_run:
        return report

    # Apply: create new + trash old + update note frontmatter.
    try:
        resp = zot.create_items([new_data])
    except Exception as exc:
        report["errors"].append(f"create_items: {exc}")
        return report
    success = (resp or {}).get("success") or {}
    if not success:
        report["errors"].append(f"create_items: no success entries in response: {resp}")
        return report
    new_key = next(iter(success.values()))
    report["new_zotero_key"] = new_key

    # v0.88.1: pyzotero's update_item() validates against the item-type
    # schema and rejects the `deleted: 1` key the soft-trash flow requires —
    # so soft-trash fails with "Invalid keys present in item 1: deleted".
    # For retype we already created a new correct-type item, so HARD-DELETE
    # of the old wrong-type item is safe: no data loss (new item has it all),
    # and Zotero web app's "Trash" UI still lets the user restore for ~30
    # days if anything went wrong. Prefer soft-trash first, fall through to
    # hard delete.
    trashed = False
    try:
        trashed = _trash_zotero_item(zot, zotero_key)
    except Exception:
        trashed = False
    if not trashed:
        try:
            zot.delete_item(item)
            trashed = True
        except Exception as exc:
            report["errors"].append(f"delete old item {zotero_key}: {exc}")

    try:
        _rewrite_paper_frontmatter(note_path, {"zotero-key": new_key})
    except Exception as exc:
        report["errors"].append(f"rewrite frontmatter {note_path}: {exc}")

    # v0.88.4 #1: also clean stale body lines (Citation + Zotero key
    # footer) so the note doesn't display contradictory info after retype.
    try:
        _rewrite_paper_body_after_retype(
            note_path,
            new_zotero_key=new_key,
            old_zotero_key=zotero_key,
            new_item_data=new_data,
            target_type=target_type,
            target_venue_field=target_venue_field,
        )
    except Exception as exc:
        report["errors"].append(f"rewrite body {note_path}: {exc}")

    _rebuild_dedup_index(cfg)
    return report


def _rewrite_paper_body_after_retype(
    note_path: Path,
    *,
    new_zotero_key: str,
    old_zotero_key: str,
    new_item_data: dict,
    target_type: str,
    target_venue_field: str,
) -> None:
    """v0.88.4 #1: rewrite ``**Citation:**`` line and ``Source: Zotero key``
    footer after a retype so they no longer display the previous itemType's
    venue / old Zotero key.

    Skips silently if either token isn't present in the note body (older
    notes that never had a Citation line written).
    """
    import re as _re

    text = note_path.read_text(encoding="utf-8")

    # Compute new Citation venue from the target template's venue field.
    venue = ""
    if target_venue_field:
        venue = str(new_item_data.get(target_venue_field, "") or "").strip()
    elif target_type == "dataset":
        doi = str(new_item_data.get("DOI", "") or "").strip().lower()
        if doi.startswith("10.5281/zenodo."):
            venue = "Dataset (Zenodo)"
        elif doi.startswith("10.6084/m9.figshare."):
            venue = "Dataset (Figshare)"
        else:
            venue = "Dataset"

    volume = str(new_item_data.get("volume", "") or "").strip()
    issue = str(new_item_data.get("issue", "") or "").strip()
    pages = str(new_item_data.get("pages", "") or "").strip()
    citation_line = venue
    if volume:
        citation_line += f", {volume}"
    if issue:
        citation_line += f"({issue})"
    if pages:
        citation_line += f", {pages}"
    new_citation = f"**Citation:** {citation_line}"

    # Replace the first `**Citation:**` line only (it's always in the
    # paper note's preamble block, never inside an abstract or quote).
    text = _re.sub(r"\*\*Citation:\*\*[^\n]*", new_citation, text, count=1)

    # Replace the `Source: Zotero key \`OLDKEY\`` footer so external readers
    # who scan the bottom-of-note attribution see the canonical key.
    if old_zotero_key:
        text = _re.sub(
            rf"(Source: Zotero key `){_re.escape(old_zotero_key)}(`)",
            rf"\g<1>{new_zotero_key}\g<2>",
            text,
        )

    note_path.write_text(text, encoding="utf-8")


def _maybe_get_zotero_client(zotero_keys: list[str], report: dict):
    if not any(str(key or "").strip() for key in zotero_keys):
        return None
    try:
        return _get_zotero_web_client()
    except Exception as exc:
        report.setdefault("zotero_errors", []).append({"key": "", "error": str(exc)})
        return None


def _get_zotero_web_client():
    from research_hub.zotero.client import ZoteroDualClient

    return ZoteroDualClient().web


def _replace_zotero_tags(zot, item_key: str, replacements: dict[str, str]) -> bool:
    item = zot.item(item_key)
    data = item.get("data", item)
    tags = data.get("tags", []) or []
    updated_tags: list[dict] = []
    changed = False
    seen: set[str] = set()
    for tag_entry in tags:
        if isinstance(tag_entry, dict):
            tag_value = str(tag_entry.get("tag", "") or "")
            new_tag = replacements.get(tag_value, tag_value)
            new_entry = dict(tag_entry)
            new_entry["tag"] = new_tag
        else:
            tag_value = str(tag_entry)
            new_tag = replacements.get(tag_value, tag_value)
            new_entry = {"tag": new_tag}
        if new_tag != tag_value:
            changed = True
        if new_tag and new_tag not in seen:
            seen.add(new_tag)
            updated_tags.append(new_entry)
    if not changed:
        return False
    data["tags"] = updated_tags
    zot.update_item(data)
    return True


def _rebind_zotero_collection(
    zot,
    item_key: str,
    target_collection: str,
    *,
    remove_collection: str = "",
    tag_from_cluster: str = "",
    tag_to_cluster: str = "",
) -> bool:
    item = zot.item(item_key)
    data = item.get("data", item)
    collections = [str(key) for key in data.get("collections", []) or []]
    updated = [
        key for key in collections
        if not remove_collection or key != remove_collection
    ]
    if target_collection not in updated:
        updated.append(target_collection)
    changed = updated != collections
    data["collections"] = updated
    if tag_from_cluster and tag_to_cluster:
        replacement_map = {
            f"cluster/{tag_from_cluster}": f"cluster/{tag_to_cluster}",
            f"topic:{tag_from_cluster}": f"topic:{tag_to_cluster}",
        }
        tag_entries, tags_changed = _replace_zotero_tag_entries(
            data.get("tags", []) or [],
            replacement_map,
        )
        data["tags"] = tag_entries
        changed = changed or tags_changed
    if not changed:
        return False
    zot.update_item(data)
    return True


def _replace_zotero_tag_entries(
    tags: list,
    replacements: dict[str, str],
) -> tuple[list[dict], bool]:
    updated_tags: list[dict] = []
    changed = False
    seen: set[str] = set()
    for tag_entry in tags:
        if isinstance(tag_entry, dict):
            tag_value = str(tag_entry.get("tag", "") or "")
            new_tag = replacements.get(tag_value, tag_value)
            new_entry = dict(tag_entry)
            new_entry["tag"] = new_tag
        else:
            tag_value = str(tag_entry)
            new_tag = replacements.get(tag_value, tag_value)
            new_entry = {"tag": new_tag}
        if new_tag != tag_value:
            changed = True
        if new_tag and new_tag not in seen:
            seen.add(new_tag)
            updated_tags.append(new_entry)
    return updated_tags, changed


def _trash_zotero_item(zot, item_key: str) -> bool:
    item = zot.item(item_key)
    data = item.get("data", item)
    if data.get("deleted"):
        return False
    data["deleted"] = 1
    zot.update_item(data)
    return True


def _parse_inline_list(value: str) -> list[str]:
    inner = value[1:-1]
    return [part.strip().strip('"').strip("'") for part in inner.split(",") if part.strip()]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_archived_path(path: Path) -> bool:
    return ARCHIVE_DIRNAME in path.parts


def _rebuild_dedup_index(cfg) -> None:
    from research_hub.dedup import DedupIndex

    index_path = cfg.research_hub_dir / "dedup_index.json"
    index = DedupIndex()
    index.rebuild_from_obsidian(cfg.raw)
    for key in list(index.title_to_hits.keys()):
        kept = [hit for hit in index.title_to_hits[key] if not (hit.obsidian_path and ARCHIVE_DIRNAME in Path(hit.obsidian_path).parts)]
        if kept:
            index.title_to_hits[key] = kept
        else:
            del index.title_to_hits[key]
    for key in list(index.doi_to_hits.keys()):
        kept = [hit for hit in index.doi_to_hits[key] if not (hit.obsidian_path and ARCHIVE_DIRNAME in Path(hit.obsidian_path).parts)]
        if kept:
            index.doi_to_hits[key] = kept
        else:
            del index.doi_to_hits[key]
    index.save(index_path)


def _read_text_preserve_newlines(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()

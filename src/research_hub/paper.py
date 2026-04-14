"""Per-paper labels, curation, and archive management."""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

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


@dataclass
class PaperLabel:
    slug: str
    cluster_slug: str
    path: Path
    labels: list[str] = field(default_factory=list)
    fit_score: int | None = None
    fit_reason: str = ""
    labeled_at: str = ""


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

    sidecar = _hub_cluster_dir(cfg, cluster_slug) / ".fit_check_rejected.json"
    if not sidecar.exists():
        return {"tagged": [], "already": [], "missing": []}

    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    rejected = payload.get("rejected") or []

    doi_to_note: dict[str, Path] = {}
    for note_path in _iter_cluster_notes(cfg, cluster_slug, include_archive=False):
        meta = _parse_frontmatter(note_path.read_text(encoding="utf-8"))
        doi = str(meta.get("doi", "") or "").strip()
        if doi:
            doi_to_note[normalize_doi(doi)] = note_path

    tagged: list[str] = []
    already: list[str] = []
    missing: list[str] = []
    for entry in rejected:
        norm = normalize_doi(str(entry.get("doi", "") or ""))
        if not norm:
            continue
        note_path = doi_to_note.get(norm)
        if note_path is None:
            missing.append(str(entry.get("doi", "") or ""))
            continue
        existing = _parse_paper_label(note_path, slug=note_path.stem).labels
        if "deprecated" in existing:
            already.append(note_path.stem)
            continue
        set_labels(
            cfg,
            note_path.stem,
            add=["deprecated"],
            fit_score=int(entry.get("score", 0)),
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
                shutil.move(str(state.path), str(dest))
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
    shutil.move(str(source), str(dest))

    state = _parse_paper_label(dest, slug=slug)
    _rewrite_paper_frontmatter(
        dest,
        {
            "topic_cluster": cluster_slug,
            "labels": [label for label in state.labels if label != "archived"],
            "labeled_at": _utc_now(),
        },
    )
    _rebuild_dedup_index(cfg)
    return {"restored": slug, "path": str(dest)}


def archive_dir(cfg, cluster_slug: str) -> Path:
    return Path(cfg.raw) / ARCHIVE_DIRNAME / cluster_slug


def label_from_fit_score(score: int) -> str | None:
    if score >= 4:
        return "core"
    if score <= 1:
        return "deprecated"
    if score == 2:
        return "tangential"
    return None


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


def _parse_frontmatter(text: str) -> dict[str, object]:
    frontmatter = _extract_frontmatter(text)
    if frontmatter is None:
        return {}
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

    fit_score_raw = meta.get("fit_score")
    fit_score: int | None = None
    if isinstance(fit_score_raw, int):
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
    )


def _rewrite_paper_frontmatter(note_path: Path, updates: dict) -> None:
    text = _read_text_preserve_newlines(note_path)
    split = _split_frontmatter(text)
    if split is None:
        logger.warning("paper labels: malformed or missing frontmatter in %s", note_path)
        return
    opening, frontmatter, body, newline = split
    parsed = _parse_frontmatter(opening + frontmatter + newline + "---" + newline)
    ordered_keys = _frontmatter_key_order(frontmatter)
    for key, value in updates.items():
        parsed[key] = value
        if key not in ordered_keys:
            ordered_keys.append(key)
    rendered = _render_frontmatter(parsed, ordered_keys, newline)
    with note_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"{opening}{rendered}{newline}---{newline}{body}")


def _split_frontmatter(text: str) -> tuple[str, str, str, str] | None:
    if text.startswith("---\r\n"):
        newline = "\r\n"
    elif text.startswith("---\n"):
        newline = "\n"
    else:
        return None
    opening = f"---{newline}"
    close = f"{newline}---{newline}"
    end = text.find(close, len(opening))
    if end == -1:
        return None
    frontmatter = text[len(opening):end]
    body = text[end + len(close):]
    return opening, frontmatter, body, newline


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
        return [f"{key}:"] + [f"  - {item}" for item in value]
    if value is None:
        return [f"{key}: "]
    if isinstance(value, bool):
        return [f"{key}: {'true' if value else 'false'}"]
    return [f'{key}: "{_escape_scalar(str(value))}"']


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

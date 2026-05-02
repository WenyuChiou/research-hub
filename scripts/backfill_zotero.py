from __future__ import annotations

import argparse
import inspect
import json
import math
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from research_hub.clusters import Cluster, ClusterRegistry
from research_hub.manifest import Manifest, new_entry
from research_hub.zotero.client import ZoteroDualClient


LEGACY_BATCH_LABEL = "legacy-pre-2026-04-11"
CASE_LABELS = {
    "A": "case_A_missing.json",
    "B": "case_B_skip.json",
    "C": "case_C_rebind.json",
    "D": "case_D_recreate.json",
}
FRONTMATTER_BLOCK_RE = re.compile(r"^---\n(.*?)\n---(?=\n|$)", re.DOTALL)
ZOTERO_KEY_LINE_RE = re.compile(
    r"(?m)^(?P<prefix>\s*zotero-key:\s*)(?P<quote>['\"]?)(?P<value>[^\n'\"]*)(?P=quote)\s*$"
)


class BackfillArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise argparse.ArgumentError(None, message)


@dataclass
class BackfillEntry:
    obsidian_path: str
    title: str
    doi: str
    zotero_key_old: str
    case: str
    zotero_key_new: str = ""
    applied_at: str = ""
    applied_status: str = ""
    error_message: str = ""
    note_zotero_key: str = field(default="", repr=False)
    target_zotero_key: str = field(default="", repr=False)
    frontmatter: dict[str, Any] = field(default_factory=dict, repr=False)

    def record_key(self) -> tuple[str, str, str]:
        return (self.obsidian_path, self.case, self.zotero_key_old)

    def to_record(self) -> dict[str, Any]:
        payload = {
            "obsidian_path": self.obsidian_path,
            "title": self.title,
            "doi": self.doi,
            "zotero_key_old": self.zotero_key_old,
            "zotero_key_new": self.zotero_key_new,
            "case": self.case,
            "applied_at": self.applied_at,
            "applied_status": self.applied_status,
        }
        if self.error_message:
            payload["error_message"] = self.error_message
        return payload


@dataclass
class ClusterPlan:
    cluster: Cluster
    note_dir: Path
    notes_scanned: int = 0
    get_calls: int = 0
    entries_by_case: dict[str, list[BackfillEntry]] = field(
        default_factory=lambda: {case: [] for case in CASE_LABELS}
    )

    def counts(self) -> dict[str, int]:
        return {case: len(self.entries_by_case[case]) for case in CASE_LABELS}

    def planned_create_count(self) -> int:
        return self.counts()["A"] + self.counts()["D"]


class RateLimiter:
    def __init__(self, rate_per_second: float) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be > 0")
        self.interval = 1.0 / rate_per_second
        self._last_acquired: float | None = None

    def acquire(self) -> None:
        now = time.monotonic()
        if self._last_acquired is not None:
            elapsed = now - self._last_acquired
            if elapsed < self.interval:
                time.sleep(self.interval - elapsed)
        self._last_acquired = time.monotonic()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_doi(value: str) -> str:
    text = str(value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text.strip()


def log_progress(message: str) -> None:
    print(message, flush=True)


def build_cfg(vault_root: Path) -> SimpleNamespace:
    root = vault_root.expanduser()
    return SimpleNamespace(
        root=root,
        raw=root / "raw",
        research_hub_dir=root / ".research_hub",
        clusters_file=root / ".research_hub" / "clusters.yaml",
        manifest_path=root / ".research_hub" / "manifest.jsonl",
    )


def resolve_pipeline_api() -> tuple[Callable[..., tuple[list[dict], list[dict], list[dict]]], int]:
    from research_hub import pipeline

    helper = getattr(pipeline, "write_papers_to_zotero", None)
    if helper is None:
        raise RuntimeError(
            "Prerequisite missing: research_hub.pipeline.write_papers_to_zotero(...) "
            "does not exist yet. Merge v0.74.0-drift-prevention first."
        )
    signature = inspect.signature(helper)
    for required_name in ("batch_coll", "batch_label"):
        if required_name not in signature.parameters:
            raise RuntimeError(
                "Prerequisite missing: research_hub.pipeline.write_papers_to_zotero(...) "
                f"must accept `{required_name}`. Merge v0.74.0-drift-prevention first."
            )
    batch_size = int(getattr(pipeline, "ZOTERO_BATCH_SIZE", 50) or 50)
    return helper, batch_size


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = BackfillArgumentParser(
        description="Audit and backfill legacy Obsidian/Zotero drift by cluster.",
    )
    parser.add_argument("--vault", required=True, help="Path to the vault root")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--cluster", default=None, help="One cluster slug to process")
    scope.add_argument("--all", dest="all_clusters", action="store_true", help="Process all clusters")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="apply", action="store_false", help="Plan only (default)")
    mode.add_argument("--apply", dest="apply", action="store_true", help="Execute the plan")
    parser.set_defaults(apply=False)
    parser.add_argument("--limit", type=int, default=0, help="Max notes to scan per cluster (0 = no limit)")
    parser.add_argument("--rate-limit", type=float, default=4.0, help="Zotero write calls per second")
    parser.add_argument("--force", action="store_true", help="Re-run entries already marked ok")
    args = parser.parse_args(argv)
    if args.limit < 0:
        raise argparse.ArgumentError(None, "--limit must be >= 0")
    if args.rate_limit <= 0:
        raise argparse.ArgumentError(None, "--rate-limit must be > 0")
    return args


def parse_frontmatter(text: str) -> dict[str, Any]:
    match = FRONTMATTER_BLOCK_RE.match(text)
    if not match:
        return {}
    body = match.group(1)
    try:
        import yaml

        loaded = yaml.safe_load(body) or {}
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        pass

    parsed: dict[str, Any] = {}
    for line in body.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        token = value.strip()
        if token.startswith("[") and token.endswith("]"):
            inner = token[1:-1].strip()
            parsed[key.strip()] = [
                item.strip().strip('"').strip("'")
                for item in inner.split(",")
                if item.strip()
            ]
            continue
        parsed[key.strip()] = token.strip('"').strip("'")
    return parsed


def read_note_frontmatter(note_path: Path) -> dict[str, Any]:
    try:
        return parse_frontmatter(note_path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return {}


def extract_note_key(frontmatter: dict[str, Any]) -> str:
    raw = frontmatter.get("zotero-key")
    if raw in (None, ""):
        raw = frontmatter.get("zotero_key")
    return str(raw or "").strip().strip('"').strip("'")


def note_title(frontmatter: dict[str, Any], note_path: Path) -> str:
    title = str(frontmatter.get("title") or note_path.stem).strip()
    return title or note_path.stem


def not_found_error(exc: Exception) -> bool:
    if getattr(exc, "status_code", None) == 404:
        return True
    return "404" in str(exc)


def fetch_item(zot: Any, key: str) -> dict[str, Any]:
    if hasattr(zot, "item"):
        return zot.item(key)
    if hasattr(zot, "get_item"):
        return zot.get_item(key)
    raise AttributeError("Zotero client has no item/get_item reader")


def search_existing_key_by_doi(zot: Any, doi: str) -> str:
    if not doi:
        return ""
    hits: Any = []
    if hasattr(zot, "search_by_doi"):
        hits = zot.search_by_doi(doi)
    elif hasattr(zot, "search"):
        hits = zot.search(doi, limit=10)
    elif hasattr(zot, "items"):
        hits = zot.items(q=doi, limit=10)
    for hit in hits or []:
        data = hit.get("data", {})
        if normalize_doi(data.get("DOI", "")) == doi:
            return str(hit.get("key") or data.get("key") or "").strip()
    return ""


def classify_note(
    zot: Any,
    cluster_slug: str,
    cluster_coll: str,
    note_path: Path,
    frontmatter: dict[str, Any],
) -> tuple[BackfillEntry, bool]:
    del cluster_slug
    zk = extract_note_key(frontmatter)
    doi = normalize_doi(str(frontmatter.get("doi") or ""))
    title = note_title(frontmatter, note_path)
    used_get = False

    if not zk:
        dedup_key = search_existing_key_by_doi(zot, doi)
        case = "C" if dedup_key else "A"
        return (
            BackfillEntry(
                obsidian_path=str(note_path),
                title=title,
                doi=doi,
                zotero_key_old=zk,
                case=case,
                note_zotero_key=zk,
                target_zotero_key=dedup_key,
                frontmatter=frontmatter,
            ),
            used_get,
        )

    try:
        item = fetch_item(zot, zk)
        used_get = True
    except Exception as exc:
        used_get = True
        if not_found_error(exc):
            dedup_key = search_existing_key_by_doi(zot, doi)
            case = "C" if dedup_key else "D"
            return (
                BackfillEntry(
                    obsidian_path=str(note_path),
                    title=title,
                    doi=doi,
                    zotero_key_old=zk,
                    case=case,
                    note_zotero_key=zk,
                    target_zotero_key=dedup_key,
                    frontmatter=frontmatter,
                ),
                used_get,
            )
        raise

    collections = list(item.get("data", {}).get("collections", []) or [])
    case = "B" if cluster_coll in collections else "C"
    return (
        BackfillEntry(
            obsidian_path=str(note_path),
            title=title,
            doi=doi,
            zotero_key_old=zk,
            case=case,
            note_zotero_key=zk,
            target_zotero_key=zk,
            frontmatter=frontmatter,
        ),
        used_get,
    )


def cluster_note_dir(cfg: SimpleNamespace, cluster: Cluster) -> Path:
    folder_name = cluster.obsidian_subfolder or cluster.slug
    return cfg.raw / folder_name


def load_existing_statuses(plan_dir: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    status_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    for filename in CASE_LABELS.values():
        path = plan_dir / filename
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, list):
            continue
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            key = (
                str(entry.get("obsidian_path", "")),
                str(entry.get("case", "")),
                str(entry.get("zotero_key_old", "")),
            )
            status_map[key] = entry
    return status_map


def merge_existing_status(entry: BackfillEntry, previous: dict[str, Any] | None) -> None:
    if not previous:
        return
    entry.zotero_key_new = str(previous.get("zotero_key_new", "") or "")
    entry.applied_at = str(previous.get("applied_at", "") or "")
    entry.applied_status = str(previous.get("applied_status", "") or "")
    entry.error_message = str(previous.get("error_message", "") or "")


def write_cluster_plan_files(plan_dir: Path, entries_by_case: dict[str, list[BackfillEntry]]) -> None:
    plan_dir.mkdir(parents=True, exist_ok=True)
    for case, filename in CASE_LABELS.items():
        payload = [entry.to_record() for entry in entries_by_case.get(case, [])]
        (plan_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def render_backup_line(source: Path, backup: Path | None) -> str:
    if backup is not None:
        return f"- Backup of `{source}` -> `{backup}`"
    return f"- Backup of `{source}` -> `(source missing; no backup created)`"


def select_clusters(registry: ClusterRegistry, args: argparse.Namespace) -> list[Cluster]:
    if args.cluster:
        cluster = registry.get(args.cluster)
        if cluster is None:
            raise ValueError(f"Unknown cluster slug: {args.cluster}")
        return [cluster]
    clusters = sorted(registry.list(), key=lambda item: item.slug)
    if not clusters:
        raise ValueError(f"No clusters found in {registry.path}")
    return clusters


def build_cluster_plan(
    zot: Any,
    cfg: SimpleNamespace,
    cluster: Cluster,
    *,
    limit: int = 0,
) -> ClusterPlan:
    if not cluster.zotero_collection_key:
        raise ValueError(f"Cluster '{cluster.slug}' has no zotero_collection_key")

    note_dir = cluster_note_dir(cfg, cluster)
    plan = ClusterPlan(cluster=cluster, note_dir=note_dir)
    note_paths = sorted(note_dir.rglob("*.md")) if note_dir.exists() else []
    if limit > 0:
        note_paths = note_paths[:limit]
    plan.notes_scanned = len(note_paths)

    previous = load_existing_statuses(cfg.research_hub_dir / "backfill" / cluster.slug)
    for note_path in note_paths:
        frontmatter = read_note_frontmatter(note_path)
        entry, used_get = classify_note(
            zot,
            cluster.slug,
            str(cluster.zotero_collection_key or ""),
            note_path,
            frontmatter,
        )
        if used_get:
            plan.get_calls += 1
        merge_existing_status(entry, previous.get(entry.record_key()))
        plan.entries_by_case[entry.case].append(entry)

    return plan


def summary_row(plan: ClusterPlan, batch_size: int) -> tuple[str, int, int, int, int, int, int]:
    counts = plan.counts()
    est_writes = counts["C"] + math.ceil((counts["A"] + counts["D"]) / batch_size) if (counts["A"] + counts["D"]) else counts["C"]
    return (
        plan.cluster.slug,
        plan.notes_scanned,
        counts["A"],
        counts["B"],
        counts["C"],
        counts["D"],
        est_writes,
    )


def write_summary(
    cfg: SimpleNamespace,
    plans: list[ClusterPlan],
    *,
    batch_size: int,
    rate_limit: float,
    papers_backup: Path | None,
    clusters_backup: Path | None,
) -> Path:
    out_dir = cfg.research_hub_dir / "backfill"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"backfill_plan_{timestamp_slug()}.md"

    rows = [summary_row(plan, batch_size) for plan in plans]
    total_scanned = sum(row[1] for row in rows)
    total_a = sum(row[2] for row in rows)
    total_b = sum(row[3] for row in rows)
    total_c = sum(row[4] for row in rows)
    total_d = sum(row[5] for row in rows)
    total_est_writes = sum(row[6] for row in rows)
    total_get_calls = sum(plan.get_calls for plan in plans)
    create_calls = sum(
        math.ceil(plan.planned_create_count() / batch_size)
        for plan in plans
        if plan.planned_create_count()
    )
    update_calls = total_c
    get_minutes = total_get_calls / 10.0 / 60.0
    create_minutes = create_calls / rate_limit / 60.0
    update_minutes = update_calls / rate_limit / 60.0
    total_minutes = get_minutes + create_minutes + update_minutes

    lines = [
        f"# Backfill plan - generated {utc_now()}",
        "",
        "| Cluster | Notes scanned | A (missing) | B (skip) | C (rebind) | D (recreate) | Est. Zotero writes |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]} | {row[6]} |"
        )
    lines.extend(
        [
            f"| **TOTAL** | **{total_scanned}** | **{total_a}** | **{total_b}** | **{total_c}** | **{total_d}** | **{total_est_writes}** |",
            "",
            "### Wall-clock estimate",
            f"- HTTP GETs (B/C/D classification): ~10/s = {get_minutes:.2f} min",
            f"- Zotero create_items writes (A/D): rate-limited to {rate_limit:g}/s = {create_minutes:.2f} min",
            f"- Zotero update_items writes (C): rate-limited to {rate_limit:g}/s = {update_minutes:.2f} min",
            f"- Total: {total_minutes:.2f} min",
            "",
            "### Safety",
            render_backup_line(cfg.root / "papers_input.json", papers_backup),
            render_backup_line(cfg.clusters_file, clusters_backup),
            f"- All writes append to `{cfg.manifest_path}` with action=backfill_<case>",
        ]
    )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def copy_backup(source: Path) -> Path | None:
    if not source.exists():
        return None
    backup = source.with_name(f"{source.name}.bak-{timestamp_slug()}")
    shutil.copy2(source, backup)
    return backup


def parse_year(value: Any) -> int | str:
    raw = str(value or "").strip()
    match = re.search(r"\d{4}", raw)
    if match:
        return int(match.group(0))
    return 2025


def parse_authors_from_fm(frontmatter: dict[str, Any]) -> list[dict[str, str]]:
    raw = frontmatter.get("authors", "")
    if isinstance(raw, list):
        names = [str(item).strip() for item in raw if str(item).strip()]
    else:
        text = str(raw or "").strip()
        if not text:
            return [{"creatorType": "author", "name": "Unknown"}]
        names = [part.strip() for part in text.split(";") if part.strip()]
        if len(names) == 1 and " and " in text.lower():
            names = [part.strip() for part in re.split(r"\band\b", text, flags=re.IGNORECASE) if part.strip()]

    creators: list[dict[str, str]] = []
    organization_tokens = {
        "agency",
        "association",
        "bureau",
        "center",
        "centre",
        "college",
        "committee",
        "corporation",
        "department",
        "institute",
        "ministry",
        "office",
        "organization",
        "society",
        "university",
    }
    for name in names:
        if "," in name:
            last, first = [part.strip() for part in name.split(",", 1)]
            creators.append(
                {
                    "creatorType": "author",
                    "firstName": first,
                    "lastName": last,
                }
            )
            continue
        lowered = name.lower()
        if any(token in lowered for token in organization_tokens):
            creators.append({"creatorType": "author", "name": name})
            continue
        parts = name.split()
        if len(parts) >= 2:
            creators.append(
                {
                    "creatorType": "author",
                    "firstName": " ".join(parts[:-1]),
                    "lastName": parts[-1],
                }
            )
        else:
            creators.append({"creatorType": "author", "name": name})
    return creators or [{"creatorType": "author", "name": "Unknown"}]


def build_paper(entry: BackfillEntry, cluster_slug: str) -> dict[str, Any]:
    frontmatter = entry.frontmatter or read_note_frontmatter(Path(entry.obsidian_path))
    note_path = Path(entry.obsidian_path)
    return {
        "title": entry.title,
        "doi": entry.doi,
        "authors": parse_authors_from_fm(frontmatter),
        "year": parse_year(frontmatter.get("year")),
        "abstract": str(frontmatter.get("abstract") or "(legacy backfill)"),
        "journal": str(frontmatter.get("journal") or "(unknown venue)"),
        "slug": str(frontmatter.get("slug") or note_path.stem),
        "sub_category": cluster_slug,
        "tags": [],
        "url": str(frontmatter.get("url") or ""),
        "volume": str(frontmatter.get("volume") or ""),
        "issue": str(frontmatter.get("issue") or ""),
        "pages": str(frontmatter.get("pages") or ""),
    }


def rewrite_note_zotero_key(note_path: Path, new_key: str) -> bool:
    text = note_path.read_text(encoding="utf-8", errors="ignore")
    match = FRONTMATTER_BLOCK_RE.match(text)
    if not match:
        new_text = f"---\nzotero-key: {new_key}\n---\n" + text.lstrip("\n")
    else:
        block = match.group(0)
        if ZOTERO_KEY_LINE_RE.search(block):
            def _replace(line_match: re.Match[str]) -> str:
                quote = line_match.group("quote")
                if quote:
                    return f"{line_match.group('prefix')}{quote}{new_key}{quote}"
                return f"{line_match.group('prefix')}{new_key}"

            new_block = ZOTERO_KEY_LINE_RE.sub(_replace, block, count=1)
        else:
            insert_at = block.rfind("\n---")
            new_block = block[:insert_at] + f"\nzotero-key: {new_key}" + block[insert_at:]
        new_text = new_block + text[len(block):]
    if new_text == text:
        return False
    note_path.write_text(new_text, encoding="utf-8")
    return True


def append_manifest_entry(
    manifest: Manifest,
    cluster_slug: str,
    case: str,
    entry: BackfillEntry,
    zotero_key: str,
    *,
    error: str = "",
) -> None:
    manifest.append(
        new_entry(
            cluster=cluster_slug,
            query="backfill",
            action=f"backfill_{case}",
            doi=entry.doi,
            title=entry.title,
            zotero_key=zotero_key,
            obsidian_path=entry.obsidian_path,
            batch_label=LEGACY_BATCH_LABEL,
            error=error,
        )
    )


def mark_entry(
    entry: BackfillEntry,
    *,
    status: str,
    zotero_key_new: str = "",
    error_message: str = "",
) -> None:
    entry.applied_at = utc_now()
    entry.applied_status = status
    if zotero_key_new:
        entry.zotero_key_new = zotero_key_new
    if error_message:
        entry.error_message = error_message


def update_item_collections(zot: Any, item_key: str, cluster_coll: str) -> str:
    item = fetch_item(zot, item_key)
    data = item.get("data", {})
    collections = list(data.get("collections", []) or [])
    if cluster_coll not in collections:
        collections.append(cluster_coll)
    data["collections"] = collections
    try:
        zot.update_item(data)
    except TypeError:
        zot.update_item(item_key, {"collections": collections})
    return item_key


def apply_case_c_entries(
    zot: Any,
    manifest: Manifest,
    plan: ClusterPlan,
    rate_limiter: RateLimiter,
    *,
    force: bool = False,
) -> int:
    failures = 0
    cluster_coll = str(plan.cluster.zotero_collection_key or "")
    for entry in plan.entries_by_case["C"]:
        if entry.applied_status == "ok" and not force:
            continue
        target_key = entry.target_zotero_key or entry.zotero_key_old
        if not target_key:
            mark_entry(entry, status="failed", error_message="missing target Zotero key for case C")
            append_manifest_entry(
                manifest,
                plan.cluster.slug,
                entry.case,
                entry,
                "",
                error="missing target Zotero key for case C",
            )
            failures += 1
            continue
        try:
            rate_limiter.acquire()
            update_item_collections(zot, target_key, cluster_coll)
            if entry.note_zotero_key != target_key:
                rewrite_note_zotero_key(Path(entry.obsidian_path), target_key)
            mark_entry(entry, status="ok", zotero_key_new=target_key)
            append_manifest_entry(manifest, plan.cluster.slug, entry.case, entry, target_key)
        except Exception as exc:
            failures += 1
            mark_entry(entry, status="failed", error_message=str(exc))
            append_manifest_entry(
                manifest,
                plan.cluster.slug,
                entry.case,
                entry,
                target_key,
                error=str(exc),
            )
    return failures


def apply_create_entries(
    zot: Any,
    manifest: Manifest,
    plan: ClusterPlan,
    rate_limiter: RateLimiter,
    *,
    write_papers_to_zotero: Callable[..., tuple[list[dict], list[dict], list[dict]]],
    batch_size: int,
    case: str,
    force: bool = False,
) -> int:
    failures = 0
    pending = [
        entry
        for entry in plan.entries_by_case[case]
        if force or entry.applied_status != "ok"
    ]
    if not pending:
        return 0

    for start in range(0, len(pending), batch_size):
        batch_entries = pending[start : start + batch_size]
        papers = [build_paper(entry, plan.cluster.slug) for entry in batch_entries]
        try:
            rate_limiter.acquire()
            write_papers_to_zotero(
                zot,
                papers,
                plan.cluster.slug,
                str(plan.cluster.zotero_collection_key or ""),
                batch_coll=None,
                batch_label=LEGACY_BATCH_LABEL,
                zotero_batch_size=batch_size,
                log=log_progress,
            )
        except Exception as exc:
            for entry in batch_entries:
                failures += 1
                mark_entry(entry, status="failed", error_message=str(exc))
                append_manifest_entry(
                    manifest,
                    plan.cluster.slug,
                    entry.case,
                    entry,
                    "",
                    error=str(exc),
                )
            continue

        for entry, paper in zip(batch_entries, papers):
            created_key = str(paper.get("zotero_key") or "").strip()
            if not created_key:
                failures += 1
                message = f"write_papers_to_zotero returned no zotero_key for {entry.title}"
                mark_entry(entry, status="failed", error_message=message)
                append_manifest_entry(
                    manifest,
                    plan.cluster.slug,
                    entry.case,
                    entry,
                    "",
                    error=message,
                )
                continue
            rewrite_note_zotero_key(Path(entry.obsidian_path), created_key)
            mark_entry(entry, status="ok", zotero_key_new=created_key)
            append_manifest_entry(
                manifest,
                plan.cluster.slug,
                entry.case,
                entry,
                created_key,
            )
    return failures


def apply_cluster_plan(
    zot: Any,
    manifest: Manifest,
    plan: ClusterPlan,
    *,
    write_papers_to_zotero: Callable[..., tuple[list[dict], list[dict], list[dict]]],
    batch_size: int,
    rate_limiter: RateLimiter,
    force: bool = False,
) -> int:
    failures = 0
    failures += apply_create_entries(
        zot,
        manifest,
        plan,
        rate_limiter,
        write_papers_to_zotero=write_papers_to_zotero,
        batch_size=batch_size,
        case="A",
        force=force,
    )
    failures += apply_case_c_entries(
        zot,
        manifest,
        plan,
        rate_limiter,
        force=force,
    )
    failures += apply_create_entries(
        zot,
        manifest,
        plan,
        rate_limiter,
        write_papers_to_zotero=write_papers_to_zotero,
        batch_size=batch_size,
        case="D",
        force=force,
    )
    return failures


def run(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except argparse.ArgumentError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return 2

    try:
        write_papers_to_zotero, batch_size = resolve_pipeline_api()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    cfg = build_cfg(Path(args.vault))
    registry = ClusterRegistry(cfg.clusters_file)
    try:
        clusters = select_clusters(registry, args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    cfg.research_hub_dir.mkdir(parents=True, exist_ok=True)
    zot = getattr(ZoteroDualClient(), "web")
    plans: list[ClusterPlan] = []
    try:
        for cluster in clusters:
            plan = build_cluster_plan(
                zot,
                cfg,
                cluster,
                limit=args.limit,
            )
            write_cluster_plan_files(cfg.research_hub_dir / "backfill" / cluster.slug, plan.entries_by_case)
            plans.append(plan)
    except Exception as exc:
        print(f"ERROR: backfill planning failed: {exc}", file=sys.stderr)
        return 1

    papers_backup = copy_backup(cfg.root / "papers_input.json") if args.apply else None
    clusters_backup = copy_backup(cfg.clusters_file) if args.apply else None
    summary_path = write_summary(
        cfg,
        plans,
        batch_size=batch_size,
        rate_limit=args.rate_limit,
        papers_backup=papers_backup,
        clusters_backup=clusters_backup,
    )
    log_progress(f"Plan summary written to {summary_path}")

    if not args.apply:
        return 0

    manifest = Manifest(cfg.manifest_path)
    rate_limiter = RateLimiter(args.rate_limit)
    failures = 0
    for plan in plans:
        log_progress(f"[apply] {plan.cluster.slug}: A={len(plan.entries_by_case['A'])} C={len(plan.entries_by_case['C'])} D={len(plan.entries_by_case['D'])}")
        failures += apply_cluster_plan(
            zot,
            manifest,
            plan,
            write_papers_to_zotero=write_papers_to_zotero,
            batch_size=batch_size,
            rate_limiter=rate_limiter,
            force=args.force,
        )
        write_cluster_plan_files(cfg.research_hub_dir / "backfill" / plan.cluster.slug, plan.entries_by_case)
    return 1 if failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())

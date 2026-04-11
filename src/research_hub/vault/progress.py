"""Vault reading-progress reporting helpers."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import re

from research_hub.clusters import ClusterRegistry

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---(?:\n|$)", re.DOTALL)
STATUS_COLUMNS = (
    ("unread", "Unread"),
    ("skim", "Skim"),
    ("deep-read", "Deep"),
    ("cited", "Cited"),
    ("archived", "Arch"),
)
STATUS_ALIASES = {
    "deep": "deep-read",
    "deep-read": "deep-read",
    "archive": "archived",
    "arch": "archived",
    "archived": "archived",
    "skim": "skim",
    "cited": "cited",
    "unread": "unread",
}


def _frontmatter_map(text: str) -> dict[str, str]:
    """Return a flat frontmatter mapping parsed from a markdown note."""

    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}

    frontmatter: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip().strip('"').strip("'")
    return frontmatter


def _iter_note_rows(raw_dir: Path) -> list[dict[str, str]]:
    """Read note metadata needed for status reports in a single vault walk."""

    rows: list[dict[str, str]] = []
    if not raw_dir.exists():
        return rows

    for path in sorted(raw_dir.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        frontmatter = _frontmatter_map(text)
        status = STATUS_ALIASES.get(frontmatter.get("status", "").strip().lower(), "unread")
        rows.append(
            {
                "cluster": frontmatter.get("topic_cluster", "").strip(),
                "status": status,
                "title": frontmatter.get("title", path.stem).strip() or path.stem,
                "path": str(path),
                "ingested_at": frontmatter.get("ingested_at", "").strip(),
            }
        )
    return rows


def count_status_by_cluster(raw_dir: Path) -> dict[str, Counter]:
    """Return per-cluster reading-status counts plus ``__unassigned__``."""

    counts: dict[str, Counter] = {}
    for row in _iter_note_rows(raw_dir):
        cluster = row["cluster"] or "__unassigned__"
        counts.setdefault(cluster, Counter())
        counts[cluster][row["status"]] += 1
    return counts


def _format_table_rows(
    rows: list[tuple[str, int, int, int, int, int, int]],
) -> list[str]:
    """Render the summary rows as a plain-text table."""

    headers = ("Cluster", "Total", "Unread", "Skim", "Deep", "Cited", "Arch")
    cluster_width = max([len(headers[0]), *[len(row[0]) for row in rows]] or [len(headers[0])])
    widths = [cluster_width]
    for index in range(1, len(headers)):
        widths.append(
            max(
                len(headers[index]),
                *[len(str(row[index])) for row in rows],
            )
        )

    def fmt(row: tuple[str, int, int, int, int, int, int] | tuple[str, ...]) -> str:
        parts = [str(row[0]).ljust(widths[0])]
        for index in range(1, len(row)):
            parts.append(str(row[index]).rjust(widths[index]))
        return "  ".join(parts)

    lines = [fmt(headers), "-" * len(fmt(headers))]
    for row in rows:
        lines.append(fmt(row))
    return lines


def print_status_table(
    raw_dir: Path,
    clusters_registry: ClusterRegistry,
    one_cluster: str | None = None,
) -> None:
    """Print either the global cluster table or one cluster's paper breakdown."""

    counts = count_status_by_cluster(raw_dir)
    rows = _iter_note_rows(raw_dir)
    known_slugs = [cluster.slug for cluster in clusters_registry.list()]

    if one_cluster is not None:
        cluster = clusters_registry.get(one_cluster)
        if cluster is None:
            raise ValueError(f"Cluster not found: {one_cluster}")
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            if row["cluster"] == one_cluster:
                grouped[row["status"]].append(row)

        cluster_counts = counts.get(one_cluster, Counter())
        total = sum(cluster_counts.values())
        print(f"{cluster.slug} ({cluster.name})")
        print(f"Total: {total}")
        for status, label in STATUS_COLUMNS:
            items = sorted(grouped.get(status, []), key=lambda item: item["title"].lower())
            print(f"\n{label} ({len(items)})")
            if not items:
                print("- none")
                continue
            for item in items:
                rel_path = Path(item["path"]).relative_to(raw_dir)
                print(f"- {item['title']} [{rel_path.as_posix()}]")
        return

    cluster_rows: list[tuple[str, int, int, int, int, int, int]] = []
    extra_slugs = sorted(
        slug for slug in counts if slug not in {"__unassigned__", *known_slugs}
    )
    for slug in [*known_slugs, *extra_slugs]:
        counter = counts.get(slug, Counter())
        total = sum(counter.values())
        cluster_rows.append(
            (
                slug,
                total,
                counter.get("unread", 0),
                counter.get("skim", 0),
                counter.get("deep-read", 0),
                counter.get("cited", 0),
                counter.get("archived", 0),
            )
        )

    cluster_rows.sort(key=lambda row: (-row[2], -row[1], row[0]))
    for line in _format_table_rows(cluster_rows):
        print(line)

    unassigned = sum(counts.get("__unassigned__", Counter()).values())
    if unassigned:
        print(f"Unassigned notes (no topic_cluster): {unassigned}")

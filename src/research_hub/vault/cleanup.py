"""Vault cleanup utilities.

Helpers for fixing duplicate wikilinks in hub pages — a common side
effect of running older builders or hand-editing hub entries.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


WIKILINK_LINE = re.compile(r"^\s*-\s*\[\[([^\]|]+)")


@dataclass
class DedupReport:
    files_scanned: int = 0
    files_modified: int = 0
    wikilinks_removed: int = 0
    per_file: dict[str, int] | None = None

    def __post_init__(self) -> None:
        if self.per_file is None:
            self.per_file = {}


def dedup_wikilinks_in_file(path: Path) -> int:
    """Remove duplicate `- [[target]]` bullet lines from a markdown file.

    Preserves the first occurrence of each target and drops subsequent ones.
    Non-wikilink lines are kept verbatim. Returns the number of lines removed.
    """
    if not path.exists():
        return 0
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return 0

    lines = text.split("\n")
    seen: set[str] = set()
    kept: list[str] = []
    removed = 0
    for line in lines:
        match = WIKILINK_LINE.match(line)
        if match:
            target = match.group(1).strip()
            if target in seen:
                removed += 1
                continue
            seen.add(target)
        kept.append(line)

    if removed == 0:
        return 0
    path.write_text("\n".join(kept), encoding="utf-8")
    return removed


def dedup_hub_pages(hub_dir: Path, dry_run: bool = False) -> DedupReport:
    """Walk a hub directory and dedupe wikilink bullets on every markdown file.

    The dry-run variant counts changes without writing.
    """
    report = DedupReport()
    if not hub_dir.exists():
        return report

    for md_path in hub_dir.rglob("*.md"):
        report.files_scanned += 1
        if dry_run:
            # Count without writing
            try:
                text = md_path.read_text(encoding="utf-8")
            except Exception:
                continue
            seen: set[str] = set()
            removed = 0
            for line in text.split("\n"):
                match = WIKILINK_LINE.match(line)
                if match:
                    target = match.group(1).strip()
                    if target in seen:
                        removed += 1
                    else:
                        seen.add(target)
            if removed > 0:
                report.files_modified += 1
                report.wikilinks_removed += removed
                rel = str(md_path.relative_to(hub_dir))
                report.per_file[rel] = removed
        else:
            removed = dedup_wikilinks_in_file(md_path)
            if removed > 0:
                report.files_modified += 1
                report.wikilinks_removed += removed
                rel = str(md_path.relative_to(hub_dir))
                report.per_file[rel] = removed

    return report

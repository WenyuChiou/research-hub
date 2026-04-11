"""YAML migration helpers for legacy vault notes."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import re

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---(?=\n|$)", re.DOTALL)
REQUIRED_FIELDS = (
    "status",
    "topic_cluster",
    "verified",
    "ingested_at",
    "ingestion_source",
)


def _frontmatter_map(frontmatter_text: str) -> dict[str, str]:
    """Parse flat YAML-style frontmatter into a string mapping."""

    match = FRONTMATTER_RE.match(frontmatter_text)
    if not match:
        return {}
    mapping: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        mapping[key.strip()] = value.strip().strip('"').strip("'")
    return mapping


def _yaml_scalar(value: Any) -> str:
    """Render a small scalar value into the repo's YAML style."""

    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(f'"{item}"' for item in value) + "]"
    if value is None:
        return '""'
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"true", "false"} or value == "" or ":" in value or value.endswith(" "):
            return f'"{value}"'
        return value
    return str(value)


def _mtime_iso(path: Path) -> str:
    """Format the file modification time as UTC ISO 8601."""

    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def needs_migration(frontmatter_text: str) -> list[str]:
    """Return required v0.3.x fields that are absent from the note."""

    current = _frontmatter_map(frontmatter_text)
    return [field for field in REQUIRED_FIELDS if field not in current]


def patch_frontmatter(frontmatter_text: str, patches: dict[str, Any]) -> str:
    """Insert or replace frontmatter keys while preserving unchanged order."""

    match = FRONTMATTER_RE.match(frontmatter_text)
    if not match:
        patch_lines = [f"{key}: {_yaml_scalar(value)}" for key, value in patches.items()]
        prefix = "---\n" + "\n".join(patch_lines) + "\n---\n"
        return prefix + frontmatter_text.lstrip("\n")

    lines = frontmatter_text.splitlines()
    closing_index = lines.index("---", 1)
    key_positions: dict[str, int] = {}
    for index in range(1, closing_index):
        line = lines[index]
        if ":" not in line:
            continue
        key = line.split(":", 1)[0].strip()
        key_positions[key] = index

    for key, value in patches.items():
        rendered = f"{key}: {_yaml_scalar(value)}"
        if key in key_positions:
            lines[key_positions[key]] = rendered
        else:
            lines.insert(closing_index, rendered)
            closing_index += 1
    return "\n".join(lines) + ("\n" if frontmatter_text.endswith("\n") else "")


def migrate_note(
    path: Path,
    default_status: str = "unread",
    cluster_override: str | None = None,
    force: bool = False,
    write: bool = True,
) -> dict[str, Any] | None:
    """Patch one note and return a migration report when a change is needed."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    current = _frontmatter_map(text)
    missing = needs_migration(text)
    patches: dict[str, Any] = {}
    skipped: str | None = None

    existing_cluster = current.get("topic_cluster", "").strip()
    if cluster_override is not None:
        if existing_cluster and existing_cluster != cluster_override and not force:
            skipped = "topic_cluster already set"
        elif existing_cluster != cluster_override:
            patches["topic_cluster"] = cluster_override

    if cluster_override is None and "status" not in missing:
        return None

    if "status" in missing:
        defaults: dict[str, Any] = {
            "topic_cluster": cluster_override or "",
            "cluster_queries": [],
            "verified": False,
            "status": default_status,
            "ingested_at": _mtime_iso(path),
            "ingestion_source": "pre-v0.3.0-migration",
        }
        for key, value in defaults.items():
            if key not in current and (key != "topic_cluster" or skipped is None):
                patches.setdefault(key, value)

    if skipped is not None and not patches:
        return {"path": str(path), "added": [], "skipped": skipped}
    if not patches:
        return None

    updated_text = patch_frontmatter(text, patches)
    if write and updated_text != text:
        path.write_text(updated_text, encoding="utf-8")
    return {"path": str(path), "added": list(patches.keys()), "skipped": skipped}


def migrate_vault(
    raw_dir: Path,
    cluster_override: str | None = None,
    folder: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Walk the vault, optionally restricting to a folder, and patch notes."""

    target_dir = raw_dir / folder if folder is not None else raw_dir
    reports: list[dict[str, Any]] = []
    skipped = 0
    scanned = 0

    if not target_dir.exists():
        return {"scanned": 0, "changed": 0, "skipped": 0, "reports": []}

    for path in sorted(target_dir.rglob("*.md")):
        scanned += 1
        report = migrate_note(
            path,
            cluster_override=cluster_override,
            force=force,
            write=not dry_run,
        )
        if report is None:
            continue
        if report.get("skipped"):
            skipped += 1
        reports.append(report)

    changed = sum(1 for report in reports if report["added"])
    return {"scanned": scanned, "changed": changed, "skipped": skipped, "reports": reports}

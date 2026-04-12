from __future__ import annotations

from pathlib import Path

from research_hub.dashboard.types import BriefingPreview


def _strip_header(text: str) -> str:
    lines = text.splitlines()
    header_prefixes = ("#", "Source:", "Downloaded:", "Sources:", "Saved briefings:")
    for index, line in enumerate(lines):
        if line.strip():
            continue
        remainder = "\n".join(lines[index + 1 :]).strip()
        if not remainder:
            return ""
        first_remainder = remainder.splitlines()[0].strip()
        if not first_remainder.startswith(header_prefixes):
            return remainder
    return text.strip()


def _truncate_at_word_boundary(text: str, char_limit: int) -> str:
    if char_limit <= 0 or len(text) <= char_limit:
        return text
    snippet = text[:char_limit]
    cut = snippet.rfind(" ")
    if cut > 0:
        snippet = snippet[:cut]
    return snippet.rstrip()


def load_briefing_preview(
    cluster_slug: str,
    cluster_name: str,
    cluster_cache: dict,
    artifacts_dir: Path,
    char_limit: int = 500,
) -> BriefingPreview | None:
    """Read the latest briefing artifact for a cluster."""
    if not artifacts_dir.exists():
        return None
    candidates = sorted(
        artifacts_dir.glob("brief-*.txt"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    latest = candidates[0]
    raw_text = latest.read_text(encoding="utf-8")
    full_text = _strip_header(raw_text)
    return BriefingPreview(
        cluster_slug=cluster_slug,
        cluster_name=cluster_name,
        notebook_url=str((cluster_cache or {}).get("notebook_url", "")),
        preview_text=_truncate_at_word_boundary(full_text, char_limit),
        full_text=full_text,
        char_count=len(full_text),
        downloaded_at=str(
            ((cluster_cache or {}).get("artifacts", {}) or {}).get("brief", {}).get(
                "downloaded_at",
                "",
            )
        ),
        titles=list(
            (((cluster_cache or {}).get("artifacts", {}) or {}).get("brief", {}) or {}).get(
                "titles",
                []
            )
            or []
        ),
    )

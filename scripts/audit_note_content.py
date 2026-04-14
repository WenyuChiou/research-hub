from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re

from research_hub.paper_schema import validate_paper_note
from research_hub.topic import _parse_frontmatter


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", type=Path, default=Path.home() / "knowledge-base")
    args = parser.parse_args()

    raw_root = args.vault / "raw"
    docs_dir = Path("docs")
    docs_dir.mkdir(parents=True, exist_ok=True)
    report_path = docs_dir / "audit_v0.26_notes.md"

    notes = [note for note in sorted(raw_root.rglob("*.md")) if _is_paper_note(note)]
    subtopic_notes = sorted(raw_root.rglob("topics/*.md"))
    note_index = {note.stem for note in raw_root.rglob("*.md")}

    missing_frontmatter: list[tuple[str, list[str]]] = []
    empty_sections: list[tuple[str, list[str]]] = []
    todo_placeholders: list[tuple[str, list[str]]] = []

    for note in notes:
        result = validate_paper_note(note)
        rel = str(note.relative_to(args.vault))
        if result.missing_frontmatter:
            missing_frontmatter.append((rel, result.missing_frontmatter))
        if result.empty_sections:
            empty_sections.append((rel, result.empty_sections))
        if result.todo_placeholders:
            todo_placeholders.append((rel, result.todo_placeholders))

    mismatches = []
    stale_links = []
    for note in subtopic_notes:
        text = note.read_text(encoding="utf-8")
        meta = _parse_frontmatter(text)
        papers_frontmatter = int(str(meta.get("papers", "0") or "0")) if str(meta.get("papers", "0") or "0").isdigit() else 0
        papers_count = len(re.findall(r"^\s*-\s+\[\[[^|\]]+(?:\|[^\]]+)?\]\]", _papers_section(text), re.MULTILINE))
        if papers_frontmatter != papers_count:
            mismatches.append((str(note.relative_to(args.vault)), papers_frontmatter, papers_count))
        for target in re.findall(r"\[\[([^|\]]+)(?:\|[^\]]+)?\]\]", text):
            if target not in note_index:
                stale_links.append((str(note.relative_to(args.vault)), target, "not in vault"))

    valid_count = len(notes) - len(missing_frontmatter) - len([item for item in empty_sections if item[0] not in {n for n, _ in missing_frontmatter}]) - len([item for item in todo_placeholders if item[0] not in {n for n, _ in missing_frontmatter} and item[0] not in {n for n, _ in empty_sections}])
    valid_count = sum(1 for note in notes if validate_paper_note(note).ok)
    total = len(notes)
    pct = f"{(valid_count / total * 100):.1f}" if total else "100.0"

    report = [
        "# Note Content Audit - v0.26.0",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}",
        "",
        "## Summary",
        "",
        f"- Total paper notes: {total}",
        f"- Fully valid: {valid_count} ({pct}%)",
        f"- Missing required frontmatter: {len(missing_frontmatter)}",
        f"- Empty content sections: {len(empty_sections)}",
        f"- TODO placeholders remaining: {len(todo_placeholders)}",
        "",
        "## Missing frontmatter",
        "",
        "| Note | Missing fields |",
        "|---|---|",
        *_rows_2(missing_frontmatter),
        "",
        "## Empty sections",
        "",
        "| Note | Empty sections |",
        "|---|---|",
        *_rows_2(empty_sections),
        "",
        "## TODO placeholders",
        "",
        "| Note | Sections still containing [TODO: |",
        "|---|---|",
        *_rows_2(todo_placeholders),
        "",
        "## Subtopic file mismatches",
        "",
        "| Subtopic file | papers: frontmatter | actual Papers section count |",
        "|---|---|---|",
        *_rows_3(mismatches),
        "",
        "## Stale wiki-links",
        "",
        "| Subtopic file | Wiki-link target | Status |",
        "|---|---|---|",
        *_rows_3(stale_links),
        "",
    ]
    report_path.write_text("\n".join(report), encoding="utf-8")

    print(
        f"audit complete: {total} paper notes, {valid_count} fully valid, "
        f"{len(missing_frontmatter)} missing frontmatter, {len(empty_sections)} empty sections, "
        f"{len(todo_placeholders)} TODO placeholders"
    )
    return 0


def _is_paper_note(path: Path) -> bool:
    return (
        path.suffix == ".md"
        and "topics" not in path.parts
        and not path.name.startswith("00_")
        and not path.name.startswith("index")
    )


def _papers_section(text: str) -> str:
    match = re.search(r"^##\s+Papers\s*\n(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    return match.group(1) if match else ""


def _rows_2(rows: list[tuple[str, list[str]]]) -> list[str]:
    if not rows:
        return ["| (none) | - |"]
    return [f"| {name} | {', '.join(values)} |" for name, values in rows]


def _rows_3(rows: list[tuple[object, ...]]) -> list[str]:
    if not rows:
        return ["| (none) | - | - |"]
    return [f"| {row[0]} | {row[1]} | {row[2]} |" for row in rows]


if __name__ == "__main__":
    raise SystemExit(main())

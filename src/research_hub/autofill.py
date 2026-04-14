"""Auto-fill paper note body content via emit/apply."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

TODO_MARKER_RE = re.compile(r"\[TODO[:\]]", re.IGNORECASE)


@dataclass
class AutofillPaper:
    slug: str
    title: str
    abstract: str
    note_path: Path


@dataclass
class AutofillResult:
    cluster_slug: str
    candidate_count: int
    filled: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def find_todo_papers(cfg, cluster_slug: str) -> list[AutofillPaper]:
    from research_hub.paper import _iter_cluster_notes

    out: list[AutofillPaper] = []
    for note_path in _iter_cluster_notes(cfg, cluster_slug, include_archive=False):
        text = note_path.read_text(encoding="utf-8")
        if not TODO_MARKER_RE.search(text):
            continue
        title, abstract = _extract_title_and_abstract(text, fallback_slug=note_path.stem)
        if not abstract or abstract.strip() in {"", "(no abstract)"}:
            continue
        out.append(
            AutofillPaper(
                slug=note_path.stem,
                title=title,
                abstract=abstract,
                note_path=note_path,
            )
        )
    return out


def emit_autofill_prompt(cfg, cluster_slug: str) -> str:
    papers = find_todo_papers(cfg, cluster_slug)
    if not papers:
        return (
            f'# Autofill: cluster "{cluster_slug}"\n\n'
            "No papers need autofill - all notes have real content.\n"
        )

    lines = [
        f'# Autofill: cluster "{cluster_slug}"',
        "",
        (
            f"{len(papers)} paper(s) have `[TODO: ...]` placeholders in their note body. "
            "Read each abstract below and produce a JSON object with filled-in content "
            "for every paper."
        ),
        "",
        "## Instructions",
        "",
        "For each paper, write:",
        "",
        "- **summary**: 2-3 sentences. What does this paper do and what is its main contribution?",
        "- **key_findings**: 3-5 bullet points. The concrete claims / results / numbers.",
        "- **methodology**: 1-3 sentences. How did they do it? (datasets, model, architecture, evaluation)",
        "- **relevance**: 1-2 sentences. Why does this paper belong in the cluster, or what unique angle does it contribute?",
        "",
        "Write in the style of a working researcher's lit-review notes. Concrete, no marketing language, no filler.",
        "",
        f"## Papers to autofill ({len(papers)} total)",
        "",
    ]
    for index, paper in enumerate(papers, start=1):
        lines.extend(
            [
                f"### {index}. {paper.title}",
                f"**Slug:** `{paper.slug}`",
                "**Abstract:**",
                paper.abstract,
                "",
            ]
        )
    lines.extend(
        [
            "## Your output",
            "",
            "Emit ONE JSON object, nothing else:",
            "",
            "```json",
            "{",
            '  "papers": [',
            "    {",
            '      "slug": "...",',
            '      "summary": "...",',
            '      "key_findings": ["...", "..."],',
            '      "methodology": "...",',
            '      "relevance": "..."',
            "    }",
            "  ]",
            "}",
            "```",
        ]
    )
    return "\n".join(lines)


def apply_autofill(cfg, cluster_slug: str, scored: dict | list) -> AutofillResult:
    from research_hub.paper import _find_note_path

    if isinstance(scored, dict) and "papers" in scored:
        papers_data = scored["papers"]
    elif isinstance(scored, list):
        papers_data = scored
    else:
        papers_data = []

    result = AutofillResult(cluster_slug=cluster_slug, candidate_count=len(papers_data))
    for entry in papers_data:
        slug = str(entry.get("slug", "") or "").strip()
        if not slug:
            result.skipped.append("(no slug)")
            continue
        note_path = _find_note_path(cfg, slug)
        if note_path is None:
            result.missing.append(slug)
            continue
        summary = str(entry.get("summary", "") or "").strip()
        key_findings = entry.get("key_findings") or []
        if not isinstance(key_findings, list):
            key_findings = [str(key_findings)]
        key_findings = [str(item).strip() for item in key_findings if str(item).strip()]
        methodology = str(entry.get("methodology", "") or "").strip()
        relevance = str(entry.get("relevance", "") or "").strip()
        if not any([summary, key_findings, methodology, relevance]):
            result.skipped.append(slug)
            continue

        text = note_path.read_text(encoding="utf-8")
        new_text = _replace_body_sections(
            text,
            summary=summary,
            key_findings=key_findings,
            methodology=methodology,
            relevance=relevance,
        )
        if new_text == text:
            result.skipped.append(slug)
            continue
        note_path.write_text(new_text, encoding="utf-8")
        result.filled.append(slug)
    return result


def _extract_title_and_abstract(text: str, fallback_slug: str = "") -> tuple[str, str]:
    title_match = re.search(r'^title:\s*"?([^"\n]+)"?\s*$', text, re.MULTILINE)
    title = title_match.group(1).strip().strip('"') if title_match else fallback_slug
    abstract_match = re.search(r"^##\s+Abstract\s*\n(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    if not abstract_match:
        return title, ""
    abstract = re.split(r"\n---\n", abstract_match.group(1).strip(), maxsplit=1)[0].strip()
    return title, abstract


def _replace_body_sections(
    text: str,
    *,
    summary: str,
    key_findings: list[str],
    methodology: str,
    relevance: str,
) -> str:
    summary_match = re.search(r"^##\s+Summary\s*$", text, re.MULTILINE)
    key_findings_match = re.search(r"^##\s+Key Findings\s*$", text, re.MULTILINE)
    methodology_match = re.search(r"^##\s+Methodology\s*$", text, re.MULTILINE)
    relevance_match = re.search(r"^##\s+Relevance\s*$", text, re.MULTILINE)
    if not all([summary_match, key_findings_match, methodology_match, relevance_match]):
        return text
    next_match = re.search(r"^##\s+", text[relevance_match.end():], re.MULTILINE)
    end = relevance_match.end() + next_match.start() if next_match else len(text)
    prefix = text[:summary_match.start()]
    suffix = text[end:]
    key_findings_md = "\n".join(f"- {item}" for item in key_findings) if key_findings else "- (none supplied)"
    replacement = (
        f"## Summary\n\n{summary or '(no summary)'}\n\n"
        f"## Key Findings\n\n{key_findings_md}\n\n"
        f"## Methodology\n\n{methodology or '(no methodology)'}\n\n"
        f"## Relevance\n\n{relevance or '(no relevance)'}\n\n"
    )
    return prefix + replacement + suffix.lstrip("\n")

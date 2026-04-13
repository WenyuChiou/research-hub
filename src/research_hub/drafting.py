"""Draft composer: assemble selected quotes + outline into markdown draft."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re

from research_hub.writing import (
    Quote,
    build_inline_citation,
    build_markdown_citation,
    load_all_quotes,
    resolve_paper_meta,
)

CITATION_STYLES = ("apa", "chicago", "mla", "latex")


@dataclass
class DraftRequest:
    cluster_slug: str
    outline: list[str] = field(default_factory=list)
    quote_slugs: list[str] = field(default_factory=list)
    style: str = "apa"
    include_bibliography: bool = True
    out_path: Path | None = None


@dataclass
class DraftResult:
    path: Path
    markdown: str
    cluster_slug: str
    quote_count: int
    cited_paper_count: int
    section_count: int


class DraftingError(ValueError):
    pass


def compose_draft(cfg, request: DraftRequest) -> DraftResult:
    """Assemble a markdown draft from selected quotes and an optional outline."""
    cluster_slug = str(request.cluster_slug or "").strip()
    if not cluster_slug:
        raise DraftingError("A cluster slug is required.")

    style = _normalize_style(request.style)
    outline = [str(section).strip() for section in request.outline if str(section).strip()]
    requested_slugs = {str(slug).strip() for slug in request.quote_slugs if str(slug).strip()}

    quotes = [quote for quote in load_all_quotes(cfg) if quote.cluster_slug == cluster_slug]
    if requested_slugs:
        quotes = [quote for quote in quotes if quote.slug in requested_slugs]
    if not quotes:
        raise DraftingError(
            f"No captured quotes found for cluster '{cluster_slug}'. "
            f"Capture one first with research-hub quote <slug> --page 12 --text \"...\"."
        )

    section_names = outline or ["Notes"]
    grouped_quotes = _group_quotes_by_section(quotes, section_names)

    paper_meta_by_slug: dict[str, dict] = {}
    for quote in quotes:
        if quote.slug not in paper_meta_by_slug:
            meta = resolve_paper_meta(cfg, quote.slug)
            paper_meta_by_slug[quote.slug] = {
                **meta,
                "slug": str(meta.get("slug", quote.slug) or quote.slug),
                "title": str(meta.get("title", quote.title) or quote.title),
                "authors": meta.get("authors", quote.authors),
                "year": str(meta.get("year", quote.year) or quote.year),
                "doi": str(meta.get("doi", quote.doi) or quote.doi),
            }

    cluster_name = next(
        (
            str(quote.cluster_name or "").strip()
            for quote in quotes
            if str(quote.cluster_name or "").strip()
        ),
        cluster_slug.replace("-", " ").title(),
    )
    generated_at = datetime.now(timezone.utc)
    markdown = _build_markdown(
        cluster_slug=cluster_slug,
        cluster_name=cluster_name,
        generated_at=generated_at,
        grouped_quotes=grouped_quotes,
        paper_meta_by_slug=paper_meta_by_slug,
        style=style,
        include_bibliography=request.include_bibliography,
    )

    out_path = request.out_path or _default_out_path(cfg, cluster_slug, generated_at)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")

    return DraftResult(
        path=out_path,
        markdown=markdown,
        cluster_slug=cluster_slug,
        quote_count=len(quotes),
        cited_paper_count=len(paper_meta_by_slug),
        section_count=len(section_names),
    )


def compose_draft_from_cli(
    cfg,
    cluster_slug: str,
    *,
    outline: str | None = None,
    quote_slugs: str | None = None,
    style: str = "apa",
    include_bibliography: bool = True,
    out: str | None = None,
) -> DraftResult:
    """Thin wrapper that parses the CLI-style string arguments."""
    request = DraftRequest(
        cluster_slug=cluster_slug,
        outline=[s.strip() for s in (outline or "").split(";") if s.strip()],
        quote_slugs=[s.strip() for s in (quote_slugs or "").split(",") if s.strip()],
        style=style,
        include_bibliography=include_bibliography,
        out_path=Path(out) if out else None,
    )
    return compose_draft(cfg, request)


def _group_quotes_by_section(quotes: list[Quote], outline: list[str]) -> dict[str, list[Quote]]:
    section_names = outline or ["Notes"]
    grouped = {section: [] for section in section_names}
    first_section = section_names[0]
    for quote in quotes:
        note = str(quote.context_note or "").strip().lower()
        match = next((section for section in section_names if section.lower() in note), None)
        grouped[match or first_section].append(quote)
    return grouped


def _build_markdown(
    *,
    cluster_slug: str,
    cluster_name: str,
    generated_at: datetime,
    grouped_quotes: dict[str, list[Quote]],
    paper_meta_by_slug: dict[str, dict],
    style: str,
    include_bibliography: bool,
) -> str:
    ordered_quotes = [quote for quotes in grouped_quotes.values() for quote in quotes]
    frontmatter = [
        "---",
        "type: draft",
        f"cluster: {cluster_slug}",
        f"style: {style}",
        f"generated_at: {generated_at.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"quote_count: {len(ordered_quotes)}",
        f"cited_paper_count: {len(paper_meta_by_slug)}",
        f"section_count: {len(grouped_quotes)}",
        "---",
        "",
    ]
    lines = frontmatter
    lines.append(f"# {cluster_name} - Draft (generated {generated_at.strftime('%Y-%m-%d')})")
    lines.append("")

    for section, quotes in grouped_quotes.items():
        lines.append(f"## {section}")
        lines.append("")
        if not quotes:
            lines.append("_No quotes assigned yet._")
            lines.append("")
            continue
        for quote in quotes:
            lines.extend(_render_quote_block(quote, paper_meta_by_slug.get(quote.slug, {}), style))

    if include_bibliography:
        lines.extend(_render_references(paper_meta_by_slug, style))

    return "\n".join(lines).rstrip() + "\n"


def _render_quote_block(quote: Quote, meta: dict, style: str) -> list[str]:
    text = str(quote.text or "").strip()
    body = ["> " + line if line else ">" for line in text.splitlines()] if text else ["> "]
    markdown_citation = build_markdown_citation(meta)
    inline_citation = build_inline_citation(meta, style=style)
    parts = [f"*Source: {markdown_citation}; {inline_citation}*"]
    if quote.page:
        parts[-1] = parts[-1][:-1] + f"; p. {quote.page}*"

    rendered = list(body)
    rendered.append("")
    rendered.append(parts[0])
    if quote.context_note:
        rendered.append(f"*Context: {quote.context_note}*")
    rendered.append("")
    return rendered


def _render_references(paper_meta_by_slug: dict[str, dict], style: str) -> list[str]:
    lines = ["## References", ""]
    metas = [paper_meta_by_slug[key] for key in sorted(paper_meta_by_slug)]
    if style == "latex":
        lines.append("```bibtex")
        for meta in metas:
            key = _bibkey(meta)
            title = _escape_bibtex(str(meta.get("title", "") or "Untitled"))
            authors = _escape_bibtex(_authors_for_bibtex(meta.get("authors", "")))
            year = _escape_bibtex(str(meta.get("year", "") or ""))
            doi = _escape_bibtex(str(meta.get("doi", "") or ""))
            lines.append(f"@article{{{key},")
            lines.append(f"  title = {{{title}}},")
            if authors:
                lines.append(f"  author = {{{authors}}},")
            if year:
                lines.append(f"  year = {{{year}}},")
            if doi:
                lines.append(f"  doi = {{{doi}}},")
            lines.append("}")
            lines.append("")
        if lines[-1] == "":
            lines.pop()
        lines.append("```")
        lines.append("")
        return lines

    for meta in metas:
        lines.append(
            f"- {build_markdown_citation(meta)} {build_inline_citation(meta, style=style)}"
        )
    lines.append("")
    return lines


def _normalize_style(style: str) -> str:
    normalized = str(style or "apa").strip().lower()
    return normalized if normalized in CITATION_STYLES else "apa"


def _default_out_path(cfg, cluster_slug: str, generated_at: datetime) -> Path:
    return cfg.root / "drafts" / f"{generated_at.strftime('%Y%m%d')}-{cluster_slug}-draft.md"


def _authors_for_bibtex(authors: str | list[str]) -> str:
    if isinstance(authors, list):
        return " and ".join(str(author).strip() for author in authors if str(author).strip())
    text = str(authors or "").strip()
    if not text:
        return ""
    if ";" in text:
        return " and ".join(part.strip() for part in text.split(";") if part.strip())
    return re.sub(r"\s+and\s+", " and ", text)


def _bibkey(meta: dict) -> str:
    slug = str(meta.get("slug", "") or "").strip()
    if slug:
        return re.sub(r"[^A-Za-z0-9:_-]+", "", slug)
    return "paper"


def _escape_bibtex(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")

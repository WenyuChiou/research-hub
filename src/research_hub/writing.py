from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re

from research_hub.utils.doi import normalize_doi

CITATION_STYLES = ("apa", "chicago", "mla", "latex")

_FRONTMATTER_BLOCK_RE = re.compile(
    r"^---\n(?P<meta>.*?)\n---\n(?P<body>.*?)(?=^---\n|\Z)",
    re.DOTALL | re.MULTILINE,
)


@dataclass
class Quote:
    """A captured excerpt from a paper."""

    slug: str
    doi: str
    title: str
    authors: str
    year: str
    cluster_slug: str = ""
    cluster_name: str = ""
    page: str = ""
    text: str = ""
    captured_at: str = ""
    context_note: str = ""


def build_inline_citation(paper_meta: dict, style: str = "apa") -> str:
    """Return an inline-style citation."""
    normalized_style = (style or "apa").strip().lower()
    if normalized_style not in CITATION_STYLES:
        normalized_style = "apa"

    surnames = _author_surnames(paper_meta.get("authors", ""))
    year = str(paper_meta.get("year", "") or "").strip()
    slug = str(paper_meta.get("slug", "") or "").strip()

    if normalized_style == "latex":
        bibkey = re.sub(r"[^A-Za-z0-9:_-]+", "", slug) or _fallback_bibkey(paper_meta)
        return f"\\citep{{{bibkey}}}"

    if not surnames:
        surnames = [str(paper_meta.get("title", "Untitled") or "Untitled").split(":")[0].strip() or "Untitled"]

    if normalized_style == "apa":
        author_part = _join_authors_apa(surnames)
        return f"({author_part}{', ' + year if year else ''})"
    if normalized_style == "chicago":
        author_part = _join_authors_chicago(surnames)
        return f"({author_part}{' ' + year if year else ''})"
    author_part = _join_authors_chicago(surnames)
    return f"({author_part}{' ' + year if year else ''})"


def build_markdown_citation(paper_meta: dict) -> str:
    """Return a markdown-friendly citation with DOI link."""
    label = _markdown_citation_label(paper_meta)
    doi = str(paper_meta.get("doi", "") or "").strip()
    normalized = normalize_doi(doi)
    if normalized:
        return f"[{label}](https://doi.org/{normalized})"
    return label


def save_quote(cfg, quote: Quote) -> Path:
    """Append a quote to <vault>/.research_hub/quotes/<slug>.md."""
    quotes_dir = cfg.research_hub_dir / "quotes"
    quotes_dir.mkdir(parents=True, exist_ok=True)
    path = quotes_dir / f"{quote.slug}.md"
    captured_at = quote.captured_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    context = _yaml_quote(quote.context_note)
    page = _yaml_quote(quote.page)
    body = _quote_body(quote.text)
    block = (
        "---\n"
        f"captured_at: {captured_at}\n"
        f"page: {page}\n"
        f"context_note: {context}\n"
        "---\n"
        f"{body}\n"
    )
    prefix = "\n" if path.exists() and path.read_text(encoding="utf-8").strip() else ""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(prefix + block)
    return path


def load_all_quotes(cfg) -> list[Quote]:
    """Walk <vault>/.research_hub/quotes/ and return every quote."""
    quotes_dir = cfg.research_hub_dir / "quotes"
    if not quotes_dir.exists():
        return []

    cluster_names = _cluster_name_map(cfg)
    out: list[Quote] = []
    for path in sorted(quotes_dir.glob("*.md")):
        slug = path.stem
        paper_meta = resolve_paper_meta(cfg, slug)
        for block in _parse_quote_file(path):
            cluster_slug = str(paper_meta.get("topic_cluster", "") or paper_meta.get("cluster_slug", "") or "")
            out.append(
                Quote(
                    slug=slug,
                    doi=str(paper_meta.get("doi", "") or ""),
                    title=str(paper_meta.get("title", slug) or slug),
                    authors=_authors_to_string(paper_meta.get("authors", "")),
                    year=str(paper_meta.get("year", "") or ""),
                    cluster_slug=cluster_slug,
                    cluster_name=cluster_names.get(cluster_slug, cluster_slug.replace("-", " ").title()),
                    page=str(block.get("page", "") or ""),
                    text=str(block.get("text", "") or ""),
                    captured_at=str(block.get("captured_at", "") or ""),
                    context_note=str(block.get("context_note", "") or ""),
                )
            )
    out.sort(key=lambda item: (item.captured_at, item.slug), reverse=True)
    return out


def format_paper_meta_from_frontmatter(md_path: Path) -> dict:
    """Pull title/authors/year/doi/slug from an Obsidian note."""
    frontmatter = _read_frontmatter(md_path)
    return {
        "slug": md_path.stem,
        "title": _frontmatter_value(frontmatter, "title", md_path.stem),
        "authors": _frontmatter_authors(frontmatter),
        "year": _frontmatter_value(frontmatter, "year"),
        "doi": _frontmatter_value(frontmatter, "doi"),
        "topic_cluster": _frontmatter_value(frontmatter, "topic_cluster"),
        "status": _frontmatter_value(frontmatter, "status"),
    }


def resolve_paper_meta(cfg, doi_or_slug: str) -> dict:
    """Resolve a paper note by DOI or slug and return frontmatter metadata."""
    identifier = str(doi_or_slug or "").strip()
    if not identifier:
        return {}

    slug_path = _find_note_by_slug(cfg.raw, identifier)
    if slug_path is not None:
        return format_paper_meta_from_frontmatter(slug_path)

    normalized = normalize_doi(identifier)
    if normalized:
        doi_path = _find_note_by_doi(cfg.raw, normalized)
        if doi_path is not None:
            return format_paper_meta_from_frontmatter(doi_path)

    return {
        "slug": identifier,
        "title": identifier,
        "authors": "",
        "year": "",
        "doi": normalized or identifier,
        "topic_cluster": "",
    }


def _read_frontmatter(md_path: Path) -> str:
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end < 0:
        return ""
    return text[3:end]


def _frontmatter_value(frontmatter: str, key: str, default: str = "") -> str:
    match = re.search(rf'^{re.escape(key)}:\s*[\'"]?([^\'"\n]*)[\'"]?', frontmatter, re.MULTILINE)
    return match.group(1).strip() if match else default


def _frontmatter_authors(frontmatter: str) -> str | list[str]:
    match = re.search(r"^authors:\s*\[(.*?)\]", frontmatter, re.MULTILINE | re.DOTALL)
    if match:
        return [part.strip().strip("\"'") for part in match.group(1).split(",") if part.strip()]
    return _frontmatter_value(frontmatter, "authors")


def _author_surnames(authors: str | list[str]) -> list[str]:
    if isinstance(authors, list):
        raw = [str(item).strip() for item in authors if str(item).strip()]
    else:
        text = str(authors or "").strip()
        if not text:
            return []
        if ";" in text:
            raw = [part.strip() for part in text.split(";") if part.strip()]
        else:
            raw = [part.strip() for part in text.split(" and ") if part.strip()]
    surnames: list[str] = []
    for author in raw:
        if "," in author:
            surnames.append(author.split(",", 1)[0].strip())
        else:
            parts = author.split()
            surnames.append(parts[-1].strip() if parts else author.strip())
    return [item for item in surnames if item]


def _authors_to_string(authors: str | list[str]) -> str:
    if isinstance(authors, list):
        return "; ".join(str(item).strip() for item in authors if str(item).strip())
    return str(authors or "").strip()


def _join_authors_apa(surnames: list[str]) -> str:
    if len(surnames) == 1:
        return surnames[0]
    if len(surnames) == 2:
        return f"{surnames[0]} & {surnames[1]}"
    return f"{surnames[0]} et al."


def _join_authors_chicago(surnames: list[str]) -> str:
    if len(surnames) == 1:
        return surnames[0]
    if len(surnames) == 2:
        return f"{surnames[0]} and {surnames[1]}"
    return f"{surnames[0]} et al."


def _fallback_bibkey(paper_meta: dict) -> str:
    surnames = _author_surnames(paper_meta.get("authors", ""))
    author = surnames[0].lower() if surnames else "paper"
    year = re.sub(r"\D+", "", str(paper_meta.get("year", "") or "")) or "nodate"
    title = re.sub(r"[^a-z0-9]+", "", str(paper_meta.get("title", "") or "").lower())[:12] or "untitled"
    return f"{author}{year}{title}"


def _markdown_citation_label(paper_meta: dict) -> str:
    surnames = _author_surnames(paper_meta.get("authors", ""))
    year = str(paper_meta.get("year", "") or "").strip()
    if not surnames:
        return str(paper_meta.get("title", "Untitled") or "Untitled")
    if len(surnames) == 1:
        author_part = surnames[0]
    elif len(surnames) == 2:
        author_part = f"{surnames[0]} and {surnames[1]}"
    else:
        author_part = f"{surnames[0]} et al."
    return f"{author_part} ({year})" if year else author_part


def _yaml_quote(value: str) -> str:
    text = str(value or "")
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _quote_body(text: str) -> str:
    stripped = str(text or "").strip()
    if not stripped:
        return "> "
    return "\n".join("> " + line if line else ">" for line in stripped.splitlines())


def _parse_quote_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    blocks: list[dict] = []
    for match in _FRONTMATTER_BLOCK_RE.finditer(text):
        meta = match.group("meta")
        body = match.group("body").strip()
        lines = []
        for raw_line in body.splitlines():
            if raw_line.startswith("> "):
                lines.append(raw_line[2:])
            elif raw_line == ">":
                lines.append("")
            else:
                lines.append(raw_line)
        blocks.append(
            {
                "captured_at": _frontmatter_value(meta, "captured_at"),
                "page": _frontmatter_value(meta, "page"),
                "context_note": _frontmatter_value(meta, "context_note"),
                "text": "\n".join(lines).strip(),
            }
        )
    return blocks


def _find_note_by_slug(raw_root: Path, slug: str) -> Path | None:
    for path in raw_root.rglob(f"{slug}.md"):
        return path
    return None


def _find_note_by_doi(raw_root: Path, normalized_doi: str) -> Path | None:
    for path in raw_root.rglob("*.md"):
        meta = format_paper_meta_from_frontmatter(path)
        if normalize_doi(str(meta.get("doi", "") or "")) == normalized_doi:
            return path
    return None


def _cluster_name_map(cfg) -> dict[str, str]:
    try:
        from research_hub.clusters import ClusterRegistry

        return {cluster.slug: cluster.name for cluster in ClusterRegistry(cfg.clusters_file).list()}
    except Exception:
        return {}

"""Citation, quote, and draft CLI handlers for Research Hub."""

from __future__ import annotations

from pathlib import Path
import re

from research_hub.cli_common import _read_zotero_key_from_frontmatter
from research_hub.config import get_config
from research_hub.dedup import DedupIndex
from research_hub.writing import (
    Quote,
    build_inline_citation,
    build_markdown_citation,
    format_paper_meta_from_frontmatter,
    load_all_quotes,
    resolve_paper_meta,
    save_quote,
)


def _collect_paper_meta_for_cluster(cfg, cluster: str) -> list[dict]:
    cluster_dir = cfg.raw / cluster
    if not cluster_dir.exists():
        raise FileNotFoundError(f"Cluster folder not found: {cluster_dir}")
    return [format_paper_meta_from_frontmatter(path) for path in sorted(cluster_dir.glob("*.md"))]


def _cite(
    identifier: str | None,
    cluster: str | None,
    content_format: str,
    out_path: str | None,
    *,
    inline: bool = False,
    markdown: bool = False,
    style: str = "apa",
) -> int:
    """Export BibTeX / BibLaTeX / RIS / CSL-JSON for a paper or cluster.

    Resolves the identifier (DOI, slug, or raw title) to one or more
    Zotero item keys via the dedup index and vault frontmatter, then
    calls ZoteroDualClient.get_formatted to fetch each entry. Concatenates
    results and writes to stdout or --out file.
    """
    from research_hub.dedup import normalize_doi
    from research_hub.zotero.client import ZoteroDualClient

    cfg = get_config()

    if inline or markdown:
        if cluster:
            try:
                metas = _collect_paper_meta_for_cluster(cfg, cluster)
            except FileNotFoundError as exc:
                print(str(exc))
                return 1
            rendered = []
            for meta in metas:
                if markdown:
                    rendered.append(build_markdown_citation(meta))
                else:
                    rendered.append(build_inline_citation(meta, style=style))
            body = "\n".join(item for item in rendered if item)
            if not body:
                print(f"No notes found in cluster '{cluster}'")
                return 1
            if out_path:
                Path(out_path).write_text(body + "\n", encoding="utf-8")
                print(f"Wrote {len(rendered)} citations to {out_path}")
            else:
                print(body)
            return 0

        if not identifier:
            print("Either a positional <identifier> or --cluster <slug> is required")
            return 2
        meta = resolve_paper_meta(cfg, identifier)
        if not meta:
            print(f"Could not resolve identifier '{identifier}'")
            return 1
        body = build_markdown_citation(meta) if markdown else build_inline_citation(meta, style=style)
        if out_path:
            Path(out_path).write_text(body + "\n", encoding="utf-8")
            print(f"Wrote citation to {out_path}")
        else:
            print(body)
        return 0

    index = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")

    keys: list[str] = []
    if cluster:
        cluster_dir = cfg.raw / cluster
        if not cluster_dir.exists():
            print(f"Cluster folder not found: {cluster_dir}")
            return 1
        for md_path in sorted(cluster_dir.glob("*.md")):
            key = _read_zotero_key_from_frontmatter(md_path)
            if key:
                keys.append(key)
        if not keys:
            print(f"No zotero-key entries found in {cluster_dir}")
            return 1
    elif identifier:
        normalized = normalize_doi(identifier)
        hits = index.doi_to_hits.get(normalized, [])
        for hit in hits:
            if hit.zotero_key and hit.zotero_key not in keys:
                keys.append(hit.zotero_key)
        if not keys:
            # Fall back: treat identifier as a filename stem in raw/
            for md_path in cfg.raw.rglob(f"{identifier}.md"):
                key = _read_zotero_key_from_frontmatter(md_path)
                if key:
                    keys.append(key)
        if not keys:
            print(f"Could not resolve identifier '{identifier}' to a Zotero key")
            return 1
    else:
        print("Either a positional <identifier> or --cluster <slug> is required")
        return 2

    dual = ZoteroDualClient()
    entries: list[str] = []
    for key in keys:
        try:
            entries.append(dual.get_formatted(key, content_format=content_format))
        except Exception as exc:
            print(f"  [warn] {key}: {exc}")
    body = "\n\n".join(e for e in entries if e)
    if out_path:
        Path(out_path).write_text(body + "\n", encoding="utf-8")
        print(f"Wrote {len(entries)} {content_format} entries to {out_path}")
    else:
        print(body)
    return 0 if entries else 1


def _quote_add(slug: str, page: str, text: str, context: str) -> int:
    cfg = get_config()
    meta = resolve_paper_meta(cfg, slug)
    quote = Quote(
        slug=str(meta.get("slug", slug) or slug),
        doi=str(meta.get("doi", "") or ""),
        title=str(meta.get("title", slug) or slug),
        authors=str(meta.get("authors", "") or ""),
        year=str(meta.get("year", "") or ""),
        cluster_slug=str(meta.get("topic_cluster", "") or ""),
        page=page,
        text=text,
        context_note=context,
    )
    path = save_quote(cfg, quote)
    print(path)
    return 0


def _quote_list(cluster: str | None) -> int:
    cfg = get_config()
    quotes = load_all_quotes(cfg)
    if cluster:
        quotes = [quote for quote in quotes if quote.cluster_slug == cluster]
    for quote in quotes:
        text = re.sub(r"\s+", " ", quote.text).strip()
        preview = text[:80] + ("..." if len(text) > 80 else "")
        print(f"{quote.slug}\t{quote.captured_at}\t{quote.page}\t{preview}")
    return 0


def _quote_remove(slug: str, at: str) -> int:
    cfg = get_config()
    path = cfg.research_hub_dir / "quotes" / f"{slug}.md"
    if not path.exists():
        print(f"Quote file not found: {path}")
        return 1
    original = path.read_text(encoding="utf-8")
    blocks = list(re.finditer(r"^---\n.*?\n---\n.*?(?:\n(?=---\n)|\Z)", original, re.DOTALL | re.MULTILINE))
    kept: list[str] = []
    removed = 0
    for match in blocks:
        block = match.group(0).strip()
        if f"captured_at: {at}" in block and removed == 0:
            removed += 1
            continue
        kept.append(block)
    if removed == 0:
        print(f"No quote block found for {slug} at {at}")
        return 1
    if kept:
        path.write_text("\n\n".join(kept) + "\n", encoding="utf-8")
    else:
        path.unlink()
    print(f"Removed quote {slug} at {at}")
    return 0


def _compose_draft(
    cluster_slug: str,
    outline: str | None,
    quotes: str | None,
    style: str,
    include_bibliography: bool,
    out: str | None,
) -> int:
    from research_hub.drafting import DraftingError, compose_draft_from_cli

    cfg = get_config()
    try:
        result = compose_draft_from_cli(
            cfg,
            cluster_slug,
            outline=outline,
            quote_slugs=quotes,
            style=style,
            include_bibliography=include_bibliography,
            out=out,
        )
    except DraftingError as exc:
        print(f"Draft composition failed: {exc}")
        return 1
    print(f"Draft written to {result.path}")
    print(
        f"  {result.quote_count} quotes, {result.cited_paper_count} cited papers, "
        f"{result.section_count} sections"
    )
    return 0

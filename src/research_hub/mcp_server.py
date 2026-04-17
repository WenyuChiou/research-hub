"""MCP stdio server exposing research-hub tools to AI assistants.

Start with:
    research-hub serve
    # or
    python -m research_hub.mcp_server

Claude Desktop config (~/.claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "research-hub": {
          "command": "research-hub",
          "args": ["serve"]
        }
      }
    }
"""

from __future__ import annotations

from dataclasses import asdict
import re
from typing import Any, Callable

from research_hub.security import ValidationError, validate_identifier, validate_slug

try:
    from fastmcp import FastMCP
except ImportError:  # pragma: no cover - dependency is optional
    FastMCP = None


class _FallbackToolManager:
    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}


class _FallbackMCP:
    def __init__(self, name: str, instructions: str = "") -> None:
        self.name = name
        self.instructions = instructions
        self._tool_manager = _FallbackToolManager()

    def tool(self, name: str | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._tool_manager._tools[name or func.__name__] = func
            return func

        return decorator

    def run(self) -> None:
        raise RuntimeError("fastmcp is not installed")


_MCP_CLS = FastMCP if FastMCP is not None else _FallbackMCP

mcp = _MCP_CLS(
    "research-hub",
    instructions=(
        "Academic literature pipeline. Search papers, verify DOIs, "
        "get integration suggestions, manage clusters, and export citations."
    ),
)


def _tool_error(exc: Exception) -> dict[str, str]:
    return {"error": str(exc)}


def _validate_mcp_args(**kwargs: object) -> dict[str, object]:
    validated: dict[str, object] = {}
    for field, value in kwargs.items():
        if value is None:
            validated[field] = None
        elif field in {"identifier", "doi_or_slug"}:
            validated[field] = validate_identifier(value, field=field)
        elif field in {"cluster", "cluster_slug", "slug", "crystal_slug", "to_cluster", "source", "into"}:
            validated[field] = validate_slug(value, field=field)
        else:
            validated[field] = value
    return validated


def search_papers(
    query: str,
    limit: int = 10,
    verify: bool = False,
    year_from: int | None = None,
    year_to: int | None = None,
    min_citations: int = 0,
    backends: list[str] | None = None,
    exclude_types: list[str] | None = None,
    exclude_terms: list[str] | None = None,
    min_confidence: float = 0.0,
    rank_by: str = "smart",
    field: str | None = None,
    region: str | None = None,
) -> list[dict[str, Any]] | dict[str, str]:
    """Search for academic papers across multiple backends."""
    try:
        from research_hub.config import get_config
        from research_hub.dedup import DedupIndex, normalize_doi
        from research_hub.search import search_papers as _search_papers
        from research_hub.search.fallback import (
            DEFAULT_BACKENDS,
            resolve_backends_for_field,
            resolve_backends_for_region,
        )

        cfg = get_config()
        index_path = cfg.research_hub_dir / "dedup_index.json"
        index = DedupIndex.load(index_path) if index_path.exists() else DedupIndex()

        if region:
            backend_list = resolve_backends_for_region(region)
        elif field:
            backend_list = resolve_backends_for_field(field)
        elif backends:
            backend_list = tuple(backends)
        else:
            backend_list = DEFAULT_BACKENDS
        results = _search_papers(
            query,
            limit=min(limit, 100),
            year_from=year_from,
            year_to=year_to,
            min_citations=min_citations,
            backends=backend_list,
            exclude_types=tuple(exclude_types or []),
            exclude_terms=tuple(exclude_terms or []),
            min_confidence=min_confidence,
            rank_by=rank_by,
        )
        ingested = {normalize_doi(doi) for doi in index.doi_to_hits.keys() if doi}

        output: list[dict[str, Any]] = []
        for result in results:
            already = normalize_doi(result.doi) in ingested
            entry: dict[str, Any] = {
                "title": result.title,
                "doi": result.doi,
                "arxiv_id": result.arxiv_id,
                "authors": result.authors,
                "year": result.year,
                "venue": result.venue,
                "citation_count": result.citation_count,
                "url": result.url,
                "pdf_url": result.pdf_url,
                "abstract": result.abstract,
                "source": result.source,
                "confidence": result.confidence,
                "found_in": result.found_in,
                "doc_type": result.doc_type,
                "already_in_vault": already,
            }
            if verify and result.doi:
                from research_hub.verify import verify_doi

                verified = verify_doi(result.doi)
                entry["verified"] = verified.ok
                entry["verification_reason"] = verified.reason
            output.append(entry)
        return output
    except Exception as exc:  # pragma: no cover - exercised via failure tests
        return _tool_error(exc)


def enrich_candidates(
    candidates: list[str],
    backends: list[str] | None = None,
) -> list[dict[str, Any]] | dict[str, str]:
    """Resolve candidate identifiers to full paper records."""
    try:
        from research_hub.search import enrich_candidates as _enrich

        backend_list = tuple(backends) if backends else ("openalex", "arxiv", "semantic-scholar")
        resolved = _enrich(candidates, backends=backend_list)
        return [asdict(r) for r in resolved if r is not None]
    except Exception as exc:
        return _tool_error(exc)


def verify_paper(
    doi: str | None = None,
    arxiv_id: str | None = None,
    title: str | None = None,
    authors: list[str] | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    """Verify a paper exists via DOI, arXiv ID, or fuzzy title match."""
    try:
        from research_hub.config import get_config
        from research_hub.verify import VerifyCache, verify_arxiv, verify_doi, verify_paper as verify_title

        cfg = get_config()
        cache = VerifyCache(cfg.research_hub_dir / "verify_cache.json")

        if doi:
            result = verify_doi(doi, cache=cache)
        elif arxiv_id:
            result = verify_arxiv(arxiv_id, cache=cache)
        elif title:
            result = verify_title(title, authors=authors or [], year=year, cache=cache)
        else:
            return {"ok": False, "reason": "Provide at least one of: doi, arxiv_id, title"}

        return asdict(result)
    except Exception as exc:  # pragma: no cover - exercised via failure tests
        return _tool_error(exc)


def suggest_integration(
    identifier: str,
    top_clusters: int = 3,
    top_related: int = 5,
) -> dict[str, Any]:
    """Suggest which cluster a paper belongs to and find related papers."""
    try:
        from research_hub.clusters import ClusterRegistry
        from research_hub.config import get_config
        from research_hub.dedup import DedupIndex
        from research_hub.search import SemanticScholarClient
        from research_hub.suggest import (
            PaperInput,
            suggest_cluster_for_paper,
            suggest_related_papers,
        )

        cfg = get_config()
        registry = ClusterRegistry(cfg.clusters_file)
        index = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")

        paper = None
        if re.match(r"10\.\d{4,}", identifier):
            fetched = SemanticScholarClient().get_paper(identifier)
            if fetched is not None:
                paper = PaperInput(
                    title=fetched.title,
                    doi=fetched.doi,
                    authors=fetched.authors,
                    year=fetched.year,
                    venue=fetched.venue,
                    abstract=fetched.abstract,
                )
        elif re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", identifier):
            fetched = SemanticScholarClient().get_paper(f"ArXiv:{identifier}")
            if fetched is not None:
                paper = PaperInput(
                    title=fetched.title,
                    doi=fetched.doi,
                    authors=fetched.authors,
                    year=fetched.year,
                    venue=fetched.venue,
                    abstract=fetched.abstract,
                )

        if paper is None:
            paper = PaperInput(title=identifier)

        clusters = suggest_cluster_for_paper(paper, registry, index, top_n=top_clusters)
        related = suggest_related_papers(paper, index, registry, top_n=top_related)

        return {
            "paper": asdict(paper),
            "cluster_suggestions": [asdict(item) for item in clusters],
            "related_papers": [asdict(item) for item in related],
        }
    except Exception as exc:  # pragma: no cover - exercised via failure tests
        return _tool_error(exc)


def list_clusters() -> list[dict[str, Any]] | dict[str, str]:
    """List all topic clusters with their bindings."""
    try:
        from research_hub.clusters import ClusterRegistry
        from research_hub.config import get_config

        cfg = get_config()
        registry = ClusterRegistry(cfg.clusters_file)
        return [asdict(cluster) for cluster in registry.list()]
    except Exception as exc:  # pragma: no cover - exercised via failure tests
        return _tool_error(exc)


def show_cluster(slug: str) -> dict[str, Any]:
    """Show detailed info for a cluster including sync status."""
    try:
        slug = _validate_mcp_args(slug=slug)["slug"]
        from research_hub.clusters import ClusterRegistry
        from research_hub.config import get_config
        from research_hub.vault.sync import compute_sync_status

        cfg = get_config()
        registry = ClusterRegistry(cfg.clusters_file)
        cluster = registry.get(slug)
        if cluster is None:
            return {"error": f"Cluster not found: {slug}"}

        status = compute_sync_status(
            cluster,
            None,
            cfg.raw,
            nlm_cache_path=cfg.research_hub_dir / "nlm_cache.json",
        )
        payload = asdict(cluster)
        payload["sync_status"] = {
            **asdict(status),
            "obsidian_only": [str(path) for path in status.obsidian_only],
        }
        return payload
    except Exception as exc:  # pragma: no cover - exercised via failure tests
        return _tool_error(exc)


def export_citation(
    identifier: str | None = None,
    cluster: str | None = None,
    format: str = "bibtex",
) -> str | dict[str, str]:
    """Export citation in BibTeX, BibLaTeX, RIS, or CSL-JSON format."""
    try:
        validated = _validate_mcp_args(identifier=identifier, cluster=cluster)
        identifier = validated["identifier"]
        cluster = validated["cluster"]
        from contextlib import redirect_stdout
        import io

        from research_hub.cli import _cite

        buf = io.StringIO()
        with redirect_stdout(buf):
            _cite(identifier, cluster, format, None)
        return buf.getvalue()
    except Exception as exc:  # pragma: no cover - exercised via failure tests
        return _tool_error(exc)


@mcp.tool()
def build_citation(doi_or_slug: str, style: str = "apa") -> dict:
    """Return an inline citation string for a paper."""
    try:
        doi_or_slug = _validate_mcp_args(doi_or_slug=doi_or_slug)["doi_or_slug"]
        from research_hub.config import get_config
        from research_hub.writing import (
            build_inline_citation,
            build_markdown_citation,
            resolve_paper_meta,
        )

        cfg = get_config()
        meta = resolve_paper_meta(cfg, doi_or_slug)
        return {
            "status": "ok",
            "inline": build_inline_citation(meta, style=style),
            "markdown": build_markdown_citation(meta),
        }
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


@mcp.tool()
def list_quotes(cluster_slug: str | None = None) -> dict:
    """List captured quotes, optionally filtered by cluster."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.writing import load_all_quotes

        cfg = get_config()
        quotes = load_all_quotes(cfg)
        if cluster_slug is not None:
            quotes = [quote for quote in quotes if quote.cluster_slug == cluster_slug]
        return {"status": "ok", "count": len(quotes), "quotes": [asdict(quote) for quote in quotes]}
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


@mcp.tool()
def capture_quote(slug: str, page: str, text: str, context: str = "") -> dict:
    """Persist a quote to <vault>/.research_hub/quotes/<slug>.md."""
    try:
        slug = _validate_mcp_args(slug=slug)["slug"]
        from research_hub.config import get_config
        from research_hub.writing import Quote, resolve_paper_meta, save_quote

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
        return {"status": "ok", "path": str(path), "quote": asdict(quote)}
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


@mcp.tool()
def compose_draft(
    cluster_slug: str,
    outline: list[str] | None = None,
    quote_slugs: list[str] | None = None,
    style: str = "apa",
    include_bibliography: bool = True,
) -> dict:
    """Assemble captured quotes into a markdown draft."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.drafting import DraftRequest, compose_draft as _compose_draft

        cfg = get_config()
        request = DraftRequest(
            cluster_slug=cluster_slug,
            outline=list(outline or []),
            quote_slugs=list(quote_slugs or []),
            style=style,
            include_bibliography=include_bibliography,
        )
        result = _compose_draft(cfg, request)
        return {
            "status": "ok",
            "path": str(result.path),
            "cluster_slug": result.cluster_slug,
            "quote_count": result.quote_count,
            "cited_paper_count": result.cited_paper_count,
            "section_count": result.section_count,
            "markdown_preview": result.markdown[:600],
        }
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


def get_references(identifier: str, limit: int = 20) -> list[dict[str, Any]] | dict[str, str]:
    """List papers cited by the given paper (its bibliography)."""
    try:
        identifier = _validate_mcp_args(identifier=identifier)["identifier"]
        from research_hub.citation_graph import CitationGraphClient

        client = CitationGraphClient()
        return [asdict(node) for node in client.get_references(identifier, limit=limit)]
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


def get_citations(identifier: str, limit: int = 20) -> list[dict[str, Any]] | dict[str, str]:
    """List papers that cite the given paper."""
    try:
        identifier = _validate_mcp_args(identifier=identifier)["identifier"]
        from research_hub.citation_graph import CitationGraphClient

        client = CitationGraphClient()
        return [asdict(node) for node in client.get_citations(identifier, limit=limit)]
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


def run_doctor() -> list[dict[str, Any]] | dict[str, str]:
    """Run health checks on the research-hub installation."""
    try:
        from research_hub.doctor import run_doctor as doctor_run

        return [asdict(item) for item in doctor_run()]
    except Exception as exc:  # pragma: no cover - exercised via failure tests
        return _tool_error(exc)


def get_config_info() -> dict[str, Any]:
    """Show current configuration paths and settings."""
    try:
        from research_hub.config import _resolve_config_path, get_config

        cfg = get_config()
        config_path = _resolve_config_path()
        return {
            "config_path": str(config_path) if config_path else None,
            "vault_root": str(cfg.root),
            "research_hub_dir": str(cfg.research_hub_dir),
            "raw_dir": str(cfg.raw),
            "clusters_file": str(cfg.clusters_file),
        }
    except Exception as exc:  # pragma: no cover - exercised via failure tests
        return _tool_error(exc)


def remove_paper(identifier: str, include_zotero: bool = False, dry_run: bool = False) -> dict[str, Any]:
    """Remove a paper from the vault, optionally deleting its Zotero item too."""
    try:
        identifier = _validate_mcp_args(identifier=identifier)["identifier"]
        from research_hub.operations import remove_paper as _remove

        return _remove(identifier, include_zotero=include_zotero, dry_run=dry_run)
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


def mark_paper(slug: str, status: str) -> dict[str, Any]:
    """Update reading status for a note."""
    try:
        slug = _validate_mcp_args(slug=slug)["slug"]
        from research_hub.operations import mark_paper as _mark

        return _mark(slug, status)
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


def move_paper(slug: str, to_cluster: str) -> dict[str, Any]:
    """Move a note to a different cluster."""
    try:
        validated = _validate_mcp_args(slug=slug, to_cluster=to_cluster)
        slug = validated["slug"]
        to_cluster = validated["to_cluster"]
        from research_hub.operations import move_paper as _move

        return _move(slug, to_cluster)
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


@mcp.tool()
def add_paper(
    identifier: str,
    cluster: str | None = None,
    no_zotero: bool = False,
    skip_verify: bool = False,
) -> dict:
    """Fetch a paper by DOI/arXiv ID and ingest it (one-shot)."""
    validated = _validate_mcp_args(identifier=identifier, cluster=cluster)
    identifier = validated["identifier"]
    cluster = validated["cluster"]
    try:
        from research_hub.operations import add_paper as _add

        return _add(
            identifier,
            cluster=cluster,
            no_zotero=no_zotero,
            skip_verify=skip_verify,
        )
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


def search_vault(
    query: str,
    cluster: str | None = None,
    status: str | None = None,
    full_text: bool = False,
) -> list[dict[str, Any]] | dict[str, str]:
    """Search local vault notes by title or full text."""
    try:
        cluster = _validate_mcp_args(cluster=cluster)["cluster"]
        from research_hub.vault_search import search_vault as _search

        return _search(query, cluster=cluster, status=status, full_text=full_text)
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


def merge_clusters(source: str, into: str) -> dict[str, Any]:
    """Merge one cluster into another."""
    try:
        validated = _validate_mcp_args(source=source, into=into)
        source = validated["source"]
        into = validated["into"]
        from research_hub.clusters import ClusterRegistry
        from research_hub.config import get_config

        cfg = get_config()
        registry = ClusterRegistry(cfg.clusters_file)
        return registry.merge(source, into, vault_raw=cfg.raw)
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


def split_cluster(source: str, query: str, new_name: str) -> dict[str, Any]:
    """Split a source cluster into a new cluster based on title keyword overlap."""
    try:
        source = _validate_mcp_args(source=source)["source"]
        from research_hub.clusters import ClusterRegistry
        from research_hub.config import get_config

        cfg = get_config()
        registry = ClusterRegistry(cfg.clusters_file)
        return registry.split(source, query, new_name, vault_raw=cfg.raw)
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


@mcp.tool()
def suggest_cluster_split(
    cluster_slug: str,
    min_community_size: int = 8,
    max_communities: int = 8,
) -> dict:
    """Analyze a cluster's citation graph and suggest sub-topic splits."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.analyze import suggest_split
        from research_hub.config import get_config

        cfg = get_config()
        return asdict(
            suggest_split(
                cfg,
                cluster_slug,
                min_community_size=min_community_size,
                max_communities=max_communities,
            )
        )
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


def get_topic_digest(cluster_slug: str) -> dict[str, Any]:
    """Return every paper in a cluster plus a markdown digest for overview writing."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.topic import get_topic_digest as _digest

        cfg = get_config()
        digest = _digest(cfg, cluster_slug)
        return {
            "cluster_slug": digest.cluster_slug,
            "cluster_title": digest.cluster_title,
            "paper_count": digest.paper_count,
            "papers": [asdict(paper) for paper in digest.papers],
            "markdown": digest.to_markdown(),
        }
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


def write_topic_overview(cluster_slug: str, markdown: str, overwrite: bool = False) -> dict[str, Any]:
    """Write a topic overview markdown file for a cluster."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.topic import overview_path

        cfg = get_config()
        path = overview_path(cfg, cluster_slug)
        if path.exists() and not overwrite:
            return {
                "ok": False,
                "reason": f"overview already exists at {path}; pass overwrite=True to replace",
            }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        return {"ok": True, "path": str(path), "bytes": len(markdown.encode("utf-8"))}
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


def read_topic_overview(cluster_slug: str) -> dict[str, Any]:
    """Return the current topic overview markdown for a cluster, if present."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.topic import read_overview

        cfg = get_config()
        content = read_overview(cfg, cluster_slug)
        if content is None:
            return {"ok": False, "reason": "no overview found"}
        return {"ok": True, "markdown": content}
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


def propose_subtopics(cluster_slug: str, target_count: int = 5) -> dict:
    """Build the Phase 1 sub-topic proposal prompt for an AI to consume."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.topic import emit_propose_prompt, get_topic_digest

        cfg = get_config()
        prompt = emit_propose_prompt(cfg, cluster_slug, target_count=target_count)
        digest = get_topic_digest(cfg, cluster_slug)
        return {
            "prompt": prompt,
            "paper_count": digest.paper_count,
            "target_count": target_count,
        }
    except Exception as exc:
        return _tool_error(exc)


def emit_assignment_prompt(cluster_slug: str, subtopics: list[dict]) -> dict:
    """Build the Phase 2 assignment prompt."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.topic import SubtopicProposal, emit_assign_prompt, get_topic_digest

        cfg = get_config()
        props = [SubtopicProposal(**item) for item in subtopics]
        prompt = emit_assign_prompt(cfg, cluster_slug, props)
        digest = get_topic_digest(cfg, cluster_slug)
        return {"prompt": prompt, "paper_count": digest.paper_count}
    except Exception as exc:
        return _tool_error(exc)


def apply_subtopic_assignments(cluster_slug: str, assignments: dict) -> dict:
    """Write subtopics frontmatter to each paper note."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.topic import apply_assignments

        cfg = get_config()
        report = apply_assignments(cfg, cluster_slug, assignments)
        return {
            "ok": True,
            "updated_count": len(report),
            "assignments": report,
        }
    except Exception as exc:
        return _tool_error(exc)


def build_topic_notes(cluster_slug: str) -> dict:
    """Generate topics/NN_<slug>.md files from paper frontmatter."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.topic import build_subtopic_notes

        cfg = get_config()
        written = build_subtopic_notes(cfg, cluster_slug)
        return {
            "ok": True,
            "written": [str(path) for path in written],
            "count": len(written),
        }
    except Exception as exc:
        return _tool_error(exc)


def list_topic_notes(cluster_slug: str) -> dict:
    """List existing sub-topic notes for a cluster."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.topic import list_subtopics

        cfg = get_config()
        descriptors = list_subtopics(cfg, cluster_slug)
        return {
            "ok": True,
            "subtopics": [
                {
                    "slug": item.slug,
                    "title": item.title,
                    "paper_count": item.paper_count,
                    "path": str(item.path),
                }
                for item in descriptors
            ],
        }
    except Exception as exc:
        return _tool_error(exc)


def fit_check_prompt(
    cluster_slug: str,
    candidates: list[dict],
    definition: str | None = None,
) -> dict:
    """Build the Gate 1 fit-check prompt for an AI to score."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.fit_check import emit_prompt

        cfg = get_config()
        prompt = emit_prompt(cluster_slug, candidates, definition=definition, cfg=cfg)
        return {"prompt": prompt, "candidate_count": len(candidates)}
    except Exception as exc:
        return _tool_error(exc)


def fit_check_apply(
    cluster_slug: str,
    candidates: list[dict],
    scores: list[dict],
    threshold: int = 3,
) -> dict:
    """Consume AI scores, filter candidates, write rejected sidecar."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.fit_check import apply_scores

        cfg = get_config()
        report = apply_scores(cluster_slug, candidates, scores, threshold=threshold, cfg=cfg)
        return {
            "cluster_slug": report.cluster_slug,
            "threshold": report.threshold,
            "candidates_in": report.candidates_in,
            "accepted": [item.to_dict() for item in report.accepted],
            "rejected": [item.to_dict() for item in report.rejected],
        }
    except Exception as exc:
        return _tool_error(exc)


def fit_check_audit(cluster_slug: str) -> dict:
    """Gate 3: parse latest NLM briefing for off-topic flags."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.fit_check import parse_nlm_off_topic
        from research_hub.notebooklm.upload import read_latest_briefing

        cfg = get_config()
        briefing = read_latest_briefing(cluster_slug, cfg)
        flagged = parse_nlm_off_topic(briefing)
        return {"ok": True, "cluster_slug": cluster_slug, "flagged": flagged}
    except FileNotFoundError:
        return {"ok": False, "reason": "no briefing found"}
    except Exception as exc:
        return _tool_error(exc)


def fit_check_drift(cluster_slug: str, threshold: int = 3) -> dict:
    """Gate 4: emit drift-check prompt against current overview."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.fit_check import drift_check

        cfg = get_config()
        return drift_check(cfg, cluster_slug, threshold=threshold)
    except Exception as exc:
        return _tool_error(exc)


def autofill_emit(cluster_slug: str) -> dict:
    """Build the paper-note autofill prompt for an AI to consume."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.autofill import emit_autofill_prompt, find_todo_papers
        from research_hub.config import get_config

        cfg = get_config()
        papers = find_todo_papers(cfg, cluster_slug)
        return {
            "prompt": emit_autofill_prompt(cfg, cluster_slug),
            "paper_count": len(papers),
        }
    except Exception as exc:
        return _tool_error(exc)


def autofill_apply(cluster_slug: str, scored: list[dict] | dict) -> dict:
    """Apply AI-supplied body content to paper notes."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.autofill import apply_autofill
        from research_hub.config import get_config

        cfg = get_config()
        result = apply_autofill(cfg, cluster_slug, scored)
        return {
            "cluster_slug": result.cluster_slug,
            "candidate_count": result.candidate_count,
            "filled": result.filled,
            "skipped": result.skipped,
            "missing": result.missing,
        }
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def list_crystals(cluster_slug: str) -> dict:
    """List all pre-computed crystal answers for a cluster."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub import crystal
        from research_hub.config import get_config

        cfg = get_config()
        crystals = crystal.list_crystals(cfg, cluster_slug)
        staleness = crystal.check_staleness(cfg, cluster_slug)
        return {
            "cluster": cluster_slug,
            "crystals": [
                {
                    "slug": item.question_slug,
                    "question": item.question,
                    "tldr": item.tldr,
                    "confidence": item.confidence,
                    "based_on_paper_count": item.based_on_paper_count,
                    "last_generated": item.last_generated,
                    "stale": staleness.get(item.question_slug, crystal.CrystalStaleness(item.question_slug, [], [], 0.0, False)).stale,
                }
                for item in crystals
            ],
        }
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def read_crystal(cluster_slug: str, crystal_slug: str, level: str = "gist") -> dict:
    """Read a specific crystal at the requested detail level."""
    validated = _validate_mcp_args(cluster_slug=cluster_slug, crystal_slug=crystal_slug)
    cluster_slug = validated["cluster_slug"]
    crystal_slug = validated["crystal_slug"]
    try:
        from research_hub import crystal
        from research_hub.config import get_config

        cfg = get_config()
        item = crystal.read_crystal(cfg, cluster_slug, crystal_slug)
        if item is None:
            return {"status": "not_found", "cluster": cluster_slug, "slug": crystal_slug}
        answer = item.tldr if level == "tldr" else item.full if level == "full" else item.gist
        return {
            "status": "ok",
            "cluster": cluster_slug,
            "slug": item.question_slug,
            "question": item.question,
            "level": level,
            "answer": answer,
            "evidence": [{"claim": ev.claim, "papers": ev.papers} for ev in item.evidence],
            "based_on_papers": item.based_on_papers,
            "based_on_paper_count": item.based_on_paper_count,
            "last_generated": item.last_generated,
            "confidence": item.confidence,
            "see_also": item.see_also,
        }
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def emit_crystal_prompt(cluster_slug: str, question_slugs: list[str] | None = None) -> dict:
    """Emit the markdown prompt the calling AI should answer to generate crystals."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub import crystal
        from research_hub.config import get_config

        cfg = get_config()
        return {"cluster": cluster_slug, "prompt": crystal.emit_crystal_prompt(cfg, cluster_slug, question_slugs=question_slugs)}
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def apply_crystals(cluster_slug: str, crystals_json: dict) -> dict:
    """Persist crystal answers to hub/<cluster>/crystals/<slug>.md."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub import crystal
        from research_hub.config import get_config

        cfg = get_config()
        return crystal.apply_crystals(cfg, cluster_slug, crystals_json).to_dict()
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def check_crystal_staleness(cluster_slug: str) -> dict:
    """Check how many crystals are stale (>10% cluster paper delta since generation)."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub import crystal
        from research_hub.config import get_config

        cfg = get_config()
        staleness = crystal.check_staleness(cfg, cluster_slug)
        return {"cluster": cluster_slug, "crystals": {slug: item.to_dict() for slug, item in staleness.items()}}
    except Exception as exc:
        return _tool_error(exc)


def label_paper(
    slug: str,
    labels: list[str] | None = None,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    fit_score: int | None = None,
    fit_reason: str | None = None,
) -> dict:
    """Set, add, or remove labels on a paper note."""
    try:
        slug = _validate_mcp_args(slug=slug)["slug"]
        from research_hub.config import get_config
        from research_hub.paper import set_labels

        cfg = get_config()
        state = set_labels(
            cfg,
            slug,
            labels=labels,
            add=add,
            remove=remove,
            fit_score=fit_score,
            fit_reason=fit_reason,
        )
        return {
            "ok": True,
            "slug": state.slug,
            "labels": state.labels,
            "fit_score": state.fit_score,
            "fit_reason": state.fit_reason,
            "labeled_at": state.labeled_at,
        }
    except Exception as exc:
        return _tool_error(exc)


def list_papers_by_label(
    cluster_slug: str,
    label: str | None = None,
    label_not: str | None = None,
) -> list[dict] | dict:
    """Return paper states for the cluster, optionally filtered by label."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.paper import list_papers_by_label as _list

        cfg = get_config()
        states = _list(cfg, cluster_slug, label=label, label_not=label_not)
        return [
            {
                "slug": state.slug,
                "cluster_slug": state.cluster_slug,
                "labels": state.labels,
                "fit_score": state.fit_score,
                "fit_reason": state.fit_reason,
                "labeled_at": state.labeled_at,
            }
            for state in states
        ]
    except Exception as exc:
        return _tool_error(exc)


def prune_cluster(
    cluster_slug: str,
    label: str = "deprecated",
    archive: bool = True,
    delete: bool = False,
    dry_run: bool = True,
) -> dict:
    """Move or delete papers with the given label."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.paper import prune_cluster as _prune

        cfg = get_config()
        return _prune(
            cfg,
            cluster_slug,
            label=label,
            archive=archive,
            delete=delete,
            dry_run=dry_run,
        )
    except Exception as exc:
        return _tool_error(exc)


def apply_fit_check_to_labels(cluster_slug: str) -> dict:
    """Tag papers rejected by fit-check as deprecated."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.paper import apply_fit_check_to_labels as _apply

        cfg = get_config()
        return _apply(cfg, cluster_slug)
    except Exception as exc:
        return _tool_error(exc)


def discover_new(
    cluster_slug: str,
    query: str,
    year_from: int | None = None,
    year_to: int | None = None,
    min_citations: int = 0,
    backends: list[str] | None = None,
    limit: int = 50,
    definition: str | None = None,
    exclude_types: list[str] | None = None,
    exclude_terms: list[str] | None = None,
    min_confidence: float = 0.0,
    rank_by: str = "smart",
    field: str | None = None,
    region: str | None = None,
    from_variants: list[dict] | None = None,
    expand_auto: bool = False,
    expand_from: list[str] | None = None,
    expand_hops: int = 1,
    seed_dois: list[str] | None = None,
    include_existing: bool = False,
) -> dict:
    """Run search + emit fit-check prompt, stashing state for discover_continue."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.discover import discover_new as _discover_new

        cfg = get_config()
        backend_list = tuple(backends) if backends else None
        variants_path = None
        if from_variants is not None:
            variants_path = cfg.research_hub_dir / "discover_variants_input.json"
            variants_path.write_text(
                json.dumps({"variations": from_variants}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        state, prompt = _discover_new(
            cfg,
            cluster_slug,
            query,
            year_from=year_from,
            year_to=year_to,
            min_citations=min_citations,
            backends=backend_list,
            field=field,
            region=region,
            limit=limit,
            definition=definition,
            exclude_types=tuple(exclude_types or []),
            exclude_terms=tuple(exclude_terms or []),
            min_confidence=min_confidence,
            rank_by=rank_by,
            from_variants=variants_path,
            expand_auto=expand_auto,
            expand_from=tuple(expand_from or []),
            expand_hops=expand_hops,
            seed_dois=tuple(seed_dois or []),
            include_existing=include_existing,
        )
        return {
            "ok": True,
            "stage": state.stage,
            "candidate_count": state.candidate_count,
            "prompt": prompt,
            "variations_used": state.variations_used,
            "expanded_from": state.expanded_from,
            "seed_dois": state.seed_dois,
            "deduped_against_cluster": state.deduped_against_cluster,
        }
    except Exception as exc:
        return _tool_error(exc)


def discover_variants(
    cluster_slug: str,
    query: str,
    count: int = 4,
) -> dict:
    """Emit a query-variation prompt for the given cluster."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.discover import emit_variation_prompt

        cfg = get_config()
        prompt = emit_variation_prompt(cfg, cluster_slug, query, target_count=count)
        return {"prompt": prompt, "target_count": count}
    except Exception as exc:
        return _tool_error(exc)


def discover_continue(
    cluster_slug: str,
    scored: list[dict] | dict,
    threshold: int | None = None,
    auto_threshold: bool = False,
) -> dict:
    """Apply AI scores and emit papers_input.json for later ingest."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.discover import discover_continue as _discover_continue

        cfg = get_config()
        state, path = _discover_continue(
            cfg,
            cluster_slug,
            scored,
            threshold=threshold,
            auto_threshold=auto_threshold,
        )
        return {
            "ok": True,
            "stage": state.stage,
            "accepted_count": state.accepted_count,
            "rejected_count": state.rejected_count,
            "threshold": state.threshold,
            "papers_input_path": str(path),
        }
    except Exception as exc:
        return _tool_error(exc)


def discover_status(cluster_slug: str) -> dict:
    """Return current discover state for a cluster."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.discover import discover_status as _discover_status

        cfg = get_config()
        state = _discover_status(cfg, cluster_slug)
        if state is None:
            return {"ok": False, "reason": "no discover state for cluster"}
        return {
            "ok": True,
            "cluster_slug": state.cluster_slug,
            "stage": state.stage,
            "candidate_count": state.candidate_count,
            "accepted_count": state.accepted_count,
            "rejected_count": state.rejected_count,
            "threshold": state.threshold,
            "variations_used": state.variations_used,
            "expanded_from": state.expanded_from,
            "seed_dois": state.seed_dois,
            "deduped_against_cluster": state.deduped_against_cluster,
        }
    except Exception as exc:
        return _tool_error(exc)


def discover_clean(cluster_slug: str) -> dict:
    """Remove the discover stash directory for a cluster."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.discover import discover_clean as _discover_clean

        cfg = get_config()
        removed = _discover_clean(cfg, cluster_slug)
        return {"ok": True, "removed": removed}
    except Exception as exc:
        return _tool_error(exc)


def examples_list() -> list[dict[str, Any]] | dict[str, str]:
    """List bundled example clusters."""
    try:
        from research_hub.examples import list_examples as _list_examples

        return _list_examples()
    except Exception as exc:
        return _tool_error(exc)


def examples_show(name: str) -> dict[str, Any]:
    """Return the full definition for one bundled example."""
    try:
        from research_hub.examples import load_example

        return load_example(name)
    except Exception as exc:
        return _tool_error(exc)


def examples_copy(name: str, cluster_slug: str | None = None) -> dict[str, Any]:
    """Copy an example into the user's cluster registry."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.examples import copy_example_as_cluster

        cfg = get_config()
        slug = copy_example_as_cluster(cfg, name, cluster_slug=cluster_slug)
        return {"ok": True, "slug": slug}
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def download_artifacts(
    cluster_slug: str,
    artifact_type: str = "brief",
    headless: bool = True,
) -> dict:
    """Download a generated NotebookLM briefing back to the vault.

    Opens the cluster's NotebookLM notebook over CDP, extracts the
    latest briefing summary text, and saves it under
    `<vault>/.research_hub/artifacts/<cluster_slug>/brief-<UTC>.txt`.
    The cluster's `nlm_cache.json` entry is updated with the new path.

    Args:
        cluster_slug: The cluster identifier.
        artifact_type: Only "brief" is supported in v0.9.0; audio,
            mind-map, and video downloads land in v0.9.1.
        headless: If True (default), drive Chrome headlessly so this
            tool can run inside an MCP server with no display.

    Returns:
        dict with status, path, char_count, notebook_name, and titles.
    """
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.clusters import ClusterRegistry
        from research_hub.notebooklm.upload import download_briefing_for_cluster

        cfg = get_config()
        registry = ClusterRegistry(cfg.clusters_file)
        cluster = registry.get(cluster_slug)
        if cluster is None:
            return {"status": "error", "error": f"Cluster not found: {cluster_slug}"}
        if artifact_type != "brief":
            return {
                "status": "error",
                "error": f"Only artifact_type='brief' is supported in v0.9.0 (got {artifact_type!r}).",
            }
        report = download_briefing_for_cluster(cluster, cfg, headless=headless)
        return {
            "status": "ok",
            "path": str(report.artifact_path),
            "notebook_name": report.notebook_name,
            "char_count": report.char_count,
            "titles": report.titles,
        }
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


_BRIEFING_MAX_CHARS = 100_000


@mcp.tool()
def read_briefing(cluster_slug: str, max_chars: int = _BRIEFING_MAX_CHARS) -> dict:
    """Return the most recently downloaded briefing text for a cluster.

    Reads the latest `brief-*.txt` from
    `<vault>/.research_hub/artifacts/<cluster_slug>/`. If no briefing
    has been downloaded yet, the response includes a remedy hint to
    call `download_artifacts` first. Use this tool when an AI agent
    needs to summarize, translate, or quote the briefing without
    re-running NotebookLM.

    Args:
        cluster_slug: The cluster identifier.
        max_chars: Truncate the returned text to this many characters
            so an unbounded briefing cannot blow up the agent context
            window. Default 100_000.

    Returns:
        dict with status and either `text` or `error`. When the briefing
        exceeds ``max_chars`` the response also carries `truncated=True`
        and the original `full_chars` count.
    """
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import get_config
        from research_hub.clusters import ClusterRegistry
        from research_hub.notebooklm.upload import read_latest_briefing

        cfg = get_config()
        registry = ClusterRegistry(cfg.clusters_file)
        cluster = registry.get(cluster_slug)
        if cluster is None:
            return {"status": "error", "error": f"Cluster not found: {cluster_slug}"}
        try:
            text = read_latest_briefing(cluster, cfg)
        except FileNotFoundError as exc:
            return {
                "status": "error",
                "error": str(exc),
                "remedy": f"Call download_artifacts(cluster_slug='{cluster_slug}') first.",
            }
        full_chars = len(text)
        if full_chars > max_chars:
            return {
                "status": "ok",
                "cluster_slug": cluster_slug,
                "text": text[:max_chars],
                "truncated": True,
                "full_chars": full_chars,
            }
        return {"status": "ok", "cluster_slug": cluster_slug, "text": text}
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


@mcp.tool()
def generate_dashboard() -> dict[str, str]:
    """Generate a personal HTML dashboard for the vault.

    Returns the path to the generated file. Open it in a browser to
    see cluster overview, paper counts, reading status breakdown, and
    NotebookLM links.
    """
    try:
        from research_hub.dashboard import generate_dashboard as _generate

        path = _generate(open_browser=False)
        return {"status": "ok", "path": str(path)}
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


@mcp.tool()
def propose_research_setup(topic: str) -> dict:
    """Propose names for a new research collection without creating anything.

    Use this BEFORE creating clusters/collections/notebooks. Show the
    suggestions to the user and ask them to confirm or override each
    name. Only after the user agrees should you call the create tools.

    Args:
        topic: The research topic in any language (e.g.,
               "AI agents in geopolitics" or "LLM 在地緣政治的應用")

    Returns:
        dict with proposed cluster_slug, cluster_name,
        zotero_collection_name, notebooklm_notebook_name,
        obsidian_folder, plus a `prompt_user` instruction string.
    """
    import re
    import unicodedata

    cleaned = unicodedata.normalize("NFKC", topic.strip())
    ascii_only = cleaned.encode("ascii", "ignore").decode("ascii")
    slug_source = ascii_only if ascii_only.strip() else cleaned
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug_source.lower()).strip("-")[:60]
    if not slug:
        slug = "untitled-cluster"

    title_case = " ".join(w.capitalize() for w in slug.split("-") if len(w) > 1)
    if not title_case:
        title_case = topic[:60]

    return {
        "topic": topic,
        "suggestions": {
            "cluster_slug": slug,
            "cluster_name": title_case,
            "zotero_collection_name": title_case,
            "notebooklm_notebook_name": title_case,
            "obsidian_folder": f"raw/{slug}/",
        },
        "prompt_user": (
            "I propose the names above. Please confirm or suggest "
            "alternatives for any of: cluster_slug, cluster_name, "
            "zotero_collection_name, notebooklm_notebook_name. "
            "I will only create them after you approve."
        ),
        "next_steps": [
            "Show the user the suggestions table",
            "Ask which they want to keep or change",
            "After user confirms, call clusters_new + bind_cluster + (optionally) create_zotero_collection",
        ],
    }


def main() -> None:
    """Entry point for `research-hub serve`."""
    if FastMCP is None:
        print("MCP server requires fastmcp. Install with:")
        print("  pip install research-hub-pipeline[mcp]")
        raise SystemExit(1)
    mcp.run()


mcp.tool()(search_papers)
mcp.tool()(enrich_candidates)
mcp.tool()(verify_paper)
mcp.tool()(suggest_integration)
mcp.tool()(list_clusters)
mcp.tool()(show_cluster)
mcp.tool()(export_citation)
mcp.tool()(get_references)
mcp.tool()(get_citations)
mcp.tool()(run_doctor)
mcp.tool()(get_config_info)
mcp.tool()(remove_paper)
mcp.tool()(mark_paper)
mcp.tool()(move_paper)
mcp.tool()(search_vault)
mcp.tool()(merge_clusters)
mcp.tool()(split_cluster)
mcp.tool()(get_topic_digest)
mcp.tool()(write_topic_overview)
mcp.tool()(read_topic_overview)
mcp.tool()(propose_subtopics)
mcp.tool()(emit_assignment_prompt)
mcp.tool()(apply_subtopic_assignments)
mcp.tool()(build_topic_notes)
mcp.tool()(list_topic_notes)
mcp.tool()(fit_check_prompt)
mcp.tool()(fit_check_apply)
mcp.tool()(fit_check_audit)
mcp.tool()(fit_check_drift)
mcp.tool()(autofill_emit)
mcp.tool()(autofill_apply)
mcp.tool()(label_paper)
mcp.tool()(list_papers_by_label)
mcp.tool()(prune_cluster)
mcp.tool()(apply_fit_check_to_labels)
mcp.tool()(discover_new)
mcp.tool()(discover_variants)
mcp.tool()(discover_continue)
mcp.tool()(discover_status)
mcp.tool()(discover_clean)
mcp.tool()(examples_list)
mcp.tool()(examples_show)
mcp.tool()(examples_copy)


if __name__ == "__main__":
    main()

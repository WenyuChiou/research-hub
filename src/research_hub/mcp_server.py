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
import json
from pathlib import Path
import re
from typing import Any, Callable

from research_hub.config import get_config
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


def _entrypoint_tool_error(exc: Exception, cluster_slug: str | None = None) -> dict[str, object]:
    if isinstance(exc, FileNotFoundError):
        return {
            "ok": False,
            "error": "vault not initialized",
            "hint": "Run: research-hub init",
            "details": str(exc),
        }
    if isinstance(exc, KeyError):
        cluster_name = cluster_slug or str(exc).strip("'")
        return {
            "ok": False,
            "error": f"cluster not found: {cluster_name}",
            "hint": f"Run: research-hub clusters new --query '{cluster_name}'",
        }
    return {
        "ok": False,
        "error": str(exc),
        "hint": "Check vault state with: research-hub doctor",
    }


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


@mcp.tool()
def web_search(query: str, max_results: int = 10, provider: str = "auto") -> dict[str, Any]:
    """General web search (blog posts / docs / news / GitHub READMEs).

    Use alongside auto_research_topic when the user's need extends beyond
    peer-reviewed papers and into official docs, engineering blogs, or news.
    """
    try:
        from research_hub.search.websearch import WebSearchBackend, _select_provider

        selected = _select_provider(None if provider == "auto" else provider)
        backend = WebSearchBackend(provider=None if provider == "auto" else provider)
        results = backend.search(query, limit=max_results)
        return {
            "ok": True,
            "provider": selected.name,
            "results": [
                {
                    "title": result.title,
                    "url": result.url,
                    "abstract": result.abstract,
                    "venue": result.venue,
                    "doc_type": result.doc_type,
                    "year": result.year,
                }
                for result in results
            ],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "provider": provider, "results": []}


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
def propose_cluster_rebind(cluster_slug: str = "") -> dict:
    """Propose moves to bind orphan papers to clusters. Returns the rebind report."""
    try:
        if cluster_slug:
            cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.cluster_rebind import emit_rebind_prompt

        cfg = get_config()
        report = emit_rebind_prompt(cfg)
        move_match = re.search(r"## Proposed moves .*?```json\s*\n(.*?)\n```", report, re.DOTALL)
        moves = json.loads(move_match.group(1)) if move_match else []
        if cluster_slug:
            moves = [move for move in moves if cluster_slug in str(move.get("dst", ""))]
        return {"cluster": cluster_slug or "(all)", "count": len(moves), "moves": moves}
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def apply_cluster_rebind(report_path: str, dry_run: bool = True, auto_create_new: bool = False) -> dict:
    """Apply rebind moves from a previously emitted report file. Default: dry-run."""
    try:
        from pathlib import Path

        from research_hub.cluster_rebind import apply_rebind

        cfg = get_config()
        result = apply_rebind(cfg, Path(report_path), dry_run=dry_run, auto_create_new=auto_create_new)
        return {
            "moved": len(result.moved),
            "skipped": len(result.skipped),
            "errors": len(result.errors),
            "log_path": result.log_path,
            "dry_run": dry_run,
        }
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def list_orphan_papers(folder: str = "") -> dict:
    """List paper notes in raw/ that aren't bound to any cluster. Filter by folder if given."""
    try:
        from research_hub.clusters import ClusterRegistry

        cfg = get_config()
        registry = ClusterRegistry(cfg.clusters_file)
        bound_dirs = {(cluster.obsidian_subfolder or cluster.slug) for cluster in registry.list()}
        orphans: list[str] = []
        if cfg.raw.exists():
            for sub in cfg.raw.iterdir():
                if not sub.is_dir() or sub.name.startswith(".") or sub.name in {"pdfs", "attachments"}:
                    continue
                if sub.name in bound_dirs:
                    continue
                if folder and sub.name != folder:
                    continue
                for md in sub.glob("*.md"):
                    orphans.append(md.relative_to(cfg.raw).as_posix())
        return {"folder": folder or "(all)", "count": len(orphans), "papers": orphans[:200]}
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def summarize_rebind_status() -> dict:
    """High-level rebind status: total orphans, proposed, stuck, would-create-clusters."""
    try:
        from research_hub.cluster_rebind import emit_rebind_prompt

        cfg = get_config()
        report = emit_rebind_prompt(cfg)
        move_match = re.search(r"## Proposed moves .*?```json\s*\n(.*?)\n```", report, re.DOTALL)
        proposals = json.loads(move_match.group(1)) if move_match else []
        new_cluster_match = re.search(r"new_cluster_proposals\s*```json\s*\n(.*?)\n```", report, re.DOTALL)
        new_clusters = json.loads(new_cluster_match.group(1)) if new_cluster_match else []
        orphan_tool = list_orphan_papers
        list_result = orphan_tool.fn() if hasattr(orphan_tool, "fn") else orphan_tool()
        total_orphans = int(list_result.get("count", 0))
        return {
            "total_orphans": total_orphans,
            "proposed_to_existing_clusters": len(proposals),
            "new_clusters_proposed": len(new_clusters),
            "stuck": total_orphans - len(proposals),
        }
    except Exception as exc:
        return _entrypoint_tool_error(exc)


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


@mcp.tool()
def import_folder_tool(folder: str, cluster_slug: str, dry_run: bool = False) -> dict:
    """Walk a local folder and ingest non-DOI files as document notes."""
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub.config import require_config
        from research_hub.importer import import_folder

        cfg = require_config()
        report = import_folder(cfg, folder, cluster_slug=cluster_slug, dry_run=dry_run)
        return {
            "cluster": cluster_slug,
            "imported": report.imported_count,
            "skipped": report.skipped_count,
            "failed": report.failed_count,
            "entries": [
                {
                    "file": str(entry.path),
                    "status": entry.status,
                    "slug": entry.slug,
                    "error": entry.error,
                }
                for entry in report.entries
            ],
        }
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
        return _entrypoint_tool_error(exc, str(cluster_slug))


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
        return _entrypoint_tool_error(exc, str(cluster_slug))


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
def summarize_cluster(
    cluster_slug: str,
    llm_cli: str = "",
    apply: bool = False,
    write_zotero: bool = True,
    write_obsidian: bool = True,
) -> dict:
    """Generate per-paper Key Findings + Methodology + Relevance via LLM CLI.

    For each paper in `cluster_slug`, builds a prompt from the abstract and
    invokes the detected LLM CLI (`claude`, `codex`, or `gemini` — pass
    `llm_cli` to override). With `apply=False` (default), returns the parsed
    JSON without writing. With `apply=True`, writes back to BOTH the Obsidian
    markdown blocks and the Zotero child note for each paper.

    Use when: user says "summarize this cluster's papers", "fill the TODO
    Findings", or after `auto` ingest before scanning the vault.

    No LLM CLI on PATH: prompt is saved to artifacts/<slug>/summarize-prompt.md;
    user can pipe it through their LLM and re-run with --apply (CLI) or pass
    the parsed payload to the apply_cluster_summaries MCP tool below.

    Returns ``{cluster_slug, ok, error, cli_used, prompt_path, apply_result}``.
    """
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub import summarize as summarize_mod
        from research_hub.config import get_config

        cfg = get_config()
        report = summarize_mod.summarize_cluster(
            cfg,
            cluster_slug,
            llm_cli=llm_cli or None,
            apply=apply,
            write_zotero=write_zotero,
            write_obsidian=write_obsidian,
        )
        return report.to_dict()
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def apply_cluster_summaries(cluster_slug: str, summaries_json: dict) -> dict:
    """Persist a JSON payload of per-paper summaries (when LLM was invoked
    out-of-band) to Obsidian + Zotero. The payload shape matches the
    `summarize_cluster` prompt's expected output: `{summaries: [...]}`.
    """
    try:
        cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
        from research_hub import summarize as summarize_mod
        from research_hub.config import get_config

        cfg = get_config()
        result = summarize_mod.apply_summaries(cfg, cluster_slug, summaries_json)
        return result.to_dict()
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


@mcp.tool()
def list_entities(cluster: str) -> dict:
    """List all entities (orgs/datasets/models) in a cluster's memory registry."""
    try:
        cluster = _validate_mcp_args(cluster=cluster)["cluster"]
        from research_hub.memory import list_entities as _list

        cfg = get_config()
        items = _list(cfg, cluster)
        return {"cluster": cluster, "count": len(items), "entities": [item.to_dict() for item in items]}
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def list_claims(cluster: str, min_confidence: str = "low") -> dict:
    """List structured claims in a cluster's memory. min_confidence in {high, medium, low}."""
    try:
        cluster = _validate_mcp_args(cluster=cluster)["cluster"]
        from research_hub.memory import list_claims as _list

        cfg = get_config()
        rank = {"high": 3, "medium": 2, "low": 1}
        threshold = rank.get(min_confidence, 1)
        items = [item for item in _list(cfg, cluster) if rank.get(item.confidence, 1) >= threshold]
        return {"cluster": cluster, "count": len(items), "claims": [item.to_dict() for item in items]}
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def list_methods(cluster: str) -> dict:
    """List methods (technique families) in a cluster's memory registry."""
    try:
        cluster = _validate_mcp_args(cluster=cluster)["cluster"]
        from research_hub.memory import list_methods as _list

        cfg = get_config()
        items = _list(cfg, cluster)
        return {"cluster": cluster, "count": len(items), "methods": [item.to_dict() for item in items]}
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def read_cluster_memory(cluster: str) -> dict:
    """Return the full ClusterMemory registry (entities + claims + methods) for a cluster."""
    try:
        cluster = _validate_mcp_args(cluster=cluster)["cluster"]
        from research_hub.memory import read_memory

        cfg = get_config()
        memory = read_memory(cfg, cluster)
        if memory is None:
            return {
                "cluster": cluster,
                "found": False,
                "message": "No memory generated yet. Run: research-hub memory emit --cluster <slug>",
            }
        return {"cluster": cluster, "found": True, **memory.to_dict()}
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


# v0.31 Track D: NotebookLM round-trip exposed via MCP.


@mcp.tool()
def notebooklm_bundle(cluster_slug: str, download_pdfs: bool = False) -> dict[str, Any]:
    """Build a NotebookLM upload bundle for a cluster."""
    cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
    try:
        from research_hub.clusters import ClusterRegistry
        from research_hub.config import get_config
        from research_hub.notebooklm.bundle import bundle_cluster

        cfg = get_config()
        registry = ClusterRegistry(cfg.clusters_file)
        cluster = registry.get(cluster_slug)
        if cluster is None:
            return {"status": "error", "error": f"Cluster not found: {cluster_slug}"}

        report = bundle_cluster(cluster, cfg, download_pdfs=download_pdfs)
        return {
            "status": "ok",
            "cluster_slug": cluster_slug,
            "bundle_dir": str(report.bundle_dir),
            "paper_count": len(report.entries),
            "pdf_count": report.pdf_count,
            "url_count": report.url_count,
            "skip_count": report.skip_count,
            "created_at": report.created_at,
        }
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


@mcp.tool()
def notebooklm_upload(
    cluster_slug: str,
    dry_run: bool = False,
    headless: bool = True,
    create_if_missing: bool = True,
) -> dict[str, Any]:
    """Upload the latest cluster bundle to NotebookLM via Playwright/CDP."""
    cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
    try:
        from research_hub.clusters import ClusterRegistry
        from research_hub.config import get_config
        from research_hub.notebooklm.upload import upload_cluster

        cfg = get_config()
        registry = ClusterRegistry(cfg.clusters_file)
        cluster = registry.get(cluster_slug)
        if cluster is None:
            return {"status": "error", "error": f"Cluster not found: {cluster_slug}"}

        report = upload_cluster(
            cluster,
            cfg,
            dry_run=dry_run,
            headless=headless,
            create_if_missing=create_if_missing,
        )
        return {
            "status": "ok",
            "cluster_slug": cluster_slug,
            "dry_run": dry_run,
            "notebook_name": report.notebook_name,
            "notebook_url": report.notebook_url,
            "notebook_id": report.notebook_id,
            "uploaded_count": report.success_count,
            "failed_count": report.fail_count,
            "skipped_already_uploaded": report.skipped_already_uploaded,
            "uploads": [asdict(item) for item in report.uploaded],
            "errors": list(report.errors),
        }
    except ImportError:  # pragma: no cover
        return {
            "status": "error",
            "error": "Playwright support is not installed. Run: pip install 'research-hub-pipeline[playwright]'",
        }
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


@mcp.tool()
def notebooklm_generate(
    cluster_slug: str,
    artifact_type: str = "brief",
    headless: bool = True,
) -> dict[str, Any]:
    """Trigger NotebookLM artifact generation for a cluster notebook."""
    cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
    valid_types = {"brief", "audio", "mind-map", "video", "all"}
    if artifact_type not in valid_types:
        return {
            "status": "error",
            "error": f"Invalid artifact_type: {artifact_type!r}. Expected one of {sorted(valid_types)}",
        }
    try:
        from datetime import datetime, timezone

        from research_hub.clusters import ClusterRegistry
        from research_hub.config import get_config
        from research_hub.notebooklm.upload import generate_artifact

        cfg = get_config()
        registry = ClusterRegistry(cfg.clusters_file)
        cluster = registry.get(cluster_slug)
        if cluster is None:
            return {"status": "error", "error": f"Cluster not found: {cluster_slug}"}

        if artifact_type == "all":
            kinds = ["brief", "audio", "mind_map", "video"]
        elif artifact_type == "mind-map":
            kinds = ["mind_map"]
        else:
            kinds = [artifact_type]

        artifacts: dict[str, str] = {}
        for kind in kinds:
            artifacts[kind] = generate_artifact(cluster, cfg, kind=kind, headless=headless)

        return {
            "status": "ok",
            "cluster_slug": cluster_slug,
            "artifact_type": artifact_type,
            "artifacts": artifacts,
            "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    except ImportError:  # pragma: no cover
        return {
            "status": "error",
            "error": "Playwright support is not installed. Run: pip install 'research-hub-pipeline[playwright]'",
        }
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


@mcp.tool()
def notebooklm_download(
    cluster_slug: str,
    artifact_type: str = "brief",
    headless: bool = True,
) -> dict[str, Any]:
    """Download the latest NotebookLM briefing artifact into the vault."""
    cluster_slug = _validate_mcp_args(cluster_slug=cluster_slug)["cluster_slug"]
    if artifact_type != "brief":
        return {
            "status": "error",
            "error": f"Only artifact_type='brief' is supported (got {artifact_type!r}).",
        }
    try:
        from research_hub.clusters import ClusterRegistry
        from research_hub.config import get_config
        from research_hub.notebooklm.upload import download_briefing_for_cluster

        cfg = get_config()
        registry = ClusterRegistry(cfg.clusters_file)
        cluster = registry.get(cluster_slug)
        if cluster is None:
            return {"status": "error", "error": f"Cluster not found: {cluster_slug}"}

        report = download_briefing_for_cluster(cluster, cfg, headless=headless)
        return {
            "status": "ok",
            "cluster_slug": cluster_slug,
            "artifact_type": artifact_type,
            "artifact_path": str(report.artifact_path),
            "char_count": report.char_count,
            "notebook_name": report.notebook_name,
            "titles": report.titles,
        }
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


@mcp.tool()
def ask_cluster_notebooklm(
    cluster: str,
    question: str,
    headless: bool = True,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    """Ask an ad-hoc question against a cluster's NotebookLM notebook."""
    cluster = _validate_mcp_args(cluster=cluster)["cluster"]
    try:
        from research_hub.clusters import ClusterRegistry
        from research_hub.notebooklm.ask import ask_cluster_notebook

        cfg = get_config()
        registry = ClusterRegistry(cfg.clusters_file)
        cluster_obj = registry.get(cluster)
        if cluster_obj is None:
            return {
                "ok": False,
                "answer": "",
                "artifact_path": "",
                "latency_seconds": 0.0,
                "hint": "Run: research-hub clusters list",
            }
        result = ask_cluster_notebook(
            cluster_obj,
            cfg,
            question=question,
            headless=headless,
            timeout_sec=timeout_sec,
        )
        payload = {
            "ok": result.ok,
            "answer": result.answer,
            "artifact_path": str(result.artifact_path) if result.artifact_path else "",
            "latency_seconds": result.latency_seconds,
        }
        if not result.ok:
            payload["hint"] = result.error
        return payload
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


# ---------------------------------------------------------------------------
# v0.33 Task-level workflow wrappers (Codex Phase 3)
# ---------------------------------------------------------------------------


@mcp.tool()
def ask_cluster(
    cluster_slug: str,
    question: str | None = None,
    detail: str = "gist",
) -> dict:
    """Answer a natural-language question about a cluster (crystal with digest fallback).

    Task-level wrapper for the common read path. Replaces the 3-call sequence
    list_crystals → read_crystal → (optional search_vault) with 1 call that
    fuzzy-matches the question against crystal questions and falls back to
    topic digest if no crystal matches.
    """
    try:
        from research_hub.workflows import ask_cluster as _impl
        cfg = get_config()
        result = _impl(cfg, cluster_slug, question=question, detail=detail)
        if isinstance(result, dict) and result.get("ok") is False and "hint" not in result:
            message = str(result.get("error", ""))
            if "unknown cluster" in message or "cluster not found" in message:
                return _entrypoint_tool_error(KeyError(cluster_slug), cluster_slug)
            if "not initialized" in message or "No such file" in message:
                return _entrypoint_tool_error(FileNotFoundError(message), cluster_slug)
            return {
                "ok": False,
                "error": message,
                "hint": "Check vault state with: research-hub doctor",
            }
        return result
    except Exception as exc:  # pragma: no cover
        return _entrypoint_tool_error(exc, cluster_slug)


@mcp.tool()
def brief_cluster(cluster_slug: str, force_regenerate: bool = False) -> dict:
    """Full NotebookLM round-trip: bundle -> upload -> generate -> download -> preview.

    Degrades gracefully if Playwright not installed (returns partial result).
    """
    try:
        from research_hub.workflows import brief_cluster as _impl
        cfg = require_config()
        return _impl(cfg, cluster_slug, force_regenerate=force_regenerate)
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


@mcp.tool()
def sync_cluster(cluster_slug: str) -> dict:
    """Aggregate maintenance view: staleness + scope drift + vault health + recommendations."""
    try:
        from research_hub.workflows import sync_cluster as _impl
        cfg = require_config()
        return _impl(cfg, cluster_slug)
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


@mcp.tool()
def compose_brief_draft(
    cluster_slug: str,
    outline: str | None = None,
    max_quotes: int = 10,
) -> dict:
    """Assemble a markdown draft from cluster quotes + overview + crystal TLDRs."""
    try:
        from research_hub.workflows import compose_brief as _impl
        cfg = require_config()
        return _impl(cfg, cluster_slug, outline=outline, max_quotes=max_quotes)
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


@mcp.tool()
def emit_cluster_base(cluster_slug: str, force: bool = False) -> dict[str, Any]:
    """Emit (or refresh) the .base dashboard file for a cluster."""
    try:
        cfg = get_config()
        from research_hub.clusters import ClusterRegistry
        from research_hub.obsidian_bases import write_cluster_base

        registry = ClusterRegistry(cfg.clusters_file)
        cluster = registry.get(cluster_slug)
        if cluster is None:
            return {"ok": False, "error": f"Cluster not found: {cluster_slug}"}

        path, written = write_cluster_base(
            hub_root=Path(cfg.hub),
            cluster_slug=cluster_slug,
            cluster_name=cluster.name,
            obsidian_subfolder=cluster.obsidian_subfolder,
            force=force,
        )
        return {
            "ok": True,
            "path": str(path),
            "bytes": path.stat().st_size if path.exists() else 0,
            "action": "created" if written else "exists",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# v0.47 — Lazy mode MCP tools so AI can drive the whole pipeline in one call.
# Mirrors the v0.46 CLI commands `auto`, `cleanup`, `tidy`.

@mcp.tool()
def auto_research_topic(
    topic: str,
    cluster_slug: str = "",
    cluster_name: str = "",
    max_papers: int = 8,
    field: str = "",
    do_nlm: bool = True,
    do_crystals: bool = False,
    do_cluster_overview: bool = True,
    do_fit_check: bool = True,
    cluster_overview_threshold: int = 0,
    fit_check_threshold: int = 3,
    zotero_batch_size: int = 50,
    llm_cli: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """One-shot research pipeline: search + ingest + NotebookLM brief (+ optional crystals).

    Slugifies ``topic`` into a cluster (or reuses ``cluster_slug``), searches
    arXiv + Semantic Scholar, ingests papers into Zotero + Obsidian, then
    bundles + uploads + generates + downloads a NotebookLM brief. With
    ``do_crystals=True`` and a detected LLM CLI on PATH (claude/codex/gemini),
    also generates and applies the canonical Q&A crystals so the cluster is
    fully ready for ``read_crystal()`` queries.

    Use when: user says "research X for me" or "find papers on X".

    Returns ``{ok, cluster_slug, papers_ingested, notebook_url,
    brief_path, total_duration_sec, error}``.
    """
    try:
        from research_hub.auto import auto_pipeline

        report = auto_pipeline(
            topic,
            cluster_slug=cluster_slug or None,
            cluster_name=cluster_name or None,
            max_papers=max_papers,
            field=field or None,
            do_nlm=do_nlm,
            do_crystals=do_crystals,
            do_cluster_overview=do_cluster_overview,
            cluster_overview_threshold=cluster_overview_threshold,
            do_fit_check=do_fit_check,
            fit_check_threshold=fit_check_threshold,
            zotero_batch_size=zotero_batch_size,
            llm_cli=llm_cli or None,
            dry_run=dry_run,
            print_progress=False,
        )
        return {
            "ok": report.ok,
            "cluster_slug": report.cluster_slug,
            "cluster_created": report.cluster_created,
            "papers_ingested": report.papers_ingested,
            "nlm_uploaded": report.nlm_uploaded,
            "notebook_url": report.notebook_url,
            "brief_path": str(report.brief_path) if report.brief_path else None,
            "total_duration_sec": report.total_duration_sec,
            "steps": [{"name": s.name, "ok": s.ok, "detail": s.detail} for s in report.steps],
            "error": report.error if not report.ok else "",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def plan_research_workflow(user_intent: str) -> dict[str, Any]:
    """Convert a freeform user intent into a structured research plan.

    **Call this BEFORE auto_research_topic when the user's request is vague,
    ambitious, or could collide with an existing cluster.** Returns a
    suggested topic + search depth + NLM/crystals choices + clarifying
    questions for you to confirm with the user.

    Use when the user says things like:
      "I want to learn about X"
      "research X for my dissertation"
      "find recent papers on X"
      "ingest X but skip NotebookLM"

    The plan includes:
      - intent_summary: rephrased one-line restatement (confirm with user)
      - suggested_topic / cluster_slug
      - suggested_max_papers (auto-tuned: 25 for thesis, 8 default, etc.)
      - suggested_do_nlm / do_crystals (with detected CLI awareness)
      - existing_cluster_match: warns if a similar cluster already exists
      - clarifying_questions: ask these BEFORE calling auto_research_topic
      - next_call: ready-to-execute auto_research_topic args after confirmation
      - estimated_duration_sec: rough time estimate

    After presenting the plan + getting user confirmation, call
    auto_research_topic with the plan's suggested args.
    """
    try:
        from research_hub.config import get_config
        from research_hub.planner import plan_to_dict, plan_workflow

        try:
            cfg = get_config()
        except Exception:
            cfg = None  # plan still works without cfg, just no collision check
        plan = plan_workflow(user_intent, cfg=cfg)
        return {"ok": True, **plan_to_dict(plan)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def cleanup_garbage(
    bundles: bool = False,
    debug_logs: bool = False,
    artifacts: bool = False,
    everything: bool = False,
    keep_bundles: int = 2,
    debug_older_than_days: int = 30,
    keep_artifacts: int = 10,
    apply: bool = False,
) -> dict[str, Any]:
    """Garbage-collect accumulated research-hub files (v0.46+).

    Pass ``everything=True`` for the common case (bundles + debug logs +
    artifacts). Default mode lists candidates without deleting; pass
    ``apply=True`` to actually remove.

    Use when: user says "clean up", "free disk space", or "GC the vault".

    Returns ``{ok, total_bytes, files_deleted, dirs_deleted, candidates}``.
    """
    try:
        from research_hub.cleanup import collect_garbage, format_bytes

        cfg = get_config()
        do_b = bundles or everything
        do_d = debug_logs or everything
        do_a = artifacts or everything
        report = collect_garbage(
            cfg,
            do_bundles=do_b,
            do_debug_logs=do_d,
            do_artifacts=do_a,
            keep_bundles=keep_bundles,
            debug_older_than_days=debug_older_than_days,
            keep_artifacts=keep_artifacts,
            apply=apply,
        )
        return {
            "ok": True,
            "total_bytes": report.total_bytes,
            "total_human": format_bytes(report.total_bytes),
            "files_deleted": report.files_deleted,
            "dirs_deleted": report.dirs_deleted,
            "applied": report.apply,
            "candidates": (
                [{"kind": "bundle", "path": str(c.path), "bytes": c.size_bytes} for c in report.bundles]
                + [{"kind": "debug_log", "path": str(c.path), "bytes": c.size_bytes} for c in report.debug_logs]
                + [{"kind": "artifact", "path": str(c.path), "bytes": c.size_bytes} for c in report.artifacts]
            ),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def tidy_vault(apply_cleanup: bool = False) -> dict[str, Any]:
    """One-shot vault maintenance: doctor autofix + dedup rebuild + bases refresh + cleanup preview.

    Each sub-step is non-fatal — failures logged but don't abort the others.

    Use when: user says "tidy", "maintenance", "vault health check".

    Returns ``{ok, steps, total_duration_sec, cleanup_preview_bytes}``.
    """
    try:
        from research_hub.tidy import run_tidy

        report = run_tidy(apply_cleanup=apply_cleanup, print_progress=False)
        return {
            "ok": all(s.ok for s in report.steps),
            "steps": [{"name": s.name, "ok": s.ok, "detail": s.detail} for s in report.steps],
            "total_duration_sec": report.total_duration_sec,
            "cleanup_preview_bytes": report.cleanup_preview_bytes,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def collect_to_cluster(
    source: str,
    cluster_slug: str,
    skip_verify: bool = False,
    no_zotero: bool = False,
    dry_run: bool = False,
) -> dict:
    """Unified ingest. Auto-routes by source shape: DOI/arXiv -> add_paper, folder -> import_folder, URL -> .url file + import."""
    try:
        from research_hub.workflows import collect_to_cluster as _impl
        cfg = require_config()
        return _impl(
            cfg, source, cluster_slug=cluster_slug,
            skip_verify=skip_verify, no_zotero=no_zotero, dry_run=dry_run,
        )
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


if __name__ == "__main__":
    main()

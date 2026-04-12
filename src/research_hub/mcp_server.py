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

    def tool(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._tool_manager._tools[func.__name__] = func
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


def search_papers(query: str, limit: int = 10, verify: bool = False) -> list[dict[str, Any]] | dict[str, str]:
    """Search Semantic Scholar for academic papers."""
    try:
        from research_hub.config import get_config
        from research_hub.dedup import DedupIndex
        from research_hub.search import SemanticScholarClient, iter_new_results

        cfg = get_config()
        index_path = cfg.research_hub_dir / "dedup_index.json"
        index = DedupIndex.load(index_path) if index_path.exists() else DedupIndex()

        client = SemanticScholarClient()
        results = iter_new_results(client, query, index.doi_to_hits.keys(), limit=min(limit, 100))

        output: list[dict[str, Any]] = []
        for result in results:
            entry: dict[str, Any] = {
                "title": result.title,
                "doi": result.doi,
                "authors": result.authors,
                "year": result.year,
                "venue": result.venue,
                "citation_count": result.citation_count,
                "url": result.url,
                "pdf_url": result.pdf_url,
                "already_in_vault": False,
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
        from contextlib import redirect_stdout
        import io

        from research_hub.cli import _cite

        buf = io.StringIO()
        with redirect_stdout(buf):
            _cite(identifier, cluster, format, None)
        return buf.getvalue()
    except Exception as exc:  # pragma: no cover - exercised via failure tests
        return _tool_error(exc)


def get_references(identifier: str, limit: int = 20) -> list[dict[str, Any]] | dict[str, str]:
    """List papers cited by the given paper (its bibliography)."""
    try:
        from research_hub.citation_graph import CitationGraphClient

        client = CitationGraphClient()
        return [asdict(node) for node in client.get_references(identifier, limit=limit)]
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


def get_citations(identifier: str, limit: int = 20) -> list[dict[str, Any]] | dict[str, str]:
    """List papers that cite the given paper."""
    try:
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
        from research_hub.operations import remove_paper as _remove

        return _remove(identifier, include_zotero=include_zotero, dry_run=dry_run)
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


def mark_paper(slug: str, status: str) -> dict[str, Any]:
    """Update reading status for a note."""
    try:
        from research_hub.operations import mark_paper as _mark

        return _mark(slug, status)
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


def move_paper(slug: str, to_cluster: str) -> dict[str, Any]:
    """Move a note to a different cluster."""
    try:
        from research_hub.operations import move_paper as _move

        return _move(slug, to_cluster)
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
        from research_hub.vault_search import search_vault as _search

        return _search(query, cluster=cluster, status=status, full_text=full_text)
    except Exception as exc:  # pragma: no cover
        return _tool_error(exc)


def merge_clusters(source: str, into: str) -> dict[str, Any]:
    """Merge one cluster into another."""
    try:
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
        from research_hub.clusters import ClusterRegistry
        from research_hub.config import get_config

        cfg = get_config()
        registry = ClusterRegistry(cfg.clusters_file)
        return registry.split(source, query, new_name, vault_raw=cfg.raw)
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


if __name__ == "__main__":
    main()

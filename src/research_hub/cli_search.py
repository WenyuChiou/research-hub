"""Search and discovery CLI handlers for Research Hub."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config
from research_hub.dedup import DedupIndex
from research_hub.search import SemanticScholarClient
from research_hub.suggest import PaperInput, suggest_cluster_for_paper, suggest_related_papers
from research_hub.verify import verify_doi
from research_hub.cli_common import (
    _parse_csv_terms,
    _parse_negative_terms,
    _parse_seed_dois,
    _parse_year_range,
)


def _search(
    query: str,
    limit: int,
    verify: bool = False,
    *,
    year_from: int | None = None,
    year_to: int | None = None,
    min_citations: int = 0,
    backends: tuple[str, ...] = ("openalex", "arxiv", "semantic-scholar", "crossref", "dblp"),
    exclude_types: tuple[str, ...] = (),
    exclude_terms: tuple[str, ...] = (),
    min_confidence: float = 0.0,
    rank_by: str = "smart",
    backend_trace: bool = False,
    emit_json: bool = False,
    to_papers_input: bool = False,
    cluster_slug: str | None = None,
    adversarial: bool = False,
    max_variants: int = 5,
    screen: bool = False,
) -> int:
    cfg = get_config()
    index = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")

    if adversarial:
        from research_hub.search import adversarial_search as _adversarial_search

        results, recall = _adversarial_search(
            query,
            limit=limit,
            max_variants=max_variants,
            year_from=year_from,
            year_to=year_to,
            min_citations=min_citations,
            backends=backends,
            exclude_types=exclude_types,
            exclude_terms=exclude_terms,
            min_confidence=min_confidence,
            rank_by=rank_by,
            backend_trace=backend_trace,
        )
        print(
            f"[recall] {recall.queries_run} query phrasings searched -> "
            f"{recall.total_unique} unique papers; "
            f"confidence={recall.confidence}"
            f"{' (saturated)' if recall.saturated else ''}",
            file=sys.stderr,
        )
    else:
        from research_hub.search import search_papers as _search_papers

        results = _search_papers(
            query,
            limit=limit,
            year_from=year_from,
            year_to=year_to,
            min_citations=min_citations,
            backends=backends,
            exclude_types=exclude_types,
            exclude_terms=exclude_terms,
            min_confidence=min_confidence,
            rank_by=rank_by,
            backend_trace=backend_trace,
        )
    from research_hub.dedup import normalize_doi

    ingested = {normalize_doi(doi) for doi in index.doi_to_hits.keys() if doi}
    results = [r for r in results if normalize_doi(r.doi) not in ingested]

    # --screen: fit-check BM25 relevance gate. Tags each result, never
    # drops one (recall-preserving — gap-to-topic Gate 1 audits on the
    # full retrieved count). Orthogonal to --rank-by (ordering is left
    # untouched; screening only annotates).
    verdicts: list[dict] | None = None
    screening_summary: dict | None = None
    if screen:
        from research_hub.fit_check import screen_relevance

        verdicts = screen_relevance([asdict(r) for r in results], query)
        kept_n = sum(1 for v in verdicts if v["kept"])
        screening_summary = {
            "retrieved": len(results),
            "kept": kept_n,
            "screened_out": len(results) - kept_n,
            "tier": (verdicts[0]["tier"] if verdicts else ""),
        }
        print(
            f"[screen] {screening_summary['retrieved']} retrieved -> "
            f"{screening_summary['kept']} kept, "
            f"{screening_summary['screened_out']} screened out "
            f"(gate tier: {screening_summary['tier'] or 'n/a'})",
            file=sys.stderr,
        )

    if to_papers_input:
        _emit_papers_input_json(results, cluster_slug)
        return 0
    if emit_json:
        if screen and verdicts is not None:
            screened_results = []
            for result, verdict in zip(results, verdicts):
                row = asdict(result)
                row["relevance"] = {
                    "score": verdict["score"],
                    "kept": verdict["kept"],
                    "tier": verdict["tier"],
                    "reason": verdict["reason"],
                }
                screened_results.append(row)
            print(json.dumps(
                {"screening_summary": screening_summary, "results": screened_results},
                indent=2,
                ensure_ascii=False,
            ))
        else:
            print(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False))
        return 0
    for i, result in enumerate(results):
        line = (
            f"{result.title}\t{result.doi or result.arxiv_id}\t"
            f"{result.year or '????'}\t{result.citation_count}\t{result.source}"
        )
        if verify:
            verified = bool(result.doi) and verify_doi(result.doi).ok
            line += "\tVERIFIED" if verified else "\tUNVERIFIED"
        if screen and verdicts is not None:
            verdict = verdicts[i]
            line += (
                f"\t{'KEEP' if verdict['kept'] else 'SCREENED-OUT'}"
                f"({verdict['score']})"
            )
        print(line)
    return 0


def _websearch(
    query: str,
    limit: int,
    *,
    provider: str,
    max_age_days: int | None = None,
    domain: str | None = None,
    emit_json: bool = False,
    ingest_into: str | None = None,
) -> int:
    from datetime import datetime, timedelta

    from research_hub.search.websearch import WebSearchBackend, _select_provider

    backend = WebSearchBackend(provider=None if provider == "auto" else provider)
    results = backend.search(query, limit=limit)
    if domain:
        domain_lower = domain.lower()
        results = [result for result in results if result.venue.lower() == domain_lower]
    if max_age_days is not None:
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        results = [
            result for result in results
            if result.year is None or datetime(result.year, 12, 31) >= cutoff
        ]

    if ingest_into:
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            for idx, result in enumerate(results, 1):
                slug = re.sub(r"[^a-z0-9]+", "-", (result.title or result.url).lower()).strip("-") or f"web-{idx}"
                (folder / f"{idx:02d}-{slug[:60]}.url").write_text(result.url + "\n", encoding="utf-8")
            cmd = [
                sys.executable,
                "-m",
                "research_hub.cli",
                "import-folder",
                str(folder),
                "--cluster",
                ingest_into,
            ]
            completed = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", env=os.environ.copy())
            if completed.returncode != 0:
                return completed.returncode

    provider_name = _select_provider(None if provider == "auto" else provider).name
    if emit_json:
        payload = {
            "ok": True,
            "provider": provider_name,
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
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print(f"provider={provider_name}")
    for result in results:
        year = result.year if result.year is not None else "????"
        print(f"{result.title}\t{result.url}\t{result.venue}\t{result.doc_type}\t{year}")
    return 0


def _emit_papers_input_json(results: list, cluster_slug: str | None) -> None:
    """Print a flat papers_input.json list to stdout."""
    from research_hub.discover import _to_papers_input

    papers = _to_papers_input([asdict(result) for result in results], cluster_slug)
    for paper, result in zip(papers, results):
        arxiv_id = str(getattr(result, "arxiv_id", "") or "")
        if arxiv_id:
            paper["arxiv_id"] = arxiv_id
            if not paper.get("doi"):
                paper["doi"] = f"10.48550/arxiv.{arxiv_id}"
    print(json.dumps(papers, indent=2, ensure_ascii=False))


def _enrich(
    candidates: list[str],
    *,
    backends: tuple[str, ...],
    to_papers_input: bool = False,
    cluster_slug: str | None = None,
) -> int:
    items = list(candidates)
    if not items or items == ["-"]:
        items = [line.strip() for line in sys.stdin if line.strip()]
    if not items:
        print("No candidates provided.", file=sys.stderr)
        return 2

    from research_hub.search import enrich_candidates

    resolved = enrich_candidates(items, backends=backends)
    hits = [r for r in resolved if r is not None]

    if to_papers_input:
        _emit_papers_input_json(hits, cluster_slug)
        return 0

    print(json.dumps([asdict(r) for r in hits], indent=2, ensure_ascii=False))
    return 0


def _references(identifier: str, limit: int, emit_json: bool) -> int:
    from research_hub.citation_graph import CitationGraphClient

    client = CitationGraphClient()
    nodes = client.get_references(identifier, limit=limit)
    if emit_json:
        print(json.dumps([asdict(node) for node in nodes], indent=2, ensure_ascii=False))
        return 0
    print(f"References of {identifier} ({len(nodes)} returned):")
    for node in nodes:
        year = node.year if node.year else "????"
        first_author = (node.authors[0] if node.authors else "Unknown").split()[-1]
        print(f"  [{year}] {first_author:15s} {node.title[:70]}")
        if node.doi:
            print(f"             DOI: {node.doi}")
    return 0


def _cited_by(identifier: str, limit: int, emit_json: bool) -> int:
    from research_hub.citation_graph import CitationGraphClient

    client = CitationGraphClient()
    nodes = client.get_citations(identifier, limit=limit)
    if emit_json:
        print(json.dumps([asdict(node) for node in nodes], indent=2, ensure_ascii=False))
        return 0
    print(f"Citations of {identifier} ({len(nodes)} returned):")
    for node in nodes:
        year = node.year if node.year else "????"
        first_author = (node.authors[0] if node.authors else "Unknown").split()[-1]
        print(f"  [{year}] {first_author:15s} {node.title[:70]}")
        if node.doi:
            print(f"             DOI: {node.doi}")
    return 0


def _suggest(identifier: str, top: int, emit_json: bool) -> int:
    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    dedup = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")

    paper = PaperInput(title=identifier)
    if re.search(r"10\.\S+", identifier):
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

    cluster_suggestions = suggest_cluster_for_paper(paper, registry, dedup, top_n=3)
    related_papers = suggest_related_papers(paper, dedup, registry, top_n=top)

    if emit_json:
        payload = {
            "identifier": identifier,
            "paper": asdict(paper),
            "cluster_suggestions": [asdict(item) for item in cluster_suggestions],
            "related_papers": [asdict(item) for item in related_papers],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("Cluster suggestions (top 3):")
    for item in cluster_suggestions:
        print(f"  [{item.score:.1f}] {item.cluster_slug}")
        print(f"         {', '.join(item.reasons)}")

    print(f"\nRelated papers (top {top}):")
    for item in related_papers:
        print(f"  [{item.score:.1f}] {item.title}  ({item.source})")
        print(f"         {', '.join(item.reasons)}")
    return 0


def _discover_new(args) -> int:
    from research_hub.discover import discover_new

    cfg = get_config()
    year_from, year_to = _parse_year_range(args.year) if args.year else (None, None)
    backends = tuple(item.strip() for item in args.backend.split(",") if item.strip()) if args.backend else None
    exclude_types = _parse_csv_terms(args.exclude_type)
    exclude_terms = _parse_negative_terms(args.exclude)
    seed_dois = _parse_seed_dois(args.seed_dois, args.seed_dois_file)
    expand_from = tuple(item.strip() for item in args.expand_from.split(",") if item.strip())
    from research_hub.discover import _DEFAULT_PER_BACKEND_LIMIT_FACTOR as _DEFAULT_FACTOR

    per_backend_factor = args.per_backend_factor if args.per_backend_factor is not None else _DEFAULT_FACTOR
    state, prompt = discover_new(
        cfg,
        args.cluster,
        args.query,
        year_from=year_from,
        year_to=year_to,
        min_citations=args.min_citations,
        backends=backends,
        field=args.field,
        region=args.region,
        limit=args.limit,
        definition=args.definition,
        exclude_types=exclude_types,
        exclude_terms=exclude_terms,
        min_confidence=args.min_confidence,
        rank_by=args.rank_by,
        from_variants=args.from_variants,
        auto_variants=args.auto_variants,
        expand_auto=args.expand_auto,
        expand_from=expand_from,
        expand_hops=args.expand_hops,
        expand_semantic=args.expand_semantic,
        seed_dois=seed_dois,
        include_existing=args.include_existing,
        per_backend_factor=per_backend_factor,
    )
    if args.prompt_out:
        Path(args.prompt_out).write_text(prompt, encoding="utf-8")
        print(f"wrote {args.prompt_out}", file=sys.stderr)
    else:
        print(prompt)
    print(
        f"[discover] stashed {state.candidate_count} candidates for {args.cluster}. "
        f"Score the prompt, save to scored.json, then run `discover continue`.",
        file=sys.stderr,
    )
    return 0


def _discover_continue(args) -> int:
    from research_hub.discover import discover_continue

    cfg = get_config()
    scored = json.loads(Path(args.scored).read_text(encoding="utf-8"))
    out_path = Path(args.out) if args.out else None
    state, papers_input_path = discover_continue(
        cfg,
        args.cluster,
        scored,
        threshold=args.threshold,
        auto_threshold=args.auto_threshold,
        out_path=out_path,
    )
    print(
        f"[discover] accepted {state.accepted_count} / {state.candidate_count} "
        f"(rejected {state.rejected_count}, threshold {state.threshold})",
        file=sys.stderr,
    )
    print(f"papers_input.json: {papers_input_path}")
    return 0


def _discover_status(args) -> int:
    from research_hub.discover import discover_status

    cfg = get_config()
    state = discover_status(cfg, args.cluster)
    if state is None:
        print(f"no discover state for cluster {args.cluster}")
        return 1
    print(f"cluster: {state.cluster_slug}")
    print(f"stage:   {state.stage}")
    print(f"query:   {state.query}")
    print(f"candidates: {state.candidate_count}")
    print(f"variations_used: {state.variations_used}")
    print(f"expanded_from: {state.expanded_from}")
    print(f"seed_dois: {state.seed_dois}")
    print(f"deduped_against_cluster: {state.deduped_against_cluster}")
    if state.stage == "done":
        print(f"accepted: {state.accepted_count} / {state.candidate_count}")
        print(f"rejected: {state.rejected_count}")
        suffix = " (auto)" if state.auto_threshold else ""
        print(f"threshold: {state.threshold}{suffix}")
    return 0


def _discover_variants(args) -> int:
    from research_hub.discover import emit_variation_prompt

    cfg = get_config()
    prompt = emit_variation_prompt(cfg, args.cluster, args.query, target_count=args.count)
    if args.out:
        Path(args.out).write_text(prompt, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(prompt)
    return 0


def _discover_clean(args) -> int:
    from research_hub.discover import discover_clean

    cfg = get_config()
    removed = discover_clean(cfg, args.cluster)
    if removed:
        print(f"removed discover state for {args.cluster}")
    else:
        print(f"no discover state for {args.cluster}")
    return 0


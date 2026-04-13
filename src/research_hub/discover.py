"""Wrapper around search + fit-check for end-to-end paper discovery."""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import asdict, dataclass, field as dataclass_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Stage = Literal["new", "scored_pending", "done"]

STATE_FILENAME = "state.json"
CANDIDATES_FILENAME = "candidates.json"
PROMPT_FILENAME = "prompt.md"
ACCEPTED_FILENAME = "accepted.json"
PAPERS_INPUT_FILENAME = "papers_input.json"

_DEFAULT_LIMIT = 50
_DEFAULT_PER_BACKEND_LIMIT_FACTOR = 3
_DEFAULT_PER_BACKEND_LIMIT_FLOOR = 40


@dataclass
class QueryVariation:
    query: str
    rationale: str = ""


@dataclass
class DiscoverState:
    cluster_slug: str
    stage: Stage
    query: str
    definition: str = ""
    created_at: str = ""
    candidate_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    threshold: int = 3
    auto_threshold: bool = False
    variations_used: list[str] = dataclass_field(default_factory=list)
    expanded_from: list[str] = dataclass_field(default_factory=list)
    seed_dois: list[str] = dataclass_field(default_factory=list)
    deduped_against_cluster: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "DiscoverState":
        data = json.loads(text)
        data.setdefault("variations_used", [])
        data.setdefault("expanded_from", [])
        data.setdefault("seed_dois", [])
        data.setdefault("deduped_against_cluster", 0)
        return cls(**data)


def stash_dir(cfg, cluster_slug: str) -> Path:
    root = getattr(cfg, "research_hub_dir", None)
    if root is None:
        root = Path(cfg.root) / ".research_hub"
    return Path(root) / "discover" / cluster_slug


def _score_values(scored: list[dict] | dict) -> list[int]:
    entries = scored.get("scores", []) if isinstance(scored, dict) else scored
    return [int(entry.get("score", 0)) for entry in entries]


def _median_int(values: list[int]) -> int | None:
    if not values:
        return None
    sorted_values = sorted(values)
    n = len(sorted_values)
    if n % 2 == 1:
        return sorted_values[n // 2]
    return (sorted_values[n // 2 - 1] + sorted_values[n // 2]) // 2


def emit_variation_prompt(
    cfg,
    cluster_slug: str,
    original_query: str,
    target_count: int = 4,
) -> str:
    """Build the query-variation prompt for an AI to consume."""
    from research_hub.fit_check import _read_definition_from_overview

    definition = _read_definition_from_overview(cfg, cluster_slug) or ""
    definition_block = definition if definition else "(no cluster definition found)"
    return f"""# Query variations for cluster "{cluster_slug}"

## Original query

{original_query}

## Cluster definition

{definition_block}

## Task

Generate {target_count} query variations that capture different facets of this topic.
Good variations hit sub-areas the original query would miss. Aim for:

- One variation focused on specific benchmarks (names, datasets)
- One variation focused on agent frameworks / architectures
- One variation focused on evaluation methodology
- One variation focused on adjacent specializations (e.g. domain-specific
  code generation)

Each variation should be 4-8 words, suitable for a keyword search engine.

## Your output

Emit ONE JSON object:

```json
{{
  "variations": [
    {{
      "query": "SWE-bench issue resolution agent",
      "rationale": "canonical SE benchmark + direct variants"
    }},
    {{
      "query": "MetaGPT multi-agent software development",
      "rationale": "multi-agent architectures missed by benchmark keywords"
    }}
  ]
}}
```"""


def _coerce_variations(variations: list[QueryVariation | dict] | None) -> list[QueryVariation]:
    out: list[QueryVariation] = []
    for item in variations or []:
        if isinstance(item, QueryVariation):
            query = item.query.strip()
            rationale = item.rationale.strip()
        else:
            query = str(item.get("query", "")).strip()
            rationale = str(item.get("rationale", "")).strip()
        if query:
            out.append(QueryVariation(query=query, rationale=rationale))
    return out


def apply_variations(
    cfg,
    cluster_slug: str,
    variations: list[QueryVariation | dict],
    *,
    year_from: int | None = None,
    year_to: int | None = None,
    min_citations: int = 0,
    backends: tuple[str, ...] | None = None,
    limit: int = _DEFAULT_LIMIT,
    exclude_types: tuple[str, ...] = (),
    exclude_terms: tuple[str, ...] = (),
    min_confidence: float = 0.0,
    rank_by: str = "smart",
) -> list[dict]:
    """Run search for each variation, merge by DOI, add _discover_meta."""
    from research_hub.search import search_papers
    from research_hub.search._rank import merge_results

    normalized_variations = _coerce_variations(variations)
    per_variation = {}
    base_confidence_by_key: dict[str, float] = {}
    per_backend_limit = max(
        limit * _DEFAULT_PER_BACKEND_LIMIT_FACTOR,
        _DEFAULT_PER_BACKEND_LIMIT_FLOOR,
    )
    for variation in normalized_variations:
        results = search_papers(
            variation.query,
            limit=limit,
            year_from=year_from,
            year_to=year_to,
            min_citations=min_citations,
            backends=backends,
            exclude_types=exclude_types,
            exclude_terms=exclude_terms,
            min_confidence=min_confidence,
            rank_by=rank_by,
            per_backend_limit=per_backend_limit,
        )
        per_variation[variation.query] = results
        for result in results:
            key = result.dedup_key
            if key not in base_confidence_by_key:
                base_confidence_by_key[key] = float(result.confidence)
            else:
                base_confidence_by_key[key] = max(base_confidence_by_key[key], float(result.confidence))

    merged = merge_results(per_variation)
    out: list[dict] = []
    for result in merged:
        matched = list(result.found_in)
        entry = asdict(result)
        entry["confidence"] = min(
            1.0,
            base_confidence_by_key.get(result.dedup_key, float(result.confidence))
            + 0.1 * max(0, len(matched) - 1),
        )
        entry["_discover_meta"] = {
            "matched_variations": matched,
            "source_tags": [result.source] if result.source else [],
            "is_seed": False,
        }
        out.append(entry)
    return out


def _citation_node_to_search_result(node):
    """Convert a CitationNode to a SearchResult for merging."""
    from research_hub.search.base import SearchResult

    return SearchResult(
        title=node.title,
        doi=(node.doi or "").lower(),
        arxiv_id="",
        abstract="",
        year=node.year,
        authors=node.authors,
        venue=node.venue,
        url=node.url,
        citation_count=node.citation_count,
        pdf_url=node.pdf_url,
        source="citation-graph",
        confidence=0.5,
        found_in=["citation-graph"],
    )


def _expand_citations(
    seed_dois: list[str],
    *,
    hops: int = 1,
    per_seed_limit: int = 30,
):
    """Run references + citations lookup for each seed DOI."""
    from research_hub.citation_graph import CitationGraphClient

    if not seed_dois or hops <= 0:
        return []

    client = CitationGraphClient()
    seen: set[str] = set()
    expanded = []
    for seed in seed_dois:
        try:
            refs = client.get_references(seed, limit=per_seed_limit)
        except Exception as exc:
            logger.warning("citation expansion (references) failed for %s: %s", seed, exc)
            refs = []
        try:
            cits = client.get_citations(seed, limit=per_seed_limit)
        except Exception as exc:
            logger.warning("citation expansion (citations) failed for %s: %s", seed, exc)
            cits = []
        for node in refs + cits:
            doi_key = _normalize_doi(node.doi or "")
            if not doi_key or doi_key in seen:
                continue
            seen.add(doi_key)
            expanded.append(_citation_node_to_search_result(node))
    return expanded


def _pick_auto_seeds(candidates: list[dict], count: int = 3) -> list[str]:
    """Pick the top-N candidates by confidence then citations."""
    ranked = sorted(
        [candidate for candidate in candidates if candidate.get("doi")],
        key=lambda candidate: (
            candidate.get("confidence", 0.5),
            candidate.get("citation_count", 0),
        ),
        reverse=True,
    )
    return [str(candidate["doi"]) for candidate in ranked[:count]]


def _load_cluster_doi_set(cfg, cluster_slug: str) -> set[str]:
    """Read every paper note in raw/<cluster>/*.md and return normalized DOIs."""
    cluster_dir = Path(cfg.raw) / cluster_slug
    if not cluster_dir.exists():
        return set()

    dois: set[str] = set()
    for note_path in cluster_dir.glob("*.md"):
        if note_path.name in {"00_overview.md", "index.md"}:
            continue
        text = note_path.read_text(encoding="utf-8", errors="ignore")
        if not text.startswith("---"):
            continue
        in_frontmatter = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == "---":
                if in_frontmatter:
                    break
                in_frontmatter = True
                continue
            if not in_frontmatter:
                continue
            match = re.match(r'doi:\s*"?([^"\s]+)"?\s*$', stripped, re.IGNORECASE)
            if match:
                normalized = _normalize_doi(match.group(1))
                if normalized:
                    dois.add(normalized)
                break
    return dois


def _resolve_seed_dois(
    seed_dois: list[str],
    existing_candidates: list[dict],
    *,
    backends: tuple[str, ...] | None = None,
) -> list[dict]:
    """Ensure each user-supplied DOI is present in the candidate set."""
    from research_hub.search import enrich_candidates

    doi_to_index = {
        _normalize_doi(candidate.get("doi", "") or ""): index
        for index, candidate in enumerate(existing_candidates)
        if candidate.get("doi")
    }

    to_fetch: list[str] = []
    for doi in seed_dois:
        normalized = _normalize_doi(doi)
        if not normalized or not normalized.startswith("10."):
            continue
        if normalized in doi_to_index:
            candidate = existing_candidates[doi_to_index[normalized]]
            meta = _ensure_discover_meta(candidate)
            meta["is_seed"] = True
            _append_unique(meta["source_tags"], "seed")
            candidate["confidence"] = min(1.0, float(candidate.get("confidence", 0.5)) + 0.25)
        else:
            to_fetch.append(doi)

    if to_fetch:
        resolved = enrich_candidates(
            to_fetch,
            backends=backends or ("openalex", "crossref", "arxiv"),
        )
        for doi, result in zip(to_fetch, resolved):
            if result is None:
                continue
            entry = asdict(result)
            entry["confidence"] = 1.0
            entry["_discover_meta"] = {
                "matched_variations": [],
                "source_tags": ["seed"],
                "is_seed": True,
            }
            existing_candidates.append(entry)

    return existing_candidates


def _normalize_doi(value: str) -> str:
    from research_hub.utils.doi import normalize_doi

    return normalize_doi(value or "")


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _ensure_discover_meta(candidate: dict) -> dict:
    meta = candidate.setdefault("_discover_meta", {})
    matched = meta.get("matched_variations")
    if not isinstance(matched, list):
        meta["matched_variations"] = []
    source_tags = meta.get("source_tags")
    if not isinstance(source_tags, list):
        meta["source_tags"] = []
    if "is_seed" not in meta:
        meta["is_seed"] = False
    return meta


def _merge_search_dict_candidates(candidates: list[dict]) -> list[dict]:
    """Deduplicate candidate dicts by DOI/arXiv/title."""
    from research_hub.search.base import SearchResult

    merged: dict[str, dict] = {}
    order: list[str] = []
    for candidate in candidates:
        result = SearchResult(
            title=str(candidate.get("title", "") or ""),
            doi=str(candidate.get("doi", "") or ""),
            arxiv_id=str(candidate.get("arxiv_id", "") or ""),
            abstract=str(candidate.get("abstract", "") or ""),
            year=candidate.get("year"),
            authors=list(candidate.get("authors") or []),
            venue=str(candidate.get("venue", "") or ""),
            url=str(candidate.get("url", "") or ""),
            citation_count=int(candidate.get("citation_count", 0) or 0),
            pdf_url=str(candidate.get("pdf_url", "") or ""),
            source=str(candidate.get("source", "") or ""),
            confidence=float(candidate.get("confidence", 0.5) or 0.5),
            found_in=list(candidate.get("found_in") or []),
            doc_type=str(candidate.get("doc_type", "") or ""),
        )
        key = result.dedup_key
        meta = _ensure_discover_meta(candidate)
        if key not in merged:
            entry = dict(candidate)
            entry["_discover_meta"] = {
                "matched_variations": list(meta["matched_variations"]),
                "source_tags": list(meta["source_tags"]),
                "is_seed": bool(meta["is_seed"]),
            }
            merged[key] = entry
            order.append(key)
            continue

        base = merged[key]
        if not base.get("abstract") and candidate.get("abstract"):
            base["abstract"] = candidate.get("abstract")
        if not base.get("doi") and candidate.get("doi"):
            base["doi"] = candidate.get("doi")
        if not base.get("arxiv_id") and candidate.get("arxiv_id"):
            base["arxiv_id"] = candidate.get("arxiv_id")
        if not base.get("pdf_url") and candidate.get("pdf_url"):
            base["pdf_url"] = candidate.get("pdf_url")
        if not base.get("venue") and candidate.get("venue"):
            base["venue"] = candidate.get("venue")
        if not base.get("doc_type") and candidate.get("doc_type"):
            base["doc_type"] = candidate.get("doc_type")
        if int(base.get("citation_count", 0) or 0) < int(candidate.get("citation_count", 0) or 0):
            base["citation_count"] = int(candidate.get("citation_count", 0) or 0)
        base["confidence"] = max(
            float(base.get("confidence", 0.5) or 0.5),
            float(candidate.get("confidence", 0.5) or 0.5),
        )
        merged_meta = _ensure_discover_meta(base)
        for variation in meta["matched_variations"]:
            _append_unique(merged_meta["matched_variations"], variation)
        for tag in meta["source_tags"]:
            _append_unique(merged_meta["source_tags"], tag)
        merged_meta["is_seed"] = bool(merged_meta["is_seed"] or meta["is_seed"])
    return [merged[key] for key in order]


def _load_variations_file(path: str | Path | None) -> list[QueryVariation]:
    if not path:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    payload = data.get("variations", data)
    if not isinstance(payload, list):
        raise ValueError("variation payload must be a list or an object with 'variations'")
    return _coerce_variations(payload)


def discover_new(
    cfg,
    cluster_slug: str,
    query: str,
    *,
    year_from: int | None = None,
    year_to: int | None = None,
    min_citations: int = 0,
    backends: tuple[str, ...] | None = None,
    field: str | None = None,
    region: str | None = None,
    limit: int = _DEFAULT_LIMIT,
    definition: str | None = None,
    exclude_types: tuple[str, ...] = (),
    exclude_terms: tuple[str, ...] = (),
    min_confidence: float = 0.0,
    rank_by: str = "smart",
    from_variants: str | Path | None = None,
    expand_auto: bool = False,
    expand_from: tuple[str, ...] = (),
    expand_hops: int = 1,
    seed_dois: tuple[str, ...] = (),
    include_existing: bool = False,
) -> tuple[DiscoverState, str]:
    """Run search, stash candidates, and build a fit-check prompt."""
    from research_hub.fit_check import emit_prompt
    from research_hub.search import search_papers
    from research_hub.search.fallback import (
        DEFAULT_BACKENDS,
        resolve_backends_for_field,
        resolve_backends_for_region,
    )

    dest = stash_dir(cfg, cluster_slug)
    dest.mkdir(parents=True, exist_ok=True)

    if region:
        resolved_backends = resolve_backends_for_region(region)
    elif field:
        resolved_backends = resolve_backends_for_field(field)
    elif backends:
        resolved_backends = backends
    else:
        resolved_backends = DEFAULT_BACKENDS

    per_backend_limit = max(
        limit * _DEFAULT_PER_BACKEND_LIMIT_FACTOR,
        _DEFAULT_PER_BACKEND_LIMIT_FLOOR,
    )
    results = search_papers(
        query,
        limit=limit,
        year_from=year_from,
        year_to=year_to,
        min_citations=min_citations,
        backends=resolved_backends,
        exclude_types=exclude_types,
        exclude_terms=exclude_terms,
        min_confidence=min_confidence,
        rank_by=rank_by,
        per_backend_limit=per_backend_limit,
    )
    candidates = [asdict(result) for result in results]

    for candidate in candidates:
        candidate["_discover_meta"] = {
            "matched_variations": [],
            "source_tags": [candidate.get("source")] if candidate.get("source") else [],
            "is_seed": False,
        }

    variations = _load_variations_file(from_variants)
    if variations:
        candidates.extend(
            apply_variations(
                cfg,
                cluster_slug,
                variations,
                year_from=year_from,
                year_to=year_to,
                min_citations=min_citations,
                backends=resolved_backends,
                limit=limit,
                exclude_types=exclude_types,
                exclude_terms=exclude_terms,
                min_confidence=min_confidence,
                rank_by=rank_by,
            )
        )
        candidates = _merge_search_dict_candidates(candidates)

    expanded_from: list[str] = []
    if expand_auto or expand_from:
        expanded_from = (
            _pick_auto_seeds(candidates, count=3)
            if expand_auto
            else [doi for doi in (_normalize_doi(item) for item in expand_from) if doi]
        )
        expanded_results = _expand_citations(expanded_from, hops=expand_hops)
        existing_dois = {
            _normalize_doi(candidate.get("doi", ""))
            for candidate in candidates
            if candidate.get("doi")
        }
        for result in expanded_results:
            normalized = _normalize_doi(result.doi)
            if normalized and normalized in existing_dois:
                for candidate in candidates:
                    if _normalize_doi(candidate.get("doi", "")) == normalized:
                        meta = _ensure_discover_meta(candidate)
                        _append_unique(meta["source_tags"], "citation-graph")
                        candidate["confidence"] = min(
                            1.0,
                            float(candidate.get("confidence", 0.5)) + 0.1,
                        )
                        break
                continue
            entry = asdict(result)
            entry["_discover_meta"] = {
                "matched_variations": [],
                "source_tags": ["citation-graph"],
                "is_seed": False,
            }
            candidates.append(entry)
            if normalized:
                existing_dois.add(normalized)

    normalized_seed_dois = tuple(
        doi for doi in (_normalize_doi(item) for item in seed_dois) if doi
    )
    if normalized_seed_dois:
        candidates = _resolve_seed_dois(
            list(normalized_seed_dois),
            candidates,
            backends=resolved_backends,
        )
        candidates = _merge_search_dict_candidates(candidates)

    deduped_count = 0
    if not include_existing:
        existing = _load_cluster_doi_set(cfg, cluster_slug)
        before = len(candidates)
        candidates = [
            candidate
            for candidate in candidates
            if not (
                candidate.get("doi")
                and _normalize_doi(candidate["doi"]) in existing
            )
        ]
        deduped_count = before - len(candidates)

    candidates = _merge_search_dict_candidates(candidates)

    (dest / CANDIDATES_FILENAME).write_text(
        json.dumps(candidates, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    prompt = emit_prompt(
        cluster_slug,
        candidates,
        definition=definition,
        cfg=cfg,
    )
    (dest / PROMPT_FILENAME).write_text(prompt, encoding="utf-8")

    state = DiscoverState(
        cluster_slug=cluster_slug,
        stage="scored_pending",
        query=query,
        definition=definition or "",
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        candidate_count=len(candidates),
        variations_used=[variation.query for variation in variations],
        expanded_from=expanded_from,
        seed_dois=list(normalized_seed_dois),
        deduped_against_cluster=deduped_count,
    )
    (dest / STATE_FILENAME).write_text(state.to_json(), encoding="utf-8")
    return state, prompt


def discover_continue(
    cfg,
    cluster_slug: str,
    scored: list[dict] | dict,
    *,
    threshold: int | None = None,
    auto_threshold: bool = False,
    out_path: Path | None = None,
) -> tuple[DiscoverState, Path]:
    """Apply AI scores, emit papers_input.json, and update discover state."""
    from research_hub.fit_check import apply_scores, compute_auto_threshold

    dest = stash_dir(cfg, cluster_slug)
    state_path = dest / STATE_FILENAME
    if not state_path.exists():
        raise FileNotFoundError(
            f"no discover state for cluster {cluster_slug}; run `discover new` first"
        )
    state = DiscoverState.from_json(state_path.read_text(encoding="utf-8"))
    if state.stage == "done":
        logger.info("discover state already done; re-applying with new scores")

    candidates_path = dest / CANDIDATES_FILENAME
    if not candidates_path.exists():
        raise FileNotFoundError(f"missing candidates at {candidates_path}")
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))

    resolved_threshold = threshold if threshold is not None else 3
    if auto_threshold and threshold is None:
        score_values = _score_values(scored)
        median = _median_int(score_values)
        resolved_threshold = compute_auto_threshold(score_values)
        logger.info(
            "auto threshold: median=%s, suggested=%d",
            "n/a" if median is None else median,
            resolved_threshold,
        )

    report = apply_scores(
        cluster_slug,
        candidates,
        scored,
        threshold=resolved_threshold,
        cfg=cfg,
    )

    accepted_keys = {
        ((item.doi or "").strip().lower(), (item.title or "").strip().lower())
        for item in report.accepted
    }
    accepted_candidates = [
        candidate
        for candidate in candidates
        if (
            (candidate.get("doi") or "").strip().lower(),
            (candidate.get("title") or "").strip().lower(),
        )
        in accepted_keys
    ]
    papers_input = _to_papers_input(accepted_candidates, cluster_slug)

    target = out_path if out_path is not None else (dest / PAPERS_INPUT_FILENAME)
    target.write_text(json.dumps(papers_input, indent=2, ensure_ascii=False), encoding="utf-8")
    (dest / ACCEPTED_FILENAME).write_text(
        json.dumps([item.to_dict() for item in report.accepted], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    state.stage = "done"
    state.accepted_count = len(report.accepted)
    state.rejected_count = len(report.rejected)
    state.threshold = resolved_threshold
    state.auto_threshold = auto_threshold
    (dest / STATE_FILENAME).write_text(state.to_json(), encoding="utf-8")
    return state, target


def discover_status(cfg, cluster_slug: str) -> DiscoverState | None:
    """Return discover state for a cluster, if present."""
    state_path = stash_dir(cfg, cluster_slug) / STATE_FILENAME
    if not state_path.exists():
        return None
    return DiscoverState.from_json(state_path.read_text(encoding="utf-8"))


def discover_clean(cfg, cluster_slug: str) -> bool:
    """Remove discover state for a cluster."""
    dest = stash_dir(cfg, cluster_slug)
    if not dest.exists():
        return False
    shutil.rmtree(dest)
    return True


def _authors_to_creators(authors: list[str] | str) -> list[dict]:
    """Convert a name list or comma-separated string into Zotero creator dicts."""
    if isinstance(authors, str):
        names = [author.strip() for author in authors.split(",") if author.strip()]
    else:
        names = [author for author in (authors or []) if author]

    creators: list[dict] = []
    for name in names:
        parts = name.split()
        if len(parts) >= 2:
            creators.append(
                {
                    "creatorType": "author",
                    "firstName": " ".join(parts[:-1]),
                    "lastName": parts[-1],
                }
            )
        else:
            creators.append(
                {
                    "creatorType": "author",
                    "firstName": "",
                    "lastName": name or "Unknown",
                }
            )
    return creators


def _to_papers_input(candidates: list[dict], cluster_slug: str | None) -> list[dict]:
    """Convert search candidates to flat papers_input.json shape."""
    from research_hub.clusters import slugify

    papers: list[dict] = []
    for candidate in candidates:
        authors_raw = candidate.get("authors") or []
        names = (
            [author.strip() for author in authors_raw.split(",") if author.strip()]
            if isinstance(authors_raw, str)
            else [author for author in authors_raw if author]
        )
        title = candidate.get("title") or ""
        first_author = names[0].split()[-1].lower() if names else "unknown"
        slug = f"{first_author}{candidate.get('year') or ''}-{slugify(title)[:60]}"
        papers.append(
            {
                "title": title,
                "doi": candidate.get("doi") or "",
                "authors": _authors_to_creators(names),
                "year": candidate.get("year") or 0,
                "abstract": candidate.get("abstract") or "(no abstract)",
                "journal": candidate.get("venue") or "preprint",
                "slug": slug,
                "sub_category": cluster_slug or "",
                "summary": f"[TODO] {title}"[:200],
                "key_findings": ["[TODO: fill from abstract]"],
                "methodology": "[TODO: fill from abstract]",
                "relevance": "[TODO: fill relevance to cluster]",
            }
        )
    return papers

"""Wrapper around search + fit-check for end-to-end paper discovery."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict, dataclass
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

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "DiscoverState":
        return cls(**json.loads(text))


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
    limit: int = 25,
    definition: str | None = None,
    exclude_types: tuple[str, ...] = (),
    exclude_terms: tuple[str, ...] = (),
    min_confidence: float = 0.0,
    rank_by: str = "smart",
) -> tuple[DiscoverState, str]:
    """Run search, stash candidates, and build a fit-check prompt."""
    from research_hub.fit_check import emit_prompt
    from research_hub.search import search_papers
    from research_hub.search.fallback import DEFAULT_BACKENDS, resolve_backends_for_field

    dest = stash_dir(cfg, cluster_slug)
    dest.mkdir(parents=True, exist_ok=True)

    if field:
        resolved_backends = resolve_backends_for_field(field)
    elif backends:
        resolved_backends = backends
    else:
        resolved_backends = DEFAULT_BACKENDS

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
    )
    candidates = [asdict(result) for result in results]
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

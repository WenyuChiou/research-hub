"""Crossref-powered DOI backfill helpers."""

from __future__ import annotations

import json
import time
from difflib import SequenceMatcher
from pathlib import Path

from research_hub.paper import _find_note_path, _parse_frontmatter, _rewrite_paper_frontmatter
from research_hub.search.crossref import CrossrefBackend


def lookup_doi_for_slug(
    cfg,
    slug: str,
    *,
    crossref: CrossrefBackend | None = None,
    prompt_for_confirmation: bool = True,
) -> dict[str, object]:
    note_path = _find_note_path(cfg, slug)
    if note_path is None:
        raise FileNotFoundError(f"paper not found: {slug}")

    meta = _parse_frontmatter(note_path.read_text(encoding="utf-8"))
    if str(meta.get("doi", "") or "").strip():
        return {"slug": slug, "status": "skipped", "reason": "already has DOI", "path": str(note_path)}

    title = str(meta.get("title", "") or note_path.stem).strip()
    year = str(meta.get("year", "") or "").strip()
    client = crossref or CrossrefBackend(delay_seconds=1.0)
    results = client.search(title, limit=5)
    best = _pick_best_match(results, title=title, year=year)
    if best is None:
        return {"slug": slug, "status": "no-match", "reason": "no Crossref match above threshold", "path": str(note_path)}

    if prompt_for_confirmation:
        answer = input(
            f'Add DOI {best.doi} to "{title}"? [y/N]: '
        ).strip().lower()
        if answer not in {"y", "yes"}:
            return {"slug": slug, "status": "skipped", "reason": "user declined", "path": str(note_path)}

    _rewrite_paper_frontmatter(note_path, {"doi": best.doi})
    return {
        "slug": slug,
        "status": "updated",
        "doi": best.doi,
        "title_similarity": round(_title_similarity(title, best.title), 3),
        "path": str(note_path),
    }


def batch_lookup_missing_dois(cfg, cluster_slug: str) -> dict[str, object]:
    cluster_dir = Path(cfg.raw) / cluster_slug
    if not cluster_dir.exists():
        raise FileNotFoundError(f"cluster not found: {cluster_slug}")

    client = CrossrefBackend(delay_seconds=1.0)
    results: list[dict[str, object]] = []
    notes = sorted(cluster_dir.glob("*.md"))
    for index, note_path in enumerate(notes):
        meta = _parse_frontmatter(note_path.read_text(encoding="utf-8"))
        if str(meta.get("doi", "") or "").strip():
            results.append({"slug": note_path.stem, "status": "skipped", "reason": "already has DOI"})
            continue
        if index > 0:
            time.sleep(1)
        results.append(
            lookup_doi_for_slug(
                cfg,
                note_path.stem,
                crossref=client,
                prompt_for_confirmation=False,
            )
        )

    log_path = cluster_dir / "lookup_log.json"
    log_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"cluster": cluster_slug, "results": results, "log_path": str(log_path)}


def _pick_best_match(results: list, *, title: str, year: str) -> object | None:
    best = None
    best_score = 0.0
    for result in results:
        score = _title_similarity(title, result.title)
        if year and str(result.year or "") == year:
            score += 0.05
        if score > best_score:
            best = result
            best_score = score
    if best is None or best_score < 0.85:
        return None
    return best


def _title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize_title(left), _normalize_title(right)).ratio()


def _normalize_title(text: str) -> str:
    return " ".join((text or "").lower().split())

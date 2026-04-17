"""Task-level workflow wrappers (v0.33, Codex Phase 3).

5 high-level MCP tools that wrap the 64 low-level tools. Every function imports
and calls existing internals; zero logic duplication. Casual Claude Desktop
users get 2-3× faster workflows (1 call instead of 3-4). All 64 low-level
tools remain registered for power users.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Source-kind detection regexes for collect_to_cluster
_DOI_RE = re.compile(r"^10\.\d{4,}/\S+$")
_ARXIV_RE = re.compile(r"^(arxiv:|arXiv:)?\d{4}\.\d{4,5}(v\d+)?$", re.IGNORECASE)


# Common research acronyms expanded before fuzzy matching. Without this,
# "what's the SOTA" fails to match crystal "sota-and-open-problems" because
# token-based scorers don't know SOTA = state of the art.
_QUESTION_ACRONYMS: dict[str, str] = {
    r"\bsota\b": "state of the art",
    r"\bnlp\b": "natural language processing",
    r"\bllm\b": "large language model",
    r"\brl\b": "reinforcement learning",
    r"\bnn\b": "neural network",
    r"\bml\b": "machine learning",
    r"\brag\b": "retrieval augmented generation",
    r"\bbenchmark(s)?\b": "benchmark evaluation standard",
    r"\bopen problem(s)?\b": "unsolved problem state of the art",
}


def _expand_acronyms(text: str) -> str:
    """Expand common research acronyms for better fuzzy matching."""
    out = text
    for pattern, expansion in _QUESTION_ACRONYMS.items():
        out = re.sub(pattern, expansion, out, flags=re.IGNORECASE)
    return out


def _err(message: str) -> dict:
    return {"ok": False, "error": message}


# ---------------------------------------------------------------------------
# W1: ask_cluster
# ---------------------------------------------------------------------------

def ask_cluster(
    cfg,
    cluster_slug: str,
    *,
    question: str | None = None,
    detail: str = "gist",
) -> dict:
    """Answer a natural-language question about a cluster.

    Tries pre-computed crystals first; falls back to topic digest if no
    crystal matches (via rapidfuzz on the question text).
    """
    from research_hub.security import validate_slug

    try:
        cluster_slug = validate_slug(cluster_slug, field="cluster_slug")
    except Exception as exc:
        return _err(f"invalid cluster_slug: {exc}")

    if detail not in {"tldr", "gist", "full"}:
        return _err(f"detail={detail!r} invalid. Use tldr / gist / full.")

    from research_hub.crystal import list_crystals, read_crystal, check_staleness

    try:
        crystals = list_crystals(cfg, cluster_slug)
    except Exception as exc:
        crystals = []
        list_error = str(exc)
    else:
        list_error = ""

    # Precompute staleness map once if we have crystals
    stale_map: dict[str, bool] = {}
    if crystals:
        try:
            staleness = check_staleness(cfg, cluster_slug)
            stale_map = {
                slug: bool(getattr(entry, "stale", False))
                for slug, entry in staleness.items()
            }
        except Exception:
            stale_map = {}

    if question and crystals:
        try:
            from rapidfuzz import process, fuzz
        except ImportError:
            process = None  # type: ignore[assignment]
            fuzz = None  # type: ignore[assignment]

        if process is not None and fuzz is not None:
            # Score the user's question against BOTH the crystal question text
            # AND the crystal slug (slug-as-prose is often a better match when
            # the user rephrases, e.g. "what is this field about" vs slug
            # "what-is-this-field" tokenises to the same words).
            # token_set_ratio is the reliable scorer here; we tried adding
            # WRatio but it promotes false positives (e.g. "Why-now" scoring
            # 85 for "what is this field about" because of "What" in the
            # question text).
            best_slug: str | None = None
            best_score: float = 0.0
            expanded_q = _expand_acronyms(question)
            for crystal in crystals:
                slug_text = crystal.question_slug.replace("-", " ")
                expanded_target_q = _expand_acronyms(crystal.question)
                expanded_target_s = _expand_acronyms(slug_text)
                score_q = fuzz.token_set_ratio(expanded_q, expanded_target_q)
                score_s = fuzz.token_set_ratio(expanded_q, expanded_target_s)
                score = max(score_q, score_s)
                if score > best_score:
                    best_score = score
                    best_slug = crystal.question_slug
            # Accept if best score >= 55 (empirically tuned on canonical
            # questions: matching question scores 60-75, unrelated <40).
            if best_slug is not None and best_score >= 55:
                matched_slug = best_slug
                score = int(best_score)
                crystal = next(
                    (c for c in crystals if c.question_slug == matched_slug),
                    None,
                )
                if crystal is not None:
                    body = {
                        "tldr": crystal.tldr,
                        "gist": crystal.gist,
                        "full": crystal.full,
                    }[detail]
                    stale = stale_map.get(matched_slug, False)
                    return {
                        "ok": True,
                        "source": "crystal",
                        "cluster": cluster_slug,
                        "crystal_slug": matched_slug,
                        "question_matched": crystal.question,
                        "match_score": int(score),
                        "answer": body,
                        "evidence": list(getattr(crystal, "based_on_papers", []) or []),
                        "confidence": getattr(crystal, "confidence", "medium"),
                        "stale": stale,
                        "suggest_regenerate": stale,
                        "detail": detail,
                    }

    # Fallback: topic digest
    from research_hub.topic import get_topic_digest, read_overview

    try:
        digest = get_topic_digest(cfg, cluster_slug)
    except Exception as exc:
        if list_error:
            return _err(
                f"no crystal match and digest failed: {exc}; crystal list error: {list_error}"
            )
        return _err(f"no crystal match and digest failed: {exc}")

    overview = ""
    try:
        overview_text = read_overview(cfg, cluster_slug)
        if overview_text:
            overview = overview_text[:800]
    except Exception:
        pass

    paper_slugs = [p.slug for p in getattr(digest, "papers", [])[:10]]

    return {
        "ok": True,
        "source": "digest",
        "cluster": cluster_slug,
        "answer": overview or f"(no overview; cluster has {len(paper_slugs)} papers)",
        "paper_count": getattr(digest, "paper_count", len(paper_slugs)),
        "evidence": paper_slugs,
        "confidence": "low",
        "stale": False,
        "suggest_regenerate": len(crystals) == 0,
        "hint": (
            f"Run `research-hub crystal emit --cluster {cluster_slug}` to "
            "pre-compute canonical answers for faster future queries."
            if len(crystals) == 0
            else ""
        ),
    }


# ---------------------------------------------------------------------------
# W2: brief_cluster
# ---------------------------------------------------------------------------

def brief_cluster(
    cfg,
    cluster_slug: str,
    *,
    force_regenerate: bool = False,
) -> dict:
    """Full NotebookLM round-trip: bundle → upload → generate → download → read.

    Degrades gracefully at each step. Returns partial results if any stage
    fails (e.g., Playwright not installed).
    """
    from research_hub.security import validate_slug

    try:
        cluster_slug = validate_slug(cluster_slug, field="cluster_slug")
    except Exception as exc:
        return _err(f"invalid cluster_slug: {exc}")

    from research_hub.clusters import ClusterRegistry
    registry = ClusterRegistry(cfg.research_hub_dir / "clusters.yaml")
    registry.load()
    cluster = registry.get(cluster_slug)
    if cluster is None:
        return _err(f"cluster not found: {cluster_slug}")

    out: dict[str, Any] = {
        "ok": True,
        "cluster": cluster_slug,
        "steps_completed": [],
        "warnings": [],
    }

    # Step 1: Bundle (no Playwright needed)
    try:
        from research_hub.notebooklm.bundle import bundle_cluster
        bundle_result = bundle_cluster(cluster, cfg)
        out["bundle_dir"] = str(getattr(bundle_result, "bundle_dir", "") or "")
        out["source_count"] = getattr(bundle_result, "source_count", 0)
        out["steps_completed"].append("bundle")
    except Exception as exc:
        return _err(f"bundle failed: {exc}")

    # Steps 2 + 3: Upload + generate (need Playwright)
    need_regen = force_regenerate or not getattr(cluster, "notebooklm_notebook_id", None)
    if need_regen:
        try:
            from research_hub.notebooklm.upload import upload_cluster, generate_artifact
            upload_cluster(cluster, cfg)
            out["steps_completed"].append("upload")
            generate_artifact(cluster, cfg)
            out["steps_completed"].append("generate")
        except ImportError:
            out["ok"] = False
            out["error"] = (
                "playwright not installed. Install: "
                "pip install 'research-hub-pipeline[playwright]' + playwright install chromium"
            )
            return out
        except Exception as exc:
            out["warnings"].append(f"upload/generate failed: {exc}")

    # Step 4: Download
    try:
        from research_hub.notebooklm.upload import download_briefing_for_cluster
        download_result = download_briefing_for_cluster(cluster, cfg)
        artifact = getattr(download_result, "artifact_path", None)
        if artifact:
            out["brief_path"] = str(artifact)
            out["steps_completed"].append("download")
    except Exception as exc:
        out["warnings"].append(f"download failed: {exc}")

    # Step 5: Read preview
    try:
        from research_hub.mcp_server import read_briefing
        fn = getattr(read_briefing, "fn", read_briefing)
        brief_text = fn(cluster_slug, max_chars=500)
        if isinstance(brief_text, dict):
            brief_text = brief_text.get("text", "") or brief_text.get("briefing", "")
        out["brief_preview"] = brief_text
    except Exception:
        pass

    return out


# ---------------------------------------------------------------------------
# W3: sync_cluster
# ---------------------------------------------------------------------------

def sync_cluster(cfg, cluster_slug: str) -> dict:
    """Aggregate maintenance view: what needs attention for this cluster."""
    from research_hub.security import validate_slug

    try:
        cluster_slug = validate_slug(cluster_slug, field="cluster_slug")
    except Exception as exc:
        return _err(f"invalid cluster_slug: {exc}")

    out: dict[str, Any] = {
        "ok": True,
        "cluster": cluster_slug,
        "recommendations": [],
    }

    # Crystal staleness
    try:
        from research_hub.crystal import list_crystals, check_staleness
        crystals = list_crystals(cfg, cluster_slug)
        out["crystal_count"] = len(crystals)
        if crystals:
            staleness = check_staleness(cfg, cluster_slug)
            stale_slugs = [
                slug for slug, entry in staleness.items()
                if getattr(entry, "stale", False)
            ]
            out["stale_crystals"] = stale_slugs
            if stale_slugs:
                out["recommendations"].append(
                    f"research-hub crystal emit --cluster {cluster_slug} > prompt.md  "
                    f"# regenerate {len(stale_slugs)} stale crystal(s)"
                )
        else:
            out["stale_crystals"] = []
            out["recommendations"].append(
                f"research-hub crystal emit --cluster {cluster_slug} > prompt.md  "
                "# no crystals yet; generate to enable fast queries"
            )
    except Exception as exc:
        out["crystal_error"] = str(exc)

    # Scope drift
    try:
        from research_hub.fit_check import drift_check
        drift = drift_check(cfg, cluster_slug)
        out["drift_score"] = drift.get("score", drift.get("drift_score", 0)) if isinstance(drift, dict) else 0
        if isinstance(drift, dict) and out.get("drift_score", 0) >= 3:
            out["recommendations"].append(
                f"research-hub fit-check drift --cluster {cluster_slug}  "
                "# scope drift detected; review flagged papers"
            )
    except Exception as exc:
        out["drift_error"] = str(exc)

    # Vault health
    try:
        from research_hub.doctor import run_doctor as _doctor
        results = _doctor()
        vault_issues = []
        for check in results or []:
            status = getattr(check, "status", "")
            message = getattr(check, "message", "") or getattr(check, "name", "")
            if status and status.lower() in {"fail", "error", "warn"}:
                vault_issues.append(f"{status.upper()}: {message}")
        out["vault_issues"] = vault_issues
        if vault_issues:
            out["recommendations"].append(
                "research-hub doctor  # vault has issues; run doctor for details"
            )
    except Exception as exc:
        out["doctor_error"] = str(exc)

    return out


# ---------------------------------------------------------------------------
# W4: compose_brief
# ---------------------------------------------------------------------------

def compose_brief(
    cfg,
    cluster_slug: str,
    *,
    outline: str | None = None,
    max_quotes: int = 10,
) -> dict:
    """Assemble a markdown draft from cluster quotes + overview + crystal TLDRs."""
    from research_hub.security import validate_slug

    try:
        cluster_slug = validate_slug(cluster_slug, field="cluster_slug")
    except Exception as exc:
        return _err(f"invalid cluster_slug: {exc}")

    if max_quotes < 0:
        return _err("max_quotes must be >= 0")

    # Build default outline from overview + crystal TLDRs if not provided
    resolved_outline = (outline or "").strip()
    if not resolved_outline:
        lines: list[str] = []
        try:
            from research_hub.topic import read_overview
            overview = read_overview(cfg, cluster_slug)
            if overview:
                lines.append("## Background")
                lines.append(overview[:500].strip())
                lines.append("")
        except Exception:
            pass
        try:
            from research_hub.crystal import list_crystals
            crystals = list_crystals(cfg, cluster_slug)
            if crystals:
                lines.append("## Key questions")
                for crystal in crystals:
                    tldr = (crystal.tldr or "").strip()
                    if tldr:
                        lines.append(f"- **{crystal.question}** — {tldr}")
                lines.append("")
        except Exception:
            pass
        if lines:
            resolved_outline = "\n".join(lines)

    if not resolved_outline:
        resolved_outline = f"# Draft: {cluster_slug}\n\n(No overview or crystals found; supply an outline explicitly.)"

    # Delegate to existing compose_draft if it exists
    try:
        from research_hub.operations import compose_draft
    except ImportError:
        try:
            from research_hub.compose import compose_draft  # alternate module name
        except ImportError:
            return _err(
                "compose_draft function not found in research_hub.operations or "
                "research_hub.compose. Cannot assemble draft."
            )

    try:
        result = compose_draft(
            cfg,
            cluster_slug=cluster_slug,
            outline=resolved_outline,
            max_quotes=max_quotes,
        )
    except TypeError:
        # Different signature
        try:
            result = compose_draft(cluster_slug, outline=resolved_outline)
        except Exception as exc:
            return _err(f"compose_draft failed: {exc}")
    except Exception as exc:
        return _err(f"compose_draft failed: {exc}")

    return {
        "ok": True,
        "cluster": cluster_slug,
        "draft_path": str(result.get("draft_path", "")) if isinstance(result, dict) else str(result),
        "outline_used": resolved_outline,
        "max_quotes": max_quotes,
    }


# ---------------------------------------------------------------------------
# W5: collect_to_cluster
# ---------------------------------------------------------------------------

def collect_to_cluster(
    cfg,
    source: str,
    *,
    cluster_slug: str,
    skip_verify: bool = False,
    no_zotero: bool = False,
    extensions: tuple[str, ...] | None = None,
    dry_run: bool = False,
) -> dict:
    """Unified ingest. Auto-routes by source shape.

    - DOI or arXiv ID → add_paper
    - Folder path → import_folder
    - URL (http/https) → write .url file + import_folder
    """
    from research_hub.security import validate_slug, validate_identifier

    try:
        cluster_slug = validate_slug(cluster_slug, field="cluster_slug")
    except Exception as exc:
        return _err(f"invalid cluster_slug: {exc}")

    if not isinstance(source, str) or not source.strip():
        return _err("source must be a non-empty string")

    source = source.strip()

    # Folder
    if os.path.isdir(source):
        try:
            from research_hub.importer import import_folder as _import
        except ImportError as exc:
            return _err(f"importer module unavailable: {exc}")
        exts = extensions or ("pdf", "md", "txt", "docx", "url")
        try:
            report = _import(
                cfg, source, cluster_slug=cluster_slug,
                extensions=exts, dry_run=dry_run,
            )
        except Exception as exc:
            return _err(f"import_folder failed: {exc}")
        return {
            "ok": True,
            "source_kind": "folder",
            "source": source,
            "cluster": cluster_slug,
            "imported": report.imported_count,
            "skipped": report.skipped_count,
            "failed": report.failed_count,
            "note_paths": [str(e.note_path) for e in report.entries if e.note_path],
        }

    # URL
    if source.startswith(("http://", "https://")):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            slug_hint = re.sub(r"[^a-z0-9]+", "-", source.lower())[:40].strip("-") or "url"
            url_file = Path(td) / f"{slug_hint}.url"
            url_file.write_text(source, encoding="utf-8")
            try:
                from research_hub.importer import import_folder as _import
                report = _import(
                    cfg, td, cluster_slug=cluster_slug,
                    extensions=("url",), dry_run=dry_run,
                )
            except Exception as exc:
                return _err(f"URL import failed: {exc}")
            return {
                "ok": True,
                "source_kind": "url",
                "source": source,
                "cluster": cluster_slug,
                "imported": report.imported_count,
                "failed": report.failed_count,
                "note_paths": [str(e.note_path) for e in report.entries if e.note_path],
            }

    # DOI or arXiv ID (or other identifier)
    is_doi = bool(_DOI_RE.match(source))
    is_arxiv = bool(_ARXIV_RE.match(source)) or source.lower().startswith("arxiv:")
    looks_like_identifier = is_doi or is_arxiv or source.startswith("10.")

    if looks_like_identifier:
        try:
            identifier = validate_identifier(source, field="source")
        except Exception as exc:
            return _err(f"source looks like identifier but validation failed: {exc}")
        if dry_run:
            return {
                "ok": True,
                "source_kind": "paper",
                "source": identifier,
                "cluster": cluster_slug,
                "dry_run": True,
            }
        try:
            from research_hub.operations import add_paper as _add
            result = _add(
                identifier, cluster=cluster_slug,
                no_zotero=no_zotero, skip_verify=skip_verify,
            )
        except Exception as exc:
            return _err(f"add_paper failed: {exc}")
        ok = result == 0 or (isinstance(result, dict) and result.get("ok", True))
        return {
            "ok": bool(ok),
            "source_kind": "paper",
            "source": identifier,
            "cluster": cluster_slug,
            "imported": 1 if ok else 0,
            "raw_result": result if isinstance(result, dict) else None,
        }

    return _err(
        f"could not determine source kind for {source!r}. "
        "Accepted: DOI (10.xxxx/…), arXiv ID (NNNN.NNNNN), folder path, or http(s):// URL."
    )


__all__ = [
    "ask_cluster",
    "brief_cluster",
    "sync_cluster",
    "compose_brief",
    "collect_to_cluster",
]

"""Fail-closed authenticity gate for ingest candidates."""

from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from research_hub.dedup import normalize_doi, normalize_title
from research_hub.locks import file_lock
from research_hub.security import atomic_write_text
from research_hub.utils.doi import extract_arxiv_id

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover - rapidfuzz is a declared dependency
    from difflib import SequenceMatcher

    class _FuzzFallback:
        @staticmethod
        def token_set_ratio(left: str, right: str) -> float:
            return SequenceMatcher(None, left, right).ratio() * 100

    fuzz = _FuzzFallback()


SCHEMA_VERSION = "1.0"
DOI_RESOLVE_CACHE = "doi_resolve_cache.json"
QUARANTINE_DIR = "quarantine"
# PR-C (deep F7): a TRANSIENT identifier-resolution failure (doi.org /
# Crossref rate-limit or network blip, after PR-B's bounded retry) is
# NOT evidence the paper is fake. It is still held out of ingest
# (fail-closed — we could not verify), but recorded under this distinct
# layer so it is reported as "deferred (retryable)" rather than
# "quarantined (rejected)", and recovers on a later run / `quarantine
# restore` once the resolver is reachable. Permanent failures
# (`*_unresolved`, 404/410) keep layer "L1" — anti-fabrication unchanged.
DEFERRED_LAYER = "L1-deferred"
_KNOWN_VENUE_STRAGGLERS = {"arxiv", "open mind"}
_LLM_UNJUDGED_REASONS = {"relevance_unjudged"}

# Curated predatory DOI registrant prefix denylist.
# Sources: Cabell's Predatory Reports / Beall's List cross-checked against
# CrossRef member data (2026-05). Only prefixes whose entire registrant
# portfolio is predatory are included; single-journal exceptions are not.
_PREDATORY_DOI_PREFIXES: frozenset[str] = frozenset(
    {
        "10.55041",  # Edtech Publishers (OPC) Pvt Ltd — IJSREM, IJCOPE, IJSMT
        "10.31695",  # IJASRE (Intl Journal of Advanced Scientific Research and Engineering)
    }
)


@dataclass
class ResolveOutcome:
    ok: bool
    key: str
    resolved_via: str
    checked_at: str
    status_code: int | None = None
    reason: str = ""
    url: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResolveOutcome":
        return cls(
            ok=bool(data.get("ok", False)),
            key=str(data.get("key", "")),
            resolved_via=str(data.get("resolved_via", "")),
            checked_at=str(data.get("checked_at", "")),
            status_code=data.get("status_code"),
            reason=str(data.get("reason", "")),
            url=str(data.get("url", "")),
        )


class DoiResolveCache:
    """Small JSON cache for identifier resolution outcomes."""

    def __init__(self, results: dict[str, ResolveOutcome] | None = None) -> None:
        self.results = results or {}

    @classmethod
    def load(cls, path: Path) -> "DoiResolveCache":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        results = {
            key: ResolveOutcome.from_dict(value)
            for key, value in data.get("results", {}).items()
            if isinstance(value, dict)
        }
        return cls(results)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "results": {
                key: asdict(outcome)
                for key, outcome in sorted(self.results.items())
            },
        }
        with file_lock(path):
            atomic_write_text(
                path,
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def get(self, key: str) -> ResolveOutcome | None:
        return self.results.get(key)

    def put(self, outcome: ResolveOutcome) -> None:
        self.results[outcome.key] = outcome

    def invalidate(self, key: str) -> bool:
        return self.results.pop(key, None) is not None


def verify_authenticity(
    papers: list[dict],
    cfg,
    *,
    cluster_slug: str | None = None,
    do_fit_check: bool = False,
    fit_check_threshold: int = 3,
) -> tuple[list[dict], list[dict]]:
    """Return accepted and quarantined papers after fail-closed checks.

    The gate routes bad candidates into quarantine. It does not raise for a
    single malformed paper; only configuration/filesystem failures should stop
    the whole ingest.
    """
    cache_path = Path(cfg.research_hub_dir) / DOI_RESOLVE_CACHE
    cache = DoiResolveCache.load(cache_path)
    accepted: list[dict] = []
    quarantined: list[dict] = []
    fit_scores = _load_fit_scores(cfg, cluster_slug) if do_fit_check else {}

    for paper in papers:
        try:
            paper.setdefault("doi", "")
            paper.setdefault("arxiv_id", _arxiv_id_for(paper))

            if not _has_identifier(paper):
                quarantined.append(
                    quarantine_paper(
                        cfg,
                        paper,
                        cluster_slug=cluster_slug,
                        layer="L0",
                        reason="no_identifier",
                    )
                )
                continue

            outcome = _resolve_identifier(paper, cache, cache_path)
            if not outcome.ok:
                reason = outcome.reason or "doi_unresolved"
                # Transient (rate-limit / unreachable after retry) ->
                # deferred-retryable; permanent (404/410, no id) -> L1.
                layer = DEFERRED_LAYER if is_transient_reason(reason) else "L1"
                quarantined.append(
                    quarantine_paper(
                        cfg,
                        paper,
                        cluster_slug=cluster_slug,
                        layer=layer,
                        reason=reason,
                        details={
                            "status_code": outcome.status_code,
                            "url": outcome.url,
                            "resolved_via": outcome.resolved_via,
                        },
                    )
                )
                continue

            integrity_reason = _metadata_integrity_reason(paper)
            if integrity_reason:
                quarantined.append(
                    quarantine_paper(
                        cfg,
                        paper,
                        cluster_slug=cluster_slug,
                        layer="L3",
                        reason="metadata_invalid",
                        details={"detail": integrity_reason},
                    )
                )
                continue

            fit_score = _existing_fit_score(paper)
            if do_fit_check:
                fit = _fit_status_for_paper(paper, fit_scores, fit_check_threshold)
                fit_score = fit.get("score")
                if not fit["kept"]:
                    quarantined.append(
                        quarantine_paper(
                            cfg,
                            paper,
                            cluster_slug=cluster_slug,
                            layer="L4",
                            reason=str(fit["reason"]),
                            details={"fit_score": fit_score},
                        )
                    )
                    continue

            # L2a: predatory venue denylist — fail-closed, recoverable via quarantine
            doi_norm = normalize_doi(paper.get("doi", "") or "")
            predatory_prefixes = _PREDATORY_DOI_PREFIXES | frozenset(
                getattr(cfg, "predatory_doi_prefixes", None) or ()
            )
            # Match on the registrant boundary, not a bare string prefix:
            # "10.550410/x" must NOT match the denylisted "10.55041" (a
            # different, possibly legitimate registrant). A DOI is
            # "<prefix>/<suffix>", so require exact-prefix or prefix + "/".
            matched_prefix = next(
                (
                    pfx
                    for pfx in predatory_prefixes
                    if doi_norm == pfx or doi_norm.startswith(pfx + "/")
                ),
                None,
            )
            if matched_prefix:
                quarantined.append(
                    quarantine_paper(
                        cfg,
                        paper,
                        cluster_slug=cluster_slug,
                        layer="L2",
                        reason="predatory_venue",
                        details={"doi_prefix": matched_prefix},
                    )
                )
                continue

            # L2b: uncorroborated single-source gate — enforces already-computed signal
            corro = _corroboration_label(paper)
            if corro == "single-source":
                # Exempt legitimate single-source cases that are inherently
                # single-source by nature (fresh preprints, PMID-indexed papers):
                #   - real arXiv preprint (arxiv_id truthy)
                #   - paper has a PMID / pubmed_id
                #   - DOI registrant is a curated preprint server (bioRxiv/medRxiv = 10.1101)
                arxiv_id = _arxiv_id_for(paper)
                pmid = str(paper.get("pmid", "") or paper.get("pubmed_id", "") or "").strip()
                doi_for_preprint = normalize_doi(paper.get("doi", "") or "")
                is_preprint_exempt = (
                    bool(arxiv_id)
                    or bool(pmid)
                    # bioRxiv / medRxiv registrant — boundary match so
                    # "10.11010/x" (a different registrant) is NOT exempted.
                    or doi_for_preprint == "10.1101"
                    or doi_for_preprint.startswith("10.1101/")
                )
                if not is_preprint_exempt:
                    try:
                        min_cit = int(getattr(cfg, "min_corroboration_citations", 1))
                    except (TypeError, ValueError):
                        min_cit = 1
                    raw_cit = paper.get("citation_count")
                    try:
                        n_cit = int(raw_cit) if raw_cit is not None else 0
                    except (TypeError, ValueError):
                        n_cit = 0
                    if n_cit < min_cit:
                        quarantined.append(
                            quarantine_paper(
                                cfg,
                                paper,
                                cluster_slug=cluster_slug,
                                layer="L2",
                                reason="uncorroborated",
                                details={"corroboration": corro, "citation_count": n_cit},
                            )
                        )
                        continue

            provenance = dict(paper.get("provenance") or {})
            provenance.update(
                {
                    "resolved_via": outcome.resolved_via,
                    "corroboration": _corroboration_label(paper),
                    "backends": _backend_names(paper),
                    "doi_checked_at": outcome.checked_at,
                    "fit_score": fit_score,
                }
            )
            paper["provenance"] = provenance
            accepted.append(paper)
        except Exception as exc:
            quarantined.append(
                quarantine_paper(
                    cfg,
                    paper if isinstance(paper, dict) else {"raw": repr(paper)},
                    cluster_slug=cluster_slug,
                    layer="gate",
                    reason="authenticity_error",
                    details={"error": f"{exc.__class__.__name__}: {exc}"},
                )
            )

    return accepted, quarantined


def quarantine_paper(
    cfg,
    paper: dict,
    *,
    cluster_slug: str | None,
    layer: str,
    reason: str,
    details: dict[str, Any] | None = None,
) -> dict:
    """Persist one quarantined candidate and return the persisted payload."""
    cluster = _cluster_for_paper(paper, cluster_slug)
    slug = _slug_for_paper(paper)
    now = _utc_now_iso()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "cluster": cluster,
        "slug": slug,
        "layer": layer,
        "reason": reason,
        "date": now,
        "details": details or {},
        "raw_candidate": paper,
    }
    path = _quarantine_path(cfg, cluster, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    payload["path"] = str(path)
    return payload


def list_quarantine(cfg, cluster: str | None = None) -> list[dict]:
    base = Path(cfg.research_hub_dir) / QUARANTINE_DIR
    if not base.exists():
        return []
    roots = [base / cluster] if cluster else [path for path in base.iterdir() if path.is_dir()]
    rows: list[dict] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            rows.append(
                {
                    "cluster": str(payload.get("cluster") or root.name),
                    "slug": str(payload.get("slug") or path.stem),
                    "layer": str(payload.get("layer", "")),
                    "reason": str(payload.get("reason", "")),
                    "date": str(payload.get("date", "")),
                    "path": str(path),
                }
            )
    return sorted(rows, key=lambda row: (row["cluster"], row["slug"]))


def show_quarantine(cfg, slug: str, cluster: str | None = None) -> dict:
    matches = _find_quarantine_payloads(cfg, slug, cluster)
    if not matches:
        raise FileNotFoundError(f"no quarantined candidate found for {slug!r}")
    if len(matches) > 1:
        clusters = ", ".join(sorted(payload["cluster"] for payload, _path in matches))
        raise ValueError(f"multiple quarantined candidates named {slug!r}; pass --cluster ({clusters})")
    return matches[0][0]


def restore_quarantine(cfg, slug: str, cluster: str) -> dict:
    matches = _find_quarantine_payloads(cfg, slug, cluster)
    if not matches:
        raise FileNotFoundError(f"no quarantined candidate found for {slug!r} in {cluster!r}")
    payload, path = matches[0]
    candidate = dict(payload.get("raw_candidate") or {})
    candidate.setdefault("sub_category", cluster)
    _append_to_papers_input(Path(cfg.root) / "papers_input.json", candidate)
    _invalidate_candidate_cache(cfg, candidate)
    path.unlink()
    return {
        "cluster": cluster,
        "slug": slug,
        "papers_input": str(Path(cfg.root) / "papers_input.json"),
        "removed_quarantine_path": str(path),
    }


# F7: resolver HEAD failures are only fabrication evidence when the
# registry gives a definitive non-registration answer (HTTP 404/410).
# Anti-bot/access/rate-limit failures (401/403/406/418/429/451/5xx) and
# network errors are deferred as ``*_check_unavailable``. Empirically
# verified against doi.org / Cloudflare blocks on 2026-05-18.
_DOI_RESOLVE_UA = "research-hub (+https://github.com/WenyuChiou/research-hub)"
# Only definitive non-registration (HTTP 404/410) fails closed as
# `*_unresolved`; every other resolver HEAD failure -- anti-bot
# 401/403/406/418/451, rate-limit 429, 5xx, network error -- defers as
# `*_check_unavailable`. Anti-fabrication guarantee = 404/410 + the L2
# corroboration layer; both unchanged.
_DEFINITIVE_NOTFOUND_HTTP_STATUS = frozenset({404, 410})


def _resolve_head_with_retry(url: str, *, attempts: int = 3) -> tuple[int | None, bool]:
    """HEAD *url* with a real User-Agent and bounded backoff.

    Returns ``(status_code, transient)``. ``transient`` is True when the
    final attempt was an access / anti-bot / rate-limit / network
    failure rather than a definitive answer. Only 2xx/3xx and HTTP
    404/410 are definitive; every other status must NOT be treated as a
    fake DOI and must NOT be cached as a permanent failure.
    """
    status_code: int | None = None
    for attempt in range(attempts):
        try:
            response = requests.head(
                url,
                allow_redirects=True,
                timeout=8,
                headers={"User-Agent": _DOI_RESOLVE_UA},
            )
            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code and status_code < 400:
                return status_code, False
            if status_code in _DEFINITIVE_NOTFOUND_HTTP_STATUS:
                return status_code, False
        except requests.RequestException:
            status_code = None
        if attempt < attempts - 1:
            time.sleep(0.5 * (2 ** attempt))
    return status_code, True


def _resolve_identifier(paper: dict, cache: DoiResolveCache, cache_path: Path) -> ResolveOutcome:
    key_url_source = _identifier_key_url_source(paper)
    if key_url_source is None:
        return ResolveOutcome(
            ok=False,
            key="missing",
            resolved_via="unresolved",
            checked_at=_utc_now_iso(),
            reason="no_resolvable_identifier",
        )
    key, url, source = key_url_source
    cached = cache.get(key)
    if cached is not None:
        return cached

    checked_at = _utc_now_iso()
    status_code, transient = _resolve_head_with_retry(url)
    if transient:
        # F7: rate-limit / anti-bot / network blip — NOT evidence the DOI
        # is fabricated. Surface as check-unavailable and do NOT cache, so
        # a later run retries fresh instead of inheriting a poisoned miss.
        return ResolveOutcome(
            ok=False,
            key=key,
            resolved_via=source,
            checked_at=checked_at,
            status_code=status_code,
            reason=_unavailable_reason_for(source),
            url=url,
        )

    ok = status_code is not None and status_code < 400
    reason = "" if ok else _unresolved_reason_for(source)
    outcome = ResolveOutcome(
        ok=ok,
        key=key,
        resolved_via=source,
        checked_at=checked_at,
        status_code=status_code,
        reason=reason,
        url=url,
    )
    cache.put(outcome)
    cache.save(cache_path)
    return outcome


def _identifier_key_url_source(paper: dict) -> tuple[str, str, str] | None:
    doi = normalize_doi(str(paper.get("doi", "") or ""))
    if doi:
        return f"doi:{doi}", f"https://doi.org/{doi}", "doi.org"
    arxiv_id = _arxiv_id_for(paper)
    if arxiv_id:
        return f"arxiv:{arxiv_id}", f"https://arxiv.org/abs/{arxiv_id}", "arxiv.org"
    pmid = _first_nonempty(paper, ("pmid", "pubmed_id", "PMID"))
    if pmid:
        cleaned = re.sub(r"\D+", "", str(pmid))
        if cleaned:
            return (
                f"pmid:{cleaned}",
                f"https://pubmed.ncbi.nlm.nih.gov/{cleaned}/",
                "pubmed.ncbi.nlm.nih.gov",
            )
    openalex = _first_nonempty(paper, ("openalex_id", "openalex", "OpenAlex"))
    if openalex:
        value = str(openalex).strip()
        if value.startswith("http"):
            url = value
            key_value = value.rsplit("/", 1)[-1]
        else:
            key_value = value
            url = f"https://openalex.org/{value}"
        return f"openalex:{key_value}", url, "openalex.org"
    return None


def _has_identifier(paper: dict) -> bool:
    return _identifier_key_url_source(paper) is not None


def _arxiv_id_for(paper: dict) -> str:
    explicit = str(paper.get("arxiv_id", "") or "").strip()
    if explicit.lower().startswith("arxiv:"):
        explicit = explicit.split(":", 1)[1]
    if explicit:
        return explicit
    return extract_arxiv_id(f"{paper.get('url', '')} {paper.get('doi', '')}")


def _unresolved_reason_for(source: str) -> str:
    if source == "doi.org":
        return "doi_unresolved"
    if source == "arxiv.org":
        return "arxiv_unresolved"
    return "identifier_unresolved"


def _unavailable_reason_for(source: str) -> str:
    if source == "doi.org":
        return "doi_check_unavailable"
    if source == "arxiv.org":
        return "arxiv_check_unavailable"
    return "identifier_check_unavailable"


def is_transient_reason(reason: str) -> bool:
    """True for a transient identifier-resolution failure (the
    `*_check_unavailable` family emitted by ``_unavailable_reason_for``
    when the resolver was rate-limited / unreachable AFTER PR-B's
    bounded retry). Permanent failures (`*_unresolved`, `no_identifier`,
    predatory/metadata/fit/uncorroborated) are NOT transient and stay
    fail-closed-quarantined. Keyed on the canonical suffix so it stays
    correct if new sources are added to ``_unavailable_reason_for``.
    """
    return reason.endswith("_check_unavailable")


def _metadata_integrity_reason(paper: dict) -> str:
    author_values = _author_values(paper)
    joined_authors = " ".join(author_values + [str(paper.get("authors_str", "") or "")])
    if re.search(r"\+\s*\d+\s+more", joined_authors, re.IGNORECASE):
        return "truncated author list"
    if len(author_values) == 1 and re.fullmatch(r"[A-Za-z]\.?", author_values[0].strip()):
        return "single-initial author list"

    text_fields = [
        str(paper.get(key, "") or "")
        for key in ("title", "journal", "venue", "abstract", "publicationTitle")
    ]
    text_fields.extend(author_values)
    combined = " ".join(text_fields)
    if "嚙窯" in combined:
        return "mojibake"
    printable_chars = [char for char in combined if not char.isspace()]
    if printable_chars:
        bad = sum(1 for char in printable_chars if not char.isprintable() or char == "\ufffd")
        if bad / len(printable_chars) > 0.10:
            return "mojibake"

    try:
        year = int(str(paper.get("year", "")).strip())
    except (TypeError, ValueError):
        return "invalid year"
    current_year = datetime.now(timezone.utc).year
    if year < 1900 or year > current_year + 1:
        return "year out of range"

    venues = [
        str(paper.get(key, "") or "").strip()
        for key in ("venue", "journal", "publicationTitle", "container_title")
    ]
    normalized_venues = {value.casefold() for value in venues if value}
    has_straggler = bool(normalized_venues & _KNOWN_VENUE_STRAGGLERS)
    has_real = bool(normalized_venues - _KNOWN_VENUE_STRAGGLERS)
    if has_straggler and has_real:
        return "straggler venue conflicts with real venue"
    return ""


def _corroboration_label(paper: dict) -> str:
    records = _backend_records(paper)
    if len(records) >= 2 and _records_agree(records):
        return "corroborated"
    backends = _backend_names(paper)
    if len(backends) >= 2 or "crossref" in backends:
        return "corroborated"
    return "single-source"


def _backend_names(paper: dict) -> list[str]:
    names: list[str] = []
    for key in ("source", "backend"):
        value = paper.get(key)
        if isinstance(value, str) and value.strip():
            names.append(value.strip())
    for key in ("found_in", "backends", "sources"):
        value = paper.get(key)
        if isinstance(value, str) and value.strip():
            names.append(value.strip())
        elif isinstance(value, list):
            names.extend(str(item).strip() for item in value if str(item).strip())
    for record in _backend_records(paper):
        value = record.get("source") or record.get("backend")
        if value:
            names.append(str(value).strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for name in names:
        token = name.casefold()
        if token in seen:
            continue
        seen.add(token)
        deduped.append(name)
    return deduped


def _backend_records(paper: dict) -> list[dict]:
    for key in ("backend_records", "source_records", "corroborating_records"):
        value = paper.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _records_agree(records: list[dict]) -> bool:
    if len(records) < 2:
        return False
    first = records[0]
    first_title = str(first.get("title", "") or "")
    first_year = _int_or_none(first.get("year"))
    first_surnames = set(_author_surnames(first))
    agreeing_sources: set[str] = set()
    for record in records:
        source = str(record.get("source") or record.get("backend") or "").strip()
        if not source:
            continue
        title = str(record.get("title", "") or "")
        if first_title and title and fuzz.token_set_ratio(first_title, title) < 85:
            continue
        year = _int_or_none(record.get("year"))
        if first_year is not None and year is not None and abs(first_year - year) > 1:
            continue
        surnames = set(_author_surnames(record))
        if first_surnames and surnames and not first_surnames.intersection(surnames):
            continue
        agreeing_sources.add(source.casefold())
    return len(agreeing_sources) >= 2


def _load_fit_scores(cfg, cluster_slug: str | None) -> dict[str, dict]:
    if not cluster_slug:
        return {}
    try:
        from research_hub.topic import hub_cluster_dir

        cluster_dir = hub_cluster_dir(cfg, cluster_slug)
    except Exception:
        cluster_dir = Path(cfg.hub) / cluster_slug

    scores: dict[str, dict] = {}
    for filename, kept_default in (
        (".fit_check_accepted.json", True),
        (".fit_check_rejected.json", False),
    ):
        path = cluster_dir / filename
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items = payload.get("accepted") if kept_default else payload.get("rejected")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            entry = dict(item)
            entry.setdefault("kept", kept_default)
            for key in _fit_match_keys(entry):
                scores[key] = entry
    return scores


def _fit_status_for_paper(paper: dict, fit_scores: dict[str, dict], threshold: int) -> dict:
    score_entry = None
    for key in _fit_match_keys(paper):
        score_entry = fit_scores.get(key)
        if score_entry:
            break
    if score_entry is None:
        return {"kept": False, "reason": "relevance_unjudged", "score": None}
    try:
        score = int(score_entry.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    if score < threshold:
        return {"kept": False, "reason": "low_relevance", "score": score}
    return {"kept": True, "reason": "", "score": score}


def _fit_match_keys(paper: dict) -> list[str]:
    keys: list[str] = []
    doi = normalize_doi(str(paper.get("doi", "") or ""))
    title = normalize_title(str(paper.get("title", "") or ""))
    if doi:
        keys.append(f"doi:{doi}")
    if title:
        keys.append(f"title:{title}")
    return keys


def _existing_fit_score(paper: dict) -> int | None:
    provenance = paper.get("provenance") if isinstance(paper.get("provenance"), dict) else {}
    value = provenance.get("fit_score") if provenance else paper.get("fit_score")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _append_to_papers_input(path: Path, candidate: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = []
    else:
        existing = []
    if isinstance(existing, dict):
        papers = existing.setdefault("papers", [])
        if not isinstance(papers, list):
            existing["papers"] = papers = []
        papers.append(candidate)
        payload = existing
    elif isinstance(existing, list):
        existing.append(candidate)
        payload = existing
    else:
        payload = {"papers": [candidate]}
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _invalidate_candidate_cache(cfg, candidate: dict) -> None:
    key_url_source = _identifier_key_url_source(candidate)
    if key_url_source is None:
        return
    key, _url, _source = key_url_source
    path = Path(cfg.research_hub_dir) / DOI_RESOLVE_CACHE
    cache = DoiResolveCache.load(path)
    if cache.invalidate(key):
        cache.save(path)


def _find_quarantine_payloads(cfg, slug: str, cluster: str | None) -> list[tuple[dict, Path]]:
    base = Path(cfg.research_hub_dir) / QUARANTINE_DIR
    candidates = [_quarantine_path(cfg, cluster, slug)] if cluster else sorted(base.glob(f"*/{slug}.json"))
    matches: list[tuple[dict, Path]] = []
    for path in candidates:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.setdefault("cluster", path.parent.name)
        payload.setdefault("slug", path.stem)
        matches.append((payload, path))
    return matches


def _quarantine_path(cfg, cluster: str, slug: str) -> Path:
    return Path(cfg.research_hub_dir) / QUARANTINE_DIR / cluster / f"{slug}.json"


def _cluster_for_paper(paper: dict, cluster_slug: str | None) -> str:
    for value in (
        cluster_slug,
        paper.get("topic_cluster"),
        paper.get("sub_category"),
        paper.get("cluster"),
    ):
        text = str(value or "").strip()
        if text:
            return _safe_path_token(text)
    return "unclustered"


def _slug_for_paper(paper: dict) -> str:
    slug = str(paper.get("slug", "") or "").strip()
    if slug:
        return _safe_path_token(slug)
    title = str(paper.get("title", "") or "paper").strip()
    return _safe_path_token(normalize_title(title).replace(" ", "-")[:80] or "paper")


def _safe_path_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    token = re.sub(r"[^a-zA-Z0-9_.-]+", "-", normalized).strip("-._")
    return token or "item"


def _first_nonempty(paper: dict, keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = paper.get(key)
        if value not in (None, "", []):
            return value
    return ""


def _author_values(paper: dict) -> list[str]:
    authors = paper.get("authors") or []
    values: list[str] = []
    if not isinstance(authors, list):
        return [str(authors)]
    for author in authors:
        if isinstance(author, str):
            values.append(author.strip())
        elif isinstance(author, dict):
            name = author.get("name")
            if name:
                values.append(str(name).strip())
            else:
                first = str(author.get("firstName", "") or "").strip()
                last = str(author.get("lastName", "") or "").strip()
                values.append(f"{first} {last}".strip())
    return [value for value in values if value]


def _author_surnames(paper: dict) -> list[str]:
    surnames: list[str] = []
    for author in _author_values(paper):
        if "," in author:
            surname = author.split(",", 1)[0]
        else:
            parts = author.split()
            surname = parts[-1] if parts else ""
        surname = re.sub(r"[^A-Za-z]", "", surname).casefold()
        if surname:
            surnames.append(surname)
    return surnames


def _int_or_none(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

"""Real HTTP verification of paper identifiers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover - fallback for environments missing the optional wheel
    from difflib import SequenceMatcher

    class _FuzzFallback:
        @staticmethod
        def token_set_ratio(left: str, right: str) -> float:
            left_tokens = set(_normalize_title(left).split())
            right_tokens = set(_normalize_title(right).split())
            left_text = " ".join(sorted(left_tokens))
            right_text = " ".join(sorted(right_tokens))
            return SequenceMatcher(None, left_text, right_text).ratio() * 100

    fuzz = _FuzzFallback()

_DOI_ORG_URL = "https://doi.org/{doi}"
_ARXIV_ABS_URL = "https://arxiv.org/abs/{arxiv_id}"
_S2_PAPER_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"

_DEFAULT_TIMEOUT = 5.0
_DEFAULT_RETRIES = 1
_RETRY_BACKOFF_S = 2.0
_CACHE_TTL_DAYS = 7
_TITLE_MATCH_THRESHOLD = 80

_SOURCE_DOI = "doi.org"
_SOURCE_ARXIV = "arxiv.org"
_SOURCE_S2 = "semantic-scholar"
_SOURCE_UNRESOLVED = "unresolved"


@dataclass
class VerificationResult:
    """Outcome of a single verification attempt."""

    ok: bool
    source: str
    resolved_url: str = ""
    title_match: float = 0.0
    reason: str = ""
    cached_at: str = ""

    def __bool__(self) -> bool:
        return self.ok


class VerifyCache:
    """7-day JSON cache for verification results."""

    def __init__(self, path: Path, ttl_days: int = _CACHE_TTL_DAYS) -> None:
        self.path = path
        self.ttl = timedelta(days=ttl_days)
        self._data: dict[str, dict[str, Any]] | None = None

    def get(self, key: str) -> VerificationResult | None:
        self._load()
        self._prune_expired()
        assert self._data is not None
        payload = self._data.get(key)
        if payload is None:
            return None
        return VerificationResult(**payload)

    def put(self, key: str, result: VerificationResult) -> None:
        self._load()
        assert self._data is not None
        if not result.cached_at:
            result.cached_at = _utc_now_iso()
        self._data[key] = asdict(result)
        self._write()

    def _load(self) -> None:
        if self._data is not None:
            return
        if not self.path.exists():
            self._data = {}
            return
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._data = {}

    def _write(self) -> None:
        assert self._data is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f"{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, ensure_ascii=False, indent=2)
            Path(tmp_name).replace(self.path)
        finally:
            tmp_path = Path(tmp_name)
            if tmp_path.exists():
                tmp_path.unlink()

    def _prune_expired(self) -> None:
        assert self._data is not None
        now = datetime.now(timezone.utc)
        expired = []
        for key, payload in self._data.items():
            cached_at = _parse_cached_at(payload.get("cached_at", ""))
            if cached_at is None or now - cached_at > self.ttl:
                expired.append(key)
        if not expired:
            return
        for key in expired:
            self._data.pop(key, None)
        self._write()


def verify_doi(
    doi: str,
    *,
    session: requests.Session | None = None,
    cache: VerifyCache | None = None,
) -> VerificationResult:
    """HEAD a DOI at doi.org and report whether it resolves."""
    normalized = _normalize_doi(doi)
    if not normalized:
        return VerificationResult(ok=False, source=_SOURCE_UNRESOLVED, reason="empty DOI")
    key = _cache_key("doi", normalized)
    cached = cache.get(key) if cache else None
    if cached is not None:
        return cached
    result = _head_exists(_DOI_ORG_URL.format(doi=normalized), _SOURCE_DOI, session=session)
    if cache:
        cache.put(key, result)
    return result


def verify_arxiv(
    arxiv_id: str,
    *,
    session: requests.Session | None = None,
    cache: VerifyCache | None = None,
) -> VerificationResult:
    """HEAD an arXiv abstract URL and report whether it resolves."""
    normalized = _normalize_arxiv_id(arxiv_id)
    if not normalized:
        return VerificationResult(ok=False, source=_SOURCE_UNRESOLVED, reason="empty arXiv ID")
    key = _cache_key("arxiv", normalized)
    cached = cache.get(key) if cache else None
    if cached is not None:
        return cached
    result = _head_exists(_ARXIV_ABS_URL.format(arxiv_id=normalized), _SOURCE_ARXIV, session=session)
    if cache:
        cache.put(key, result)
    return result


def verify_paper(
    title: str,
    authors: list[str] | None = None,
    year: int | None = None,
    *,
    session: requests.Session | None = None,
    cache: VerifyCache | None = None,
) -> VerificationResult:
    """Fuzzy-match a paper title against Semantic Scholar."""
    normalized_title = _normalize_title(title)
    if not normalized_title:
        return VerificationResult(ok=False, source=_SOURCE_UNRESOLVED, reason="empty title")
    key = _cache_key("paper", f"{normalized_title}|{year or ''}")
    cached = cache.get(key) if cache else None
    if cached is not None:
        return cached

    client = session or requests.Session()
    try:
        response = client.get(
            _S2_PAPER_SEARCH,
            params={"query": title, "limit": 3, "fields": "title,year,authors,url"},
            timeout=_DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        result = VerificationResult(
            ok=False,
            source=_SOURCE_UNRESOLVED,
            reason=f"request failed: {exc.__class__.__name__}",
        )
        if cache:
            cache.put(key, result)
        return result

    author_surnames = {_surname(name) for name in authors or [] if _surname(name)}
    best_result: VerificationResult | None = None
    best_reason = "no candidate matched"
    for item in response.json().get("data", []):
        candidate_title = item.get("title") or ""
        score = float(fuzz.token_set_ratio(title, candidate_title))
        if score < _TITLE_MATCH_THRESHOLD:
            best_reason = f"title match below threshold ({score:.1f})"
            continue
        candidate_year = item.get("year")
        if year is not None and candidate_year is not None and abs(int(candidate_year) - year) > 1:
            best_reason = f"year mismatch ({candidate_year})"
            continue
        if author_surnames:
            candidate_surnames = {
                _surname(author.get("name", ""))
                for author in item.get("authors") or []
                if isinstance(author, dict)
            }
            if not author_surnames.intersection(candidate_surnames):
                best_reason = "author mismatch"
                continue
        best_result = VerificationResult(
            ok=True,
            source=_SOURCE_S2,
            resolved_url=item.get("url", "") or "",
            title_match=score,
            reason=f"title match {score:.1f}",
        )
        break

    result = best_result or VerificationResult(
        ok=False,
        source=_SOURCE_UNRESOLVED,
        reason=best_reason,
    )
    if cache:
        cache.put(key, result)
    return result


def _head_exists(
    url: str,
    source: str,
    *,
    session: requests.Session | None = None,
) -> VerificationResult:
    client = session or requests.Session()
    last_error: str | None = None
    for attempt in range(_DEFAULT_RETRIES + 1):
        try:
            response = client.head(
                url,
                allow_redirects=True,
                timeout=_DEFAULT_TIMEOUT,
                headers={"User-Agent": "research-hub/0.4.1"},
            )
        except requests.exceptions.ConnectionError as exc:
            last_error = exc.__class__.__name__
            if attempt < _DEFAULT_RETRIES:
                time.sleep(_RETRY_BACKOFF_S)
                continue
            return VerificationResult(ok=False, source=source, reason=f"connection error: {last_error}")
        except requests.exceptions.RequestException as exc:
            return VerificationResult(
                ok=False,
                source=source,
                reason=f"request failed: {exc.__class__.__name__}",
            )

        status = response.status_code
        if status in (200, 401, 403):
            return VerificationResult(
                ok=True,
                source=source,
                resolved_url=response.url,
                reason=f"{status} {response.reason}".strip(),
            )
        if status in (404, 410):
            return VerificationResult(
                ok=False,
                source=source,
                resolved_url=response.url,
                reason=f"{status} {response.reason}".strip(),
            )
        return VerificationResult(
            ok=False,
            source=source,
            resolved_url=response.url,
            reason=f"{status} {response.reason}".strip(),
        )
    return VerificationResult(ok=False, source=source, reason="unreachable")


def _cache_key(kind: str, identifier: str) -> str:
    return hashlib.sha1(f"{kind}:{identifier}".encode("utf-8")).hexdigest()


def _normalize_doi(doi: str) -> str:
    normalized = (doi or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    return normalized.strip()


def _normalize_arxiv_id(arxiv_id: str) -> str:
    value = (arxiv_id or "").strip()
    match = re.search(r"(\d{4}\.\d{4,5}(?:v\d+)?)", value, re.IGNORECASE)
    return match.group(1) if match else value


def _normalize_title(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
    return re.sub(r"\s+", " ", normalized)


def _surname(name: str) -> str:
    parts = [part for part in re.split(r"\s+", name.strip()) if part]
    if not parts:
        return ""
    return re.sub(r"[^a-z0-9-]", "", parts[-1].lower())


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_cached_at(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None

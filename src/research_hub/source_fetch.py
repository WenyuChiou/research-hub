"""Credential-free acquisition of public scholarly source material.

The output directory is an immutable evidence bundle: every HTTP response is
saved before parsing, extracted text is hashed, and the terminal JSON record
never promotes a login, paywall, or challenge page to full-text evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import ipaddress
import json
from pathlib import Path
import re
import socket
from typing import Any, Literal
from urllib.parse import quote, urljoin, urlsplit

import requests
from research_hub._useragent import user_agent
from research_hub.security import is_safe_fetch_url
from research_hub.source_fetch_extraction import (
    _Extracted,
    _crossref_metadata,
    _extract_html,
    _extract_pdf,
    _identity,
)
from research_hub.utils.doi import extract_arxiv_id, normalize_doi


SCHEMA_VERSION = "source-fetch-result/v1"
VALIDATION_SCHEMA_VERSION = "source-fetch-validation/v1"
Status = Literal[
    "available", "inaccessible", "rate-limited", "parse-error", "identity-mismatch"
]
EvidenceLevel = Literal["metadata", "abstract", "full-text"]
IdentityStatus = Literal["verified", "consistent", "unverified", "mismatch"]
_TIMEOUT_SECONDS = 30.0
_MAX_RESPONSE_BYTES = 50 * 1024 * 1024
_MAX_REDIRECTS = 8


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(data: bytes) -> str:
    return sha256(data).hexdigest()


@dataclass
class FetchAttempt:
    sequence: int
    purpose: str
    url: str
    final_url: str
    requested_at: str
    received_at: str | None = None
    http_status: int | None = None
    content_type: str = ""
    outcome: str = "network-error"
    response_bytes: int | None = None
    response_truncated: bool = False
    raw_path: str | None = None
    raw_sha256: str | None = None
    error: str | None = None


@dataclass
class SourceFetchResult:
    schema_version: str
    request: dict[str, Any]
    receipt_sha256: str
    status: Status
    evidence_level: EvidenceLevel
    source_url: str
    final_url: str
    retrieved_at: str
    expected_identity: dict[str, str]
    observed_identity: dict[str, str]
    identity_status: IdentityStatus
    source_version: str
    attempts: list[FetchAttempt]
    raw_path: str | None
    raw_sha256: str | None
    extracted_text_path: str | None
    extracted_text_sha256: str | None
    locators: list[dict[str, Any]]
    errors: list[str] = field(default_factory=list)
    output_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _resolve_host_addresses(host: str) -> tuple[str, ...]:
    """Resolve all addresses for a fetch host for a fail-closed public check."""
    return tuple(
        sorted(
            {
                str(sockaddr[0])
                for _family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(
                    host, None, type=socket.SOCK_STREAM
                )
            }
        )
    )


def _address_is_public(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_global and not address.is_multicast


def _is_public_url(url: str, *, resolve_dns: bool = False) -> bool:
    if not is_safe_fetch_url(url):
        return False
    parts = urlsplit(url)
    if parts.username is not None or parts.password is not None:
        return False
    host = (parts.hostname or "").lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not resolve_dns:
            return True
        try:
            addresses = _resolve_host_addresses(host)
        except OSError:
            return False
        return bool(addresses) and all(_address_is_public(value) for value in addresses)
    return _address_is_public(host)


def _new_public_session() -> requests.Session:
    """Return a session isolated from netrc, environment proxies, and cookies."""
    session = requests.Session()
    session.trust_env = False
    session.auth = None
    session.cookies.clear()
    return session


def _artifact_path(output_dir: Path, *parts: str) -> Path:
    candidate = output_dir.joinpath(*parts).resolve()
    try:
        candidate.relative_to(output_dir)
    except ValueError as exc:
        raise ValueError("artifact path escapes output directory") from exc
    return candidate


def _write_once(path: Path, data: bytes) -> tuple[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
    return str(path), _hash(data)


def _suffix(content_type: str, data: bytes) -> str:
    content_type = content_type.lower()
    if "pdf" in content_type or data.startswith(b"%PDF-"):
        return "pdf"
    if "json" in content_type:
        return "json"
    if "html" in content_type or b"<html" in data[:1024].lower():
        return "html"
    if "text" in content_type:
        return "txt"
    return "bin"


def _request_in_session(
    url: str,
    *,
    purpose: str,
    output_dir: Path,
    attempts: list[FetchAttempt],
    timeout: float,
    session: requests.Session,
) -> tuple[bytes | None, FetchAttempt]:
    current = url
    last: FetchAttempt | None = None
    for _ in range(_MAX_REDIRECTS + 1):
        if not _is_public_url(current, resolve_dns=True):
            attempt = FetchAttempt(
                sequence=len(attempts) + 1,
                purpose=purpose,
                url=current,
                final_url=current,
                requested_at=_now(),
                outcome="unsafe-url",
                error="only public http(s) URLs are allowed",
            )
            attempts.append(attempt)
            return None, attempt
        attempt = FetchAttempt(
            sequence=len(attempts) + 1,
            purpose=purpose,
            url=current,
            final_url=current,
            requested_at=_now(),
        )
        attempts.append(attempt)
        last = attempt
        response = None
        try:
            # Reject cookies from an earlier public response; public-only means
            # no ambient or acquired session identity on any request.
            session.cookies.clear()
            response = session.get(
                current,
                allow_redirects=False,
                timeout=timeout,
                stream=True,
                headers={"User-Agent": user_agent(None), "Accept": "*/*"},
            )
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                remaining = _MAX_RESPONSE_BYTES + 1 - size
                chunks.append(bytes(chunk[:remaining]))
                size += len(chunks[-1])
                if size > _MAX_RESPONSE_BYTES:
                    break
            data = b"".join(chunks)
            attempt.received_at = _now()
            attempt.http_status = int(response.status_code)
            attempt.final_url = str(getattr(response, "url", current) or current)
            attempt.content_type = str(response.headers.get("Content-Type", ""))
            attempt.response_bytes = len(data)
            raw = _artifact_path(
                output_dir,
                "raw",
                f"{attempt.sequence:03d}-{_suffix(attempt.content_type, data)}-response.{_suffix(attempt.content_type, data)}",
            )
            attempt.raw_path, attempt.raw_sha256 = _write_once(raw, data)
            if len(data) > _MAX_RESPONSE_BYTES:
                attempt.response_truncated = True
                attempt.outcome = "response-too-large"
                attempt.error = f"response exceeds {_MAX_RESPONSE_BYTES} bytes"
                return None, attempt
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location", "")
                if not location:
                    attempt.outcome = "redirect-error"
                    attempt.error = "redirect response has no Location header"
                    return None, attempt
                current = urljoin(current, location)
                attempt.outcome = "redirect"
                continue
            if response.status_code == 429:
                attempt.outcome = "rate-limited"
                attempt.error = "HTTP 429"
                return None, attempt
            if response.status_code in {401, 402, 403}:
                attempt.outcome = "inaccessible"
                attempt.error = f"HTTP {response.status_code}"
                return None, attempt
            if not 200 <= response.status_code < 300:
                attempt.outcome = "http-error"
                attempt.error = f"HTTP {response.status_code}"
                return None, attempt
            attempt.outcome = "success"
            return data, attempt
        except requests.Timeout as exc:
            attempt.outcome = "timeout"
            attempt.error = f"{type(exc).__name__}: {exc}"
            return None, attempt
        except requests.RequestException as exc:
            attempt.outcome = "network-error"
            attempt.error = f"{type(exc).__name__}: {exc}"
            return None, attempt
        finally:
            if response is not None:
                response.close()
    assert last is not None
    last.outcome = "redirect-error"
    last.error = f"more than {_MAX_REDIRECTS} redirects"
    return None, last


def _request(
    url: str,
    *,
    purpose: str,
    output_dir: Path,
    attempts: list[FetchAttempt],
    timeout: float,
) -> tuple[bytes | None, FetchAttempt]:
    session = _new_public_session()
    try:
        return _request_in_session(
            url,
            purpose=purpose,
            output_dir=output_dir,
            attempts=attempts,
            timeout=timeout,
            session=session,
        )
    finally:
        session.close()


def _candidate_urls(doi: str, url: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    normalized = normalize_doi(doi)
    arxiv_id = ""
    if normalized.startswith("10.48550/arxiv."):
        arxiv_id = extract_arxiv_id(normalized)
    elif re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", normalized, flags=re.I):
        arxiv_id = normalized
    elif url:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
        if host in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"} and re.match(
            r"^/(?:abs|pdf)/", parts.path, flags=re.I
        ):
            arxiv_id = extract_arxiv_id(parts.path)
    if arxiv_id:
        candidates.append(("arxiv-pdf", f"https://arxiv.org/pdf/{arxiv_id}.pdf"))
    if url:
        candidates.append(("provided-url", url))
    return candidates


def _receipt_hash(
    request: dict[str, Any],
    attempts: list[FetchAttempt],
    extracted_sha256: str | None,
    result_claims: dict[str, Any] | None = None,
) -> str:
    """Bind normalized request inputs to the exact persisted response bytes."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "request": request,
        "attempts": [
            {
                "sequence": attempt.sequence,
                "purpose": attempt.purpose,
                "url": attempt.url,
                "final_url": attempt.final_url,
                "http_status": attempt.http_status,
                "outcome": attempt.outcome,
                "raw_sha256": attempt.raw_sha256,
            }
            for attempt in attempts
        ],
        "extracted_text_sha256": extracted_sha256,
        "result": result_claims or {},
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return _hash(canonical.encode("utf-8"))


def _receipt_result_fields(
    result: SourceFetchResult | dict[str, Any],
) -> dict[str, Any]:
    if isinstance(result, SourceFetchResult):
        payload = result.to_dict()
    else:
        payload = result
    keys = (
        "status",
        "evidence_level",
        "source_url",
        "final_url",
        "expected_identity",
        "observed_identity",
        "identity_status",
        "source_version",
        "raw_path",
        "raw_sha256",
        "extracted_text_path",
        "extracted_text_sha256",
        "locators",
    )
    return {key: payload.get(key) for key in keys}


def fetch_public_source(
    *,
    output_dir: Path,
    doi: str = "",
    url: str = "",
    title: str = "",
    timeout: float = _TIMEOUT_SECONDS,
) -> SourceFetchResult:
    """Fetch public source evidence into a new immutable output directory."""
    normalized_doi = normalize_doi(doi)
    url = url.strip()
    title = title.strip()
    if not normalized_doi and not url:
        raise ValueError("at least one of doi or url is required")
    if url and not _is_public_url(url):
        raise ValueError("url must be a public http(s) URL")

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    request_record: dict[str, Any] = {
        "operation": "source fetch",
        "doi": normalized_doi,
        "url": url,
        "title": title,
        "output_dir": str(output_dir),
        "public_only": True,
    }
    attempts: list[FetchAttempt] = []
    errors: list[str] = []
    candidates = _candidate_urls(normalized_doi, url)
    if normalized_doi:
        unpaywall = (
            "https://api.unpaywall.org/v2/"
            f"{quote(normalized_doi, safe='')}?email=research-hub@example.invalid"
        )
        data, attempt = _request(
            unpaywall,
            purpose="unpaywall-metadata",
            output_dir=output_dir,
            attempts=attempts,
            timeout=timeout,
        )
        if data is not None:
            try:
                payload = json.loads(data.decode("utf-8"))
                best = payload.get("best_oa_location") or {}
                oa_url = best.get("url_for_pdf") or best.get("url") or ""
                if oa_url and _is_public_url(oa_url):
                    candidates.append(("unpaywall-oa", str(oa_url)))
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
                attempt.outcome = "parse-error"
                attempt.error = f"Unpaywall JSON: {exc}"
                errors.append(attempt.error)

    seen: set[str] = set()
    best: tuple[_Extracted, FetchAttempt, str] | None = None
    for purpose, candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        data, attempt = _request(
            candidate,
            purpose=purpose,
            output_dir=output_dir,
            attempts=attempts,
            timeout=timeout,
        )
        if data is None:
            if attempt.error:
                errors.append(f"{purpose}: {attempt.error}")
            continue
        try:
            content_type = attempt.content_type.lower()
            if "pdf" in content_type or data.startswith(b"%PDF-"):
                extracted = _extract_pdf(data)
            elif "html" in content_type or b"<html" in data[:1024].lower():
                extracted = _extract_html(data, attempt.final_url)
            else:
                raise ValueError(
                    f"unsupported content type: {attempt.content_type or '(missing)'}"
                )
            attempt.outcome = "parsed"
            best = (extracted, attempt, candidate)
            if extracted.evidence_level == "full-text":
                break
        except PermissionError as exc:
            attempt.outcome = "inaccessible"
            attempt.error = str(exc)
            errors.append(f"{purpose}: {exc}")
        except Exception as exc:  # parser/library failures are recorded evidence
            attempt.outcome = "parse-error"
            attempt.error = str(exc)
            errors.append(f"{purpose}: {exc}")

    # Crossref is a public metadata/abstract fallback and can also advertise an
    # openly reachable PDF. It is skipped when full text is already available.
    if normalized_doi and (best is None or best[0].evidence_level != "full-text"):
        crossref_url = (
            f"https://api.crossref.org/works/{quote(normalized_doi, safe='')}"
        )
        data, attempt = _request(
            crossref_url,
            purpose="crossref-metadata",
            output_dir=output_dir,
            attempts=attempts,
            timeout=timeout,
        )
        if data is not None:
            try:
                extracted, pdf_links = _crossref_metadata(
                    json.loads(data.decode("utf-8"))
                )
                attempt.outcome = "parsed"
                if best is None or (
                    best[0].evidence_level == "metadata"
                    and extracted.evidence_level == "abstract"
                ):
                    best = (extracted, attempt, crossref_url)
                for pdf_url in pdf_links:
                    if pdf_url in seen:
                        continue
                    seen.add(pdf_url)
                    pdf_data, pdf_attempt = _request(
                        pdf_url,
                        purpose="crossref-public-pdf",
                        output_dir=output_dir,
                        attempts=attempts,
                        timeout=timeout,
                    )
                    if pdf_data is None:
                        continue
                    try:
                        pdf_extracted = _extract_pdf(pdf_data)
                        pdf_attempt.outcome = "parsed"
                        best = (pdf_extracted, pdf_attempt, pdf_url)
                        break
                    except (
                        Exception
                    ) as exc:  # parser/library failures are recorded evidence
                        pdf_attempt.outcome = "parse-error"
                        pdf_attempt.error = str(exc)
                        errors.append(f"crossref-public-pdf: {exc}")
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                ValueError,
                AttributeError,
            ) as exc:
                attempt.outcome = "parse-error"
                attempt.error = f"Crossref JSON: {exc}"
                errors.append(attempt.error)

    # A DOI resolver is the final public HTML fallback. It may yield an abstract
    # or full article, but challenge/login pages remain inaccessible.
    if normalized_doi and (best is None or best[0].evidence_level == "metadata"):
        resolver = f"https://doi.org/{quote(normalized_doi, safe='/')}"
        data, attempt = _request(
            resolver,
            purpose="doi-resolver",
            output_dir=output_dir,
            attempts=attempts,
            timeout=timeout,
        )
        if data is not None:
            try:
                extracted = _extract_html(data, attempt.final_url)
                attempt.outcome = "parsed"
                if best is None or extracted.evidence_level != "metadata":
                    best = (extracted, attempt, resolver)
            except PermissionError as exc:
                attempt.outcome = "inaccessible"
                attempt.error = str(exc)
                errors.append(f"doi-resolver: {exc}")
            except Exception as exc:  # HTML parser failures are recorded evidence
                attempt.outcome = "parse-error"
                attempt.error = str(exc)
                errors.append(f"doi-resolver: {exc}")

    retrieved_at = _now()
    if best is not None:
        extracted, selected, source_url = best
        identity_status = _identity(
            normalized_doi,
            title,
            extracted.observed_doi,
            extracted.observed_title,
        )
        text_bytes = extracted.text.encode("utf-8")
        text_path = _artifact_path(output_dir, "extracted", "source.txt")
        extracted_path, extracted_hash = _write_once(text_path, text_bytes)
        status: Status = (
            "identity-mismatch" if identity_status == "mismatch" else "available"
        )
        result = SourceFetchResult(
            schema_version=SCHEMA_VERSION,
            request=request_record,
            receipt_sha256="",
            status=status,
            evidence_level=extracted.evidence_level,
            source_url=source_url,
            final_url=selected.final_url,
            retrieved_at=retrieved_at,
            expected_identity={"doi": normalized_doi, "title": title},
            observed_identity={
                "doi": normalize_doi(extracted.observed_doi),
                "title": extracted.observed_title,
            },
            identity_status=identity_status,
            source_version=f"sha256:{selected.raw_sha256}",
            attempts=attempts,
            raw_path=selected.raw_path,
            raw_sha256=selected.raw_sha256,
            extracted_text_path=extracted_path,
            extracted_text_sha256=extracted_hash,
            locators=extracted.locators,
            errors=errors,
            output_dir=str(output_dir),
        )
    else:
        outcomes = {attempt.outcome for attempt in attempts}
        if "rate-limited" in outcomes:
            status = "rate-limited"
        elif "inaccessible" in outcomes or "unsafe-url" in outcomes:
            status = "inaccessible"
        elif "parse-error" in outcomes:
            status = "parse-error"
        else:
            status = "inaccessible"
        if not errors:
            errors.append("no public source produced usable evidence")
        result = SourceFetchResult(
            schema_version=SCHEMA_VERSION,
            request=request_record,
            receipt_sha256="",
            status=status,
            evidence_level="metadata",
            source_url=url
            or (f"https://doi.org/{normalized_doi}" if normalized_doi else ""),
            final_url=attempts[-1].final_url if attempts else "",
            retrieved_at=retrieved_at,
            expected_identity={"doi": normalized_doi, "title": title},
            observed_identity={"doi": "", "title": ""},
            identity_status="unverified",
            source_version="",
            attempts=attempts,
            raw_path=None,
            raw_sha256=None,
            extracted_text_path=None,
            extracted_text_sha256=None,
            locators=[],
            errors=errors,
            output_dir=str(output_dir),
        )

    result.receipt_sha256 = _receipt_hash(
        request_record,
        attempts,
        result.extracted_text_sha256,
        _receipt_result_fields(result),
    )
    result_path = _artifact_path(output_dir, "source-fetch-result.json")
    encoded = json.dumps(result.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
    _write_once(result_path, encoded)
    return result


def validate_source_fetch(
    result_path: Path,
    *,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Replay and validate a SourceFetchResult without network access."""
    from research_hub.source_fetch_validation import validate_source_fetch as _validate

    return _validate(result_path, output_dir=output_dir)


__all__ = [
    "SCHEMA_VERSION",
    "VALIDATION_SCHEMA_VERSION",
    "FetchAttempt",
    "SourceFetchResult",
    "fetch_public_source",
    "validate_source_fetch",
]

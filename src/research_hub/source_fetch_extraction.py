"""Deterministic extraction and identity helpers for public source fetches."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import re
from typing import Any, Literal
from urllib.parse import urlsplit

from rapidfuzz.fuzz import ratio

from research_hub.importer import _html_to_text
from research_hub.security import is_safe_fetch_url
from research_hub.utils.doi import normalize_doi

EvidenceLevel = Literal["metadata", "abstract", "full-text"]
IdentityStatus = Literal["verified", "consistent", "unverified", "mismatch"]
_LOGIN_MARKERS = (
    "sign in to continue",
    "log in to continue",
    "institutional login",
    "access through your institution",
    "verify you are human",
    "captcha",
    "cloudflare challenge",
    "purchase this article",
    "subscribe to read",
)


@dataclass
class _Extracted:
    text: str
    evidence_level: EvidenceLevel
    observed_doi: str = ""
    observed_title: str = ""
    locators: list[dict[str, Any]] = field(default_factory=list)


class _HtmlMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.headings: list[str] = []
        self.meta: dict[str, str] = {}
        self.in_title = False
        self.in_heading = False
        self._heading_parts: list[str] = []
        self.article_depth = 0
        self.saw_article = False
        self.suppressed_depth = 0
        self.article_parts: list[str] = []
        self.section_parts: list[tuple[str, list[str]]] = []
        self._current_section: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        values = {str(key).lower(): str(value or "") for key, value in attrs}
        if tag in {"script", "style", "noscript", "template"}:
            self.suppressed_depth += 1
            return
        if self.suppressed_depth:
            return
        if tag == "title":
            self.in_title = True
        if tag in {"h1", "h2", "h3"} and self.article_depth:
            self.in_heading = True
            self._heading_parts = []
        if tag in {"article", "main"}:
            self.article_depth += 1
            self.saw_article = True
        if tag == "meta":
            name = (values.get("name") or values.get("property") or "").lower()
            content = values.get("content", "").strip()
            if name and content:
                self.meta[name] = content

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template"}:
            if self.suppressed_depth:
                self.suppressed_depth -= 1
            return
        if self.suppressed_depth:
            return
        if tag == "title":
            self.in_title = False
        if tag in {"h1", "h2", "h3"} and self.in_heading:
            heading = " ".join(self._heading_parts).strip()
            if heading:
                self.headings.append(heading)
                self.article_parts.append(heading)
                body_parts: list[str] = []
                self.section_parts.append((heading, body_parts))
                self._current_section = body_parts
            self.in_heading = False
        if tag in {"article", "main"} and self.article_depth:
            self.article_depth -= 1

    def handle_data(self, data: str) -> None:
        clean = data.strip()
        if not clean or self.suppressed_depth:
            return
        if self.in_title:
            self.title_parts.append(clean)
        if self.in_heading:
            self._heading_parts.append(clean)
        elif self.article_depth:
            self.article_parts.append(clean)
            if self._current_section is not None:
                self._current_section.append(clean)


def _looks_restricted(text: str, final_url: str) -> bool:
    lowered = text.lower()
    path = urlsplit(final_url).path.lower()
    return any(marker in lowered for marker in _LOGIN_MARKERS) or any(
        marker in path for marker in ("/login", "/signin", "/challenge", "/captcha")
    )


def _extract_html(data: bytes, final_url: str) -> _Extracted:
    text = data.decode("utf-8", errors="replace")
    if _looks_restricted(text, final_url):
        raise PermissionError("response is a login, paywall, or challenge page")
    parser = _HtmlMetadataParser()
    parser.feed(text)
    clean = " ".join(parser.article_parts).strip()
    abstract = (
        parser.meta.get("citation_abstract")
        or parser.meta.get("dc.description")
        or parser.meta.get("description")
        or ""
    ).strip()
    observed_title = (
        parser.meta.get("citation_title")
        or parser.meta.get("dc.title")
        or parser.meta.get("og:title")
        or " ".join(parser.title_parts).strip()
    )
    # Body text can contain many bibliography DOIs. Only explicit metadata is
    # strong enough to identify the fetched work.
    observed_doi = normalize_doi(
        parser.meta.get("citation_doi") or parser.meta.get("dc.identifier")
    )
    headings = [heading for heading in parser.headings if len(heading) <= 200][:50]
    positions: list[tuple[int, str]] = []
    search_from = 0
    clean_folded = clean.casefold()
    for heading in headings:
        position = clean_folded.find(heading.casefold(), search_from)
        if position < 0:
            position = clean_folded.find(heading.casefold())
        if position >= 0:
            positions.append((position, heading))
            search_from = position + len(heading)
    locators = [
        {
            "type": "html-section",
            "value": heading,
            "start": start,
            "end": positions[index + 1][0]
            if index + 1 < len(positions)
            else len(clean),
        }
        for index, (start, heading) in enumerate(positions)
    ]
    substantive_sections = [
        (match.group(1).lower(), " ".join(parts).strip())
        for heading, parts in parser.section_parts
        for match in [
            re.search(
                r"\b(introduction|methods?|results?|discussion|conclusions?)\b",
                heading,
                re.I,
            )
        ]
        if match and len(" ".join(parts).strip()) >= 80
    ]
    if (
        parser.saw_article
        and len({kind for kind, _body in substantive_sections}) >= 2
        and len(clean) >= 500
    ):
        return _Extracted(clean, "full-text", observed_doi, observed_title, locators)
    if abstract:
        return _Extracted(
            abstract,
            "abstract",
            observed_doi,
            observed_title,
            [
                {
                    "type": "html-section",
                    "value": "Abstract",
                    "start": 0,
                    "end": len(abstract),
                }
            ],
        )
    if observed_title:
        return _Extracted(
            observed_title,
            "metadata",
            observed_doi,
            observed_title,
            [
                {
                    "type": "metadata-field",
                    "value": "title",
                    "start": 0,
                    "end": len(observed_title),
                }
            ],
        )
    raise ValueError("HTML response did not contain extractable scholarly content")


def _extract_pdf(data: bytes) -> _Extracted:
    if not data.startswith(b"%PDF-"):
        raise ValueError("response labeled as PDF does not have a PDF signature")
    try:
        import io
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - dependency-gated
        raise RuntimeError(
            "PDF extraction requires pdfplumber; install research-hub-pipeline[import]"
        ) from exc
    pages: list[str] = []
    metadata: dict[str, Any] = {}
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            metadata = {
                str(key).lower(): value for key, value in (pdf.metadata or {}).items()
            }
            title = str(metadata.get("title", "") or "").strip()
            for page in pdf.pages:
                pages.append((page.extract_text() or "").strip())
    except Exception as exc:
        raise ValueError(f"PDF parse failed: {type(exc).__name__}: {exc}") from exc
    nonempty = [
        (index + 1, page_text) for index, page_text in enumerate(pages) if page_text
    ]
    combined = "\n\n".join(page_text for _, page_text in nonempty).strip()
    if not combined:
        raise ValueError("PDF contains no extractable text")
    locators: list[dict[str, Any]] = []
    cursor = 0
    for page, page_text in nonempty:
        start = cursor
        end = start + len(page_text)
        locators.append({"type": "pdf-page", "value": page, "start": start, "end": end})
        cursor = end + 2
    metadata_doi = ""
    for key in ("doi", "dc:identifier", "identifier"):
        value = normalize_doi(str(metadata.get(key, "") or ""))
        if re.fullmatch(r"10\.\d{4,9}/\S+", value, flags=re.I):
            metadata_doi = value
            break
    section_kinds = {
        match.group(1).lower()
        for match in re.finditer(
            r"(?im)^\s*(introduction|methods?|results?|discussion|conclusions?)\b",
            combined,
        )
    }
    abstract_only = (
        len(nonempty) <= 2
        and bool(re.search(r"(?im)^\s*abstract\b", combined))
        and len(combined) < 5000
    )
    if abstract_only:
        evidence_level: EvidenceLevel = "abstract"
    elif (
        len(nonempty) >= 3
        or (len(section_kinds) >= 2 and len(combined) >= 1500)
        or len(combined) >= 5000
    ):
        evidence_level = "full-text"
    else:
        evidence_level = "metadata"
    return _Extracted(combined, evidence_level, metadata_doi, title, locators)


def _crossref_metadata(payload: object) -> tuple[_Extracted, list[str]]:
    if not isinstance(payload, dict):
        raise ValueError("Crossref response root must be an object")
    message = payload.get("message")
    if not isinstance(message, dict):
        raise ValueError("Crossref response is missing message object")
    raw_title = message.get("title") or []
    title = str(
        raw_title[0] if isinstance(raw_title, list) and raw_title else raw_title or ""
    ).strip()
    doi = normalize_doi(str(message.get("DOI", "") or ""))
    abstract_html = str(message.get("abstract", "") or "")
    abstract = _html_to_text(abstract_html) if abstract_html else ""
    links = []
    for item in message.get("link") or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("URL", "") or "")
        content_type = str(item.get("content-type", "") or "").lower()
        if url and "pdf" in content_type and is_safe_fetch_url(url):
            links.append(url)
    if abstract:
        extracted = _Extracted(
            abstract,
            "abstract",
            doi,
            title,
            [
                {
                    "type": "metadata-field",
                    "value": "abstract",
                    "start": 0,
                    "end": len(abstract),
                }
            ],
        )
    elif title or doi:
        text = title or doi
        extracted = _Extracted(
            text,
            "metadata",
            doi,
            title,
            [
                {
                    "type": "metadata-field",
                    "value": "title" if title else "DOI",
                    "start": 0,
                    "end": len(text),
                }
            ],
        )
    else:
        raise ValueError("Crossref response has no DOI, title, or abstract")
    return extracted, links


def _identity(
    expected_doi: str,
    expected_title: str,
    observed_doi: str,
    observed_title: str,
) -> IdentityStatus:
    observed_doi = normalize_doi(observed_doi)
    title_similarity: float | None = None
    if expected_title and observed_title:
        title_similarity = ratio(expected_title.casefold(), observed_title.casefold())
    if expected_doi and observed_doi:
        if expected_doi != observed_doi:
            return "mismatch"
        if title_similarity is not None and title_similarity < 45:
            return "mismatch"
        if title_similarity is not None and title_similarity < 85:
            return "unverified"
        return "verified"
    if title_similarity is not None:
        if title_similarity >= 85:
            return "consistent"
        if title_similarity < 45:
            return "mismatch"
    return "unverified"


__all__ = [
    "EvidenceLevel",
    "IdentityStatus",
    "_Extracted",
    "_crossref_metadata",
    "_extract_html",
    "_extract_pdf",
    "_identity",
]

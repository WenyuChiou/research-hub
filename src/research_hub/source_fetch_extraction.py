"""Deterministic extraction and identity helpers for public source fetches."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
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
    diagnostics: dict[str, Any] = field(default_factory=dict)
    bibliographic_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class _TableCell:
    text_parts: list[str]
    char_start: int
    char_end: int = 0


class _PublicationTableParser(HTMLParser):
    """Collect isolated label/value rows with exact raw-source boundaries."""

    def __init__(self, source: str, source_bytes: bytes) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.source_bytes = source_bytes
        self._line_starts = [0]
        for match in re.finditer(r"\n", source):
            self._line_starts.append(match.end())
        self.tables: list[list[list[_TableCell]]] = []
        self._table_depth = 0
        self._table: list[list[_TableCell]] | None = None
        self._row: list[_TableCell] | None = None
        self._cell: _TableCell | None = None
        self._invalid_table = False
        self._suppressed_depth = 0

    def _offset(self) -> int:
        line, column = self.getpos()
        return self._line_starts[line - 1] + column

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if self._suppressed_depth:
            if tag not in _HtmlAbstractParser._VOID:
                self._suppressed_depth += 1
            return
        if tag in {"script", "style", "noscript", "template", "form", "nav"}:
            self._suppressed_depth = 1
            return
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._table = []
                self._invalid_table = False
            else:
                self._invalid_table = True
            return
        if self._table_depth != 1 or self._invalid_table:
            return
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None and self._cell is None:
            self._cell = _TableCell([], self._offset())

    def handle_startendtag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if self._suppressed_depth or tag in {
            "script",
            "style",
            "noscript",
            "template",
            "form",
            "nav",
        }:
            return
        self.handle_starttag(tag, attrs)
        if tag not in _HtmlAbstractParser._VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._suppressed_depth:
            self._suppressed_depth -= 1
            return
        if tag == "table":
            if self._table_depth == 1 and self._table is not None:
                if not self._invalid_table:
                    self.tables.append(self._table)
                self._table = None
                self._row = None
                self._cell = None
            self._table_depth = max(0, self._table_depth - 1)
            return
        if self._table_depth != 1 or self._invalid_table:
            return
        if tag in {"td", "th"} and self._cell is not None:
            close_start = self._offset()
            close_end = self.source.find(">", close_start)
            self._cell.char_end = len(self.source) if close_end < 0 else close_end + 1
            if self._row is not None:
                self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._table is not None:
                self._table.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if not self._suppressed_depth and self._cell is not None and data.strip():
            self._cell.text_parts.append(data.strip())


def _publication_table_candidate(
    text: str,
    data: bytes,
    metadata_parser: "_HtmlMetadataParser",
) -> tuple[dict[str, str], list[dict[str, Any]]] | None:
    parser = _PublicationTableParser(text, data)
    parser.feed(text)
    semantic_labels = {
        "doi": "doi",
        "author": "authors",
        "authors": "authors",
        "year": "year",
        "publication year": "year",
        "abstract": "abstract",
    }
    candidates: list[tuple[dict[str, str], list[tuple[str, str, _TableCell]], int]] = []
    identities: list[tuple[str, str, int]] = []
    for table_index, rows in enumerate(parser.tables, start=1):
        fields: dict[str, str] = {}
        raw_fields: list[tuple[str, str, _TableCell]] = []
        invalid = False
        for row in rows:
            if len(row) != 2:
                continue
            label = re.sub(r"\s+", " ", " ".join(row[0].text_parts)).strip(" :\t\r\n")
            value = re.sub(r"\s+", " ", " ".join(row[1].text_parts)).strip()
            normalized = label.casefold()
            if re.fullmatch(
                r"(?:article\s+|publication\s+)?title(?:\s*\(primary\))?",
                normalized,
            ):
                semantic = "title"
            else:
                semantic = semantic_labels.get(normalized, "")
            if not semantic:
                continue
            if semantic in fields:
                invalid = True
                break
            fields[semantic] = value
            raw_fields.append((semantic, label, row[1]))
        doi = normalize_doi(fields.get("doi", ""))
        fields["doi"] = doi
        if (
            not invalid
            and fields.get("title", "")
            and re.fullmatch(r"10\.\d{4,9}/\S+", doi, flags=re.I)
        ):
            identities.append(
                (
                    re.sub(r"\s+", " ", fields["title"]).casefold(),
                    doi.casefold(),
                    table_index,
                )
            )
        if (
            not invalid
            and len(fields.get("title", "")) >= 4
            and re.fullmatch(r"10\.\d{4,9}/\S+", doi, flags=re.I)
            and fields.get("authors", "")
            and re.fullmatch(r"(?:18|19|20|21)\d{2}", fields.get("year", ""))
            and len(fields.get("abstract", "")) >= 30
        ):
            candidates.append((fields, raw_fields, table_index))
    if len(candidates) != 1:
        return None
    fields, raw_fields, table_index = candidates[0]
    candidate_identity = (
        re.sub(r"\s+", " ", fields["title"]).casefold(),
        fields["doi"].casefold(),
    )
    if any(identity[:2] != candidate_identity for identity in identities):
        return None
    meta_groups = {
        "title": ("citation_title", "dc.title"),
        "doi": ("citation_doi", "dc.identifier"),
        "abstract": ("citation_abstract", "dc.description"),
    }
    for semantic, names in meta_groups.items():
        values = [
            value.strip()
            for name in names
            for value in metadata_parser.meta_values.get(name, [])
            if value.strip()
        ]
        normalized = {
            normalize_doi(value)
            if semantic == "doi"
            else re.sub(r"\s+", " ", value).casefold()
            for value in values
        }
        table_value = (
            normalize_doi(fields[semantic])
            if semantic == "doi"
            else re.sub(r"\s+", " ", fields[semantic]).casefold()
        )
        if len(normalized) > 1 or (normalized and table_value not in normalized):
            return None
    provenance: list[dict[str, Any]] = []
    for semantic, label, cell in raw_fields:
        char_start, char_end = cell.char_start, cell.char_end
        byte_start = len(text[:char_start].encode("utf-8"))
        byte_end = len(text[:char_end].encode("utf-8"))
        raw_element = data[byte_start:byte_end]
        provenance.append(
            {
                "field": semantic,
                "label": label,
                "locator": f"table[{table_index}]",
                "raw_characters": [char_start, char_end],
                "raw_utf8_bytes": [byte_start, byte_end],
                "raw_element_sha256": sha256(raw_element).hexdigest(),
                "clean_value_sha256": sha256(
                    fields[semantic].encode("utf-8")
                ).hexdigest(),
            }
        )
    return fields, provenance


class _HtmlAbstractParser(HTMLParser):
    """Read an explicitly marked abstract container, excluding page chrome."""

    _VOID = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.hidden: list[bool] = []
        self.root_depth: int | None = None
        self.parts: list[str] = []
        self.abstracts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._VOID:
            return
        values = dict(attrs)
        style = str(values.get("style") or "")
        hidden = (
            "hidden" in values
            or str(values.get("aria-hidden") or "").casefold() == "true"
            or bool(
                re.search(
                    r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*(?:hidden|collapse))\s*(?:!important\s*)?(?:;|$)",
                    style,
                    re.I,
                )
            )
        )
        markers = " ".join(
            str(values.get(k) or "") for k in ("id", "class", "itemprop")
        )
        restricted = {"script", "style", "noscript", "template", "form", "nav"}
        if (
            self.root_depth is None
            and tag in {"div", "section", "p", "span"}
            and not restricted.intersection(self.stack)
            and not hidden
            and not any(self.hidden)
            and re.search(r"(?:^|[\s_-])abstract(?:portal)?(?:$|[\s_-])", markers, re.I)
        ):
            self.root_depth = len(self.stack)
            self.parts = []
        self.stack.append(tag)
        self.hidden.append(hidden)

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag not in self.stack:
            return
        index = len(self.stack) - 1 - self.stack[::-1].index(tag)
        del self.stack[index:]
        del self.hidden[index:]
        if self.root_depth is not None and len(self.stack) <= self.root_depth:
            text = " ".join(self.parts).strip()
            text = re.sub(r"^abstract\s*[:.\-]?\s+", "", text, flags=re.I)
            if len(text) >= 30:
                self.abstracts.append(text)
            self.root_depth = None

    def handle_data(self, data: str) -> None:
        if (
            self.root_depth is not None
            and not any(self.hidden)
            and not {
                "script",
                "style",
                "noscript",
                "template",
                "form",
                "nav",
            }.intersection(self.stack)
        ):
            if data.strip():
                self.parts.append(data.strip())


class _HtmlMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.headings: list[str] = []
        self.meta: dict[str, str] = {}
        self.meta_values: dict[str, list[str]] = {}
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
                self.meta_values.setdefault(name, []).append(content)

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
    try:
        lossless_text: str | None = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        lossless_text = None
    if _looks_restricted(text, final_url):
        raise PermissionError("response is a login, paywall, or challenge page")
    parser = _HtmlMetadataParser()
    parser.feed(text)
    abstract_parser = _HtmlAbstractParser()
    abstract_parser.feed(text)
    table_candidate = (
        _publication_table_candidate(lossless_text, data, parser)
        if lossless_text is not None
        else None
    )
    clean = " ".join(parser.article_parts).strip()
    abstract = (
        parser.meta.get("citation_abstract")
        or parser.meta.get("dc.description")
        or next(iter(abstract_parser.abstracts), "")
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
    # dc.identifier may contain a page URL, ISBN or repository ID. Prefix
    # normalization alone does not establish DOI syntax. Keep all raw metadata
    # in the saved response; expose only an unambiguous DOI from these fields.
    metadata_dois = {
        normalized
        for name in ("citation_doi", "dc.identifier")
        for value in parser.meta_values.get(name, [])
        if re.fullmatch(r"10\.\d{4,9}/\S+", normalized := normalize_doi(value), re.IGNORECASE)
    }
    observed_doi = next(iter(metadata_dois)) if len(metadata_dois) == 1 else ""
    table_fields: dict[str, str] = {}
    field_provenance: list[dict[str, Any]] = []
    if table_candidate is not None:
        table_fields, field_provenance = table_candidate
        observed_doi = table_fields["doi"]
        observed_title = table_fields["title"]
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
        return _Extracted(
            clean,
            "full-text",
            observed_doi,
            observed_title,
            locators,
            diagnostics={"publication_table_count": 1} if table_fields else {},
            bibliographic_metadata=table_fields,
        )
    if table_fields:
        table_abstract = table_fields["abstract"]
        return _Extracted(
            table_abstract,
            "abstract",
            observed_doi,
            observed_title,
            [
                {
                    "type": "html-publication-table",
                    "value": "Abstract",
                    "start": 0,
                    "end": len(table_abstract),
                    "source_sha256": sha256(data).hexdigest(),
                    "fields": field_provenance,
                }
            ],
            diagnostics={"publication_table_count": 1},
            bibliographic_metadata=table_fields,
        )
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
    default_media_box_pages: list[int] = []
    try:
        pdf_buffer = io.BytesIO(data)
        pdf = pdfplumber.open(pdf_buffer)
        try:
            metadata = {
                str(key).lower(): value for key, value in (pdf.metadata or {}).items()
            }
            title = str(metadata.get("title", "") or "").strip()
            for page in pdf.pages:
                pages.append((page.extract_text() or "").strip())
        finally:
            pdf_buffer.close()
    except TypeError as exc:
        if "'NoneType' object is not iterable" not in str(exc):
            raise ValueError(f"PDF parse failed: {type(exc).__name__}: {exc}") from exc
        try:
            from pdfminer.pdfpage import PDFPage
            from pdfplumber.page import Page, resolve_all

            pages = []
            pdf_buffer = io.BytesIO(data)
            pdf = pdfplumber.open(pdf_buffer)
            recovered_pages = []
            try:
                metadata = {
                    str(key).lower(): value
                    for key, value in (pdf.metadata or {}).items()
                }
                title = str(metadata.get("title", "") or "").strip()
                doctop = 0
                for page_number, page_obj in enumerate(
                    PDFPage.create_pages(pdf.doc), start=1
                ):
                    if resolve_all(page_obj.attrs.get("MediaBox")) is None:
                        page_obj.attrs["MediaBox"] = [0.0, 0.0, 612.0, 792.0]
                        default_media_box_pages.append(page_number)
                    page = Page(pdf, page_obj, page_number, initial_doctop=doctop)
                    recovered_pages.append(page)
                    pages.append((page.extract_text() or "").strip())
                    doctop += page.height
            finally:
                for recovered_page in recovered_pages:
                    recovered_page.close()
                pdf_buffer.close()
            if not default_media_box_pages:
                raise exc
        except TypeError as recovery_exc:
            raise ValueError(
                f"PDF parse failed: {type(recovery_exc).__name__}: {recovery_exc}"
            ) from recovery_exc
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
    diagnostics = {
        "pages_total": len(pages),
        "readable_pages": [page for page, _text in nonempty],
        "blank_pages": [
            index + 1 for index, page_text in enumerate(pages) if not page_text
        ],
        "omitted_pages": [],
    }
    if default_media_box_pages:
        diagnostics.update(
            {
                "geometry_default_pages": default_media_box_pages,
                "geometry_default_media_box": [0.0, 0.0, 612.0, 792.0],
                "extraction_fidelity": (
                    "Page structure and readable-page coverage were preserved; "
                    "reading-order and complete readable-content fidelity remain pending."
                ),
            }
        )
        locators.append(
            {
                "type": "pdf-geometry-recovery",
                "value": "MediaBox",
                "start": 0,
                "end": len(combined),
                **diagnostics,
            }
        )
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
    return _Extracted(
        combined,
        evidence_level,
        metadata_doi,
        title,
        locators,
        diagnostics=diagnostics,
    )


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

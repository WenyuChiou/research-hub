"""Deterministic extraction and identity helpers for public source fetches."""

from __future__ import annotations

from collections import Counter
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
_TEXT_CONTENT_TYPES = {"text/markdown", "text/plain", "text/x-markdown"}


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


class _HtmlRestrictionParser(HTMLParser):
    """Collect visible restriction text without treating script config as content."""

    _SUPPRESSED = {"script", "style", "template"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.suppressed_depth = 0
        self.form_depth = 0
        self.restricted_form = False

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        values = {str(key).lower(): str(value or "") for key, value in attrs}
        if self.suppressed_depth:
            if tag not in _HtmlAbstractParser._VOID:
                self.suppressed_depth += 1
            return
        if tag in self._SUPPRESSED:
            self.suppressed_depth = 1
            return
        if tag == "form":
            self.form_depth += 1
            action = values.get("action", "").lower()
            if any(
                marker in action
                for marker in ("/login", "/signin", "/challenge", "/captcha")
            ):
                self.restricted_form = True
        elif (
            tag == "input"
            and self.form_depth
            and values.get("type", "").lower() == "password"
        ):
            self.restricted_form = True

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _HtmlAbstractParser._VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.suppressed_depth:
            if tag in self._SUPPRESSED or self.suppressed_depth > 1:
                self.suppressed_depth -= 1
            return
        if tag == "form" and self.form_depth:
            self.form_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.suppressed_depth and data.strip():
            self.parts.append(data.strip())


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
        # Reuse the document parser's visible reference-heading scope before
        # collecting table rows, rather than implementing a second heading rule.
        self._identity_context = _HtmlDocumentDoiParser()

    def _offset(self) -> int:
        line, column = self.getpos()
        return self._line_starts[line - 1] + column

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        self._identity_context.handle_starttag(tag, attrs)
        if self._suppressed_depth:
            if tag not in _HtmlAbstractParser._VOID:
                self._suppressed_depth += 1
            return
        if (
            self._identity_context.reference_scope is not None
            or _HtmlDocumentDoiParser._suppresses_identity(tag, attrs)
        ):
            if tag not in _HtmlAbstractParser._VOID:
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
        if (
            self._suppressed_depth
            or self._identity_context.reference_scope is not None
            or _HtmlDocumentDoiParser._suppresses_identity(tag, attrs)
        ):
            self._identity_context.handle_startendtag(tag, attrs)
            return
        self.handle_starttag(tag, attrs)
        if tag not in _HtmlAbstractParser._VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        self._identity_context.handle_endtag(tag)
        if tag in _HtmlAbstractParser._VOID:
            return
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
        self._identity_context.handle_data(data)
        if not self._suppressed_depth and self._cell is not None and data.strip():
            self._cell.text_parts.append(data.strip())


def _publication_table_candidate(
    text: str,
    data: bytes,
    metadata_parser: "_HtmlMetadataParser",
    doi_candidates: set[str] | None = None,
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
        # Partial publication tables can still contradict another identity field.
        labeled_values = [
            (
                re.sub(r"\s+", " ", " ".join(row[0].text_parts))
                .strip(" :\t\r\n")
                .casefold(),
                " ".join(row[1].text_parts).strip(),
            )
            for row in rows
            if len(row) == 2
        ]
        if doi_candidates is not None:
            doi_candidates.update(
                doi
                for label, value in labeled_values
                if label == "doi"
                and re.fullmatch(r"10\.\d{4,9}/\S+", doi := normalize_doi(value), re.I)
            )
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


class _HtmlDocumentDoiParser(HTMLParser):
    """Read only closed, explicitly labeled article DOI spans outside citations."""

    _SUPPRESSED = {
        "script",
        "style",
        "noscript",
        "template",
        "form",
        "nav",
        "cite",
        "blockquote",
    }
    _REFERENCE_MARKER = re.compile(
        r"(?:^|[\s_-])(?:references?|bibliography|bibliographies|citations?|biblioentry|biblioref)(?:$|[\s_-])",
        re.I,
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []
        self.root_depth: int | None = None
        self.parts: list[str] = []
        self.valid = False
        self.dois: set[str] = set()
        self.heading: tuple[int, int] | None = None
        self.heading_parts: list[str] = []
        self.reference_scope: tuple[int, int] | None = None

    @classmethod
    def _suppresses_identity(cls, tag: str, attrs) -> bool:
        values = dict(attrs)
        markers = " ".join(
            str(values.get(key) or "")
            for key in ("id", "class", "role", "itemprop", "rel", "aria-label")
        )
        return (
            tag in cls._SUPPRESSED
            or bool(cls._REFERENCE_MARKER.search(markers))
            or "hidden" in values
            or str(values.get("aria-hidden") or "").casefold() == "true"
            or bool(
                re.search(
                    r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*(?:hidden|collapse))\s*(?:!important\s*)?(?:;|$)",
                    str(values.get("style") or ""),
                    re.I,
                )
            )
        )

    def handle_starttag(self, tag: str, attrs) -> None:
        suppressed = (
            bool(self.stack) and self.stack[-1][1]
        ) or self._suppresses_identity(tag, attrs)
        # Visibility is independent of reference scope: a visible next heading
        # can end that scope, while a hidden/template heading cannot.
        if re.fullmatch(r"h[1-6]", tag) and not suppressed:
            level = int(tag[1])
            if self.reference_scope is not None and level <= self.reference_scope[1]:
                self.reference_scope = None
            self.heading = (len(self.stack), level)
            self.heading_parts = []
        values = dict(attrs)
        field_suppressed = suppressed or self.reference_scope is not None
        marked = (
            tag == "span"
            and "artdoi" in str(values.get("class") or "").casefold().split()
        )
        if self.root_depth is not None:
            # Inline markup may wrap the value, but nested fields and hidden
            # fragments make the outer field ambiguous rather than truncating it.
            if marked or field_suppressed or tag not in {"a", "b", "em", "i", "strong"}:
                self.valid = False
        elif marked and not field_suppressed:
            self.root_depth = len(self.stack)
            self.parts = []
            self.valid = len({key for key, _ in attrs}) == len(attrs)
        if tag not in _HtmlAbstractParser._VOID:
            self.stack.append((tag, suppressed))

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _HtmlAbstractParser._VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _HtmlAbstractParser._VOID:
            return
        if not self.stack or self.stack[-1][0] != tag:
            if self.root_depth is not None:
                self.valid = False
            matching = [
                index
                for index, (open_tag, _) in enumerate(self.stack)
                if open_tag == tag
            ]
            if not matching:
                return
            index = matching[-1]
        else:
            index = len(self.stack) - 1
        if self.heading is not None and index <= self.heading[0]:
            if (
                index == self.heading[0]
                and tag == f"h{self.heading[1]}"
                and not self.stack[index][1]
                and re.fullmatch(
                    r"references?|bibliography|bibliographies|citations?",
                    "".join(self.heading_parts).strip(" :\t\r\n"),
                    re.I,
                )
            ):
                self.reference_scope = self.heading
            self.heading = None
        if self.reference_scope is not None and index < self.reference_scope[0]:
            self.reference_scope = None
        if self.root_depth is not None and index <= self.root_depth:
            if index == self.root_depth and tag == "span" and self.valid:
                value = "".join(self.parts).strip()
                match = re.fullmatch(r"doi\s*:\s*(\S+)", value, re.I)
                doi = normalize_doi(match.group(1)) if match else ""
                if (
                    re.fullmatch(r"10\.\d{4,9}/[^\s<>]+", doi, re.I)
                    and len(re.findall(r"10\.\d{4,9}/", doi, re.I)) == 1
                ):
                    self.dois.add(doi)
            self.root_depth = None
        del self.stack[index:]

    def handle_data(self, data: str) -> None:
        if self.root_depth is not None:
            self.parts.append(data)
        if self.heading is not None and not (self.stack and self.stack[-1][1]):
            self.heading_parts.append(data)


def _looks_restricted(text: str, final_url: str, *, html: bool = False) -> bool:
    path = urlsplit(final_url).path.lower()
    if any(
        marker in path for marker in ("/login", "/signin", "/challenge", "/captcha")
    ):
        return True
    restricted_form = False
    if html:
        parser = _HtmlRestrictionParser()
        parser.feed(text)
        text = " ".join(parser.parts)
        restricted_form = parser.restricted_form
    lowered = text.lower()
    return restricted_form or any(marker in lowered for marker in _LOGIN_MARKERS)


def _is_text_content_type(content_type: str) -> bool:
    media_type = content_type.partition(";")[0].strip().lower()
    return media_type in _TEXT_CONTENT_TYPES


def _extract_text(data: bytes, final_url: str) -> _Extracted:
    """Extract a complete, inert UTF-8 plain-text or Markdown response."""

    if b"\x00" in data:
        raise ValueError("plain-text response contains NUL bytes")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("plain-text response is not valid UTF-8") from exc
    if _looks_restricted(text, final_url, html=True):
        raise PermissionError("response is a login, paywall, or challenge page")
    if re.match(r"(?is)^\s*(?:<!doctype\s+html\b|<html\b)", text):
        raise ValueError("plain-text response contains an HTML document")
    if not text.strip():
        raise ValueError("plain-text response is empty")
    if any(ord(char) < 32 and char not in "\t\r\n" for char in text):
        raise ValueError("plain-text response contains binary control bytes")
    headings = list(re.finditer(r"(?m)^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", text))
    observed_title = ""
    for heading in headings:
        if len(heading.group(1)) == 1:
            observed_title = heading.group(2).strip()
            break
    locators = [
        {
            "type": "text-section",
            "value": heading.group(2).strip(),
            "start": heading.start(),
            "end": headings[index + 1].start()
            if index + 1 < len(headings)
            else len(text),
        }
        for index, heading in enumerate(headings)
    ]
    if not locators:
        locators = [
            {
                "type": "text-document",
                "value": "Document",
                "start": 0,
                "end": len(text),
            }
        ]
    return _Extracted(
        text,
        "full-text",
        observed_title=observed_title,
        locators=locators,
        diagnostics={"content_format": "markdown" if headings else "plain-text"},
    )


def _extract_html(data: bytes, final_url: str) -> _Extracted:
    text = data.decode("utf-8", errors="replace")
    try:
        lossless_text: str | None = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        lossless_text = None
    if _looks_restricted(text, final_url, html=True):
        raise PermissionError("response is a login, paywall, or challenge page")
    parser = _HtmlMetadataParser()
    parser.feed(text)
    abstract_parser = _HtmlAbstractParser()
    abstract_parser.feed(text)
    document_doi_parser = _HtmlDocumentDoiParser()
    document_doi_parser.feed(text)
    table_dois: set[str] = set()
    table_candidate = (
        _publication_table_candidate(lossless_text, data, parser, table_dois)
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
    # Bibliography and arbitrary body DOIs do not identify the fetched work.
    # Accept only typed metadata or an explicit document DOI field.
    # dc.identifier may contain a page URL, ISBN or repository ID. Prefix
    # normalization alone does not establish DOI syntax. Keep all raw metadata
    # in the saved response; expose only an unambiguous DOI from these fields.
    metadata_dois = {
        normalized
        for name in ("citation_doi", "dc.identifier")
        for value in parser.meta_values.get(name, [])
        if re.fullmatch(
            r"10\.\d{4,9}/\S+", normalized := normalize_doi(value), re.IGNORECASE
        )
    }
    identity_dois = metadata_dois | document_doi_parser.dois
    if table_candidate is not None:
        identity_dois.add(table_candidate[0]["doi"])
    observed_doi = (
        next(iter(identity_dois))
        if len(identity_dois) == 1 and not (table_dois - identity_dois)
        else ""
    )
    table_fields: dict[str, str] = {}
    field_provenance: list[dict[str, Any]] = []
    if table_candidate is not None and observed_doi == table_candidate[0]["doi"]:
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


_DOCUMENT_FILENAME_TITLE = re.compile(
    r"^[^\s<>:\"/\\|?*]+\.(?:pdf|dvi|ps|eps|tex|doc|docx|rtf|odt)$", re.I
)
_NON_TITLE_FIRST_PAGE_LINE = re.compile(
    r"^(?:abstract|keywords?|introduction|doi\b|https?://|arxiv\b|preprint\b)", re.I
)


def _pdf_observed_title(
    metadata_title: str, first_page_text: str
) -> tuple[str, dict[str, Any] | None]:
    """Return metadata title or a conservative, located first-page proposal."""

    metadata_title = metadata_title.strip()
    if metadata_title and not _DOCUMENT_FILENAME_TITLE.fullmatch(metadata_title):
        return metadata_title, None

    bounded_text = first_page_text[:1600]
    for match in re.finditer(r"[^\r\n]+", bounded_text):
        if (
            match.end() == len(bounded_text)
            and len(first_page_text) > len(bounded_text)
            and first_page_text[len(bounded_text)] not in "\r\n"
        ):
            continue
        candidate = " ".join(match.group().split())
        words = re.findall(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", candidate)
        if (
            15 <= len(candidate) <= 240
            and 4 <= len(words) <= 30
            and sum(char.isalpha() for char in candidate) >= 12
            and not _NON_TITLE_FIRST_PAGE_LINE.match(candidate)
            and "@" not in candidate
        ):
            status = "filename-like" if metadata_title else "missing"
            return candidate, {
                "type": "pdf-observed-title",
                "value": candidate,
                "quotation": match.group(),
                "page": 1,
                "start": match.start(),
                "end": match.end(),
                "provenance": "conservative-first-page-line",
                "proposal": True,
                "rejected_metadata_title": metadata_title,
                "rejected_metadata_title_status": status,
            }
    return "", None


_PDF_SECTION_NUMBER = r"\d+(?:\.\d+)*(?:\.[ \t]*|[ \t]+)"
_PDF_BODY_HEADING = re.compile(
    rf"(?:{_PDF_SECTION_NUMBER})?"
    r"(introduction|methods?|results?|discussion|conclusions?)[ \t]*[:.]?",
    re.I,
)


def _pdf_reading_order_text(
    page: Any, original: str
) -> tuple[str, dict[str, Any] | None]:
    """Reorder only two sustained prose flows with an observed clear gutter."""
    words = page.extract_words()
    rows: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if not rows or abs(word["top"] - rows[-1][0]["top"]) > 3:
            rows.append([])
        rows[-1].append(word)
    for row in rows:
        row.sort(key=lambda w: w["x0"])
    candidates = {
        (left["x1"] + right["x0"]) / 2
        for row in rows
        for left, right in zip(row, row[1:])
        if right["x0"] - left["x1"] >= 18
        and page.width * 0.3 < (left["x1"] + right["x0"]) / 2 < page.width * 0.7
    }
    if not candidates:
        return original, None

    def pending(reason: str) -> tuple[str, dict[str, Any]]:
        return original, {
            "status": "pending",
            "reason": reason,
            "words": len(words),
            "source_text_sha256": sha256(original.encode()).hexdigest(),
            "output_text_sha256": sha256(original.encode()).hexdigest(),
        }

    def support(point: float) -> list[int]:
        found = []
        for index, row in enumerate(rows):
            left = [w for w in row if w["x1"] <= point]
            right = [w for w in row if w["x0"] >= point]
            if left and right and len(left) + len(right) == len(row):
                if min(w["x0"] for w in right) - max(w["x1"] for w in left) >= 18:
                    found.append(index)
        return found

    votes = [(point, support(point)) for point in sorted(candidates)]
    point, supported = max(
        votes, key=lambda item: (len(item[1]), -abs(item[0] - page.width / 2))
    )
    if len(supported) < 6:
        return pending("insufficient-sustained-column-geometry")
    if any(
        abs(other - point) > 40 and len(indices) >= len(supported) * 0.85
        for other, indices in votes
    ):
        return pending("multiple-gutters-or-table-layout")
    first, last = supported[0], supported[-1]
    body = rows[first : last + 1]
    if any(w["x0"] < point < w["x1"] for row in body for w in row):
        return pending("full-width-content-inside-column-flow")
    top, bottom = body[0][0]["top"], max(w["bottom"] for w in body[-1])
    max_line_gap = 2.5 * max(w["bottom"] - w["top"] for row in body for w in row)
    for adjacent, anchor in [
        (rows[:first][-1:], top),
        (rows[last + 1 : last + 2], bottom),
    ]:
        for row in adjacent:
            distance = min(abs(w["top"] - anchor) for w in row)
            if distance <= max_line_gap and (
                all(w["x1"] <= point for w in row) or all(w["x0"] >= point for w in row)
            ):
                return pending("adjacent-single-column-head-or-tail-unresolved")
    horizontal = [
        edge
        for edge in page.edges
        if edge.get("orientation") == "h" and edge["x0"] < point < edge["x1"]
    ]
    if any(top <= edge["top"] <= bottom for edge in horizontal) or (
        len(horizontal) >= 2
        and min(edge["top"] for edge in horizontal) <= bottom
        and max(edge["top"] for edge in horizontal) >= top
    ):
        return pending("spanning-horizontal-table-or-graphic-geometry")
    columns = [
        [[w for w in row if w["x1"] <= point] for row in body],
        [[w for w in row if w["x0"] >= point] for row in body],
    ]
    for column in columns:
        prose_rows = 0
        column_words = [w for row in column for w in row]
        if (
            sum(bool(re.fullmatch(r"[\d.,%+−-]+", w["text"])) for w in column_words)
            >= len(column_words) * 0.25
        ):
            return pending("numeric-table-or-equation-layout")
        for row in column:
            line = " ".join(w["text"] for w in row)
            letters = len(re.findall(r"[^\W\d_]", line))
            if (
                "(cid:" not in line
                and letters >= 20
                and letters >= len("".join(line.split())) * 0.65
            ):
                prose_rows += 1
        if prose_rows < 6:
            return pending("insufficient-readable-prose-in-both-columns")
    ordered_rows = rows[:first] + columns[0] + columns[1] + rows[last + 1 :]
    reordered = "\n".join(
        " ".join(w["text"] for w in row) for row in ordered_rows if row
    ).strip()
    before = Counter(char for char in original if not char.isspace())
    after = Counter(char for char in reordered if not char.isspace())
    if before != after or sum(len(row) for row in ordered_rows) != len(words):
        return pending("extracted-word-or-character-preservation-unverified")
    return reordered, {
        "status": "reordered",
        "reason": "sustained-two-column-prose",
        "gutter_x": round(point, 3),
        "words": len(words),
        "word_preservation": "verified",
        "fidelity_status": "pending",
        "source_text_sha256": sha256(original.encode()).hexdigest(),
        "output_text_sha256": sha256(reordered.encode()).hexdigest(),
    }


def _pdf_column_heading_starts(page: Any, text: str) -> list[int]:
    """Locate isolated headings merged with a separate column's prose."""
    if not _PDF_BODY_HEADING.search(text):
        return []
    rows: list[list[dict[str, Any]]] = []
    for word in sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"])):
        if not rows or abs(word["top"] - rows[-1][0]["top"]) > 3:
            rows.append([])
        rows[-1].append(word)
    lines_by_text: dict[str, list[re.Match[str]]] = {}
    for line in re.finditer(r"[^\r\n]+", text):
        lines_by_text.setdefault(" ".join(line.group().split()), []).append(line)
    starts: list[int] = []
    for row_index, row in enumerate(rows):
        row.sort(key=lambda w: w["x0"])
        parts: list[list[dict[str, Any]]] = [[]]
        for word in row:
            if parts[-1] and word["x0"] - parts[-1][-1]["x1"] >= 24:
                parts.append([])
            parts[-1].append(word)
        if len(parts) != 2:
            continue
        heading_parts = [
            (index, part)
            for index, part in enumerate(parts)
            if _PDF_BODY_HEADING.fullmatch(" ".join(w["text"] for w in part))
        ]
        if not heading_parts:
            continue
        row_text = " ".join(word["text"] for word in row)
        matching_lines = lines_by_text.get(row_text, [])
        if len(matching_lines) != 1:
            continue
        for part_index, part in heading_parts:
            # Require an adjacent paragraph in this column. A distant footer,
            # an isolated label, or prose after the next section is not proof.
            low = part[0]["x0"] - 3 if part_index == 0 else parts[0][-1]["x1"] + 12
            high = parts[1][0]["x0"] - 12 if part_index == 0 else page.width
            has_body = False
            previous_top = part[0]["top"]
            max_line_gap = 2.5 * max(w["bottom"] - w["top"] for w in part)
            paragraph_rows = 0
            for later in rows[row_index + 1 :]:
                if later[0]["top"] - previous_top > max_line_gap:
                    break
                column_words = sorted(
                    (w for w in later if w["x0"] >= low and w["x1"] <= high),
                    key=lambda w: w["x0"],
                )
                if not column_words or abs(column_words[0]["x0"] - part[0]["x0"]) > 30:
                    continue
                if any(w["bottom"] > page.height * 0.9 for w in column_words):
                    break
                body_line = " ".join(w["text"] for w in column_words)
                if _PDF_BODY_HEADING.fullmatch(body_line) or re.match(
                    rf"{_PDF_SECTION_NUMBER}[^\W\d_]", body_line
                ):
                    break
                if not re.search(r"[^\W\d_]", body_line):
                    break
                previous_top = column_words[0]["top"]
                paragraph_rows += 1
                if paragraph_rows >= 2:
                    has_body = True
                    break
            if has_body:
                line = matching_lines[0]
                fragment = re.search(
                    r"[ \t]+".join(re.escape(w["text"]) for w in part), line.group()
                )
                if fragment is not None:
                    starts.append(line.start() + fragment.start())
    return starts


def _pdf_unnumbered_body_boundary(
    text: str, headings: list[re.Match[str]], locators: list[dict[str, Any]]
) -> bool:
    """Require readable article sections on distinct pages before references."""
    references = list(
        re.finditer(r"(?im)^[ \t]*(?:references|bibliography)[ \t]*[:.]?[ \t]*$", text)
    )
    abstracts = list(re.finditer(r"(?im)^[ \t]*abstract\b", text))
    boundaries = sorted(
        {m.start() for m in headings + references} | {m.start() for m in abstracts}
    )
    body_boundaries = sorted(
        set(boundaries)
        | {
            m.start()
            for m in re.finditer(rf"(?im)^[ \t]*{_PDF_SECTION_NUMBER}[^\W\d_]", text)
        }
    )

    def page_at(offset: int) -> int:
        return next(
            (
                item["value"]
                for item in locators
                if item["type"] == "pdf-page" and item["start"] <= offset < item["end"]
            ),
            0,
        )

    def has_local_prose(heading: re.Match[str]) -> bool:
        end = next(
            (start for start in body_boundaries if start > heading.start()), len(text)
        )
        lines = text[heading.end() : end].splitlines()
        readable = [
            line
            for line in lines
            if "(cid:" not in line
            and len(re.findall(r"[^\W\d_]", line)) >= 40
            and len(re.findall(r"[^\W\d_]", line)) >= len("".join(line.split())) * 0.65
        ]
        return len(readable) >= 3 and sum(len(line) for line in readable) >= 600

    sections = sorted(
        (m for m in headings if has_local_prose(m)), key=lambda m: m.start()
    )
    cited_references = []
    for reference in references:
        end = next(
            (start for start in boundaries if start > reference.start()), len(text)
        )
        citation_lines = {
            line
            for line in text[reference.end() : end].splitlines()
            if re.search(r"\b(?:18|19|20)\d{2}[a-z]?\b", line)
            and len(re.findall(r"[^\W\d_]", line)) >= 20
        }
        if len(citation_lines) >= 2:
            cited_references.append(reference)
    for intro in sections:
        if intro.group(1).lower() != "introduction" or re.match(
            r"\s*\d", intro.group()
        ):
            continue
        intro_page = page_at(intro.start())
        if not intro_page:
            continue
        for results in sections:
            if results.group(1).lower() not in {"result", "results", "discussion"}:
                continue
            if page_at(results.start()) <= intro_page or results.start() <= intro.end():
                continue
            for conclusion in sections:
                if conclusion.group(1).lower() not in {"conclusion", "conclusions"}:
                    continue
                if page_at(conclusion.start()) <= page_at(results.start()):
                    continue
                if any(
                    page_at(ref.start()) > page_at(conclusion.start())
                    and not any(
                        intro.start() < m.start() < ref.start() for m in abstracts
                    )
                    for ref in cited_references
                ):
                    return True
    return False


def _pdf_abstract_body_unconfirmed(
    text: str, headings: list[re.Match[str]], locators: list[dict[str, Any]]
) -> bool:
    """Page count and length do not establish a body outside an abstract."""
    abstract = re.search(r"(?im)^\s*abstract\b", text)
    if abstract is None:
        return False
    after_abstract = [m for m in headings if m.start() >= abstract.end()]
    boundaries = sorted(
        {m.start() for m in headings}
        | {
            m.start()
            for m in re.finditer(
                rf"(?im)^[ \t]*(?:{_PDF_SECTION_NUMBER}[^\W\d_]|references\b|"
                r"bibliography\b|abstract\b)",
                text,
            )
        }
    )

    def has_body_text_after(heading: re.Match[str]) -> bool:
        end = next(
            (start for start in boundaries if start > heading.start()), len(text)
        )
        return any(
            re.search(r"[^\W\d_]", line)
            for line in text[heading.end() : end].splitlines()
        )

    if any(
        m.group(1).lower() == "introduction"
        and re.match(r"\s*\d", m.group(0))
        and has_body_text_after(m)
        for m in after_abstract
    ):
        return False
    # Unnumbered headings can be subheadings of a structured abstract.
    # Keywords supply an observed end boundary before such a body section.
    keywords = re.search(r"(?im)^\s*key\s*words?\s*:", text[abstract.end() :])
    if keywords is not None:
        boundary = abstract.end() + keywords.end()
        if any(
            m.start() >= boundary and has_body_text_after(m) for m in after_abstract
        ):
            return False
    return not _pdf_unnumbered_body_boundary(text, after_abstract, locators)


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
    column_heading_starts: list[list[int]] = []
    reading_order_pages: list[dict[str, Any]] = []
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
                text, order = _pdf_reading_order_text(
                    page, (page.extract_text() or "").strip()
                )
                pages.append(text)
                if order is not None:
                    reading_order_pages.append({"page": page.page_number, **order})
                column_heading_starts.append(
                    _pdf_column_heading_starts(page, pages[-1])
                )
        finally:
            pdf_buffer.close()
    except TypeError as exc:
        if "'NoneType' object is not iterable" not in str(exc):
            raise ValueError(f"PDF parse failed: {type(exc).__name__}: {exc}") from exc
        try:
            from pdfminer.pdfpage import PDFPage
            from pdfplumber.page import Page, resolve_all

            pages = []
            column_heading_starts = []
            reading_order_pages = []
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
                    text, order = _pdf_reading_order_text(
                        page, (page.extract_text() or "").strip()
                    )
                    pages.append(text)
                    if order is not None:
                        reading_order_pages.append({"page": page_number, **order})
                    column_heading_starts.append(
                        _pdf_column_heading_starts(page, pages[-1])
                    )
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
    raw_metadata_title = title
    title, title_locator = _pdf_observed_title(title, pages[0] if pages else "")
    if title_locator is not None:
        locators.append(title_locator)
    diagnostics = {
        "pages_total": len(pages),
        "readable_pages": [page for page, _text in nonempty],
        "blank_pages": [
            index + 1 for index, page_text in enumerate(pages) if not page_text
        ],
        "omitted_pages": [],
    }
    if reading_order_pages:
        diagnostics["reading_order"] = {
            "status": "pending",
            "reason": "Geometry and extracted-word checks do not confirm complete content fidelity.",
            "pages": reading_order_pages,
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
    if title_locator is not None:
        diagnostics["observed_title"] = {
            "value": title,
            "page": 1,
            "provenance": title_locator["provenance"],
            "proposal": True,
            "rejected_metadata_title": title_locator["rejected_metadata_title"],
            "rejected_metadata_title_status": title_locator[
                "rejected_metadata_title_status"
            ],
        }
    elif raw_metadata_title and _DOCUMENT_FILENAME_TITLE.fullmatch(raw_metadata_title):
        diagnostics["observed_title"] = {
            "value": "",
            "proposal": False,
            "status": "unresolved-no-readable-title",
            "rejected_metadata_title": raw_metadata_title,
            "rejected_metadata_title_status": "filename-like",
        }
    metadata_doi = ""
    for key in ("doi", "dc:identifier", "identifier"):
        value = normalize_doi(str(metadata.get(key, "") or ""))
        if re.fullmatch(r"10\.\d{4,9}/\S+", value, flags=re.I):
            metadata_doi = value
            break
    headings = list(
        re.finditer(
            rf"(?im)^[ \t]*(?:{_PDF_SECTION_NUMBER})?"
            r"(introduction|methods?|results?|discussion|conclusions?)\s*[:.]?\s*$",
            combined,
        )
    )
    for locator in locators:
        if locator["type"] != "pdf-page":
            continue
        for offset in column_heading_starts[locator["value"] - 1]:
            match = _PDF_BODY_HEADING.match(combined, locator["start"] + offset)
            if match is not None:
                headings.append(match)
    section_kinds = {match.group(1).lower() for match in headings}
    if _pdf_abstract_body_unconfirmed(combined, headings, locators):
        # Preserve all readable text and locators. This is a limit on confirmed
        # evidence, not an assertion that the document contains no other text.
        diagnostics["full_body_status"] = "unconfirmed"
        diagnostics["full_body_reason"] = "abstract-without-observed-body-boundary"
        evidence_level: EvidenceLevel = "abstract"
    elif (
        len(nonempty) >= 3
        or (len(section_kinds) >= 2 and len(combined) >= 1500)
        or len(combined) >= 5000
    ):
        evidence_level = "full-text"
    elif re.search(r"(?im)^\s*abstract\b", combined):
        diagnostics["full_body_status"] = "unconfirmed"
        diagnostics["full_body_reason"] = (
            "body-boundary-insufficient-full-text-evidence"
        )
        evidence_level = "abstract"
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


def _source_identity(
    expected_doi: str, expected_title: str, extracted: _Extracted
) -> IdentityStatus:
    """Evaluate authoritative identity without promoting a title proposal."""

    title_diagnostics = extracted.diagnostics.get("observed_title")
    observed_title = extracted.observed_title
    if (
        isinstance(title_diagnostics, dict)
        and title_diagnostics.get("proposal") is True
    ):
        observed_title = ""
    return _identity(
        expected_doi,
        expected_title,
        extracted.observed_doi,
        observed_title,
    )


__all__ = [
    "EvidenceLevel",
    "IdentityStatus",
    "_Extracted",
    "_crossref_metadata",
    "_extract_html",
    "_extract_pdf",
    "_extract_text",
    "_identity",
    "_is_text_content_type",
    "_source_identity",
]

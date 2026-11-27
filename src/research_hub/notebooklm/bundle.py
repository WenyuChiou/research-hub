"""Bundle a cluster's papers into a drag-drop-ready folder for NotebookLM."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from research_hub.utils.doi import normalize_doi as _normalize_doi

logger = logging.getLogger(__name__)

@dataclass
class BundleEntry:
    doi: str
    title: str
    obsidian_path: str
    action: str
    pdf_path: str = ""
    pdf_source: str = ""
    url: str = ""
    text: str = ""
    skip_reason: str = ""
    url_quality: str = ""
    url_quality_reason: str = ""
    url_quality_signal: str = ""


@dataclass
class BundleReport:
    cluster_slug: str
    bundle_dir: Path
    entries: list[BundleEntry] = field(default_factory=list)
    created_at: str = ""

    @property
    def pdf_count(self) -> int:
        return sum(1 for entry in self.entries if entry.action == "pdf")

    @property
    def url_count(self) -> int:
        return sum(1 for entry in self.entries if entry.action == "url")

    @property
    def text_count(self) -> int:
        return sum(1 for entry in self.entries if entry.action == "text")

    @property
    def skip_count(self) -> int:
        return sum(1 for entry in self.entries if entry.action == "skip")


def _read_frontmatter(md_path: Path) -> str:
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end < 0:
        return ""
    return text[3:end]


def _parse_note_metadata(md_path: Path) -> dict[str, str]:
    """Extract title, doi, url, authors, year, summarize_status from note YAML frontmatter."""
    meta = {"title": "", "doi": "", "url": "", "authors": "", "year": "", "summarize_status": ""}
    frontmatter = _read_frontmatter(md_path)
    if not frontmatter:
        return meta
    for key in ("title", "doi", "url", "authors", "year", "summarize_status"):
        pattern = rf'^{key}:\s*[\'"]?([^\'"\n]*)[\'"]?'
        match = re.search(pattern, frontmatter, re.MULTILINE)
        if match:
            value = match.group(1).strip()
            meta[key] = _normalize_doi(value) if key == "doi" else value
    return meta


def _read_abstract_content(md_path: Path) -> str | None:
    """Read Abstract content without counting callout syntax or block anchors."""
    from research_hub.markdown_conventions import unwrap_callout
    from research_hub.paper_summarize import extract_markdown_section

    try:
        body = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None  # unreadable is unknown, not an absence observation
    abstract = unwrap_callout(extract_markdown_section(body, "Abstract"))
    # Strip standalone Obsidian IDs, preserving inline scientific notation.
    return re.sub(r"(?m)^\^[A-Za-z0-9_-]+[ \t]*\r?$", "", abstract).strip()


def _extract_abstract(md_path: Path, meta: dict[str, str]) -> str:
    """F8 content ladder rung 3: the paper's abstract as a self-describing
    text source. Pulls the `## Abstract` section from the note body (the
    abstract is not a frontmatter key). Returns "" if absent/placeholder
    so the caller can fall through to the URL rung. Prefixed with
    title/DOI so the NotebookLM text source is identifiable."""
    abstract = _read_abstract_content(md_path)
    if abstract is None:
        return ""
    # Skip empty / TODO-placeholder abstracts (research-hub leaves these
    # when summarize had no abstract — uploading them is noise).
    if len(abstract) < 40 or abstract.lower().startswith(("[", "todo", "n/a")):
        return ""
    header = []
    if meta.get("title"):
        header.append(meta["title"])
    if meta.get("doi"):
        header.append(f"DOI: {meta['doi']}")
    prefix = ("\n".join(header) + "\n\n") if header else ""
    return (prefix + "Abstract\n" + abstract)[:8000]


_EXPLICIT_DOI_RE = re.compile(r"10\.\d{4,9}[/_-][^\s]+", re.IGNORECASE)


def _is_within_pdfs_root(candidate: Path, pdfs_root: Path) -> bool:
    try:
        return candidate.resolve().is_relative_to(pdfs_root)
    except OSError:
        return False


def _has_conflicting_doi(stem: str, normalized_doi: str) -> bool:
    if not normalized_doi:
        return False
    for match in _EXPLICIT_DOI_RE.finditer(stem):
        raw = re.sub(r"^(10\.\d{4,9})[/_-]", r"\1/", match.group(0))
        if _normalize_doi(raw) != normalized_doi:
            return True
    return False


def _matches_token_boundary(text: str, token: str) -> bool:
    if not token:
        return False
    pattern = re.compile(
        rf"(?<![a-z0-9.]){re.escape(token)}(?![a-z0-9]|\.[a-z0-9])",
        re.IGNORECASE,
    )
    return pattern.search(text) is not None


def _match_pdf_for_note_with_source(
    pdfs_dir: Path,
    note_path: Path | None,
    doi: str,
    *,
    pdf_index: list[Path] | None = None,
) -> tuple[Path | None, str]:
    """Match a PDF for a note and return (path, source_tag)."""
    normalized = _normalize_doi(doi) if doi else ""
    if not pdfs_dir.exists() or (not normalized and note_path is None):
        return None, ""

    pdfs_root = pdfs_dir.resolve()
    if normalized:
        exact = pdfs_dir / (re.sub(r"[^a-z0-9._-]", "_", normalized) + ".pdf")
        if exact.exists() and _is_within_pdfs_root(exact, pdfs_root):
            return exact, "local-doi"

    raw_candidates = pdf_index if pdf_index is not None else sorted(pdfs_dir.rglob("*.pdf"))
    safe_candidates = [
        candidate
        for candidate in raw_candidates
        if _is_within_pdfs_root(candidate, pdfs_root)
        and not _has_conflicting_doi(candidate.stem, normalized)
    ]

    if normalized:
        doi_underscore = re.sub(r"[^a-z0-9._-]", "_", normalized)
        doi_hyphen = re.sub(r"[^a-z0-9._-]", "-", normalized)
        doi_slash_hyphen = normalized.replace("/", "-")
        variants = list(dict.fromkeys(v for v in (doi_underscore, doi_hyphen, doi_slash_hyphen) if v))
        variant_lowers = {v.lower() for v in variants}
        stem_matches = [c for c in safe_candidates if c.stem.lower() in variant_lowers]
        if len(stem_matches) == 1:
            return stem_matches[0], "local-doi"
        if len(stem_matches) >= 2:
            return None, ""
        boundary_matches = [
            c for c in safe_candidates if any(_matches_token_boundary(c.stem, v) for v in variants)
        ]
        if len(boundary_matches) == 1:
            return boundary_matches[0], "local-doi"
        if len(boundary_matches) >= 2:
            return None, ""

    if note_path is not None and note_path.stem:
        stem_lower = note_path.stem.lower()
        note_stem_matches = [c for c in safe_candidates if c.stem.lower() == stem_lower]
        if len(note_stem_matches) == 1:
            return note_stem_matches[0], "local-slug"
        if len(note_stem_matches) >= 2:
            return None, ""

    if normalized and "/" in normalized:
        tail = normalized.rsplit("/", 1)[-1]
        if len(tail) >= 4 and (not tail.isdigit() or len(tail) >= 6):
            tail_matches = [
                candidate
                for candidate in safe_candidates
                if _matches_token_boundary(candidate.stem, tail)
            ]
            if len(tail_matches) == 1:
                return tail_matches[0], "local-doi"
            if len(tail_matches) >= 2:
                return None, ""

    return None, ""


def _match_pdf_for_note(
    pdfs_dir: Path,
    note_path: Path | None,
    doi: str,
    *,
    pdf_index: list[Path] | None = None,
) -> Path | None:
    """Match a PDF for a note using strict DOI/stem token boundaries."""
    matched, _ = _match_pdf_for_note_with_source(
        pdfs_dir, note_path, doi, pdf_index=pdf_index
    )
    return matched


def _find_pdf_for_doi(
    pdfs_dir: Path,
    doi: str,
    *,
    note_path: Path | None = None,
    pdf_index: list[Path] | None = None,
) -> Path | None:
    """Look for a PDF file matching the DOI.

    v0.88.11: callers can pass a precomputed ``pdf_index`` (sorted
    ``rglob("*.pdf")``) so they don't pay the O(P) directory walk for
    every paper in a cluster. ``bundle_cluster`` now builds the index
    once at the top of the loop, dropping `_find_pdf_for_doi`'s
    cluster-wide cost from O(P²) to O(P) — a 50× speedup at 49 papers
    and a 500× speedup at 500.
    """
    return _match_pdf_for_note(pdfs_dir, note_path, doi, pdf_index=pdf_index)


_DEFAULT_MATCH_PDF_FOR_NOTE = _match_pdf_for_note
_DEFAULT_FIND_PDF_FOR_DOI = _find_pdf_for_doi


def _extract_first_author_surname(authors_str: str) -> str:
    """Extract the first author's last name from a semicolon-separated string.

    Handles "Last, First; Last2, First2; ..." format (Zotero standard)
    and "First Last; First2 Last2; ..." format.
    """
    if not authors_str:
        return ""
    first_author = authors_str.split(";")[0].strip()
    if "," in first_author:
        return first_author.split(",")[0].strip()
    parts = first_author.split()
    return parts[-1] if parts else ""


def _find_pdf_by_author_year(
    pdfs_dir: Path,
    authors: str,
    year: str,
    *,
    pdf_index: list[Path] | None = None,
) -> Path | None:
    """Match a PDF by Author_Year naming convention (e.g., Ben-Zion_2025.pdf).

    The surname must appear at the START of the filename (case-insensitive)
    followed by a non-alphabetic separator (`_`, `-`, space, digit).
    This prevents false positives like "Li" matching "Liu" or "Ma"
    matching "Mao".

    v0.88.11: same memoize pattern as `_find_pdf_for_doi`.
    """
    if not pdfs_dir.exists():
        return None
    surname = _extract_first_author_surname(authors)
    if not surname or len(surname) < 2:
        return None
    pdfs_root = pdfs_dir.resolve()
    escaped = re.escape(surname.lower())
    pattern = re.compile(rf"^{escaped}(?:[_\-\s\d]|$)", re.IGNORECASE)
    year_str = str(year).strip() if year else ""
    candidates = pdf_index if pdf_index is not None else sorted(pdfs_dir.rglob("*.pdf"))
    matches = [
        candidate
        for candidate in candidates
        if _is_within_pdfs_root(candidate, pdfs_root)
        and pattern.match(candidate.stem)
        and (not year_str or year_str in candidate.stem)
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def _resolve_local_pdf(
    pdfs_dir: Path,
    note_path: Path,
    meta: dict[str, str],
    doi: str,
    pdf_index: list[Path],
) -> tuple[Path | None, str]:
    pdf: Path | None = None
    pdf_source = ""
    if _find_pdf_for_doi is _DEFAULT_FIND_PDF_FOR_DOI and _match_pdf_for_note is _DEFAULT_MATCH_PDF_FOR_NOTE:
        pdf, pdf_source = _match_pdf_for_note_with_source(
            pdfs_dir, note_path, doi, pdf_index=pdf_index
        )
    else:
        pdf = _find_pdf_for_doi(pdfs_dir, doi, note_path=note_path, pdf_index=pdf_index)
        if pdf is not None:
            pdf_source = "local-doi" if doi else "local-slug"
    if pdf is None:
        pdf = _find_pdf_by_author_year(
            pdfs_dir, meta.get("authors", ""), meta.get("year", ""),
            pdf_index=pdf_index,
        )
        if pdf is not None:
            normalized_doi = _normalize_doi(doi) if doi else ""
            if normalized_doi and _has_conflicting_doi(pdf.stem, normalized_doi):
                pdf = None
            else:
                pdf_source = "local-slug"
    if pdf is not None and pdfs_dir.exists():
        if not _is_within_pdfs_root(pdf, pdfs_dir.resolve()):
            return None, ""
    return pdf, pdf_source


def _copy_file_no_clobber(src: Path, dst: Path) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(dst, flags, 0o644)
    try:
        with src.open("rb") as in_handle, os.fdopen(fd, "wb") as out_handle:
            fd = -1
            shutil.copyfileobj(in_handle, out_handle)
    finally:
        if fd >= 0:
            os.close(fd)
    try:
        shutil.copystat(src, dst)
    except OSError:
        pass


def _pick_url(meta: dict[str, str]) -> str:
    """Prefer DOI URL, then existing `url` YAML field."""
    doi = _normalize_doi(meta.get("doi", ""))
    url = meta.get("url", "").strip()

    if doi:
        arxiv_match = re.search(r"arxiv[.:/]?([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)", doi, re.IGNORECASE)
        if arxiv_match:
            return f"https://arxiv.org/abs/{arxiv_match.group(1)}"
        return f"https://doi.org/{doi}"
    if url.startswith(("http://", "https://")):
        return url
    return ""


def bundle_cluster(
    cluster,
    cfg,
    out_root: Path | None = None,
    download_pdfs: bool = False,
) -> BundleReport:
    """Walk a cluster's papers and emit a drag-drop bundle."""
    from research_hub.vault.sync import list_cluster_notes

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundles_root = out_root or (cfg.research_hub_dir / "bundles")
    bundles_root.mkdir(parents=True, exist_ok=True)
    base_dir_name = f"{cluster.slug}-{timestamp}"
    bundle_dir = bundles_root / base_dir_name
    dir_suffix = 2
    while True:
        try:
            bundle_dir.mkdir(parents=False, exist_ok=False)
            break
        except FileExistsError:
            bundle_dir = bundles_root / f"{base_dir_name}-{dir_suffix}"
            dir_suffix += 1
    bundle_pdfs = bundle_dir / "pdfs"
    bundle_pdfs.mkdir(parents=False, exist_ok=False)

    report = BundleReport(
        cluster_slug=cluster.slug,
        bundle_dir=bundle_dir,
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    pdfs_dir = cfg.root / "pdfs"
    notes = list_cluster_notes(cluster.slug, cfg.raw)
    # v0.88.11: build the PDF index ONCE per bundle instead of having
    # `_find_pdf_for_doi` rglob the whole directory for every paper
    # (was O(P²) — 49 papers × 49 file-system walks). At 49 papers this
    # already saves ~50× time; at 500 papers ~500×.
    pdf_index = sorted(pdfs_dir.rglob("*.pdf")) if pdfs_dir.exists() else []
    copied_pdfs: dict[str, Path] = {}
    for note_path in notes:
        meta = _parse_note_metadata(note_path)
        entry = BundleEntry(
            doi=meta.get("doi", ""),
            title=meta.get("title") or note_path.stem,
            obsidian_path=str(note_path),
            action="skip",
        )

        pdf, resolved_source = _resolve_local_pdf(
            pdfs_dir, note_path, meta, entry.doi, pdf_index
        )
        if pdf is not None:
            entry.pdf_source = resolved_source

        fetch_result = None
        if pdf is None and download_pdfs:
            from research_hub.notebooklm.pdf_fetcher import fetch_paper_pdf

            fetch_result = fetch_paper_pdf(entry.doi, note_path.stem, pdfs_dir, cfg=cfg)
            if fetch_result.ok:
                pdf = fetch_result.path
                entry.pdf_source = fetch_result.source
            else:
                logger.info("pdf_fetch failed for %s: %s", entry.doi or note_path.stem, fetch_result.error)

        # Classify the URL quality so the field is always written into the
        # manifest entry (even when the entry ends up taking the pdf path).
        # When a local PDF is already present (pdf is not None) the URL will
        # never be uploaded, so we skip the network probe to avoid wasted
        # traffic — classify with probe=False in that case.
        url = _pick_url(meta)
        if url:
            from research_hub.notebooklm.url_quality import classify_url_source
            from research_hub.paper_summarize import is_bad_abstract

            summarize_status = meta.get("summarize_status", "")
            # Summary completion cannot clear the separate absent/short-abstract
            # prior. Observe the saved Abstract, without changing the note or
            # treating supplied summaries as acquisition/access evidence.
            abstract_usable = None
            if pdf is None:
                abstract = _read_abstract_content(note_path)
                if abstract is not None:
                    abstract_usable = not is_bad_abstract(abstract)
            # Only probe when there is no local PDF (pdf is None); a PDF-backed
            # entry will take action="pdf" and the URL is never uploaded.
            quality_result = classify_url_source(
                url, summarize_status, probe=(pdf is None), abstract_usable=abstract_usable,
            )
            entry.url_quality = quality_result.quality
            entry.url_quality_reason = quality_result.reason
            entry.url_quality_signal = quality_result.signal

            # Auto-prefer local PDF when the URL is known to be a likely error
            # page but no local PDF was found in the initial scan.  If a PDF
            # is already present (pdf is not None) it is handled below.
            if quality_result.quality == "likely_error_page" and pdf is None:
                pdf_retry, retry_source = _resolve_local_pdf(
                    pdfs_dir, note_path, meta, entry.doi, pdf_index
                )
                if pdf_retry is not None:
                    pdf = pdf_retry
                    entry.pdf_source = entry.pdf_source or retry_source

        if pdf is not None:
            src_resolved = pdf.resolve()
            dest_name = pdf.name
            dest_key = dest_name.casefold()
            destination = bundle_pdfs / dest_name
            if (dest_key in copied_pdfs and copied_pdfs[dest_key] != src_resolved) or (
                dest_key not in copied_pdfs and destination.exists()
            ):
                candidate_name = f"{note_path.stem}_{pdf.name}"
                candidate_key = candidate_name.casefold()
                candidate_dest = bundle_pdfs / candidate_name
                if (candidate_key in copied_pdfs and copied_pdfs[candidate_key] != src_resolved) or (
                    candidate_key not in copied_pdfs and candidate_dest.exists()
                ):
                    counter = 2
                    while True:
                        numbered_name = f"{note_path.stem}_{pdf.stem}-{counter}{pdf.suffix}"
                        numbered_key = numbered_name.casefold()
                        numbered_dest = bundle_pdfs / numbered_name
                        if (
                            numbered_key not in copied_pdfs
                            or copied_pdfs[numbered_key] == src_resolved
                        ) and (numbered_key in copied_pdfs or not numbered_dest.exists()):
                            candidate_name = numbered_name
                            break
                        counter += 1
                dest_name = candidate_name
                dest_key = dest_name.casefold()
                destination = bundle_pdfs / dest_name
            if dest_key not in copied_pdfs:
                _copy_file_no_clobber(pdf, destination)
                copied_pdfs[dest_key] = src_resolved
            entry.action = "pdf"
            entry.pdf_path = str(destination)
            report.entries.append(entry)
            continue

        # F8 content ladder rung 3: no PDF (local or OA-fetched). Prefer
        # the abstract as a copied-text source over a paywalled URL that
        # NotebookLM can't read. A *good* URL (not likely_error_page —
        # e.g. an open landing page with full text) is still better than
        # an abstract, so only take the text rung when there is no URL or
        # the URL is the suspect/paywall kind.
        #
        # "probe_cleared_failed_no_abstract": HTTP 200 but no abstract body
        # found — characteristic of Springer/Wiley skeleton paywall pages.
        # These are indistinguishable from real full-text pages by status
        # code alone, so the probe rates them "ok", but NotebookLM gets the
        # same empty shell. Treat them the same as likely_error_page and fall
        # back to the abstract text instead.
        _is_no_content = (
            entry.url_quality == "likely_error_page"
            or entry.url_quality_reason == "probe_cleared_failed_no_abstract"
        )
        if not url or _is_no_content:
            abstract = _extract_abstract(note_path, meta)
            if abstract:
                entry.action = "text"
                entry.text = abstract
                if url:
                    entry.url = url  # keep for provenance/manifest
                    entry.skip_reason = "paywall URL -> abstract text used"
                report.entries.append(entry)
                continue

        if url:
            entry.action = "url"
            entry.url = url
            if download_pdfs and fetch_result is not None:
                entry.skip_reason = "no OA; url fallback used"
            report.entries.append(entry)
            continue

        entry.skip_reason = "no DOI, no URL, no local PDF"
        report.entries.append(entry)

    sources_file = bundle_dir / "sources.txt"
    with sources_file.open("w", encoding="utf-8", newline="\n") as handle:
        for entry in report.entries:
            if entry.action == "url" and entry.url:
                handle.write(f"{entry.url}\n")

    manifest_file = bundle_dir / "manifest.json"
    manifest_file.write_text(
        json.dumps(
            {
                "cluster_slug": cluster.slug,
                "cluster_name": cluster.name,
                "created_at": report.created_at,
                "pdf_count": report.pdf_count,
                "url_count": report.url_count,
                "text_count": report.text_count,
                "skip_count": report.skip_count,
                "entries": [asdict(entry) for entry in report.entries],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    readme = bundle_dir / "README.md"
    readme.write_text(_render_readme(cluster, report), encoding="utf-8")
    pdf_sources = Counter(
        entry.pdf_source for entry in report.entries if entry.action == "pdf" and entry.pdf_source
    )
    source_summary = ", ".join(
        f"{source}: {count}" for source, count in sorted(pdf_sources.items())
    )
    print(f"bundle summary - {cluster.slug}:")
    if source_summary:
        print(f"  pdf: {report.pdf_count} ({source_summary})")
    else:
        print(f"  pdf: {report.pdf_count}")
    print(f"  url: {report.url_count}")
    print(f"  text (abstract): {report.text_count}")
    print(f"  skip: {report.skip_count}")
    return report


def _render_readme(cluster, report: BundleReport) -> str:
    lines = [
        f"# Bundle: {cluster.name}",
        "",
        f"- Cluster slug: `{cluster.slug}`",
        f"- Created at: {report.created_at}",
        (
            f"- Papers: {len(report.entries)} total "
            f"({report.pdf_count} PDFs, {report.url_count} URLs, "
            f"{report.text_count} abstracts, {report.skip_count} skipped)"
        ),
        "",
        "## Upload to NotebookLM (manual fallback)",
        "",
        (
            "1. Open <https://notebooklm.google.com/> and create or open the notebook "
            f"named `{cluster.name}`."
        ),
        "2. Drag each file from `pdfs/` into the notebook Sources panel.",
        (
            "3. For each URL in `sources.txt`, use NotebookLM's Website source flow and "
            "paste one URL at a time."
        ),
        "4. After upload, run the NotebookLM workflows you need.",
        "",
        "If you have v0.4.1+ installed, the same bundle can be uploaded automatically:",
        "",
        "```bash",
        f"research-hub notebooklm upload --cluster {cluster.slug}",
        "```",
        "",
        "## Skipped papers",
        "",
    ]
    skipped = [entry for entry in report.entries if entry.action == "skip"]
    if not skipped:
        lines.append("_None; every paper has a PDF, a URL, or an abstract text source._")
    else:
        for entry in skipped:
            lines.append(
                f"- `{entry.doi or '(no DOI)'}` {entry.title[:80]} - {entry.skip_reason}"
            )
    return "\n".join(lines) + "\n"

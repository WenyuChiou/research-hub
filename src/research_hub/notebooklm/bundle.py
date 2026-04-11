"""Bundle a cluster's papers into a drag-drop-ready folder for NotebookLM."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class BundleEntry:
    doi: str
    title: str
    obsidian_path: str
    action: str
    pdf_path: str = ""
    url: str = ""
    skip_reason: str = ""


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


def _normalize_doi(doi: str) -> str:
    if not doi:
        return ""
    normalized = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    return normalized.strip()


def _parse_note_metadata(md_path: Path) -> dict[str, str]:
    """Extract title, doi, url from note YAML frontmatter."""
    meta = {"title": "", "doi": "", "url": ""}
    frontmatter = _read_frontmatter(md_path)
    if not frontmatter:
        return meta
    for key in ("title", "doi", "url"):
        pattern = rf'^{key}:\s*[\'"]?([^\'"\n]*)[\'"]?'
        match = re.search(pattern, frontmatter, re.MULTILINE)
        if match:
            value = match.group(1).strip()
            meta[key] = _normalize_doi(value) if key == "doi" else value
    return meta


def _find_pdf_for_doi(pdfs_dir: Path, doi: str) -> Path | None:
    """Look for a PDF file matching the DOI."""
    normalized = _normalize_doi(doi)
    if not pdfs_dir.exists() or not normalized:
        return None

    exact = pdfs_dir / f"{normalized.replace('/', '_').replace(':', '_')}.pdf"
    if exact.exists():
        return exact

    tail = normalized.rsplit("/", 1)[-1]
    if tail:
        for candidate in sorted(pdfs_dir.rglob("*.pdf")):
            if tail.lower() in candidate.name.lower():
                return candidate

    doi_without_prefix = normalized.replace("/", "_")
    for candidate in sorted(pdfs_dir.rglob("*.pdf")):
        if doi_without_prefix.lower() in candidate.name.lower():
            return candidate
    return None


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
) -> BundleReport:
    """Walk a cluster's papers and emit a drag-drop bundle."""
    from research_hub.vault.sync import list_cluster_notes

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundles_root = out_root or (cfg.research_hub_dir / "bundles")
    bundle_dir = bundles_root / f"{cluster.slug}-{timestamp}"
    bundle_pdfs = bundle_dir / "pdfs"
    bundle_pdfs.mkdir(parents=True, exist_ok=True)

    report = BundleReport(
        cluster_slug=cluster.slug,
        bundle_dir=bundle_dir,
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    pdfs_dir = cfg.root / "pdfs"
    notes = list_cluster_notes(cluster.slug, cfg.raw)
    for note_path in notes:
        meta = _parse_note_metadata(note_path)
        entry = BundleEntry(
            doi=meta.get("doi", ""),
            title=meta.get("title") or note_path.stem,
            obsidian_path=str(note_path),
            action="skip",
        )

        pdf = _find_pdf_for_doi(pdfs_dir, entry.doi)
        if pdf is not None:
            destination = bundle_pdfs / pdf.name
            shutil.copy2(pdf, destination)
            entry.action = "pdf"
            entry.pdf_path = str(destination)
            report.entries.append(entry)
            continue

        url = _pick_url(meta)
        if url:
            entry.action = "url"
            entry.url = url
            report.entries.append(entry)
            continue

        entry.skip_reason = "no local PDF and no usable URL"
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
    return report


def _render_readme(cluster, report: BundleReport) -> str:
    lines = [
        f"# Bundle: {cluster.name}",
        "",
        f"- Cluster slug: `{cluster.slug}`",
        f"- Created at: {report.created_at}",
        (
            f"- Papers: {len(report.entries)} total "
            f"({report.pdf_count} PDFs, {report.url_count} URLs, {report.skip_count} skipped)"
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
        lines.append("_None; every paper has either a PDF or a URL._")
    else:
        for entry in skipped:
            lines.append(
                f"- `{entry.doi or '(no DOI)'}` {entry.title[:80]} - {entry.skip_reason}"
            )
    return "\n".join(lines) + "\n"

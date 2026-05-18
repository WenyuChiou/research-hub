"""Re-enrich existing Zotero items from DOI metadata backends."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from research_hub.search import CrossrefBackend, OpenAlexBackend

ENRICH_FIELDS = ["volume", "issue", "pages", "url", "abstractNote", "ISSN"]
_ABSTRACT_SECTION_RE = re.compile(
    r"(^##\s+Abstract\s*\n+)(.*?)(?=^---\s*$|^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
_SUMMARY_SECTION_RE = re.compile(
    r"^##\s+Summary\s*\n(.*?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
_ZOTERO_KEY_RE = re.compile(r'^zotero-key:\s*[\'"]?([^\'"\n]+)', re.MULTILINE)


@dataclass
class EnrichPlan:
    item_key: str
    title: str
    doi: str
    fields_to_fill: dict[str, str] = field(default_factory=dict)
    abstract_source: str = ""


def _to_search_field(zotero_field: str) -> str:
    """Map a Zotero field name to the normalized backend field name."""
    return {"abstractNote": "abstract", "publicationTitle": "venue"}.get(zotero_field, zotero_field)


def _result_value(result, field_name: str) -> str:
    if result is None:
        return ""
    if isinstance(result, dict):
        value = result.get(field_name, "")
        if not value and field_name == "ISSN":
            value = result.get("issn", "")
        return str(value or "").strip()
    value = getattr(result, field_name, "")
    if not value and field_name == "ISSN":
        value = getattr(result, "issn", "")
    return str(value or "").strip()


def plan_enrichment(
    zot_or_items,
    items: list[dict] | None = None,
    *,
    rate_limit_rps: float = 5.0,
    pdfs_dir: Path | None = None,
    disable_pdf_fallback: bool = False,
) -> list[EnrichPlan]:
    """Identify empty Zotero fields and plan DOI-based metadata fill-ins.

    Each per-item probe hits both Crossref AND OpenAlex (~2 outbound HTTP
    per item). For 250+ items that's 500 calls — Crossref's polite-pool
    allows ~50 rps, OpenAlex caps at ~10 rps. Default 5 rps stays safely
    under both. Override via rate_limit_rps for explicit faster/slower.

    pdfs_dir: when supplied (and disable_pdf_fallback is False), abstract
    recovery will also attempt to extract the abstract from a local PDF
    as a last resort (after all 4 online metadata sources fail).
    disable_pdf_fallback: honour cfg.disable_pdf_fallback; forces pdf_path
    to None so the PDF fallback link is never reached.
    """
    import time as _time
    if items is None:
        items = zot_or_items
    crossref = CrossrefBackend()
    openalex = OpenAlexBackend()
    sleep_s = 1.0 / max(rate_limit_rps, 0.1)
    plans: list[EnrichPlan] = []
    for item in items:
        data = item.get("data", {})
        doi = str(data.get("DOI", "") or "").strip()
        if not doi:
            continue
        empty_fields = [
            field_name
            for field_name in ENRICH_FIELDS
            if not str(data.get(field_name, "") or "").strip()
        ]
        if not empty_fields:
            continue

        fields_to_fill: dict[str, str] = {}
        abstract_source = ""
        for backend in (crossref, openalex):
            try:
                result = backend.get_paper(doi)
            except Exception:
                result = None
            _time.sleep(sleep_s)
            if result is None:
                continue
            for field_name in empty_fields:
                if field_name in fields_to_fill:
                    continue
                value = _result_value(result, _to_search_field(field_name))
                if value:
                    fields_to_fill[field_name] = value
                    if field_name == "abstractNote":
                        abstract_source = str(
                            getattr(result, "abstract_source", "") or getattr(result, "source", "") or ""
                        ).strip()
        if "abstractNote" in empty_fields and "abstractNote" not in fields_to_fill:
            try:
                from research_hub.search.abstract_recovery import recover_abstract
                from research_hub.notebooklm.pdf_fetcher import _filename_from_doi
                from research_hub.utils.doi import normalize_doi

                pdf_path: Path | None = None
                if pdfs_dir is not None and not disable_pdf_fallback:
                    normalized = normalize_doi(doi) if doi else ""
                    if normalized:
                        candidate_doi = pdfs_dir / f"{_filename_from_doi(normalized)}.pdf"
                        if candidate_doi.exists():
                            pdf_path = candidate_doi
                        else:
                            # Also try slug-based name (<slug>.pdf) derived from
                            # the item title, as a secondary convention.
                            item_data = item.get("data", {})
                            item_title = str(item_data.get("title", "") or "")
                            if item_title:
                                from research_hub.clusters import slugify
                                slug_candidate = pdfs_dir / f"{slugify(item_title)[:80]}.pdf"
                                if slug_candidate.exists():
                                    pdf_path = slug_candidate

                # Mirror discover.py: only pass pdf_path when present so a
                # stubbed/old-signature recover_abstract still works and the
                # bare `except` below can't silently swallow a TypeError.
                if pdf_path is not None:
                    recovered = recover_abstract(doi, pdf_path=pdf_path)
                else:
                    recovered = recover_abstract(doi)
            except Exception:
                recovered = None
            if recovered and recovered.text:
                fields_to_fill["abstractNote"] = recovered.text
                abstract_source = recovered.source
                _time.sleep(sleep_s)
        if fields_to_fill:
            plans.append(
                EnrichPlan(
                    item_key=item.get("key", ""),
                    title=str(data.get("title", "") or "")[:60],
                    doi=doi,
                    fields_to_fill=fields_to_fill,
                    abstract_source=abstract_source,
                )
            )
    return plans


def _cluster_raw_dir(cfg, cluster_slug: str) -> Path:
    from research_hub.clusters import ClusterRegistry

    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    subfolder = cluster.obsidian_subfolder if cluster and cluster.obsidian_subfolder else cluster_slug
    return Path(cfg.raw) / subfolder


def _index_cluster_notes(cfg, cluster_slug: str) -> dict[str, Path]:
    note_by_key: dict[str, Path] = {}
    raw_dir = _cluster_raw_dir(cfg, cluster_slug)
    if not raw_dir.exists():
        return note_by_key
    for note_path in sorted(raw_dir.glob("*.md")):
        if note_path.name in {"00_overview.md", "index.md"}:
            continue
        try:
            text = note_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text.startswith("---\n"):
            continue
        end = text.find("\n---\n", 4)
        if end < 0:
            continue
        match = _ZOTERO_KEY_RE.search(text[4:end])
        if match:
            note_by_key[match.group(1).strip()] = note_path
    return note_by_key


def _upsert_frontmatter_scalar(text: str, key: str, value: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    if end < 0:
        return text
    frontmatter = text[4:end]
    body = text[end:]
    pattern = re.compile(rf"^{re.escape(key)}:\s*.*$", re.MULTILINE)
    line = f'{key}: "{value}"'
    if pattern.search(frontmatter):
        frontmatter = pattern.sub(line, frontmatter, count=1)
    else:
        if frontmatter and not frontmatter.endswith("\n"):
            frontmatter += "\n"
        frontmatter += line + "\n"
    return f"---\n{frontmatter}{body}"


def _note_summary_has_todo(note_path: Path) -> bool:
    try:
        text = note_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    match = _SUMMARY_SECTION_RE.search(text)
    if not match:
        return False
    summary_block = match.group(1)
    return "[TODO]" in summary_block or "[TODO:" in summary_block


def _rewrite_note_abstract(note_path: Path, abstract_text: str, *, abstract_source: str = "") -> bool:
    try:
        text = note_path.read_text(encoding="utf-8")
    except OSError:
        return False

    replacement = f"{abstract_text.strip()}\n\n"
    new_text, replaced = _ABSTRACT_SECTION_RE.subn(
        lambda match: f"{match.group(1)}{replacement}",
        text,
        count=1,
    )
    if replaced == 0:
        return False
    if abstract_source:
        new_text = _upsert_frontmatter_scalar(new_text, "abstract_source", abstract_source)
    if new_text != text:
        note_path.write_text(new_text, encoding="utf-8")
    return True


def apply_enrichment(
    zot,
    plans: Iterable[EnrichPlan],
    *,
    rate_limit_rps: float = 2.0,
    chain_resummarize: bool = True,
    cfg=None,
    cluster_slug: str = "",
) -> dict[str, str]:
    """PATCH Zotero items with planned metadata, without overwriting existing values."""
    sleep_s = 1.0 / max(rate_limit_rps, 0.1)
    materialized_plans = list(plans)
    results: dict[str, str] = {}
    resummarize_keys: list[str] = []
    note_by_key = _index_cluster_notes(cfg, cluster_slug) if cfg is not None and cluster_slug else {}
    for plan in materialized_plans:
        try:
            item = zot.item(plan.item_key)
            data = item["data"]
            had_abstract_before = bool(str(data.get("abstractNote", "") or "").strip())
            for field_name, value in plan.fields_to_fill.items():
                if not str(data.get(field_name, "") or "").strip():
                    data[field_name] = value
            zot.update_item(data)
            results[plan.item_key] = "ok"
            has_abstract_now = bool(str(data.get("abstractNote", "") or "").strip())
            if not had_abstract_before and has_abstract_now:
                note_path = note_by_key.get(plan.item_key)
                if note_path is not None:
                    _rewrite_note_abstract(
                        note_path,
                        str(data.get("abstractNote", "") or ""),
                        abstract_source=plan.abstract_source,
                    )
                    if _note_summary_has_todo(note_path):
                        resummarize_keys.append(plan.item_key)
            time.sleep(sleep_s)
        except Exception as exc:
            results[plan.item_key] = str(exc)[:80]
    if chain_resummarize and resummarize_keys and cfg is not None and cluster_slug:
        try:
            from research_hub.summarize import summarize_cluster

            print(
                f"\nChaining re-summarize for {len(resummarize_keys)} paper(s) with newly recovered abstracts..."
            )
            report = summarize_cluster(cfg, cluster_slug, apply=True, paper_keys=resummarize_keys)
            if report.prompt_path is not None:
                print(f"[warn] chained resummarize skipped: no LLM CLI on PATH ({report.prompt_path})")
            elif not report.ok:
                print(f"[warn] chained resummarize failed: {report.error}")
            elif report.apply_result is not None and report.apply_result.errors:
                print(
                    f"[warn] chained resummarize applied with {len(report.apply_result.errors)} error(s)"
                )
        except Exception as exc:
            print(f"[warn] chained resummarize failed: {exc}")
    return results

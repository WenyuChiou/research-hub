"""Zotero hygiene backfills for legacy research-hub libraries."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from research_hub.clusters import ClusterRegistry
from research_hub.dedup import DedupIndex
from research_hub.pipeline import _compose_hub_tags
from research_hub.pipeline_repair import _iter_collection_items
from research_hub.zotero.client import add_note, safe_api_call


@dataclass
class BackfillReport:
    dry_run: bool
    clusters_scanned: int = 0
    items_audited: int = 0
    tags_added: list[dict] = field(default_factory=list)
    notes_added: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    report_path: str = ""

    def summary(self) -> str:
        mode = "dry-run" if self.dry_run else "applied"
        lines = [
            f"Zotero backfill report ({mode}):",
            f"  Clusters scanned: {self.clusters_scanned}",
            f"  Items audited:    {self.items_audited}",
            f"  Tag updates:      {len(self.tags_added)}",
            f"  Notes added:      {len(self.notes_added)}",
            f"  Errors:           {len(self.errors)}",
        ]
        if self.report_path:
            lines.append(f"  Report:           {self.report_path}")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        lines = [
            "# Zotero Backfill Report",
            "",
            f"- Mode: {'dry-run' if self.dry_run else 'applied'}",
            f"- Clusters scanned: {self.clusters_scanned}",
            f"- Items audited: {self.items_audited}",
            f"- Tag updates: {len(self.tags_added)}",
            f"- Notes added: {len(self.notes_added)}",
            f"- Errors: {len(self.errors)}",
            "",
            "## Tags Added",
        ]
        if self.tags_added:
            for row in self.tags_added:
                lines.append(f"- `{row.get('key')}` in `{row.get('slug')}`: {', '.join(row.get('added', []))}")
        else:
            lines.append("- None")
        lines.extend(["", "## Notes Added"])
        if self.notes_added:
            for row in self.notes_added:
                lines.append(f"- `{row.get('key')}` in `{row.get('slug')}` from {row.get('source')}")
        else:
            lines.append("- None")
        lines.extend(["", "## Errors"])
        if self.errors:
            for row in self.errors:
                key = row.get("key") or row.get("slug") or "unknown"
                lines.append(f"- `{key}`: {row.get('error')}")
        else:
            lines.append("- None")
        return "\n".join(lines) + "\n"


def _frontmatter_payload(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    frontmatter = text[3:end]
    try:
        import yaml

        payload = yaml.safe_load(frontmatter) or {}
        return payload if isinstance(payload, dict) else {}
    except Exception:
        payload: dict[str, object] = {}
        for line in frontmatter.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            payload[key.strip()] = value.strip().strip('"').strip("'")
        return payload


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _note_from_obsidian(path: Path) -> str:
    payload = _frontmatter_payload(path)
    summary = html.escape(str(payload.get("summary", "") or ""))
    methodology = html.escape(str(payload.get("methodology", "") or ""))
    relevance = html.escape(str(payload.get("relevance", "") or ""))
    findings = _as_list(payload.get("key_findings"))
    note = f"<h1>Summary</h1><p>{summary}</p>"
    note += "<h2>Key Findings</h2><ul>"
    note += "".join(f"<li>{html.escape(item)}</li>" for item in findings)
    note += "</ul>"
    note += f"<h2>Methodology</h2><p>{methodology}</p>"
    note += f"<h2>Relevance</h2><p>{relevance}</p>"
    return note


def _stub_note(slug: str, doi: str) -> str:
    safe_slug = html.escape(slug)
    safe_doi = html.escape(doi or "n/a")
    return f"<p>Imported from cluster <b>{safe_slug}</b>. DOI: {safe_doi}</p>"


def _first_obsidian_path(dedup_index: DedupIndex, *, doi: str, title: str = "") -> Path | None:
    for hit in dedup_index.lookup(doi=doi, title=title):
        obsidian_path = getattr(hit, "obsidian_path", None)
        if obsidian_path:
            path = Path(obsidian_path)
            if path.exists():
                return path
    return None


def run_backfill(
    cfg,
    *,
    cluster_slugs: list[str] | None = None,
    do_tags: bool = True,
    do_notes: bool = True,
    apply: bool = False,
    progress: Callable[[str], None] | None = None,
) -> BackfillReport:
    registry = ClusterRegistry(cfg.clusters_file)
    dedup_path = getattr(cfg, "dedup_index_path", cfg.research_hub_dir / "dedup_index.json")
    dedup_index = DedupIndex.load(dedup_path)
    from research_hub.zotero.client import ZoteroDualClient

    dual = ZoteroDualClient()
    zot = getattr(dual, "web", dual)
    report = BackfillReport(dry_run=not apply)
    requested = {slug.strip().lower() for slug in (cluster_slugs or []) if slug.strip()}
    clusters = [cluster for cluster in registry.list() if not requested or cluster.slug in requested]

    for cluster in clusters:
        report.clusters_scanned += 1
        if progress:
            progress(f"Scanning cluster {cluster.slug}")
        if not cluster.zotero_collection_key:
            report.errors.append(
                {"slug": cluster.slug, "error": "cluster has no Zotero collection"}
            )
            continue
        for item in _iter_collection_items(zot, cluster.zotero_collection_key):
            data = item.get("data", {})
            key = item.get("key") or data.get("key", "")
            report.items_audited += 1
            try:
                existing_tags = [
                    tag.get("tag", "")
                    for tag in data.get("tags", [])
                    if isinstance(tag, dict) and tag.get("tag")
                ]
                doi = str(data.get("DOI", "") or "")
                pp = {
                    "doi": doi,
                    "title": data.get("title", ""),
                    "source": data.get("libraryCatalog") or "zotero",
                    "tags": existing_tags,
                }
                if do_tags:
                    desired = _compose_hub_tags(pp, cluster.slug)
                    existing_tag_set = set(existing_tags)
                    to_add = [tag for tag in desired if tag not in existing_tag_set]
                    if to_add:
                        report.tags_added.append(
                            {"key": key, "slug": cluster.slug, "added": to_add}
                        )
                        if apply:
                            data["tags"] = data.get("tags", []) + [{"tag": tag} for tag in to_add]
                            safe_api_call(zot.update_item, data)
                if do_notes:
                    children = safe_api_call(zot.children, key)
                    notes = [
                        child
                        for child in (children or [])
                        if child.get("data", {}).get("itemType") == "note"
                    ]
                    if not notes:
                        obsidian_path = _first_obsidian_path(
                            dedup_index,
                            doi=doi,
                            title=str(data.get("title", "") or ""),
                        )
                        if obsidian_path:
                            source = "obsidian"
                            note_html = _note_from_obsidian(obsidian_path)
                        else:
                            source = "stub"
                            note_html = _stub_note(cluster.slug, doi)
                        report.notes_added.append(
                            {"key": key, "slug": cluster.slug, "source": source}
                        )
                        if apply:
                            safe_api_call(add_note, zot, key, note_html)
            except Exception as exc:
                report.errors.append({"key": key, "error": str(exc)})

    if apply:
        run_dir = getattr(cfg, "run_dir", cfg.research_hub_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = run_dir / f"backfill-{timestamp}.md"
        out_path.write_text(report.to_markdown(), encoding="utf-8")
        report.report_path = str(out_path)
    return report

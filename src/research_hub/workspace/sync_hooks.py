"""Post-connection workspace export & sync hooks (NotebookLM, Zotero, Obsidian).

Security invariants:
- Requires opt-in ``LocalIntegrationsManager`` (`integrations.enabled == True`).
- Never reads from or writes into ``--obsidian-vault``; ``ObsidianValidation`` remains
  strictly read-only. All generated NotebookLM bundles and Obsidian ``.md`` / ``.base``
  packs are confined inside ``<workspace_root>/.research/exports/`` via ``safe_path``.
- Never echoes raw API keys, cookies, or host filesystem paths outside the workspace.
"""

from __future__ import annotations

import contextlib
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any
import unicodedata
from urllib.parse import quote, urlsplit
import uuid

from research_hub.locks import file_lock
from .core import Workspace, WorkspaceError, atomic_json, digest, resolve_reading_scope, safe_path
from .integrations import LocalIntegrationsManager

_PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_CURATION_KEYS = (
    "category",
    "year",
    "authors",
    "venue",
    "doi",
    "relevance",
    "summary",
    "tags",
    "archived",
)
_MAX_SELECTED_IDS = 2000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".hub-exp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _clean_line(value: object) -> str:
    if value is None or isinstance(value, bool):
        return ""
    text = str(value) if isinstance(value, (str, int, float)) else ""
    return re.sub(r"[\r\n\x85\u2028\u2029]+", " ", text).strip()


def _inline_md(value: object) -> str:
    return _clean_line(value).replace("`", "'")


def _yaml_quote(value: object) -> str:
    return json.dumps(_clean_line(value), ensure_ascii=False)


def _clean_bare_doi(value: object) -> str:
    raw = _clean_line(value)
    raw = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"^doi:\s*", "", raw, flags=re.IGNORECASE)
    return raw.strip()


def _safe_http_url(locator: object, locator_kind: object = None) -> str:
    if locator_kind == "local-copy" or not isinstance(locator, str):
        return ""
    candidate = locator.strip()
    if not candidate:
        return ""
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return ""
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        return candidate
    return ""


def _slugify(value: str, fallback: str = "source", max_len: int = 56) -> str:
    ascii_folded = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not ascii_folded:
        return fallback
    return ascii_folded[:max_len].rstrip("-") or fallback


def _collect_authors(value: object) -> list[str]:
    if isinstance(value, str):
        cleaned = _clean_line(value)
        return [cleaned] if cleaned else []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            cleaned = _clean_line(item)
            if cleaned:
                out.append(cleaned)
        elif isinstance(item, dict):
            direct = _clean_line(item.get("name") or item.get("literal"))
            if direct:
                out.append(direct)
            else:
                family = _clean_line(item.get("family"))
                given = _clean_line(item.get("given"))
                joined = ", ".join(part for part in (family, given) if part)
                if joined:
                    out.append(joined)
    return out


def _author_surnames(value: object) -> set[str]:
    surnames: set[str] = set()
    items = _collect_authors(value)
    if not items and isinstance(value, list):
        for entry in value:
            if isinstance(entry, dict) and entry.get("lastName"):
                items.append(str(entry["lastName"]))
    for author in items:
        raw = author.split(",", 1)[0] if "," in author else (author.split()[-1] if author.split() else "")
        cleaned = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
        token = re.sub(r"[^a-z0-9]+", "", cleaned.lower())
        if token:
            surnames.add(token)
    return surnames


def _zotero_creators(value: object) -> list[dict[str, str]]:
    if isinstance(value, str):
        raw_items: list[object] = [value] if value.strip() else []
    elif isinstance(value, list):
        raw_items = value
    else:
        return []
    creators: list[dict[str, str]] = []
    for item in raw_items:
        if isinstance(item, dict):
            family = _clean_line(item.get("family"))
            given = _clean_line(item.get("given"))
            literal = _clean_line(item.get("literal") or item.get("name"))
            if family:
                creators.append({
                    "creatorType": "author",
                    "lastName": family,
                    "firstName": given,
                })
            elif literal:
                creators.append({"creatorType": "author", "name": literal})
        elif isinstance(item, str):
            cleaned = _clean_line(item)
            if not cleaned:
                continue
            if "," in cleaned:
                first_part, rest = cleaned.split(",", 1)
                last_name = first_part.strip()
                first_name = rest.strip()
                if last_name:
                    creators.append({
                        "creatorType": "author",
                        "lastName": last_name,
                        "firstName": first_name,
                    })
                elif first_name:
                    creators.append({"creatorType": "author", "name": first_name})
            else:
                parts = cleaned.split()
                if len(parts) == 1:
                    creators.append({"creatorType": "author", "name": parts[0]})
                else:
                    creators.append({
                        "creatorType": "author",
                        "firstName": " ".join(parts[:-1]),
                        "lastName": parts[-1],
                    })
    return creators


def _collect_tags(data: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for field in ("tags", "labels"):
        raw_list = data.get(field)
        if not isinstance(raw_list, list):
            continue
        for entry in raw_list:
            if not isinstance(entry, str):
                continue
            cleaned = _clean_line(entry).lstrip("#").strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key not in seen:
                seen.add(key)
                out.append(cleaned)
    return out


def _reading_scope(data: dict[str, Any]) -> str:
    return resolve_reading_scope(data)


def _is_full_text_scope(scope: str) -> bool:
    return scope.casefold() in {"full-text", "fulltext"}


def _saved_summary(data: dict[str, Any]) -> str:
    for field in ("summary", "abstract"):
        val = data.get(field)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _working_summary_text(data: dict[str, Any]) -> str:
    ws = data.get("working_summary")
    if isinstance(ws, dict):
        txt = ws.get("text")
        if isinstance(txt, str) and txt.strip():
            return txt.strip()
    elif isinstance(ws, str) and ws.strip():
        return ws.strip()
    return ""


def _category_slug(data: dict[str, Any]) -> str:
    return _clean_line(data.get("category")) or _clean_line(data.get("sub_category"))


def _source_revision_sha256(
    record: dict[str, Any],
    screening: str,
    artifact_ref: dict[str, str] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "id": _clean_line(record.get("id")),
        "revision": record.get("revision"),
        "data": record.get("data") if isinstance(record.get("data"), dict) else {},
        "screening": screening,
    }
    if artifact_ref:
        payload["artifact_status"] = _clean_line(artifact_ref.get("artifact_status"))
        payload["artifact_sha256"] = _clean_line(artifact_ref.get("artifact_sha256"))
    return digest(payload)


def _zotero_source_fingerprint(record: dict[str, Any]) -> str:
    return digest({
        "id": _clean_line(record.get("id")),
        "revision": record.get("revision"),
        "data": record.get("data") if isinstance(record.get("data"), dict) else {},
    })


def _get_zotero_client(library_id: str, library_type: str, api_key: str):
    from pyzotero import zotero

    return zotero.Zotero(library_id, library_type, api_key)


def _find_zotero_duplicate_item(zot: Any, title: str, doi: str = "") -> dict[str, Any] | None:
    """Lookup existing Zotero item by DOI or title, returning it or raising WorkspaceError on API failure."""
    from research_hub.utils.doi import normalize_doi

    norm_doi = normalize_doi(doi) if doi else ""
    norm_title = (title or "").casefold()

    def _find_match(items: object) -> dict[str, Any] | None:
        if not isinstance(items, list):
            return None
        for entry in items:
            if not isinstance(entry, dict):
                continue
            edata = entry.get("data")
            if not isinstance(edata, dict):
                continue
            entry_doi = normalize_doi(str(edata.get("DOI") or ""))
            if norm_doi and entry_doi:
                if norm_doi == entry_doi:
                    return entry
                continue
            if norm_title and str(edata.get("title") or "").casefold() == norm_title:
                return entry
        return None

    query = doi or (title or "")[:50]
    try:
        existing = zot.items(q=query, limit=5)
        hit = _find_match(existing)
        if hit is not None:
            return hit
        if not existing and doi and title:
            fallback = zot.items(q=title[:50], limit=5)
            return _find_match(fallback)
    except Exception as exc:
        raise WorkspaceError(
            "Zotero duplicate lookup failed; verify API credentials, connection, or rate limits before syncing",
            "zotero_lookup_failed",
        ) from exc
    return None


def _check_zotero_duplicate_strict(zot: Any, title: str, doi: str = "") -> bool:
    """Lookup existing Zotero item by DOI or title, raising WorkspaceError on API failure."""
    return _find_zotero_duplicate_item(zot, title, doi) is not None


def _sanitize_zotero_failure(err_val: object, secret: str) -> str:
    if isinstance(err_val, dict):
        msg = _clean_line(err_val.get("message") or err_val.get("error") or "")
        code = _clean_line(err_val.get("code"))
        text = f"HTTP {code}: {msg}" if code and msg else (msg or (f"HTTP {code}" if code else ""))
    else:
        text = _clean_line(err_val)
    if secret:
        text = text.replace(secret, "[REDACTED]")
    return (text[:160] if text else "Rejected by Zotero API")


def _build_obsidian_base_yaml(project_id: str, project_title: str) -> str:
    safe_slug = re.sub(r"[^a-z0-9-_]", "-", project_id.lower()) or "research-hub"
    safe_title = _clean_line(project_title or safe_slug).replace('"', '\\"')
    escaped_slug = safe_slug.replace("\\", "\\\\").replace('"', '\\"')
    cluster_expr = f'topic_cluster == "{escaped_slug}"'.replace("'", "''")

    return "\n".join([
        f"# Obsidian Base for {safe_title} (scoped to {safe_slug})",
        "filters:",
        "  and:",
        "    - 'file.ext == \"md\"'",
        f"    - '{cluster_expr}'",
        "views:",
        "  - type: table",
        '    name: "All Literature"',
        "    order:",
        "      - file.name",
        "      - title",
        "      - year",
        "      - category",
        "      - reading_scope",
        "      - screening",
        "      - tags",
        "      - doi",
        "    groupBy:",
        "      property: category",
        "      direction: ASC",
        "  - type: table",
        '    name: "Included Cohort"',
        "    filters:",
        "      or:",
        "        - 'screening == \"include\"'",
        "        - 'status == \"included\"'",
        "    order:",
        "      - year",
        "      - title",
        "      - category",
        "      - reading_scope",
        "      - doi",
        "    groupBy:",
        "      property: year",
        "      direction: DESC",
        "  - type: cards",
        '    name: "Needs Full-Text or Triage"',
        "    filters:",
        "      or:",
        "        - 'screening == \"unscreened\"'",
        "        - 'status == \"unread\"'",
        "        - 'reading_scope != \"full-text\"'",
        "    order:",
        "      - title",
        "      - reading_scope",
        "      - screening",
        "      - category",
        "",
    ])


def _render_obsidian_note(
    record: dict[str, Any],
    *,
    project_id: str,
    screening: str,
    artifact_ref: dict[str, str] | None = None,
) -> str:
    data = record["data"]
    source_id = _clean_line(record.get("id"))
    source_rev = _clean_line(record.get("revision") or 1)
    rev_sha256 = _source_revision_sha256(record, screening, artifact_ref)
    title = _clean_line(data.get("title")) or "Untitled source"
    authors = _collect_authors(data.get("authors"))
    tags = _collect_tags(data)
    category = _category_slug(data)
    doi = _clean_bare_doi(data.get("doi"))
    url = _safe_http_url(data.get("locator"), data.get("locator_kind"))
    venue = _clean_line(data.get("venue")) or _clean_line(data.get("journal"))
    year = _clean_line(data.get("year"))
    scope = _reading_scope(data)
    identity = _clean_line(data.get("identity_status")) or "unverified"
    pub_version = _clean_line(data.get("publication_version"))
    art_status = _clean_line((artifact_ref or {}).get("artifact_status"))
    art_id = _clean_line((artifact_ref or {}).get("artifact_id"))
    art_path = _clean_line((artifact_ref or {}).get("artifact_path")) if art_status == "verified" else ""
    art_sha = _clean_line((artifact_ref or {}).get("artifact_sha256")) if art_status == "verified" else ""
    summary = _saved_summary(data)
    working = _working_summary_text(data)
    relevance = str(data.get("relevance") or "").strip()

    fm_lines = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"source_id: {_yaml_quote(source_id)}",
        f"source_revision: {_yaml_quote(source_rev)}",
        f"source_revision_sha256: {_yaml_quote(rev_sha256)}",
        f"topic_cluster: {_yaml_quote(project_id)}",
        f"authors: [{', '.join(_yaml_quote(a) for a in authors)}]",
        f"year: {_yaml_quote(year)}",
        f"venue: {_yaml_quote(venue)}",
        f"doi: {_yaml_quote(doi)}",
        f"url: {_yaml_quote(url)}",
        f"category: {_yaml_quote(category)}",
        f"tags: [{', '.join(_yaml_quote(t) for t in tags)}]",
        f"reading_scope: {_yaml_quote(scope)}",
        f"screening: {_yaml_quote(screening)}",
        f"identity_status: {_yaml_quote(identity)}",
    ]
    if pub_version:
        fm_lines.append(f"publication_version: {_yaml_quote(pub_version)}")
    if art_status:
        fm_lines.append(f"artifact_status: {_yaml_quote(art_status)}")
    if art_id:
        fm_lines.append(f"artifact_id: {_yaml_quote(art_id)}")
    if art_path:
        fm_lines.append(f"artifact_path: {_yaml_quote(art_path)}")
    if art_sha:
        fm_lines.append(f"artifact_sha256: {_yaml_quote(art_sha)}")
    fm_lines.append("---")
    frontmatter = "\n".join(fm_lines)

    if art_status == "verified" and art_path:
        prov_suffix = f" · Workspace artifact: `{_inline_md(art_path)}`"
    elif art_status == "unknown":
        prov_suffix = " · Workspace artifact: `unknown` (changed or unavailable since registration)"
    else:
        prov_suffix = ""
    body_lines = [
        f"# {_inline_md(title)}",
        "",
        f"> Source ID: `{_inline_md(source_id)}` · Revision SHA-256: `{rev_sha256}`{prov_suffix}",
        f"> Reading scope: `{_inline_md(scope)}` · Screening: `{_inline_md(screening)}` · Identity: `{_inline_md(identity)}`",
        "",
        "## Summary",
        summary or "_No summary recorded yet._",
    ]
    if working:
        body_lines.extend(["", "## Working Summary (Unverified Draft)", working])
    body_lines.extend([
        "",
        "## Relevance",
        relevance or "_No relevance note recorded yet._",
    ])
    return f"{frontmatter}\n\n" + "\n".join(body_lines) + "\n"


def _render_nlm_individual_source(
    record: dict[str, Any],
    *,
    index: int,
    project_id: str,
    project_title: str,
    screening: str,
    artifact_ref: dict[str, str] | None = None,
) -> str:
    data = record["data"]
    source_id = _clean_line(record.get("id"))
    rev_sha256 = _source_revision_sha256(record, screening, artifact_ref)
    title = _clean_line(data.get("title")) or f"Source {index}"
    authors = ", ".join(_collect_authors(data.get("authors"))) or "Unknown"
    year = _clean_line(data.get("year")) or "n.d."
    venue = _clean_line(data.get("venue")) or _clean_line(data.get("journal"))
    doi = _clean_bare_doi(data.get("doi"))
    url = _safe_http_url(data.get("locator"), data.get("locator_kind"))
    art_status = _clean_line((artifact_ref or {}).get("artifact_status"))
    art_path = _clean_line((artifact_ref or {}).get("artifact_path")) if art_status == "verified" else ""
    scope = _reading_scope(data)
    category = _category_slug(data) or "unclassified"
    tags = _collect_tags(data)
    summary = _saved_summary(data)
    working = _working_summary_text(data)
    relevance = str(data.get("relevance") or "").strip()

    is_full = _is_full_text_scope(scope)
    boundary = (
        "Full-text declared in Research Hub."
        if is_full
        else "Abstract / metadata-only source — do NOT attribute unverified sample sizes, p-values, or full-text experimental details."
    )

    lines = [
        f"# {_inline_md(title)} ({_inline_md(year)})",
        "",
        f"- **Project**: {_inline_md(project_title)} (`{_inline_md(project_id)}`)",
        f"- **Source ID**: `{_inline_md(source_id)}`",
        f"- **Source Revision SHA-256**: `{rev_sha256}`",
        f"- **Authors**: {_inline_md(authors)}",
        f"- **Year**: {_inline_md(year)}",
    ]
    if venue:
        lines.append(f"- **Venue**: {_inline_md(venue)}")
    if doi:
        lines.append(f"- **DOI**: {_inline_md(doi)}")
    if url:
        lines.append(f"- **URL**: {url}")
    if art_status == "verified" and art_path:
        lines.append(f"- **Workspace Artifact**: `{_inline_md(art_path)}`")
    elif art_status == "unknown":
        lines.append("- **Workspace Artifact**: `unknown` (changed or unavailable since registration)")
    lines.extend([
        f"- **Category**: {_inline_md(category)}",
        f"- **Screening**: {_inline_md(screening)}",
        f"- **Reading Scope**: `{_inline_md(scope)}`",
        f"- **Evidence Boundary**: {boundary}",
    ])
    if tags:
        lines.append(f"- **Labels**: {', '.join(_inline_md(t) for t in tags)}")
    lines.extend([
        "",
        "## Summary / Abstract",
        summary or "[No abstract or summary saved locally.]",
    ])
    if working:
        lines.extend(["", "## Working Summary (Unverified Draft)", working])
    if relevance:
        lines.extend(["", "## Relevance Note", relevance])
    return "\n".join(lines) + "\n"


def _render_nlm_pack_markdown(
    sources: list[dict[str, Any]],
    *,
    project_id: str,
    project_title: str,
    screenings: dict[str, str] | None = None,
    artifact_refs: dict[str, dict[str, str]] | None = None,
) -> str:
    full_text = [s for s in sources if _is_full_text_scope(_reading_scope(s["data"]))]
    abstract_or_meta = [s for s in sources if not _is_full_text_scope(_reading_scope(s["data"]))]
    screening_map = screenings or {}
    art_map = artifact_refs or {}

    def _entry(record: dict[str, Any], idx: int) -> str:
        data = record["data"]
        source_id = _clean_line(record.get("id"))
        decision = screening_map.get(source_id, "unscreened")
        art_ref = art_map.get(source_id)
        art_status = _clean_line((art_ref or {}).get("artifact_status"))
        art_path = _clean_line((art_ref or {}).get("artifact_path")) if art_status == "verified" else ""
        rev_sha256 = _source_revision_sha256(record, decision, art_ref)
        title = _clean_line(data.get("title")) or f"Source {idx}"
        authors = ", ".join(_collect_authors(data.get("authors"))) or "Unknown"
        year = _clean_line(data.get("year")) or "n.d."
        doi = _clean_bare_doi(data.get("doi"))
        url = _safe_http_url(data.get("locator"), data.get("locator_kind"))
        scope = _reading_scope(data)
        identity = _clean_line(data.get("identity_status")) or "unverified"
        pub_version = _clean_line(data.get("publication_version"))
        recorded_at = _clean_line(data.get("recorded_at"))
        cat = _category_slug(data) or "unclassified"
        tags = _collect_tags(data)
        summary = _saved_summary(data)
        working = _working_summary_text(data)
        relevance = str(data.get("relevance") or "").strip()

        parts = [
            f"### {idx}. {_inline_md(title)} ({_inline_md(year)})",
            f"- Source ID: `{_inline_md(source_id)}`",
            f"- Source Revision SHA-256: `{rev_sha256}`",
            f"- Authors: {_inline_md(authors)}",
            f"- Reading Scope: {_inline_md(scope)}",
            f"- Screening: {_inline_md(decision)} · Identity: {_inline_md(identity)}",
            f"- Category: {_inline_md(cat)}",
        ]
        if pub_version:
            parts.append(f"- Publication Version: {_inline_md(pub_version)}")
        if recorded_at:
            parts.append(f"- Recorded At: {_inline_md(recorded_at)}")
        if tags:
            parts.append(f"- Keywords/Labels: {', '.join(_inline_md(t) for t in tags)}")
        if doi:
            parts.append(f"- DOI: {_inline_md(doi)}")
        if url:
            parts.append(f"- Locator: {url}")
        if art_status == "verified" and art_path:
            parts.append(f"- Workspace Artifact: `{_inline_md(art_path)}`")
        elif art_status == "unknown":
            parts.append("- Workspace Artifact: `unknown` (changed or unavailable since registration)")
        parts.append(f"\n{summary}" if summary else "\n[No abstract or summary saved locally.]")
        if working:
            parts.append(f"\n#### Working Summary (Unverified Draft)\n{working}")
        if relevance:
            parts.append(f"\nRelevance note: {relevance}")
        return "\n".join(parts)

    full_block = (
        "\n\n".join(_entry(rec, i + 1) for i, rec in enumerate(full_text))
        if full_text
        else "_None in the current selection. Attach or ingest full-text PDFs before generating full-text NotebookLM claims._"
    )
    partial_block = (
        "\n\n".join(_entry(rec, i + 1) for i, rec in enumerate(abstract_or_meta))
        if abstract_or_meta
        else "_None._"
    )

    return "\n".join([
        f"# NotebookLM Source Pack: {_inline_md(project_title or project_id)}",
        "",
        "> **Evidence-Boundary Notice for NotebookLM**:",
        f"> - Full-text declared sources: {len(full_text)}",
        f"> - Abstract / metadata-only / unknown-scope sources: {len(abstract_or_meta)}",
        "> - Do NOT attribute detailed experimental methods, sample sizes, or p-values to abstract-only or metadata-only items unless verified in full text.",
        "",
        f"## Full-Text Declared Sources ({len(full_text)})",
        full_block,
        "",
        f"## Abstract-Only & Metadata Sources ({len(abstract_or_meta)})",
        partial_block,
        "",
    ])


class WorkspaceSyncHooks:
    """Workspace-scoped export bundles and dry-run-first external software sync."""

    def __init__(
        self,
        workspace: Workspace,
        integrations: LocalIntegrationsManager | None,
        *,
        obsidian_validation: Any = None,
    ) -> None:
        self.workspace = workspace
        self.integrations = integrations
        self.obsidian_validation = obsidian_validation
        self._lock_guard = threading.Lock()
        self._export_locks: dict[str, threading.Lock] = {}

    @contextlib.contextmanager
    def _export_lock(self, key: str, lock_name: str):
        lock_base_rel = f".research/exports/{lock_name}"
        lock_file_rel = f"{lock_base_rel}.lock"
        with self._lock_guard:
            exports_root = safe_path(self.workspace.root, ".research/exports")
            exports_root.mkdir(parents=True, exist_ok=True)
            lock_target = safe_path(self.workspace.root, lock_base_rel)
            safe_path(self.workspace.root, lock_file_rel)
            thread_lock = self._export_locks.get(key)
            if thread_lock is None:
                thread_lock = threading.Lock()
                self._export_locks[key] = thread_lock
        with thread_lock:
            lock_target = safe_path(self.workspace.root, lock_base_rel)
            safe_path(self.workspace.root, lock_file_rel)
            with file_lock(lock_target):
                yield

    def _require_enabled(self) -> LocalIntegrationsManager:
        if self.integrations is None or not self.integrations.enabled:
            raise WorkspaceError(
                "Local integrations are unavailable in this server mode",
                "integrations_unavailable",
            )
        return self.integrations

    def _validate_project_id(self, project_id: str) -> dict[str, Any]:
        if not isinstance(project_id, str) or not _PROJECT_ID_RE.fullmatch(project_id):
            raise WorkspaceError("Invalid project identifier", "invalid_request")
        return self.workspace.project(project_id)

    def _load_curated_sources(
        self,
        project_id: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
        project = self._validate_project_id(project_id)
        from .native_summary import snapshot_records

        raw_records = snapshot_records(self.workspace.records(project_id))
        overlays: dict[str, dict[str, Any]] = {}
        screenings: dict[str, str] = {}
        raw_sources: list[dict[str, Any]] = []

        for rec in raw_records:
            kind = rec.get("kind")
            rdata = rec.get("data")
            if not isinstance(rdata, dict):
                continue
            if kind == "source":
                raw_sources.append(rec)
            elif kind == "source_curation":
                sid = rdata.get("source_id")
                if isinstance(sid, str) and sid:
                    cur = overlays.setdefault(sid, {})
                    for k in _CURATION_KEYS:
                        if k in rdata:
                            cur[k] = rdata[k]
            elif kind == "screening":
                sid = rdata.get("source_id")
                decision = rdata.get("decision")
                rationale = rdata.get("rationale")
                if (
                    isinstance(sid, str)
                    and decision in {"include", "exclude"}
                    and isinstance(rationale, str)
                    and rationale.strip()
                ):
                    screenings[sid] = decision

        curated_sources: list[dict[str, Any]] = []
        curated_by_id: dict[str, dict[str, Any]] = {}
        for src in raw_sources:
            sid = src["id"]
            overlay = overlays.get(sid)
            if overlay:
                merged = {**src["data"], **overlay}
                if "category" in overlay and not _clean_line(overlay.get("category")):
                    merged["sub_category"] = ""
                if "summary" in overlay and not _clean_line(overlay.get("summary")):
                    merged["abstract"] = ""
                if "venue" in overlay and not _clean_line(overlay.get("venue")):
                    merged["journal"] = ""
                if "tags" in overlay:
                    merged["labels"] = []
                curated = {**src, "data": merged}
            else:
                curated = {**src, "data": dict(src["data"])}
            curated_sources.append(curated)
            curated_by_id[sid] = curated
            if sid not in screenings:
                inline_screening = curated["data"].get("screening")
                if isinstance(inline_screening, str) and inline_screening in {"include", "exclude"}:
                    screenings[sid] = inline_screening

        return project, curated_sources, curated_by_id, screenings

    def _resolve_project_sources(
        self,
        project_id: str,
        selected_source_ids: object,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
        if selected_source_ids is not None:
            if not isinstance(selected_source_ids, list):
                raise WorkspaceError("selected_source_ids must be a list of strings", "invalid_request")
            if not selected_source_ids:
                raise WorkspaceError("selected_source_ids cannot be empty when provided", "invalid_request")
            if len(selected_source_ids) > _MAX_SELECTED_IDS:
                raise WorkspaceError(f"selected_source_ids exceeds maximum of {_MAX_SELECTED_IDS}", "invalid_request")
            for sid in selected_source_ids:
                if not isinstance(sid, str) or not sid.strip():
                    raise WorkspaceError("selected_source_ids must contain non-empty strings", "invalid_request")

        project, curated_sources, curated_by_id, screenings = self._load_curated_sources(project_id)

        if selected_source_ids is not None:
            deduped: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for raw_sid in selected_source_ids:
                sid = raw_sid.strip()
                if sid not in curated_by_id:
                    raise WorkspaceError(
                        "One or more selected_source_ids do not belong to this project",
                        "invalid_source",
                    )
                if screenings.get(sid) == "exclude":
                    raise WorkspaceError(
                        "One or more selected_source_ids have been excluded by screening",
                        "invalid_source",
                    )
                if sid not in seen_ids:
                    seen_ids.add(sid)
                    deduped.append(curated_by_id[sid])
            return project, deduped, screenings

        active_sources = [
            s
            for s in curated_sources
            if s["data"].get("archived") is not True
            and screenings.get(s["id"]) != "exclude"
        ]
        return project, active_sources, screenings

    def _clean_stale_files(self, directory: Path, suffixes: tuple[str, ...]) -> None:
        if not directory.is_dir():
            return
        for child in directory.iterdir():
            if child.is_symlink():
                raise WorkspaceError("Linked paths are not allowed", "unsafe_path")
            if child.is_file() and child.suffix.lower() in suffixes and not child.name.startswith(".hub-"):
                safe_path(self.workspace.root, child)
                child.unlink(missing_ok=True)

    def _safe_nlm_status(self, integrations: LocalIntegrationsManager) -> str:
        try:
            checked = integrations.check_notebooklm()
            probe = checked.get("probe") if isinstance(checked, dict) else None
            if isinstance(probe, dict) and isinstance(probe.get("status"), str):
                return probe["status"]
        except Exception:
            pass
        try:
            cap = integrations.capability()
            return "configured" if cap.get("nlm_state_present") else "missing"
        except Exception:
            return "missing"

    def _resolve_vault_name(self, integrations: LocalIntegrationsManager) -> str:
        scope = getattr(self.obsidian_validation, "scope", None)
        if isinstance(scope, Path) and scope.name and not any(c in scope.name for c in ("/", "\\", ":")):
            return scope.name
        try:
            cap = integrations.capability()
            name = _clean_line(cap.get("obsidian_vault_name"))
            if name and not any(c in name for c in ("/", "\\", ":")) and name not in {".", ".."}:
                return name
        except Exception:
            pass
        return ""

    def _resolve_source_artifacts(self, project_id: str, sources: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
        lookup_failed = False
        items: list[dict[str, Any]] = []
        try:
            items = self.workspace.artifacts(project_id)
        except Exception:
            lookup_failed = True

        by_id: dict[str, dict[str, Any]] = {}
        by_source: dict[str, dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            aid = _clean_line(item.get("id"))
            if aid:
                by_id[aid] = item
            sid = _clean_line(item.get("source_record_id"))
            if sid:
                by_source[sid] = item

        resolved_map: dict[str, dict[str, str]] = {}
        for rec in sources:
            sid = _clean_line(rec.get("id"))
            if not sid:
                continue
            sdata = rec.get("data") if isinstance(rec.get("data"), dict) else {}
            explicit_aid = _clean_line(sdata.get("artifact_id"))
            is_local_copy = _clean_line(sdata.get("locator_kind")) == "local-copy"
            if lookup_failed:
                if explicit_aid or is_local_copy:
                    resolved_map[sid] = {
                        "artifact_status": "unknown",
                        "artifact_id": explicit_aid,
                        "artifact_path": "",
                        "artifact_sha256": "",
                    }
                continue

            if explicit_aid:
                cand = by_id.get(explicit_aid)
                art = cand if cand and _clean_line(cand.get("source_record_id")) in {"", sid} else None
            else:
                art = by_source.get(sid)

            if not art:
                if explicit_aid or is_local_copy:
                    resolved_map[sid] = {
                        "artifact_status": "unknown",
                        "artifact_id": explicit_aid,
                        "artifact_path": "",
                        "artifact_sha256": "",
                    }
                continue

            found_aid = _clean_line(art.get("id")) or explicit_aid
            raw_rel = _clean_line(art.get("path"))
            safe_rel = ""
            if raw_rel:
                try:
                    safe_rel = safe_path(self.workspace.root, raw_rel).relative_to(self.workspace.root).as_posix()
                except (WorkspaceError, ValueError, OSError):
                    safe_rel = ""

            if safe_rel and not safe_rel.startswith(".research/") and art.get("current") is True:
                resolved_map[sid] = {
                    "artifact_status": "verified",
                    "artifact_id": found_aid,
                    "artifact_path": safe_rel,
                    "artifact_sha256": _clean_line(art.get("sha256")),
                }
            else:
                resolved_map[sid] = {
                    "artifact_status": "unknown",
                    "artifact_id": found_aid,
                    "artifact_path": "",
                    "artifact_sha256": "",
                }
        return resolved_map

    def _bundle_notebooklm_locked(
        self, project_id: str, selected_source_ids: Any
    ) -> dict[str, Any]:
        integrations = self._require_enabled()
        export_rel = f".research/exports/notebooklm-{project_id}"
        pack_rel = f"{export_rel}/00-notebooklm-source-pack.md"
        manifest_rel = f"{export_rel}/manifest.json"

        used_names: set[str] = set()
        source_files: list[str] = []
        manifest_sources: list[dict[str, Any]] = []
        prepared_entries: list[dict[str, Any]] = []
        project, sources, screenings = self._resolve_project_sources(
            project_id, selected_source_ids
        )
        artifact_refs = self._resolve_source_artifacts(project_id, sources)
        full_text_count = sum(1 for s in sources if _is_full_text_scope(_reading_scope(s["data"])))
        abstract_only_count = len(sources) - full_text_count
        generated_at = _utc_now()
        manifest: dict[str, Any] = {
            "project_id": project_id,
            "project_title": project["title"],
            "source_count": len(sources),
            "full_text_count": full_text_count,
            "abstract_only_count": abstract_only_count,
            "generated_at": generated_at,
        }

        export_dir = safe_path(self.workspace.root, export_rel)
        sources_dir = safe_path(self.workspace.root, f"{export_rel}/sources")
        pack_path = safe_path(self.workspace.root, pack_rel)
        manifest_path = safe_path(self.workspace.root, manifest_rel)
        export_dir.mkdir(parents=True, exist_ok=True)
        sources_dir.mkdir(parents=True, exist_ok=True)
        self._clean_stale_files(sources_dir, (".md",))

        for index, rec in enumerate(sources, start=1):
            slug = _slugify(_clean_line(rec["data"].get("title")), fallback=f"source-{index}")
            stem = f"{index:02d}-{slug}"
            candidate_name = f"{stem}.md"
            collision = 2
            while candidate_name in used_names:
                candidate_name = f"{stem}-{collision}.md"
                collision += 1
            used_names.add(candidate_name)

            file_rel = f"{export_rel}/sources/{candidate_name}"
            file_path = safe_path(self.workspace.root, file_rel)
            decision = screenings.get(rec["id"], "unscreened")
            art_ref = artifact_refs.get(rec["id"])
            rendered = _render_nlm_individual_source(
                rec,
                index=index,
                project_id=project_id,
                project_title=project["title"],
                screening=decision,
                artifact_ref=art_ref,
            )
            _atomic_text(file_path, rendered)
            source_files.append(file_rel)
            rev_sha = _source_revision_sha256(rec, decision, art_ref)
            title_val = _clean_line(rec["data"].get("title")) or f"Source {index}"
            doi_val = _clean_bare_doi(rec["data"].get("doi"))
            manifest_sources.append({
                "index": index,
                "source_id": _clean_line(rec.get("id")),
                "title": title_val,
                "doi": doi_val,
                "locator": _safe_http_url(
                    rec["data"].get("locator"), rec["data"].get("locator_kind")
                ),
                "artifact_status": (art_ref or {}).get("artifact_status", ""),
                "artifact_id": (art_ref or {}).get("artifact_id", ""),
                "artifact_path": (art_ref or {}).get("artifact_path", ""),
                "artifact_sha256": (art_ref or {}).get("artifact_sha256", ""),
                "reading_scope": _reading_scope(rec["data"]),
                "screening": decision,
                "identity_status": _clean_line(rec["data"].get("identity_status")) or "unverified",
                "publication_version": _clean_line(rec["data"].get("publication_version")),
                "recorded_at": _clean_line(rec["data"].get("recorded_at")),
                "revision_sha256": rev_sha,
                "source_file": file_rel,
            })
            prepared_entries.append({
                "index": index,
                "source_id": _clean_line(rec.get("id")),
                "title": title_val,
                "doi": doi_val,
                "revision_sha256": rev_sha,
                "content": rendered,
            })

        _atomic_text(
            pack_path,
            _render_nlm_pack_markdown(
                sources,
                project_id=project_id,
                project_title=project["title"],
                screenings=screenings,
                artifact_refs=artifact_refs,
            ),
        )
        manifest["sources"] = manifest_sources
        atomic_json(manifest_path, manifest)

        nlm_status = self._safe_nlm_status(integrations)
        return {
            "project_title": project["title"],
            "prepared_entries": prepared_entries,
            "result": {
                "ok": True,
                "export_dir": export_rel,
                "pack_file": pack_rel,
                "manifest_file": manifest_rel,
                "source_files": source_files,
                "source_count": len(sources),
                "full_text_count": full_text_count,
                "abstract_or_metadata_count": abstract_only_count,
                "nlm_status": nlm_status,
                "notebook_url": "https://notebooklm.google.com/",
            },
        }

    def bundle_notebooklm(self, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._require_enabled()
        body = dict(payload or {})
        extra = set(body) - {"selected_source_ids"}
        if extra:
            raise WorkspaceError(f"Unsupported fields: {', '.join(sorted(extra))}", "invalid_request")

        self._validate_project_id(project_id)
        with self._export_lock(f"notebooklm:{project_id}", f".notebooklm-{project_id}"):
            return self._bundle_notebooklm_locked(project_id, body.get("selected_source_ids"))["result"]

    def upload_notebooklm(self, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Bundle project sources atomically under lock and upload to a NotebookLM notebook."""
        integrations = self._require_enabled()
        body = dict(payload or {})
        extra = set(body) - {"selected_source_ids", "notebook_title"}
        if extra:
            raise WorkspaceError(f"Unsupported fields: {', '.join(sorted(extra))}", "invalid_request")

        self._validate_project_id(project_id)
        export_rel = f".research/exports/notebooklm-{project_id}"
        receipt_rel = f"{export_rel}/upload_receipt.json"
        receipt_path = safe_path(self.workspace.root, receipt_rel)

        with self._export_lock(f"notebooklm:{project_id}", f".notebooklm-{project_id}"):
            bundled = self._bundle_notebooklm_locked(project_id, body.get("selected_source_ids"))
            prepared_entries: list[dict[str, Any]] = bundled["prepared_entries"]
            custom_title = _clean_line(body.get("notebook_title"))
            notebook_title = custom_title or f"[Research Hub] {_clean_line(bundled['project_title']) or project_id}"
            prior_receipt: dict[str, Any] = {}
            if receipt_path.is_file():
                try:
                    loaded = json.loads(receipt_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        prior_receipt = loaded
                except (OSError, json.JSONDecodeError):
                    prior_receipt = {}

        try:
            _, data = integrations._read_config_dict()
            state_file = integrations._nlm_state_file(data)
        except Exception as exc:
            raise WorkspaceError(f"Could not resolve NotebookLM state file: {type(exc).__name__}", "nlm_auth_missing") from exc

        if not state_file.is_file() or state_file.stat().st_size == 0:
            raise WorkspaceError(
                "NotebookLM session not found. Click 'Sign in to NotebookLM' in Setup first.",
                "nlm_auth_missing",
            )

        from research_hub.notebooklm.auth import ensure_session_health
        from research_hub.notebooklm.client import NotebookLMClient, NotebookLMError

        try:
            health = ensure_session_health(state_file)
        except Exception as exc:
            raise WorkspaceError(
                f"NotebookLM session expired or invalid ({type(exc).__name__}). Sign in again in Setup.",
                "nlm_auth_expired",
            ) from exc
        if isinstance(health, dict) and not health.get("ok", False):
            raise WorkspaceError(
                "NotebookLM Google session has expired. Open Setup -> Connections & Sync to sign in again before uploading.",
                "nlm_auth_expired",
            )

        uploaded_sources: list[dict[str, Any]] = []
        failed_sources: list[dict[str, Any]] = []
        skipped_duplicates = 0

        client: NotebookLMClient | None = None
        try:
            client = NotebookLMClient(state_file, headless=True, timeout_sec=120)
            handle = client.find_or_create_notebook(notebook_title)
            existing_titles: set[str] = set()
            existing_ids: set[str] = set()
            try:
                for src in client.list_sources(handle.notebook_id):
                    t = _clean_line(getattr(src, "title", "") or (src.get("title") if isinstance(src, dict) else ""))
                    if t:
                        existing_titles.add(t.casefold())
                    sid_remote = _clean_line(getattr(src, "id", "") or getattr(src, "source_id", "") or (src.get("id") if isinstance(src, dict) else ""))
                    if sid_remote:
                        existing_ids.add(sid_remote)
            except Exception:
                existing_titles = set()
                existing_ids = set()

            # Key prior uploaded revisions by source_id when matching the same notebook_id
            prior_revisions: dict[str, tuple[str, str]] = {}
            if prior_receipt.get("notebook_id") == handle.notebook_id:
                for prev in (prior_receipt.get("uploaded_sources") or []):
                    if isinstance(prev, dict) and isinstance(prev.get("source_id"), str):
                        prior_revisions[prev["source_id"]] = (
                            str(prev.get("revision_sha256") or ""),
                            str(prev.get("nlm_source_id") or ""),
                        )

            seen_batch_titles: set[str] = set()
            for entry in prepared_entries:
                sid = str(entry.get("source_id") or "")
                rev_sha = str(entry.get("revision_sha256") or "")
                base_title = _clean_line(entry.get("title")) or f"Source {entry['index']}"
                upload_title = base_title
                if upload_title.casefold() in seen_batch_titles:
                    upload_title = f"{base_title} ({entry['index']})"
                seen_batch_titles.add(upload_title.casefold())

                prev_rev, prev_nlm_id = prior_revisions.get(sid, ("", ""))
                still_present = (
                    (bool(prev_nlm_id) and prev_nlm_id in existing_ids)
                    or (upload_title.casefold() in existing_titles)
                )
                if sid and sid in prior_revisions:
                    if prev_rev and prev_rev == rev_sha and still_present:
                        skipped_duplicates += 1
                        continue
                elif upload_title.casefold() in existing_titles:
                    skipped_duplicates += 1
                    continue

                res = client.upload_source(handle.notebook_id, text=entry["content"], title=upload_title)
                if getattr(res, "ok", False):
                    existing_titles.add(upload_title.casefold())
                    uploaded_sources.append({
                        "source_id": sid,
                        "revision_sha256": rev_sha,
                        "title": upload_title,
                        "nlm_source_id": getattr(res, "source_id", "") or "",
                        "doi": entry.get("doi", ""),
                    })
                else:
                    failed_sources.append({
                        "source_id": sid,
                        "title": upload_title,
                        "error": _clean_line(getattr(res, "error", "")) or "NotebookLM upload failed",
                    })
        except WorkspaceError:
            raise
        except NotebookLMError as exc:
            low = str(exc).lower()
            if "expired" in low or "auth" in low or "sign-in" in low or "login" in low:
                raise WorkspaceError(
                    "NotebookLM Google session has expired or is invalid. Open Setup -> Connections & Sync to sign in again.",
                    "nlm_auth_expired",
                ) from exc
            raise WorkspaceError("NotebookLM upload failed; verify notebook access and session status.", "nlm_upload_failed") from exc
        except Exception as exc:
            raise WorkspaceError(f"NotebookLM upload failed: {type(exc).__name__}", "nlm_upload_failed") from exc
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

        uploaded_count = len(uploaded_sources)
        failed_count = len(failed_sources)
        status = (
            "uploaded"
            if failed_count == 0
            else ("partial_failure" if uploaded_count > 0 else "failed")
        )
        raw_nb_url = _clean_line(getattr(handle, "url", ""))
        safe_nb_url = (
            raw_nb_url
            if raw_nb_url.lower().startswith(("https://", "http://"))
            else f"https://notebooklm.google.com/notebook/{quote(handle.notebook_id, safe='-_')}"
            if getattr(handle, "notebook_id", "")
            else "https://notebooklm.google.com/"
        )
        uploaded_ids_now = {s["source_id"] for s in uploaded_sources}
        with self._export_lock(f"notebooklm:{project_id}", f".notebooklm-{project_id}"):
            latest_prior: dict[str, Any] = {}
            if receipt_path.is_file():
                try:
                    loaded_latest = json.loads(receipt_path.read_text(encoding="utf-8"))
                    if isinstance(loaded_latest, dict):
                        latest_prior = loaded_latest
                except (OSError, json.JSONDecodeError):
                    latest_prior = {}
            retained_sources = list(uploaded_sources)
            if latest_prior.get("notebook_id") == handle.notebook_id:
                for prev in (latest_prior.get("uploaded_sources") or []):
                    if isinstance(prev, dict) and prev.get("source_id") not in uploaded_ids_now:
                        retained_sources.append(prev)
            receipt = {
                "ok": True,
                "status": status,
                "project_id": project_id,
                "notebook_id": handle.notebook_id,
                "notebook_name": handle.name,
                "notebook_url": safe_nb_url,
                "uploaded_count": uploaded_count,
                "skipped_duplicates": skipped_duplicates,
                "failed_count": failed_count,
                "uploaded_sources": retained_sources,
                "failed_sources": failed_sources,
                "uploaded_at": _utc_now(),
                "receipt_file": receipt_rel,
            }
            atomic_json(receipt_path, receipt)
        return receipt

    def sync_zotero(self, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        integrations = self._require_enabled()
        body = dict(payload or {})
        extra = set(body) - {
            "dry_run",
            "selected_source_ids",
            "expected_revisions",
            "expected_library",
            "expected_plan_digest",
        }
        if extra:
            raise WorkspaceError(f"Unsupported fields: {', '.join(sorted(extra))}", "invalid_request")

        raw_dry_run = body.get("dry_run", True)
        if type(raw_dry_run) is not bool:
            raise WorkspaceError("dry_run must be a boolean", "invalid_request")
        dry_run: bool = raw_dry_run

        expected_revisions: dict[str, str] | None = None
        raw_expected = body.get("expected_revisions")
        if raw_expected is not None:
            if not isinstance(raw_expected, dict) or any(
                not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
                for k, v in raw_expected.items()
            ):
                raise WorkspaceError(
                    "expected_revisions must be a mapping of source IDs to non-empty revision digests",
                    "invalid_request",
                )
            expected_revisions = {k.strip(): v.strip() for k, v in raw_expected.items()}

        expected_library: str | None = None
        raw_expected_lib = body.get("expected_library")
        if raw_expected_lib is not None:
            if not isinstance(raw_expected_lib, str) or not raw_expected_lib.strip():
                raise WorkspaceError(
                    "expected_library must be a non-empty string when provided",
                    "invalid_request",
                )
            expected_library = raw_expected_lib.strip()

        expected_plan_digest: str | None = None
        raw_expected_plan = body.get("expected_plan_digest")
        if raw_expected_plan is not None:
            if not isinstance(raw_expected_plan, str) or not raw_expected_plan.strip():
                raise WorkspaceError(
                    "expected_plan_digest must be a non-empty string when provided",
                    "invalid_request",
                )
            expected_plan_digest = raw_expected_plan.strip()

        def _read_zotero_target() -> tuple[str, str, str, str]:
            c_path, c_data = integrations._read_config_dict()
            res = integrations._resolve_zotero_effective(c_data, c_path.parent)
            a_key = str(res.get("api_key") or "").strip()
            l_id = str(res.get("library_id") or "").strip()
            l_type = str(res.get("library_type") or "user").strip() or "user"
            dest = f"{l_type}:{l_id}" if (a_key and l_id) else ""
            return a_key, l_id, l_type, dest

        selected_ids_arg = body.get("selected_source_ids")
        project, sources, _ = self._resolve_project_sources(
            project_id, selected_ids_arg
        )
        source_revisions = {s["id"]: _zotero_source_fingerprint(s) for s in sources}
        collection_name = f"[Research Hub] {_clean_line(project.get('title')) or project_id}"

        api_key, library_id, library_type, destination_library = _read_zotero_target()

        if not api_key or not library_id:
            if not dry_run and (expected_library is not None or expected_plan_digest is not None):
                raise WorkspaceError(
                    "Zotero destination library changed after the dry-run preview; run Preview again before writing",
                    "stale_preview",
                )
            return {
                "ok": True,
                "status": "missing_credentials",
                "dry_run": dry_run,
                "candidate_count": len(sources),
                "would_create": 0,
                "duplicates": 0,
                "source_revisions": source_revisions,
                "items": [
                    {
                        "id": s["id"],
                        "title": _clean_line(s["data"].get("title")),
                        "doi": _clean_bare_doi(s["data"].get("doi")),
                        "action": "missing_credentials",
                    }
                    for s in sources
                ],
            }

        if not dry_run and expected_library is not None and destination_library != expected_library:
            raise WorkspaceError(
                "Zotero destination library changed after the dry-run preview; run Preview again before writing",
                "stale_preview",
            )

        from research_hub.utils.doi import normalize_doi

        locked_destination = destination_library
        safe_lib_slug = _slugify(f"{library_type}-{library_id}", fallback=project_id)
        write_guard = (
            contextlib.nullcontext()
            if dry_run
            else self._export_lock(
                f"zotero:{library_type}:{library_id}",
                f".zotero-{safe_lib_slug}",
            )
        )

        with write_guard:
            if not dry_run:
                api_key, library_id, library_type, destination_library = _read_zotero_target()
                if (
                    not api_key
                    or not library_id
                    or destination_library != locked_destination
                    or (expected_library is not None and destination_library != expected_library)
                ):
                    raise WorkspaceError(
                        "Zotero destination library changed during or after the dry-run preview; run Preview again before writing",
                        "stale_preview",
                    )
                _, sources, _ = self._resolve_project_sources(
                    project_id, selected_ids_arg
                )
                source_revisions = {s["id"]: _zotero_source_fingerprint(s) for s in sources}
                if expected_revisions is not None and source_revisions != expected_revisions:
                    raise WorkspaceError(
                        "Source metadata changed after the Zotero dry-run preview; run Preview again before writing",
                        "stale_preview",
                    )

            try:
                zot = _get_zotero_client(library_id, library_type, api_key)
            except Exception as exc:
                raise WorkspaceError(
                    "Could not initialize Zotero client; verify Zotero library configuration",
                    "zotero_unavailable",
                ) from exc

            collection_attachment_supported = bool(
                hasattr(zot, "collections")
                and hasattr(zot, "create_collections")
                and hasattr(zot, "update_item")
            )
            existing_collection_key: str | None = None
            collections_checked = False
            if collection_attachment_supported:
                try:
                    existing_cols = zot.collections() or []
                    collections_checked = True
                    for col in existing_cols:
                        if not isinstance(col, dict):
                            continue
                        col_data = col.get("data") if isinstance(col.get("data"), dict) else col
                        if _clean_line(col_data.get("name")) == collection_name:
                            found_key = col.get("key") or col_data.get("key")
                            if isinstance(found_key, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", found_key.strip()):
                                existing_collection_key = found_key.strip()
                                break
                except Exception as exc:
                    raise WorkspaceError(
                        "Could not inspect Zotero collections before syncing",
                        "zotero_lookup_failed",
                    ) from exc

            items_plan: list[dict[str, Any]] = []
            records_to_create: list[dict[str, Any]] = []
            pending_collection_attachments: list[tuple[dict[str, Any], dict[str, Any], str]] = []
            seen_remote_attach_keys: set[str] = set()
            seen_dois: set[str] = set()
            seen_doiless_titles: set[str] = set()
            seen_all_titles: set[str] = set()
            duplicates = 0

            for src in sources:
                sdata = src["data"]
                title = _clean_line(sdata.get("title")) or "Untitled source"
                doi = _clean_bare_doi(sdata.get("doi"))
                norm_doi = normalize_doi(doi) if doi else ""
                norm_title = title.casefold()

                if norm_doi:
                    in_batch_dup = bool(
                        norm_doi in seen_dois
                        or (norm_title and norm_title in seen_doiless_titles)
                    )
                else:
                    in_batch_dup = bool(norm_title and norm_title in seen_all_titles)
                remote_match = None if in_batch_dup else _find_zotero_duplicate_item(zot, title, doi)
                if in_batch_dup or remote_match is not None:
                    duplicates += 1
                    needs_attach = False
                    if remote_match is not None and collection_attachment_supported:
                        rem_data = remote_match.get("data") if isinstance(remote_match.get("data"), dict) else {}
                        rem_key = str(remote_match.get("key") or rem_data.get("key") or "").strip()
                        rem_cols = rem_data.get("collections") if isinstance(rem_data.get("collections"), list) else []
                        if (
                            rem_key
                            and rem_key not in seen_remote_attach_keys
                            and (existing_collection_key is None or existing_collection_key not in rem_cols)
                        ):
                            seen_remote_attach_keys.add(rem_key)
                            pending_collection_attachments.append((src, remote_match, rem_key))
                            needs_attach = True
                    items_plan.append({
                        "id": src["id"],
                        "title": title,
                        "doi": doi,
                        "action": "attach_to_collection" if needs_attach else "skip_duplicate",
                    })
                else:
                    if norm_doi:
                        seen_dois.add(norm_doi)
                    elif norm_title:
                        seen_doiless_titles.add(norm_title)
                    if norm_title:
                        seen_all_titles.add(norm_title)
                    records_to_create.append(src)
                    items_plan.append({
                        "id": src["id"],
                        "title": title,
                        "doi": doi,
                        "action": "create",
                    })

            plan_digest = digest({
                "destination_library": destination_library,
                "source_revisions": source_revisions,
                "items": [
                    {
                        "id": item["id"],
                        "action": item["action"],
                        "doi": item["doi"],
                        "title": item["title"],
                    }
                    for item in items_plan
                ],
            })

            if dry_run:
                return {
                    "ok": True,
                    "status": "ready",
                    "dry_run": True,
                    "candidate_count": len(sources),
                    "would_create": len(records_to_create),
                    "would_attach": len(pending_collection_attachments),
                    "duplicates": duplicates,
                    "destination_library": destination_library,
                    "collection_name": collection_name,
                    "source_revisions": source_revisions,
                    "plan_digest": plan_digest,
                    "items": items_plan,
                }

            if expected_plan_digest is not None and plan_digest != expected_plan_digest:
                raise WorkspaceError(
                    "Zotero sync plan changed since the dry-run preview; run Preview again before writing",
                    "stale_preview",
                )

            collection_key: str | None = existing_collection_key
            if (
                collection_key is None
                and (records_to_create or pending_collection_attachments)
                and hasattr(zot, "collections")
                and hasattr(zot, "create_collections")
            ):
                try:
                    if not collections_checked:
                        existing_cols = zot.collections() or []
                        for col in existing_cols:
                            if not isinstance(col, dict):
                                continue
                            col_data = col.get("data") if isinstance(col.get("data"), dict) else col
                            if _clean_line(col_data.get("name")) == collection_name:
                                found_key = col.get("key") or col_data.get("key")
                                if isinstance(found_key, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", found_key.strip()):
                                    collection_key = found_key.strip()
                                    break
                    if collection_key is None:
                        col_resp = zot.create_collections([{"name": collection_name}])
                        if isinstance(col_resp, dict):
                            col_succ = col_resp.get("successful") or col_resp.get("success") or {}
                            if isinstance(col_succ, dict):
                                first = next(iter(col_succ.values()), None)
                                if isinstance(first, dict):
                                    found_key = first.get("key") or (
                                        first.get("data", {}).get("key")
                                        if isinstance(first.get("data"), dict)
                                        else None
                                    )
                                    if isinstance(found_key, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", found_key.strip()):
                                        collection_key = found_key.strip()
                                elif isinstance(first, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", first.strip()):
                                    collection_key = first.strip()
                except Exception as exc:
                    raise WorkspaceError(
                        "Could not resolve or create target Zotero collection",
                        "zotero_sync_failed",
                    ) from exc
                if collection_key is None:
                    raise WorkspaceError(
                        "Could not confirm creation of target Zotero collection",
                        "zotero_sync_failed",
                    )

            zotero_payloads: list[dict[str, Any]] = []
            template_base: dict[str, Any] = {}
            if hasattr(zot, "item_template"):
                try:
                    tpl = zot.item_template("journalArticle")
                    if isinstance(tpl, dict):
                        template_base = dict(tpl)
                except Exception:
                    template_base = {}

            for src in records_to_create:
                sdata = src["data"]
                title = _clean_line(sdata.get("title")) or "Untitled source"
                doi = _clean_bare_doi(sdata.get("doi"))
                year = _clean_line(sdata.get("year"))
                venue = _clean_line(sdata.get("venue")) or _clean_line(sdata.get("journal"))
                url = _safe_http_url(sdata.get("locator"), sdata.get("locator_kind"))
                summary = _saved_summary(sdata)
                scope = _reading_scope(sdata)
                cat = _category_slug(sdata)

                raw_tags = ["research-hub", f"cluster/{project_id}"]
                if cat:
                    raw_tags.append(cat)
                raw_tags.extend(_collect_tags(sdata))
                deduped_tags: list[str] = []
                seen_tag_keys: set[str] = set()
                for t in raw_tags:
                    cleaned_tag = _clean_line(t)
                    if not cleaned_tag:
                        continue
                    tk = cleaned_tag.casefold()
                    if tk not in seen_tag_keys:
                        seen_tag_keys.add(tk)
                        deduped_tags.append(cleaned_tag)

                entry = dict(template_base)
                entry.update({
                    "itemType": "journalArticle",
                    "title": title,
                    "creators": _zotero_creators(sdata.get("authors")),
                    "date": year,
                    "publicationTitle": venue,
                    "DOI": doi,
                    "url": url,
                    "abstractNote": summary,
                    "extra": f"Research Hub project: {project_id}; Reading scope: {scope}",
                    "tags": [{"tag": tag} for tag in deduped_tags],
                })
                if collection_key:
                    entry["collections"] = [collection_key]
                zotero_payloads.append(entry)

            confirmed_created = 0
            created_keys: list[str] = []
            failed_items: list[dict[str, Any]] = []
            failed_source_ids: set[str] = set()
            if zotero_payloads:
                try:
                    for offset in range(0, len(zotero_payloads), 50):
                        batch = zotero_payloads[offset:offset + 50]
                        batch_records = records_to_create[offset:offset + 50]
                        response = zot.create_items(batch)
                        if not isinstance(response, dict):
                            raise WorkspaceError(
                                "Unexpected Zotero write response; could not confirm item creation",
                                "zotero_sync_failed",
                            )

                        batch_ok_indices: set[int] = set()
                        successful = response.get("successful")
                        success_legacy = response.get("success")
                        failed_map = response.get("failed")

                        if isinstance(successful, dict):
                            for seq_idx, (raw_idx, val) in enumerate(successful.items()):
                                try:
                                    parsed_idx = int(raw_idx)
                                except (TypeError, ValueError):
                                    parsed_idx = seq_idx
                                batch_ok_indices.add(parsed_idx)
                                if isinstance(val, dict):
                                    key = val.get("key") or (
                                        val.get("data", {}).get("key")
                                        if isinstance(val.get("data"), dict)
                                        else None
                                    )
                                    if isinstance(key, str) and key:
                                        created_keys.append(key)
                                elif isinstance(val, str) and val:
                                    created_keys.append(val)
                        elif isinstance(success_legacy, dict):
                            for seq_idx, (raw_idx, val) in enumerate(success_legacy.items()):
                                try:
                                    parsed_idx = int(raw_idx)
                                except (TypeError, ValueError):
                                    parsed_idx = seq_idx
                                batch_ok_indices.add(parsed_idx)
                                if isinstance(val, str) and val:
                                    created_keys.append(val)

                        batch_failed_reasons: dict[int, str] = {}
                        if isinstance(failed_map, dict):
                            for seq_idx, (raw_idx, err_val) in enumerate(failed_map.items()):
                                try:
                                    parsed_idx = int(raw_idx)
                                except (TypeError, ValueError):
                                    parsed_idx = seq_idx
                                batch_failed_reasons[parsed_idx] = _sanitize_zotero_failure(
                                    err_val, api_key
                                )

                        for local_idx, rec in enumerate(batch_records):
                            if local_idx in batch_ok_indices and local_idx not in batch_failed_reasons:
                                confirmed_created += 1
                            else:
                                reason = batch_failed_reasons.get(
                                    local_idx, "Rejected or unconfirmed by Zotero API"
                                )
                                failed_source_ids.add(rec["id"])
                                failed_items.append({
                                    "id": rec["id"],
                                    "title": _clean_line(rec["data"].get("title")) or "Untitled source",
                                    "doi": _clean_bare_doi(rec["data"].get("doi")),
                                    "reason": reason,
                                })
                except WorkspaceError:
                    raise
                except Exception as exc:
                    raise WorkspaceError(
                        "Zotero item creation failed; verify API write permissions and connection",
                        "zotero_sync_failed",
                    ) from exc

            collection_added_keys: list[str] = []
            if collection_key and pending_collection_attachments and hasattr(zot, "update_item"):
                for src, rem, rem_key in pending_collection_attachments:
                    rem_data = rem.get("data") if isinstance(rem.get("data"), dict) else {}
                    existing_cols = rem_data.get("collections")
                    if isinstance(existing_cols, list) and collection_key in existing_cols:
                        continue
                    updated = copy.deepcopy(rem)
                    if not isinstance(updated.get("data"), dict):
                        updated["data"] = {}
                    updated_cols = list(updated["data"].get("collections") or [])
                    updated_cols.append(collection_key)
                    updated["data"]["collections"] = updated_cols
                    try:
                        upd_ok = zot.update_item(updated)
                        if upd_ok is False:
                            raise WorkspaceError("Zotero collection attachment rejected", "zotero_sync_failed")
                        collection_added_keys.append(rem_key)
                    except Exception as exc:
                        failed_source_ids.add(src["id"])
                        failed_items.append({
                            "id": src["id"],
                            "title": _clean_line(src["data"].get("title")) or "Untitled source",
                            "doi": _clean_bare_doi(src["data"].get("doi")),
                            "reason": _sanitize_zotero_failure(str(exc), api_key),
                        })

            if failed_source_ids:
                for plan_entry in items_plan:
                    if plan_entry["id"] in failed_source_ids:
                        plan_entry["action"] = "failed"

            failed_count = len(failed_items)
            sync_status = (
                "synced"
                if failed_count == 0
                else ("partial_failure" if (confirmed_created > 0 or len(collection_added_keys) > 0) else "failed")
            )

            prefix = "groups" if library_type == "group" else "users"
            library_url = (
                f"https://www.zotero.org/{prefix}/{library_id}/collections/{collection_key}/items"
                if collection_key
                else f"https://www.zotero.org/{prefix}/{library_id}/items"
            )

            return {
                "ok": True,
                "status": sync_status,
                "dry_run": False,
                "created_count": confirmed_created,
                "failed_count": failed_count,
                "skipped_duplicates": duplicates,
                "created_keys": created_keys,
                "collection_key": collection_key,
                "collection_name": collection_name,
                "collection_added_count": len(collection_added_keys),
                "collection_added_keys": collection_added_keys,
                "library_url": library_url,
                "failed_items": failed_items,
                "items": items_plan,
            }

    def pack_obsidian(self, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        integrations = self._require_enabled()
        body = dict(payload or {})
        extra = set(body) - {"selected_source_ids"}
        if extra:
            raise WorkspaceError(f"Unsupported fields: {', '.join(sorted(extra))}", "invalid_request")

        self._validate_project_id(project_id)
        export_rel = f".research/exports/obsidian-{project_id}"
        base_rel = f"{export_rel}/{project_id}.base"
        manifest_rel = f"{export_rel}/manifest.json"

        used_names: set[str] = set()
        note_files: list[str] = []
        manifest_notes: list[dict[str, Any]] = []
        with self._export_lock(f"obsidian:{project_id}", f".obsidian-{project_id}"):
            project, sources, screenings = self._resolve_project_sources(
                project_id, body.get("selected_source_ids")
            )
            artifact_refs = self._resolve_source_artifacts(project_id, sources)
            generated_at = _utc_now()
            export_dir = safe_path(self.workspace.root, export_rel)
            base_path = safe_path(self.workspace.root, base_rel)
            manifest_path = safe_path(self.workspace.root, manifest_rel)
            export_dir.mkdir(parents=True, exist_ok=True)
            self._clean_stale_files(export_dir, (".md", ".base"))

            for index, rec in enumerate(sources, start=1):
                slug = _slugify(_clean_line(rec["data"].get("title")), fallback=f"note-{index}")
                stem = f"{index:02d}-{slug}"
                candidate_name = f"{stem}.md"
                collision = 2
                while candidate_name in used_names:
                    candidate_name = f"{stem}-{collision}.md"
                    collision += 1
                used_names.add(candidate_name)

                note_rel = f"{export_rel}/{candidate_name}"
                note_path = safe_path(self.workspace.root, note_rel)
                decision = screenings.get(rec["id"], "unscreened")
                art_ref = artifact_refs.get(rec["id"])
                _atomic_text(
                    note_path,
                    _render_obsidian_note(
                        rec,
                        project_id=project_id,
                        screening=decision,
                        artifact_ref=art_ref,
                    ),
                )
                note_files.append(note_rel)
                manifest_notes.append({
                    "index": index,
                    "source_id": _clean_line(rec.get("id")),
                    "source_revision": rec.get("revision", 1),
                    "revision_sha256": _source_revision_sha256(rec, decision, art_ref),
                    "title": _clean_line(rec["data"].get("title")) or f"Note {index}",
                    "doi": _clean_bare_doi(rec["data"].get("doi")),
                    "locator": _safe_http_url(
                        rec["data"].get("locator"), rec["data"].get("locator_kind")
                    ),
                    "artifact_status": (art_ref or {}).get("artifact_status", ""),
                    "artifact_id": (art_ref or {}).get("artifact_id", ""),
                    "artifact_path": (art_ref or {}).get("artifact_path", ""),
                    "artifact_sha256": (art_ref or {}).get("artifact_sha256", ""),
                    "reading_scope": _reading_scope(rec["data"]),
                    "screening": decision,
                    "identity_status": _clean_line(rec["data"].get("identity_status")) or "unverified",
                    "publication_version": _clean_line(rec["data"].get("publication_version")),
                    "note_file": note_rel,
                })

            _atomic_text(
                base_path,
                _build_obsidian_base_yaml(project_id, project["title"]),
            )
            atomic_json(
                manifest_path,
                {
                    "project_id": project_id,
                    "project_title": project["title"],
                    "note_count": len(sources),
                    "generated_at": generated_at,
                    "notes": manifest_notes,
                },
            )

        return {
            "ok": True,
            "export_dir": export_rel,
            "base_file": base_rel,
            "manifest_file": manifest_rel,
            "note_files": note_files,
            "note_count": len(sources),
            "obsidian_vault_name": self._resolve_vault_name(integrations),
        }

    def import_obsidian_notes(
        self, project_id: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Import read-only Obsidian vault frontmatter notes into Workspace sources."""
        self._require_enabled()
        body = dict(payload or {})
        extra = set(body) - {"collection_id", "note_ids", "dry_run"}
        if extra:
            raise WorkspaceError(
                f"Unsupported fields: {', '.join(sorted(extra))}",
                "invalid_request",
            )

        raw_dry_run = body.get("dry_run", False)
        if type(raw_dry_run) is not bool:
            raise WorkspaceError("dry_run must be a boolean", "invalid_request")
        dry_run: bool = raw_dry_run

        raw_collection = body.get("collection_id")
        collection_id: str | None = None
        if raw_collection is not None:
            if not isinstance(raw_collection, str) or not raw_collection.strip():
                raise WorkspaceError(
                    "collection_id must be a non-empty string",
                    "invalid_request",
                )
            collection_id = raw_collection.strip()

        raw_note_ids = body.get("note_ids")
        requested_note_ids: list[str] | None = None
        if raw_note_ids is not None:
            if (
                not isinstance(raw_note_ids, list)
                or not raw_note_ids
                or any(not isinstance(nid, str) or not nid.strip() for nid in raw_note_ids)
            ):
                raise WorkspaceError(
                    "note_ids must be a non-empty list of non-empty strings",
                    "invalid_request",
                )
            if len(raw_note_ids) > _MAX_SELECTED_IDS:
                raise WorkspaceError(
                    f"note_ids exceeds maximum of {_MAX_SELECTED_IDS}",
                    "invalid_request",
                )
            requested_note_ids = list(dict.fromkeys(nid.strip() for nid in raw_note_ids))

        self._validate_project_id(project_id)

        scope_path = getattr(self.obsidian_validation, "scope", None)
        if scope_path is None:
            raise WorkspaceError(
                "Obsidian vault is not configured for this workspace",
                "obsidian_not_configured",
            )

        from research_hub.dedup import normalize_title
        from research_hub.utils.doi import normalize_doi
        from .library_snapshot import read_vault_snapshot
        from .service import call_workspace

        snapshot = read_vault_snapshot(
            scope_path,
            collection_id=collection_id,
            note_ids=requested_note_ids,
        )
        if snapshot.get("ok") is False:
            raise WorkspaceError(
                _clean_line(snapshot.get("error")) or "Obsidian vault snapshot is unavailable",
                _clean_line(snapshot.get("code")) or "library_snapshot_unavailable",
            )
        truncated = bool(snapshot.get("truncated"))

        if collection_id is not None:
            known_collections = {
                c["id"]
                for c in (snapshot.get("collections") or [])
                if isinstance(c, dict) and isinstance(c.get("id"), str)
            }
            if collection_id not in known_collections:
                raise WorkspaceError(
                    "Requested collection_id does not exist in the configured Obsidian vault",
                    "invalid_source",
                )

        raw_notes = snapshot.get("notes") or []
        candidate_notes = [
            note
            for note in raw_notes
            if isinstance(note, dict)
            and isinstance(note.get("data"), dict)
            and (collection_id is None or note["data"].get("collection_id") == collection_id)
        ]

        if requested_note_ids is not None:
            notes_by_id = {
                note["id"]: note
                for note in candidate_notes
                if isinstance(note.get("id"), str)
            }
            selected_notes: list[dict[str, Any]] = []
            for nid in requested_note_ids:
                if nid not in notes_by_id:
                    if truncated:
                        raise WorkspaceError(
                            "One or more requested note_ids could not be resolved because the Obsidian vault snapshot was truncated",
                            "snapshot_truncated",
                        )
                    raise WorkspaceError(
                        "One or more requested note_ids do not exist in the selected Obsidian scope",
                        "invalid_source",
                    )
                selected_notes.append(notes_by_id[nid])
        else:
            selected_notes = candidate_notes

        batch_id = f"obsidian-vault:{hashlib.sha256(str(scope_path).encode('utf-8')).hexdigest()[:16]}"

        def _norm_title_token(value: object) -> str:
            cleaned = _clean_line(value)
            if not cleaned:
                return ""
            return normalize_title(cleaned) or cleaned.casefold()

        with self._export_lock(f"obsidian-import:{project_id}", f".obsidian-import-{project_id}"):
            _, existing_sources, _, _ = self._load_curated_sources(project_id)
            seen_dois: dict[str, list[dict[str, Any]]] = {}
            seen_zkeys: dict[str, list[dict[str, Any]]] = {}
            seen_path_records: dict[str, list[dict[str, Any]]] = {}
            seen_title_year_records: dict[tuple[str, str], list[dict[str, Any]]] = {}

            for existing in existing_sources:
                edata = existing.get("data") if isinstance(existing.get("data"), dict) else {}
                existing_doi = normalize_doi(_clean_bare_doi(edata.get("doi")))
                existing_zkey = _clean_line(edata.get("zotero_key") or edata.get("zotero-key"))
                norm_existing_zkey = existing_zkey.casefold() if existing_zkey else ""
                existing_path = _clean_line(edata.get("origin_note_path") or edata.get("note_path"))
                existing_vault_id = _clean_line(edata.get("origin_vault_id"))
                if not existing_vault_id:
                    raw_batch = _clean_line(edata.get("batch_id"))
                    if raw_batch.startswith("obsidian-vault:"):
                        existing_vault_id = raw_batch
                existing_title = _norm_title_token(edata.get("title"))
                existing_year = _clean_line(edata.get("year"))
                existing_authors = _author_surnames(edata.get("authors"))
                rec = {
                    "vault_id": existing_vault_id,
                    "doi": existing_doi,
                    "zkey": norm_existing_zkey,
                    "title": existing_title,
                    "year": existing_year,
                    "authors": existing_authors,
                }
                if existing_doi:
                    seen_dois.setdefault(existing_doi, []).append(rec)
                if norm_existing_zkey:
                    seen_zkeys.setdefault(norm_existing_zkey, []).append(rec)
                if existing_path:
                    seen_path_records.setdefault(existing_path, []).append(rec)
                if existing_title and existing_year:
                    seen_title_year_records.setdefault((existing_title, existing_year), []).append(rec)

            batch_items: list[dict[str, Any]] = []
            preview_items: list[dict[str, Any]] = []
            skipped_existing = 0

            for note in selected_notes:
                ndata = note["data"]
                note_id = _clean_line(note.get("id"))
                note_path = _clean_line(ndata.get("note_path"))
                title = _clean_line(ndata.get("title")) or (Path(note_path).stem if note_path else note_id)
                doi = _clean_bare_doi(ndata.get("doi"))
                norm_doi = normalize_doi(doi) if doi else ""
                zotero_key = _clean_line(ndata.get("zotero_key"))
                norm_zkey = zotero_key.casefold() if zotero_key else ""
                year = _clean_line(ndata.get("year"))
                norm_title = _norm_title_token(title)
                authors = _collect_authors(ndata.get("authors"))
                inc_authors = _author_surnames(authors)
                title_year = (norm_title, year) if (norm_title and year) else None

                doi_match = False
                if norm_doi and norm_doi in seen_dois:
                    for ex in seen_dois[norm_doi]:
                        title_conflict = bool(norm_title and ex["title"] and norm_title != ex["title"])
                        zkey_conflict = bool(norm_zkey and ex["zkey"] and norm_zkey != ex["zkey"])
                        if not title_conflict and not zkey_conflict:
                            doi_match = True
                            break

                zkey_match = False
                if norm_zkey and norm_zkey in seen_zkeys:
                    for ex in seen_zkeys[norm_zkey]:
                        doi_conflict = bool(norm_doi and ex["doi"] and norm_doi != ex["doi"])
                        title_conflict = bool(norm_title and ex["title"] and norm_title != ex["title"])
                        year_conflict = bool(year and ex["year"] and year != ex["year"])
                        author_conflict = bool(
                            inc_authors and ex["authors"] and not (inc_authors & ex["authors"])
                        )
                        if ex["vault_id"] and ex["vault_id"] == batch_id:
                            if not doi_conflict and not title_conflict:
                                zkey_match = True
                                break
                        elif (
                            not doi_conflict
                            and not title_conflict
                            and not year_conflict
                            and not author_conflict
                        ):
                            zkey_match = True
                            break

                title_year_match = False
                if title_year is not None and title_year in seen_title_year_records:
                    for ex in seen_title_year_records[title_year]:
                        doi_conflict = bool(norm_doi and ex["doi"] and norm_doi != ex["doi"])
                        zkey_conflict = bool(norm_zkey and ex["zkey"] and norm_zkey != ex["zkey"])
                        author_conflict = bool(
                            inc_authors and ex["authors"] and not (inc_authors & ex["authors"])
                        )
                        if not doi_conflict and not zkey_conflict and not author_conflict:
                            title_year_match = True
                            break

                path_match = False
                if note_path and note_path in seen_path_records:
                    for ex in seen_path_records[note_path]:
                        ex_vault_id = ex["vault_id"]
                        if ex_vault_id and ex_vault_id != batch_id:
                            continue
                        doi_conflict = bool(norm_doi and ex["doi"] and norm_doi != ex["doi"])
                        zkey_conflict = bool(norm_zkey and ex["zkey"] and norm_zkey != ex["zkey"])
                        title_conflict = bool(norm_title and ex["title"] and norm_title != ex["title"])
                        year_conflict = bool(year and ex["year"] and year != ex["year"])
                        author_conflict = bool(
                            inc_authors and ex["authors"] and not (inc_authors & ex["authors"])
                        )
                        if ex_vault_id == batch_id:
                            if not doi_conflict and not zkey_conflict and not title_conflict:
                                path_match = True
                                break
                        elif (
                            not doi_conflict
                            and not zkey_conflict
                            and not title_conflict
                            and not year_conflict
                            and not author_conflict
                        ):
                            path_match = True
                            break

                is_duplicate = bool(
                    doi_match
                    or zkey_match
                    or path_match
                    or title_year_match
                )
                if is_duplicate:
                    skipped_existing += 1
                    preview_items.append({
                        "note_id": note_id,
                        "note_path": note_path,
                        "title": title,
                        "doi": doi,
                        "zotero_key": zotero_key,
                        "action": "skip_existing",
                    })
                    continue

                inc_rec = {
                    "vault_id": batch_id,
                    "doi": norm_doi,
                    "zkey": norm_zkey,
                    "title": norm_title,
                    "year": year,
                    "authors": inc_authors,
                }
                if norm_doi:
                    seen_dois.setdefault(norm_doi, []).append(inc_rec)
                if norm_zkey:
                    seen_zkeys.setdefault(norm_zkey, []).append(inc_rec)
                if note_path:
                    seen_path_records.setdefault(note_path, []).append(inc_rec)
                if title_year is not None:
                    seen_title_year_records.setdefault(title_year, []).append(inc_rec)

                locator = (
                    _safe_http_url(ndata.get("locator"))
                    or (f"https://doi.org/{norm_doi}" if norm_doi else f"obsidian:{note_path or note_id}")
                )
                abstract = str(ndata.get("abstract") or "").strip()[:12000]
                category = _clean_line(ndata.get("category"))
                tags = _collect_tags(ndata)

                source_item: dict[str, Any] = {
                    "batch_id": batch_id,
                    "origin_vault_id": batch_id,
                    "id": note_id,
                    "upstream_id": note_id,
                    "title": title,
                    "locator": locator,
                    "doi": doi,
                    "year": year,
                    "authors": authors,
                    "abstract": abstract,
                    "category": category,
                    "tags": tags,
                    "zotero_key": zotero_key,
                    "origin_note_path": note_path,
                    "reading_scope": "note-metadata",
                    "reading_level": "note-metadata",
                    "identity_status": "unverified",
                    "human_acceptance": "pending",
                }
                batch_items.append(source_item)
                preview_items.append({
                    "note_id": note_id,
                    "note_path": note_path,
                    "title": title,
                    "doi": doi,
                    "zotero_key": zotero_key,
                    "action": "import",
                })

            if dry_run:
                return {
                    "ok": True,
                    "dry_run": True,
                    "would_import": len(batch_items),
                    "skipped_existing": skipped_existing,
                    "truncated": truncated,
                    "items": preview_items,
                }

            created_ids: list[str] = []
            imported_count = 0
            if batch_items:
                batch_res = call_workspace(
                    self.workspace.root,
                    "project",
                    "record-batch",
                    {
                        "project_id": project_id,
                        "kind": "source",
                        "data": batch_items,
                    },
                )
                if not batch_res.get("ok"):
                    raise WorkspaceError(
                        _clean_line(batch_res.get("error")) or "Obsidian note import failed",
                        _clean_line(batch_res.get("code")) or "invalid_request",
                    )
                batch_info = batch_res.get("batch") or {}
                created_records = batch_info.get("records") or []
                created_ids = [
                    _clean_line(rec.get("id"))
                    for rec in created_records
                    if isinstance(rec, dict) and _clean_line(rec.get("id"))
                ]
                counts = batch_info.get("counts") or {}
                imported_count = int(counts.get("created", len(created_ids)))

        return {
            "ok": True,
            "dry_run": False,
            "imported_count": imported_count,
            "skipped_existing": skipped_existing,
            "truncated": truncated,
            "created_ids": created_ids,
        }

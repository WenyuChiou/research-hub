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
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any
from urllib.parse import urlsplit

from research_hub.locks import file_lock
from .core import Workspace, WorkspaceError, atomic_json, digest, safe_path
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
    return (
        _clean_line(data.get("reading_level"))
        or _clean_line(data.get("reading_scope"))
        or "unknown"
    )


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


def _source_revision_sha256(record: dict[str, Any], screening: str) -> str:
    return digest({
        "id": _clean_line(record.get("id")),
        "data": record.get("data") if isinstance(record.get("data"), dict) else {},
        "screening": screening,
    })


def _zotero_source_fingerprint(record: dict[str, Any]) -> str:
    return digest({
        "id": _clean_line(record.get("id")),
        "revision": record.get("revision"),
        "data": record.get("data") if isinstance(record.get("data"), dict) else {},
    })


def _get_zotero_client(library_id: str, library_type: str, api_key: str):
    from pyzotero import zotero

    return zotero.Zotero(library_id, library_type, api_key)


def _check_zotero_duplicate_strict(zot: Any, title: str, doi: str = "") -> bool:
    """Lookup existing Zotero item by DOI or title, raising WorkspaceError on API failure."""
    from research_hub.utils.doi import normalize_doi

    norm_doi = normalize_doi(doi) if doi else ""
    norm_title = (title or "").lower()

    def _matches(items: object) -> bool:
        if not isinstance(items, list):
            return False
        for entry in items:
            if not isinstance(entry, dict):
                continue
            edata = entry.get("data")
            if not isinstance(edata, dict):
                continue
            if norm_title and str(edata.get("title") or "").lower() == norm_title:
                return True
            if norm_doi and normalize_doi(str(edata.get("DOI") or "")) == norm_doi:
                return True
        return False

    query = doi or (title or "")[:50]
    try:
        existing = zot.items(q=query, limit=5)
        if _matches(existing):
            return True
        if not existing and doi and title:
            fallback = zot.items(q=title[:50], limit=5)
            return _matches(fallback)
    except Exception as exc:
        raise WorkspaceError(
            "Zotero duplicate lookup failed; verify API credentials, connection, or rate limits before syncing",
            "zotero_lookup_failed",
        ) from exc
    return False


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
) -> str:
    data = record["data"]
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
    summary = _saved_summary(data)
    working = _working_summary_text(data)
    relevance = str(data.get("relevance") or "").strip()

    frontmatter = "\n".join([
        "---",
        f"title: {_yaml_quote(title)}",
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
        "---",
    ])

    body_lines = [
        f"# {_inline_md(title)}",
        "",
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
) -> str:
    data = record["data"]
    title = _clean_line(data.get("title")) or f"Source {index}"
    authors = ", ".join(_collect_authors(data.get("authors"))) or "Unknown"
    year = _clean_line(data.get("year")) or "n.d."
    venue = _clean_line(data.get("venue")) or _clean_line(data.get("journal"))
    doi = _clean_bare_doi(data.get("doi"))
    url = _safe_http_url(data.get("locator"), data.get("locator_kind"))
    scope = _reading_scope(data)
    category = _category_slug(data) or "unclassified"
    tags = _collect_tags(data)
    summary = _saved_summary(data)
    working = _working_summary_text(data)
    relevance = str(data.get("relevance") or "").strip()

    is_full = scope == "full-text"
    boundary = (
        "Full-text declared in Research Hub."
        if is_full
        else "Abstract / metadata-only source — do NOT attribute unverified sample sizes, p-values, or full-text experimental details."
    )

    lines = [
        f"# {_inline_md(title)} ({_inline_md(year)})",
        "",
        f"- **Project**: {_inline_md(project_title)} (`{_inline_md(project_id)}`)",
        f"- **Authors**: {_inline_md(authors)}",
        f"- **Year**: {_inline_md(year)}",
    ]
    if venue:
        lines.append(f"- **Venue**: {_inline_md(venue)}")
    if doi:
        lines.append(f"- **DOI**: {_inline_md(doi)}")
    if url:
        lines.append(f"- **URL**: {url}")
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
) -> str:
    full_text = [s for s in sources if _reading_scope(s["data"]) == "full-text"]
    abstract_or_meta = [s for s in sources if _reading_scope(s["data"]) != "full-text"]
    screening_map = screenings or {}

    def _entry(record: dict[str, Any], idx: int) -> str:
        data = record["data"]
        source_id = _clean_line(record.get("id"))
        decision = screening_map.get(source_id, "unscreened")
        rev_sha256 = _source_revision_sha256(record, decision)
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

    def _resolve_project_sources(
        self,
        project_id: str,
        selected_source_ids: object,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
        project = self._validate_project_id(project_id)
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
                if sid not in seen_ids:
                    seen_ids.add(sid)
                    deduped.append(curated_by_id[sid])
            return project, deduped, screenings

        active_sources = [
            s for s in curated_sources if s["data"].get("archived") is not True
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

    def bundle_notebooklm(self, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        integrations = self._require_enabled()
        body = dict(payload or {})
        extra = set(body) - {"selected_source_ids"}
        if extra:
            raise WorkspaceError(f"Unsupported fields: {', '.join(sorted(extra))}", "invalid_request")

        project, sources, screenings = self._resolve_project_sources(
            project_id, body.get("selected_source_ids")
        )
        export_rel = f".research/exports/notebooklm-{project_id}"
        pack_rel = f"{export_rel}/00-notebooklm-source-pack.md"
        manifest_rel = f"{export_rel}/manifest.json"

        full_text_count = sum(1 for s in sources if _reading_scope(s["data"]) == "full-text")
        abstract_only_count = len(sources) - full_text_count
        generated_at = _utc_now()

        manifest = {
            "project_id": project_id,
            "project_title": project["title"],
            "source_count": len(sources),
            "full_text_count": full_text_count,
            "abstract_only_count": abstract_only_count,
            "generated_at": generated_at,
        }

        used_names: set[str] = set()
        source_files: list[str] = []
        manifest_sources: list[dict[str, Any]] = []
        with self._export_lock(f"notebooklm:{project_id}", f".notebooklm-{project_id}"):
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
                _atomic_text(
                    file_path,
                    _render_nlm_individual_source(
                        rec,
                        index=index,
                        project_id=project_id,
                        project_title=project["title"],
                        screening=decision,
                    ),
                )
                source_files.append(file_rel)
                manifest_sources.append({
                    "index": index,
                    "source_id": _clean_line(rec.get("id")),
                    "title": _clean_line(rec["data"].get("title")) or f"Source {index}",
                    "doi": _clean_bare_doi(rec["data"].get("doi")),
                    "locator": _safe_http_url(
                        rec["data"].get("locator"), rec["data"].get("locator_kind")
                    ),
                    "reading_scope": _reading_scope(rec["data"]),
                    "screening": decision,
                    "identity_status": _clean_line(rec["data"].get("identity_status")) or "unverified",
                    "publication_version": _clean_line(rec["data"].get("publication_version")),
                    "recorded_at": _clean_line(rec["data"].get("recorded_at")),
                    "revision_sha256": _source_revision_sha256(rec, decision),
                    "source_file": file_rel,
                })

            _atomic_text(
                pack_path,
                _render_nlm_pack_markdown(
                    sources,
                    project_id=project_id,
                    project_title=project["title"],
                    screenings=screenings,
                ),
            )
            manifest["sources"] = manifest_sources
            atomic_json(manifest_path, manifest)

        nlm_status = self._safe_nlm_status(integrations)
        return {
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
        }

    def sync_zotero(self, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        integrations = self._require_enabled()
        body = dict(payload or {})
        extra = set(body) - {"dry_run", "selected_source_ids", "expected_revisions"}
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

        selected_ids_arg = body.get("selected_source_ids")
        _, sources, _ = self._resolve_project_sources(
            project_id, selected_ids_arg
        )
        source_revisions = {s["id"]: _zotero_source_fingerprint(s) for s in sources}

        cfg_path, cfg_data = integrations._read_config_dict()
        resolved = integrations._resolve_zotero_effective(cfg_data, cfg_path.parent)
        api_key = str(resolved.get("api_key") or "").strip()
        library_id = str(resolved.get("library_id") or "").strip()
        library_type = str(resolved.get("library_type") or "user").strip() or "user"

        if not api_key or not library_id:
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

        from research_hub.utils.doi import normalize_doi

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

            items_plan: list[dict[str, Any]] = []
            records_to_create: list[dict[str, Any]] = []
            seen_dois: set[str] = set()
            seen_titles: set[str] = set()
            duplicates = 0

            for src in sources:
                sdata = src["data"]
                title = _clean_line(sdata.get("title")) or "Untitled source"
                doi = _clean_bare_doi(sdata.get("doi"))
                norm_doi = normalize_doi(doi) if doi else ""
                norm_title = title.casefold()

                in_batch_dup = bool(
                    (norm_doi and norm_doi in seen_dois)
                    or (norm_title and norm_title in seen_titles)
                )
                remote_dup = False if in_batch_dup else _check_zotero_duplicate_strict(zot, title, doi)
                if in_batch_dup or remote_dup:
                    duplicates += 1
                    items_plan.append({
                        "id": src["id"],
                        "title": title,
                        "doi": doi,
                        "action": "skip_duplicate",
                    })
                else:
                    if norm_doi:
                        seen_dois.add(norm_doi)
                    if norm_title:
                        seen_titles.add(norm_title)
                    records_to_create.append(src)
                    items_plan.append({
                        "id": src["id"],
                        "title": title,
                        "doi": doi,
                        "action": "create",
                    })

            if dry_run:
                return {
                    "ok": True,
                    "status": "ready",
                    "dry_run": True,
                    "candidate_count": len(sources),
                    "would_create": len(records_to_create),
                    "duplicates": duplicates,
                    "source_revisions": source_revisions,
                    "items": items_plan,
                }

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

            if failed_source_ids:
                for plan_entry in items_plan:
                    if plan_entry["id"] in failed_source_ids:
                        plan_entry["action"] = "failed"

            failed_count = len(failed_items)
            sync_status = (
                "synced"
                if failed_count == 0
                else ("partial_failure" if confirmed_created > 0 else "failed")
            )

            return {
                "ok": True,
                "status": sync_status,
                "dry_run": False,
                "created_count": confirmed_created,
                "failed_count": failed_count,
                "skipped_duplicates": duplicates,
                "created_keys": created_keys,
                "failed_items": failed_items,
                "items": items_plan,
            }

    def pack_obsidian(self, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        integrations = self._require_enabled()
        body = dict(payload or {})
        extra = set(body) - {"selected_source_ids"}
        if extra:
            raise WorkspaceError(f"Unsupported fields: {', '.join(sorted(extra))}", "invalid_request")

        project, sources, screenings = self._resolve_project_sources(
            project_id, body.get("selected_source_ids")
        )
        export_rel = f".research/exports/obsidian-{project_id}"
        base_rel = f"{export_rel}/{project_id}.base"

        used_names: set[str] = set()
        note_files: list[str] = []
        with self._export_lock(f"obsidian:{project_id}", f".obsidian-{project_id}"):
            export_dir = safe_path(self.workspace.root, export_rel)
            base_path = safe_path(self.workspace.root, base_rel)
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
                _atomic_text(
                    note_path,
                    _render_obsidian_note(rec, project_id=project_id, screening=decision),
                )
                note_files.append(note_rel)

            _atomic_text(
                base_path,
                _build_obsidian_base_yaml(project_id, project["title"]),
            )

        return {
            "ok": True,
            "export_dir": export_rel,
            "base_file": base_rel,
            "note_files": note_files,
            "note_count": len(sources),
            "obsidian_vault_name": self._resolve_vault_name(integrations),
        }

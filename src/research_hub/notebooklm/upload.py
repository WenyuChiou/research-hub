"""Upload a cluster's bundle to NotebookLM and cache the resulting state."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from research_hub.notebooklm.auth import default_state_file
from research_hub.notebooklm.client import (
    BriefingArtifact,
    NotebookHandle,
    NotebookLMClient,
    NotebookLMError,
    UploadResult,
    _parse_notebook_id,
)

BETWEEN_UPLOADS_SEC = 1.0
DATASET_DOI_PREFIXES = ("10.5281/zenodo.", "10.6084/m9.figshare.")
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
BAD_TITLE_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("unable_to_load", "unable to load", re.compile(r"(?i)unable to load")),
    ("error", "error page", re.compile(r"(?i)\berror\s*\d*\b")),
    ("abstract_id_pattern", "abstract-id pattern", re.compile(r"^Abstract [A-Z]+[-\d]+$")),
    ("blank_vol_no", "blank vol/no", re.compile(r"\|\s*Vol\s*,\s*No\s*$")),
    ("page_not_found", "page not found", re.compile(r"(?i)page not found")),
    ("forbidden_403", "403 forbidden", re.compile(r"(?i)403\s*forbidden")),
)

# Legacy test monkeypatch anchors. The RPC implementation no longer uses them.
open_cdp_session = None
Entry = dict[str, Any]
OVER_CAP_STRATEGIES = frozenset({"fail", "top-n-recent", "top-n-cited", "fit-score", "shard"})
SHARD_ORDER_STRATEGIES = frozenset({"recent", "cited", "fit"})

BRIEFING_OFF_TOPIC_SECTION = """### Off-topic papers

List any papers in the provided sources that are NOT about the cluster topic.
For each, give the paper's title and a one-sentence explanation of why it
doesn't fit. If every paper is on-topic, write "none" on a single line.
"""


def _check_session_health(_page) -> tuple[bool, str]:
    return True, "ok"


@dataclass
class SuspiciousSource:
    doi: str
    title: str
    matched_rule: str
    matched_label: str
    fulltext_chars: int | None = None
    source_id: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "doi": self.doi,
            "title": self.title,
            "matched_rule": self.matched_rule,
        }
        if self.fulltext_chars is not None:
            payload["fulltext_chars"] = self.fulltext_chars
        return payload


@dataclass
class IngestValidationReport:
    cluster_slug: str
    validated_at: str
    total: int
    suspicious: list[SuspiciousSource] = field(default_factory=list)

    @property
    def suspicious_count(self) -> int:
        return len(self.suspicious)

    def to_dict(self) -> dict[str, object]:
        return {
            "cluster_slug": self.cluster_slug,
            "validated_at": self.validated_at,
            "total": self.total,
            "suspicious_count": self.suspicious_count,
            "suspicious": [source.to_dict() for source in self.suspicious],
        }

    def warning_text(self) -> str:
        if not self.suspicious:
            return ""
        lines = [
            f"[warn] {self.suspicious_count} source(s) look like they did not ingest content:",
        ]
        for source in self.suspicious:
            doi = source.doi or "(unknown DOI)"
            title = source.title or "(untitled)"
            lines.append(f'  - {doi}  "{title}"  (matched: {source.matched_label})')
        lines.extend(
            [
                "These poison downstream artifacts. Consider replacing the URL or",
                "uploading a PDF directly via the NotebookLM web UI.",
            ]
        )
        return "\n".join(lines)


class NotebookLMCapacityError(NotebookLMError):
    """Raised when a cluster exceeds NotebookLM's per-notebook source cap."""


@dataclass
class UploadReport:
    cluster_slug: str
    notebook_url: str = ""
    notebook_id: str = ""
    notebook_name: str = ""
    notebook_was_reused: bool = False
    uploaded: list[UploadResult] = field(default_factory=list)
    skipped_already_uploaded: int = 0
    errors: list[dict] = field(default_factory=list)
    dry_run: bool = False
    ingest_validation: IngestValidationReport | None = None
    over_cap_skipped: list[Entry] = field(default_factory=list)
    over_cap_strategy: str = "fail"

    @property
    def success_count(self) -> int:
        return sum(1 for result in self.uploaded if result.success)

    @property
    def fail_count(self) -> int:
        return sum(1 for result in self.uploaded if not result.success)


@dataclass
class DownloadReport:
    cluster_slug: str
    notebook_name: str
    artifact_path: Path
    char_count: int
    titles: list[str] = field(default_factory=list)
    brief_md_path: Path | None = None


def _load_nlm_cache(cache_path: Path) -> dict:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_nlm_cache(cache_path: Path, cache: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_latest_bundle(bundles_root: Path, cluster_slug: str) -> Path | None:
    """Pick the most recent bundle folder for a cluster."""
    if not bundles_root.exists():
        return None
    candidates = sorted(
        bundles_root.glob(f"{cluster_slug}-*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _open_debug_log(research_hub_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = research_hub_dir / f"nlm-debug-{timestamp}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _log_jsonl(path: Path, event: dict) -> None:
    payload = dict(event)
    payload["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def validate_uploaded_sources(
    client,
    handle,
    doi_list,
    *,
    cluster_slug: str = "",
    artifacts_dir: Path | None = None,
) -> IngestValidationReport:
    """Validate NotebookLM source titles/fulltext after upload.

    This is intentionally advisory: unsupported SDK methods or malformed
    source objects produce an empty report instead of failing the upload.
    """

    doi_values = [str(doi).strip() for doi in doi_list if str(doi).strip()]
    validated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    resolved_cluster = cluster_slug or Path(getattr(handle, "name", "") or "notebook").name
    try:
        sources = _list_notebook_sources(client, getattr(handle, "notebook_id", ""))
    except Exception:
        sources = []

    suspicious: list[SuspiciousSource] = []
    for index, source in enumerate(sources):
        title = str(getattr(source, "title", "") or "")
        source_id = str(getattr(source, "id", "") or getattr(source, "source_id", "") or "")
        fulltext = _fetch_source_fulltext(client, getattr(handle, "notebook_id", ""), source_id)
        fulltext_chars = _fulltext_char_count(fulltext)
        doi = _doi_for_source(source, index, doi_values, fulltext)
        match = _title_rule_match(title)
        if match is None and fulltext_chars is not None and fulltext_chars < 2000 and not _is_dataset_doi(doi):
            match = ("short_fulltext", "short fulltext")
        if match is None:
            continue
        rule_id, label = match
        suspicious.append(
            SuspiciousSource(
                doi=doi,
                title=title,
                matched_rule=rule_id,
                matched_label=label,
                fulltext_chars=fulltext_chars,
                source_id=source_id,
            )
        )

    report = IngestValidationReport(
        cluster_slug=resolved_cluster,
        validated_at=validated_at,
        total=len(doi_values) if doi_values else len(sources),
        suspicious=suspicious,
    )
    if artifacts_dir is not None:
        _write_ingest_validation_sidecar(report, artifacts_dir)
    return report


def _write_ingest_validation_sidecar(report: IngestValidationReport, artifacts_dir: Path) -> None:
    try:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        (artifacts_dir / ".ingest_validation.json").write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _list_notebook_sources(client, notebook_id: str) -> list[Any]:
    list_sources = getattr(client, "list_sources", None)
    if list_sources is not None:
        return list(list_sources(notebook_id) or [])
    sources_api = getattr(client, "sources", None)
    if sources_api is None:
        return []
    list_method = getattr(sources_api, "list", None)
    if list_method is None:
        return []
    try:
        return list(list_method(notebook_id) or [])
    except TypeError:
        return list(list_method() or [])


def _fetch_source_fulltext(client, notebook_id: str, source_id: str) -> Any | None:
    if not source_id:
        return None
    source_fulltext = getattr(client, "source_fulltext", None)
    if source_fulltext is not None:
        try:
            return source_fulltext(notebook_id, source_id)
        except Exception:
            return None
    sources_api = getattr(client, "sources", None)
    if sources_api is None:
        return None
    for method_name in ("get_fulltext", "fulltext"):
        method = getattr(sources_api, method_name, None)
        if method is None:
            continue
        try:
            return method(notebook_id, source_id)
        except TypeError:
            try:
                return method(source_id)
            except Exception:
                return None
        except Exception:
            return None
    return None


def _fulltext_char_count(fulltext: Any | None) -> int | None:
    if fulltext is None:
        return None
    char_count = getattr(fulltext, "char_count", None)
    if isinstance(char_count, int):
        return char_count
    if isinstance(fulltext, str):
        return len(fulltext)
    content = getattr(fulltext, "content", None)
    if isinstance(content, str):
        return len(content)
    if isinstance(fulltext, dict):
        value = fulltext.get("char_count")
        if isinstance(value, int):
            return value
        content_value = fulltext.get("content")
        if isinstance(content_value, str):
            return len(content_value)
    return None


def _title_rule_match(title: str) -> tuple[str, str] | None:
    for rule_id, label, pattern in BAD_TITLE_PATTERNS:
        if pattern.search(title):
            return rule_id, label
    return None


def _doi_for_source(source: Any, index: int, doi_list: list[str], fulltext: Any | None) -> str:
    candidates = [
        getattr(source, "doi", ""),
        getattr(source, "url", ""),
        getattr(source, "title", ""),
        getattr(source, "id", ""),
    ]
    content = getattr(fulltext, "content", "") if fulltext is not None else ""
    if isinstance(fulltext, str):
        content = fulltext
    elif isinstance(fulltext, dict):
        content = str(fulltext.get("content") or "")
    candidates.append(content)
    for candidate in candidates:
        doi = _extract_doi(str(candidate or ""))
        if doi:
            return doi
    if index < len(doi_list):
        return doi_list[index]
    return ""


def _extract_doi(text: str) -> str:
    normalized = unquote(text)
    match = DOI_RE.search(normalized)
    if not match:
        return ""
    return match.group(0).rstrip(".,;:)]}").lower()


def _is_dataset_doi(doi: str) -> bool:
    lowered = doi.lower()
    return any(lowered.startswith(prefix) for prefix in DATASET_DOI_PREFIXES)


def _manifest_doi_list(manifest: dict) -> list[str]:
    seen: set[str] = set()
    dois: list[str] = []
    for entry in manifest.get("entries", []):
        doi = str(entry.get("doi", "") or "").strip()
        if not doi or doi in seen:
            continue
        seen.add(doi)
        dois.append(doi)
    return dois


def _uploadable_entries(manifest: dict) -> list[Entry]:
    return [
        entry
        for entry in manifest.get("entries", [])
        if isinstance(entry, dict) and entry.get("action", "skip") != "skip"
    ]


def check_cluster_capacity(cluster, cfg, *, rate_limit_cap: int = 50) -> None:
    """Raise before browser/session work when the latest bundle exceeds the cap."""
    bundle_dir = _find_latest_bundle(cfg.research_hub_dir / "bundles", cluster.slug)
    if bundle_dir is None:
        raise FileNotFoundError(
            "No bundle found for cluster '{0}'. Run `research-hub notebooklm bundle "
            "--cluster {0}` first.".format(cluster.slug)
        )
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    source_count = len(_uploadable_entries(manifest))
    if source_count > rate_limit_cap:
        raise NotebookLMCapacityError(_capacity_error_message(cluster, source_count, rate_limit_cap))


def _entry_key(entry: Entry) -> str:
    return str(entry.get("pdf_path") or entry.get("url") or entry.get("doi") or "")


def _entry_doi(entry: Entry) -> str:
    return str(entry.get("doi", "") or "").strip()


def _entry_title(entry: Entry) -> str:
    return str(entry.get("title", "") or "").strip()


def _capacity_error_message(cluster, source_count: int, cap: int) -> str:
    overflow = max(0, source_count - cap)
    cluster_name = getattr(cluster, "name", "") or getattr(cluster, "slug", "")
    cluster_slug = getattr(cluster, "slug", "")
    source_word = "source" if overflow == 1 else "sources"
    return (
        f"NotebookLM source cap exceeded for cluster '{cluster_name}' ({cluster_slug}): "
        f"{source_count} sources, {overflow} {source_word} over the {cap}-source cap. "
        "NotebookLM accepts at most 50 sources per notebook. Re-run with "
        "`--over-cap-strategy top-n-recent`, `top-n-cited`, or `fit-score` to prune "
        "explicitly, or use `--over-cap-strategy shard --shard-size 50` / "
        f"`research-hub notebooklm shard --cluster {cluster_slug} --strategy recent` "
        "to split the cluster into multiple notebooks. No sources were uploaded."
    )


def _load_entry_frontmatter(entry: Entry) -> dict[str, Any]:
    path_value = str(entry.get("obsidian_path", "") or "")
    if not path_value:
        return {}
    note_path = Path(path_value)
    try:
        text = note_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    body = text[3:end]
    try:
        import yaml

        parsed = yaml.safe_load(body) or {}
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        meta: dict[str, str] = {}
        for line in body.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip("\"'")
        return meta


def _entry_value(entry: Entry, frontmatter: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = entry.get(key)
        if value not in (None, ""):
            return value
        value = frontmatter.get(key)
        if value not in (None, ""):
            return value
    return ""


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


def _entry_recency_value(entry: Entry, frontmatter: dict[str, Any]) -> str:
    value = _entry_value(
        entry,
        frontmatter,
        "ingested_at",
        "created_at",
        "published_at",
        "published",
        "publication_date",
        "published_date",
    )
    if value:
        return str(value)
    year = _entry_value(entry, frontmatter, "year", "publication_year")
    year_int = _as_int(year)
    return f"{year_int:04d}" if year_int else ""


def _load_fit_score_map(cfg, cluster_slug: str) -> dict[str, int]:
    candidates: list[Path] = []
    hub_root = getattr(cfg, "hub", None)
    if hub_root is not None:
        candidates.append(Path(hub_root) / cluster_slug / ".fit_check_accepted.json")
    raw_root = getattr(cfg, "raw", None)
    if raw_root is not None:
        candidates.append(Path(raw_root) / cluster_slug / ".fit_check_accepted.json")

    scores: dict[str, int] = {}
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            items = payload.get("accepted") or payload.get("scores") or []
        elif isinstance(payload, list):
            items = payload
        else:
            items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            doi = str(item.get("doi", "") or "").strip().lower()
            if doi:
                scores[doi] = _as_int(item.get("score"))
    return scores


def _ranked_entries(
    entries: list[Entry],
    strategy: str,
    cfg,
    cluster_slug: str,
) -> list[tuple[int, Entry]]:
    frontmatter_by_index = {index: _load_entry_frontmatter(entry) for index, entry in enumerate(entries)}
    fit_scores = _load_fit_score_map(cfg, cluster_slug) if strategy == "fit-score" else {}

    def key(item: tuple[int, Entry]) -> tuple[Any, ...]:
        index, entry = item
        frontmatter = frontmatter_by_index[index]
        title = (_entry_title(entry) or str(frontmatter.get("title", "") or "")).lower()
        recency = _entry_recency_value(entry, frontmatter)
        citations = _as_int(
            _entry_value(
                entry,
                frontmatter,
                "citation_count",
                "cited_by_count",
                "is_referenced_by_count",
                "references_count",
            )
        )
        if strategy == "top-n-recent":
            return (recency, citations, title)
        if strategy == "top-n-cited":
            return (citations, recency, title)
        if strategy == "fit-score":
            doi = _entry_doi(entry).lower()
            score = _as_int(_entry_value(entry, frontmatter, "fit_score", "score"), fit_scores.get(doi, 0))
            if doi in fit_scores:
                score = fit_scores[doi]
            return (score, recency, citations, title)
        return (0, -index)

    return sorted(enumerate(entries), key=key, reverse=True)


def _prune_manifest_for_cap(
    manifest: dict,
    cluster,
    cfg,
    *,
    strategy: str,
    rate_limit_cap: int,
    log_path: Path,
) -> tuple[dict, list[Entry]]:
    source_entries = _uploadable_entries(manifest)
    if len(source_entries) <= rate_limit_cap:
        return manifest, []
    if strategy == "fail":
        raise NotebookLMCapacityError(_capacity_error_message(cluster, len(source_entries), rate_limit_cap))
    if strategy not in {"top-n-recent", "top-n-cited", "fit-score"}:
        return manifest, []

    ranked = _ranked_entries(source_entries, strategy, cfg, getattr(cluster, "slug", ""))
    kept = [entry for _index, entry in ranked[:rate_limit_cap]]
    skipped = [dict(entry) for _index, entry in ranked[rate_limit_cap:]]
    skipped_actions = [
        entry
        for entry in manifest.get("entries", [])
        if isinstance(entry, dict) and entry.get("action", "skip") == "skip"
    ]
    _log_jsonl(
        log_path,
        {
            "kind": "upload_over_cap_pruned",
            "cluster_slug": getattr(cluster, "slug", ""),
            "strategy": strategy,
            "source_count": len(source_entries),
            "cap": rate_limit_cap,
            "skipped_count": len(skipped),
            "skipped": [{"doi": _entry_doi(entry), "title": _entry_title(entry)} for entry in skipped],
        },
    )
    pruned_manifest = dict(manifest)
    pruned_manifest["entries"] = kept + skipped_actions
    return pruned_manifest, skipped


def _shard_order_strategy(strategy: str) -> str:
    if strategy == "cited":
        return "top-n-cited"
    if strategy == "fit":
        return "fit-score"
    return "top-n-recent"


def _dedup_doi_list(entries: list[Entry]) -> list[str]:
    seen: set[str] = set()
    dois: list[str] = []
    for entry in entries:
        doi = _entry_doi(entry)
        if not doi or doi in seen:
            continue
        seen.add(doi)
        dois.append(doi)
    return dois


def _chunk_entries(entries: list[Entry], shard_size: int) -> list[list[Entry]]:
    return [entries[index:index + shard_size] for index in range(0, len(entries), shard_size)]


def _attempt_upload(
    client,
    entry: dict,
    log_path: Path,
    *,
    max_attempts: int = 3,
):
    """Try an upload up to ``max_attempts`` times with exponential backoff."""
    action = entry.get("action", "?")
    key = entry.get("pdf_path") or entry.get("url") or entry.get("doi") or ""
    last_result = None
    for attempt in range(1, max_attempts + 1):
        _log_jsonl(log_path, {"kind": "upload_attempt", "attempt": attempt, "action": action, "key": key})
        if action == "pdf":
            result = client.upload_pdf(Path(entry["pdf_path"]))
        elif action == "url":
            result = client.upload_url(entry["url"])
        else:
            _log_jsonl(log_path, {"kind": "upload_skip", "action": action, "key": key})
            return None
        last_result = result
        if result.success:
            _log_jsonl(log_path, {"kind": "upload_ok", "attempt": attempt, "action": action, "key": key})
            return result
        _log_jsonl(
            log_path,
            {
                "kind": "upload_fail",
                "attempt": attempt,
                "action": action,
                "key": key,
                "error": result.error,
            },
        )
        if attempt < max_attempts:
            time.sleep(3 ** (attempt - 1))
    return last_result


def _ordered_shard_entries(manifest: dict, cfg, cluster_slug: str, shard_strategy: str) -> list[Entry]:
    if shard_strategy not in SHARD_ORDER_STRATEGIES:
        raise ValueError("--strategy must be one of: recent, cited, fit")
    entries = _uploadable_entries(manifest)
    ranked = _ranked_entries(entries, _shard_order_strategy(shard_strategy), cfg, cluster_slug)
    return [entry for _index, entry in ranked]


def _plan_shard_dry_run(
    report: UploadReport,
    manifest: dict,
    cfg,
    cluster,
    notebook_name: str,
    *,
    shard_size: int,
    shard_strategy: str,
) -> None:
    ordered = _ordered_shard_entries(manifest, cfg, getattr(cluster, "slug", ""), shard_strategy)
    chunks = _chunk_entries(ordered, shard_size)
    total = len(chunks) or 1
    for shard_index, chunk in enumerate(chunks, start=1):
        shard_name = f"{notebook_name} [{shard_index}/{total}]"
        for entry in chunk:
            key = _entry_key(entry)
            report.uploaded.append(
                UploadResult(
                    source_kind=entry.get("action", "?"),
                    path_or_url=key,
                    success=True,
                    title=f"{shard_name}: {_entry_title(entry)}".strip(),
                )
            )
    report.notebook_name = notebook_name


def _upload_cluster_shards(
    cluster,
    cfg,
    manifest: dict,
    report: UploadReport,
    cache: dict,
    cluster_cache: dict,
    log_path: Path,
    notebook_name: str,
    *,
    create_if_missing: bool,
    headless: bool,
    rate_limit_cap: int,
    shard_size: int,
    shard_strategy: str,
) -> UploadReport:
    from research_hub.clusters import ClusterRegistry, NotebookShard

    if shard_size < 1:
        raise ValueError("--shard-size must be at least 1")
    if shard_size > rate_limit_cap:
        raise ValueError(f"--shard-size must be <= {rate_limit_cap} for NotebookLM")

    ordered = _ordered_shard_entries(manifest, cfg, getattr(cluster, "slug", ""), shard_strategy)
    chunks = _chunk_entries(ordered, shard_size)
    state_file = default_state_file(cfg.research_hub_dir)
    retry_count = 0
    shards: list[NotebookShard] = []
    shard_cache = cluster_cache.setdefault("shard_uploaded_sources", {})
    report.notebook_name = notebook_name

    client = _make_client(state_file, headless=headless)
    try:
        total = len(chunks) or 1
        for shard_index, chunk in enumerate(chunks, start=1):
            shard_name = f"{notebook_name} [{shard_index}/{total}]"
            handle = (
                _find_or_create_notebook(client, shard_name)
                if create_if_missing
                else client.open_notebook_by_name(shard_name)
            )
            _set_active_notebook(client, handle.notebook_id)
            if shard_index == 1:
                prior_url = (cluster.notebooklm_notebook_url or "").strip()
                report.notebook_was_reused = bool(prior_url and prior_url == handle.url)
                report.notebook_url = handle.url
                report.notebook_id = handle.notebook_id
            _log_jsonl(
                log_path,
                {
                    "kind": "upload_shard_opened",
                    "cluster_slug": getattr(cluster, "slug", ""),
                    "shard_index": shard_index,
                    "shard_total": total,
                    "notebook_url": handle.url,
                    "notebook_id": handle.notebook_id,
                    "notebook_name": handle.name,
                    "source_count": len(chunk),
                },
            )

            uploaded_sources = {str(item) for item in shard_cache.get(shard_name, [])}
            for entry in chunk:
                key = _entry_key(entry)
                if key in uploaded_sources:
                    report.skipped_already_uploaded += 1
                    _log_jsonl(log_path, {"kind": "upload_cached_skip", "key": key, "shard": shard_name})
                    continue

                result = _attempt_upload(client, entry, log_path)
                if result is None:
                    continue
                report.uploaded.append(result)
                retry_count += max(0, _count_attempts_for_key(log_path, key) - 1)
                if result.success:
                    uploaded_sources.add(key)
                else:
                    report.errors.append({"source": key, "error": result.error, "shard": shard_name})
                time.sleep(BETWEEN_UPLOADS_SEC)

            shard_cache[shard_name] = sorted(uploaded_sources)
            created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            shards.append(
                NotebookShard(
                    notebook_id=handle.notebook_id,
                    notebook_url=handle.url,
                    notebook_name=handle.name,
                    source_count=len(chunk),
                    source_doi_list=_dedup_doi_list(chunk),
                    created_at=created_at,
                )
            )
            safe_slug = Path(cluster.slug).name
            report.ingest_validation = validate_uploaded_sources(
                client,
                handle,
                _manifest_doi_list({"entries": chunk}),
                cluster_slug=safe_slug,
                artifacts_dir=cfg.research_hub_dir / "artifacts" / safe_slug,
            )
    finally:
        getattr(client, "close", lambda: None)()

    cluster_cache["shards"] = [
        {
            "notebook_url": shard.notebook_url,
            "notebook_id": shard.notebook_id,
            "notebook_name": shard.notebook_name,
            "source_count": shard.source_count,
            "source_doi_list": shard.source_doi_list,
            "created_at": shard.created_at,
        }
        for shard in shards
    ]
    cluster_cache["last_synced"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _save_nlm_cache(cfg.research_hub_dir / "nlm_cache.json", cache)

    bind_kwargs = {"notebooklm_shards": shards}
    if shards:
        bind_kwargs.update(
            {
                "notebooklm_notebook_url": shards[0].notebook_url,
                "notebooklm_notebook_id": shards[0].notebook_id,
            }
        )
    ClusterRegistry(cfg.clusters_file).bind(slug=cluster.slug, **bind_kwargs)

    _log_jsonl(
        log_path,
        {
            "kind": "upload_run_complete",
            "success_count": report.success_count,
            "fail_count": report.fail_count,
            "retry_count": retry_count,
            "shard_count": len(shards),
        },
    )
    return report


_upload_with_retry = _attempt_upload


def upload_cluster(
    cluster,
    cfg,
    *,
    dry_run: bool = False,
    create_if_missing: bool = True,
    headless: bool = False,
    rate_limit_cap: int = 50,
    over_cap_strategy: str = "fail",
    shard_size: int = 50,
    shard_strategy: str = "recent",
) -> UploadReport:
    """Upload a cluster bundle to NotebookLM, resuming from ``nlm_cache.json``."""
    from research_hub.clusters import ClusterRegistry

    if over_cap_strategy not in OVER_CAP_STRATEGIES:
        raise ValueError("--over-cap-strategy must be one of: fail, top-n-recent, top-n-cited, fit-score, shard")
    if over_cap_strategy == "shard":
        if shard_size < 1:
            raise ValueError("--shard-size must be at least 1")
        if shard_size > rate_limit_cap:
            raise ValueError(f"--shard-size must be <= {rate_limit_cap} for NotebookLM")

    report = UploadReport(
        cluster_slug=cluster.slug,
        dry_run=dry_run,
        over_cap_strategy=over_cap_strategy,
    )
    bundle_dir = _find_latest_bundle(cfg.research_hub_dir / "bundles", cluster.slug)
    if bundle_dir is None:
        raise FileNotFoundError(
            "No bundle found for cluster '{0}'. Run `research-hub notebooklm bundle "
            "--cluster {0}` first.".format(cluster.slug)
        )

    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    log_path = _open_debug_log(cfg.research_hub_dir)
    _log_jsonl(
        log_path,
        {
            "kind": "upload_run_start",
            "cluster_slug": cluster.slug,
            "manifest_entries": len(manifest.get("entries", [])),
            "headless": headless,
            "dry_run": dry_run,
            "over_cap_strategy": over_cap_strategy,
        },
    )

    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    cache = _load_nlm_cache(cache_path)
    cluster_cache = cache.setdefault(cluster.slug, {})
    uploaded_sources: set[str] = {str(item) for item in cluster_cache.get("uploaded_sources", [])}
    notebook_name = cluster.notebooklm_notebook or cluster.name

    if over_cap_strategy == "shard":
        if dry_run:
            _plan_shard_dry_run(
                report,
                manifest,
                cfg,
                cluster,
                notebook_name,
                shard_size=shard_size,
                shard_strategy=shard_strategy,
            )
            _log_jsonl(
                log_path,
                {
                    "kind": "upload_run_complete",
                    "success_count": report.success_count,
                    "fail_count": report.fail_count,
                    "retry_count": 0,
                    "dry_run": True,
                    "shard_count": len(_chunk_entries(_uploadable_entries(manifest), shard_size)),
                },
            )
            return report
        return _upload_cluster_shards(
            cluster,
            cfg,
            manifest,
            report,
            cache,
            cluster_cache,
            log_path,
            notebook_name,
            create_if_missing=create_if_missing,
            headless=headless,
            rate_limit_cap=rate_limit_cap,
            shard_size=shard_size,
            shard_strategy=shard_strategy,
        )

    manifest, over_cap_skipped = _prune_manifest_for_cap(
        manifest,
        cluster,
        cfg,
        strategy=over_cap_strategy,
        rate_limit_cap=rate_limit_cap,
        log_path=log_path,
    )
    report.over_cap_skipped = over_cap_skipped

    if dry_run:
        _plan_dry_run(report, manifest, uploaded_sources, notebook_name, rate_limit_cap)
        _log_jsonl(
            log_path,
            {
                "kind": "upload_run_complete",
                "success_count": report.success_count,
                "fail_count": report.fail_count,
                "retry_count": 0,
                "dry_run": True,
            },
        )
        return report

    state_file = default_state_file(cfg.research_hub_dir)
    retry_count = 0
    client = _make_client(state_file, headless=headless)
    try:
        handle = (
            _find_or_create_notebook(client, notebook_name)
            if create_if_missing
            else client.open_notebook_by_name(notebook_name)
        )
        _set_active_notebook(client, handle.notebook_id)
        prior_url = (cluster.notebooklm_notebook_url or "").strip()
        report.notebook_was_reused = bool(prior_url and prior_url == handle.url)
        report.notebook_url = handle.url
        report.notebook_id = handle.notebook_id
        report.notebook_name = handle.name
        _log_jsonl(
            log_path,
            {
                "kind": "upload_notebook_opened",
                "notebook_url": handle.url,
                "notebook_id": handle.notebook_id,
                "notebook_name": handle.name,
            },
        )

        uploads = 0
        source_count = len(_uploadable_entries(manifest))
        for entry in manifest.get("entries", []):
            action = entry.get("action", "skip")
            if action == "skip":
                continue
            if uploads >= rate_limit_cap:
                raise NotebookLMCapacityError(_capacity_error_message(cluster, source_count, rate_limit_cap))

            key = str(entry.get("pdf_path") or entry.get("url") or entry.get("doi") or "")
            if key in uploaded_sources:
                report.skipped_already_uploaded += 1
                _log_jsonl(log_path, {"kind": "upload_cached_skip", "key": key})
                continue

            result = _attempt_upload(client, entry, log_path)
            if result is None:
                continue
            report.uploaded.append(result)
            retry_count += max(0, _count_attempts_for_key(log_path, key) - 1)
            if result.success:
                uploaded_sources.add(key)
                uploads += 1
            else:
                report.errors.append({"source": key, "error": result.error})
            time.sleep(BETWEEN_UPLOADS_SEC)

        safe_slug = Path(cluster.slug).name
        report.ingest_validation = validate_uploaded_sources(
            client,
            handle,
            _manifest_doi_list(manifest),
            cluster_slug=safe_slug,
            artifacts_dir=cfg.research_hub_dir / "artifacts" / safe_slug,
        )
        warning_text = report.ingest_validation.warning_text()
        if warning_text:
            print(warning_text)
    finally:
        getattr(client, "close", lambda: None)()

    cluster_cache["notebook_url"] = report.notebook_url
    cluster_cache["notebook_id"] = report.notebook_id
    cluster_cache["notebook_name"] = report.notebook_name
    cluster_cache["uploaded_sources"] = sorted(uploaded_sources)
    cluster_cache["uploaded_doi_count"] = len(uploaded_sources)
    cluster_cache["last_synced"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _save_nlm_cache(cache_path, cache)

    ClusterRegistry(cfg.clusters_file).bind(
        slug=cluster.slug,
        notebooklm_notebook_url=report.notebook_url,
        notebooklm_notebook_id=report.notebook_id,
    )

    _log_jsonl(
        log_path,
        {
            "kind": "upload_run_complete",
            "success_count": report.success_count,
            "fail_count": report.fail_count,
            "retry_count": retry_count,
        },
    )
    return report


def _plan_dry_run(
    report: UploadReport,
    manifest: dict,
    uploaded_sources: set[str],
    notebook_name: str,
    rate_limit_cap: int,
) -> None:
    planned = 0
    for entry in manifest.get("entries", []):
        if entry.get("action") == "skip":
            continue
        key = str(entry.get("pdf_path") or entry.get("url") or entry.get("doi") or "")
        if key in uploaded_sources:
            report.skipped_already_uploaded += 1
            continue
        report.uploaded.append(
            UploadResult(
                source_kind=entry.get("action", "?"),
                path_or_url=key,
                success=True,
            )
        )
        planned += 1
        if planned >= rate_limit_cap:
            break
    report.notebook_name = notebook_name


def _count_attempts_for_key(log_path: Path, key: str) -> int:
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return 1
    count = 0
    for line in lines:
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if payload.get("kind") == "upload_attempt" and str(payload.get("key")) == str(key):
            count += 1
    return max(count, 1)


def download_briefing_for_cluster(
    cluster,
    cfg,
    *,
    headless: bool = False,
) -> DownloadReport:
    """Download the latest briefing text and save it into the vault."""
    log_path = _open_debug_log(cfg.research_hub_dir)
    _log_jsonl(log_path, {"kind": "download_start", "cluster_slug": cluster.slug, "headless": headless})
    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    cache = _load_nlm_cache(cache_path)
    cluster_cache = cache.setdefault(cluster.slug, {})

    state_file = default_state_file(cfg.research_hub_dir)
    client = _make_client(state_file, headless=headless)
    try:
        handle = _resolve_notebook_handle(client, cluster, cluster_cache, create_if_missing=False)
        _log_jsonl(log_path, {"kind": "download_navigate", "notebook_url": handle.url})
        artifact: BriefingArtifact = client.download_briefing(handle)
    finally:
        getattr(client, "close", lambda: None)()

    if artifact.source_count == 0:
        artifact.source_count = int(cluster_cache.get("uploaded_doi_count", 0))

    safe_slug = Path(cluster.slug).name
    artifacts_dir = cfg.research_hub_dir / "artifacts" / safe_slug
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    out_path = artifacts_dir / f"brief-{timestamp}.txt"
    header = (
        "# {0}\n\n"
        "Source: {1}\n"
        "Downloaded: {2}\n"
        "Sources: {3}\n"
    ).format(artifact.notebook_name, artifact.notebook_url, timestamp, artifact.source_count)
    if artifact.titles:
        header += "Saved briefings: " + "; ".join(artifact.titles) + "\n"
    out_path.write_text(header + "\n" + artifact.text + "\n", encoding="utf-8")
    from research_hub.notebooklm.download import (
        mirror_brief_and_populate_overview,
        source_dois_for_cluster,
    )

    source_doi_list = source_dois_for_cluster(cfg.root, safe_slug)
    brief_md_path = mirror_brief_and_populate_overview(
        cluster=cluster,
        vault_root=cfg.root,
        artifact=artifact,
        archive_path=out_path,
        generated_at=now,
        source_doi_list=source_doi_list,
    )

    cluster_cache.setdefault("artifacts", {})
    cluster_cache["artifacts"]["brief"] = {
        "path": str(out_path),
        "md_path": str(brief_md_path),
        "downloaded_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "char_count": len(artifact.text),
        "titles": artifact.titles,
        "source_doi_list": source_doi_list,
    }
    _save_nlm_cache(cache_path, cache)
    _log_jsonl(log_path, {"kind": "download_ok", "artifact_path": str(out_path)})

    return DownloadReport(
        cluster_slug=cluster.slug,
        notebook_name=artifact.notebook_name,
        artifact_path=out_path,
        char_count=len(artifact.text),
        titles=artifact.titles,
        brief_md_path=brief_md_path,
    )


def download_slide_deck_for_cluster(
    cluster,
    cfg,
    *,
    headless: bool = False,
    output_format: str = "pdf",
) -> DownloadReport:
    """Download the latest slide deck artifact and save it under .research_hub/artifacts/<cluster>/.

    Mirrors the briefing flow's storage layout (timestamped file in the
    artifacts dir + nlm_cache.json entry), but does not write a `.md`
    mirror — slide decks are PDF/PPTX binaries, not markdown.
    """
    log_path = _open_debug_log(cfg.research_hub_dir)
    _log_jsonl(
        log_path,
        {"kind": "download_slide_deck_start", "cluster_slug": cluster.slug, "format": output_format},
    )
    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    cache = _load_nlm_cache(cache_path)
    cluster_cache = cache.setdefault(cluster.slug, {})

    safe_slug = Path(cluster.slug).name
    artifacts_dir = cfg.research_hub_dir / "artifacts" / safe_slug
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    suffix = "pptx" if output_format.lower() == "pptx" else "pdf"
    out_path = artifacts_dir / f"slide-deck-{timestamp}.{suffix}"

    state_file = default_state_file(cfg.research_hub_dir)
    client = _make_client(state_file, headless=headless)
    try:
        handle = _resolve_notebook_handle(client, cluster, cluster_cache, create_if_missing=False)
        _log_jsonl(log_path, {"kind": "download_navigate", "notebook_url": handle.url})
        client.download_slide_deck(handle, output_path=out_path, output_format=output_format)
    finally:
        getattr(client, "close", lambda: None)()

    cluster_cache.setdefault("artifacts", {})
    cluster_cache["artifacts"]["slide_deck"] = {
        "path": str(out_path),
        "downloaded_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "format": suffix,
        "size_bytes": out_path.stat().st_size if out_path.exists() else 0,
    }
    _save_nlm_cache(cache_path, cache)
    _log_jsonl(log_path, {"kind": "download_slide_deck_ok", "artifact_path": str(out_path)})

    return DownloadReport(
        cluster_slug=cluster.slug,
        notebook_name=handle.url,
        artifact_path=out_path,
        char_count=out_path.stat().st_size if out_path.exists() else 0,
        titles=[],
        brief_md_path=None,
    )


def read_latest_briefing(cluster, cfg) -> str:
    """Return the most recently downloaded briefing text for a cluster."""
    cluster_slug = cluster if isinstance(cluster, str) else cluster.slug
    safe_slug = Path(cluster_slug).name
    artifacts_dir = cfg.research_hub_dir / "artifacts" / safe_slug
    if not artifacts_dir.exists():
        raise FileNotFoundError(
            "No artifacts directory for cluster '{0}'. Run `research-hub notebooklm "
            "download --cluster {0}` first.".format(cluster_slug)
        )
    candidates = sorted(
        artifacts_dir.glob("brief-*.txt"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            "No brief-*.txt files in {0}. Run `research-hub notebooklm download "
            "--cluster {1}` first.".format(artifacts_dir, cluster_slug)
        )
    return candidates[0].read_text(encoding="utf-8")


def generate_artifact(
    cluster,
    cfg,
    *,
    artifact_type: str | None = None,
    kind: str | None = None,
    headless: bool = False,
) -> str:
    """Trigger NotebookLM artifact generation and return an artifact id or URL."""
    kind_name = _normalize_artifact_kind(artifact_type or kind or "brief")
    log_path = _open_debug_log(cfg.research_hub_dir)
    _log_jsonl(
        log_path,
        {"kind": "generate_start", "cluster_slug": cluster.slug, "kind_name": kind_name, "headless": headless},
    )

    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    cache = _load_nlm_cache(cache_path)
    cluster_cache = cache.setdefault(cluster.slug, {})
    state_file = default_state_file(cfg.research_hub_dir)
    client = _make_client(state_file, headless=headless)
    try:
        handle = _resolve_notebook_handle(client, cluster, cluster_cache, create_if_missing=True)
        _set_active_notebook(client, handle.notebook_id)
        if kind_name == "brief":
            artifact_ref = _call_trigger(client.trigger_briefing, handle.notebook_id)
            cluster_cache["briefing_url"] = artifact_ref
        elif kind_name == "audio":
            artifact_ref = _call_trigger(client.trigger_audio_overview, handle.notebook_id)
            cluster_cache["audio_url"] = artifact_ref
        elif kind_name == "mind_map":
            artifact_ref = _call_trigger(client.trigger_mind_map, handle.notebook_id)
            cluster_cache["mind_map_url"] = artifact_ref
        elif kind_name == "video":
            artifact_ref = _call_trigger(client.trigger_video_overview, handle.notebook_id)
            cluster_cache["video_url"] = artifact_ref
        else:
            raise ValueError(f"Unknown generation kind: {kind_name}")
        if not artifact_ref:
            raise NotebookLMError("Generation button not found")
    finally:
        getattr(client, "close", lambda: None)()

    cluster_cache["notebook_url"] = handle.url
    cluster_cache["notebook_id"] = handle.notebook_id
    cluster_cache["notebook_name"] = handle.name
    cluster_cache["last_synced"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _save_nlm_cache(cache_path, cache)
    _log_jsonl(log_path, {"kind": "generate_ok", "kind_name": kind_name, "artifact_ref": artifact_ref})
    return artifact_ref


def _normalize_artifact_kind(kind: str) -> str:
    if kind == "mind-map":
        return "mind_map"
    return kind


def _resolve_notebook_handle(
    client,
    cluster,
    cluster_cache: dict,
    *,
    create_if_missing: bool,
) -> NotebookHandle:
    notebook_name = cluster.notebooklm_notebook or cluster.name
    notebook_id = (
        getattr(cluster, "notebooklm_notebook_id", "")
        or cluster_cache.get("notebook_id", "")
        or _parse_notebook_id(getattr(cluster, "notebooklm_notebook_url", "") or cluster_cache.get("notebook_url", ""))
    )
    notebook_url = getattr(cluster, "notebooklm_notebook_url", "") or cluster_cache.get("notebook_url", "")
    if notebook_id:
        return NotebookHandle(name=notebook_name, url=notebook_url, notebook_id=notebook_id)
    if create_if_missing:
        return _find_or_create_notebook(client, notebook_name)
    return client.open_notebook_by_name(notebook_name)


def _set_active_notebook(client, notebook_id: str) -> None:
    setter = getattr(client, "set_active_notebook", None)
    if setter is not None:
        setter(notebook_id)
    else:
        setattr(client, "_active_notebook_id", notebook_id)


def _call_trigger(method, notebook_id: str):
    try:
        return method(notebook_id)
    except TypeError:
        return method()


def _make_client(state_file: Path, *, headless: bool):
    try:
        return NotebookLMClient(state_file, headless=headless)
    except TypeError:
        legacy_page = type(
            "_LegacyNotebookLMPage",
            (),
            {"url": "https://notebooklm.google.com/notebook/fixture", "calls": []},
        )()
        return NotebookLMClient(legacy_page)


def _find_or_create_notebook(client, notebook_name: str):
    method = getattr(client, "find_or_create_notebook", None)
    if method is not None:
        return method(notebook_name)
    return client.open_or_create_notebook(notebook_name)

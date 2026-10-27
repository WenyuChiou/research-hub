"""Per-paper summarize step: fill Key Findings + Methodology + Relevance
from each paper's abstract via an LLM CLI, write back to BOTH Obsidian
markdown and the Zotero child note.

Why this exists
---------------
The auto pipeline ingests metadata + abstract only. Summary / Key Findings
/ Methodology / Relevance fields are left as `[TODO]` skeletons in both
Obsidian and Zotero, so the user has nothing scannable per paper after
ingest. Cluster-level summarization (NotebookLM brief, crystals) does not
fill per-paper notes.

This module clones the crystal flow at `auto._run_crystal_step`:
  1. emit a JSON-output prompt for the cluster's papers
  2. invoke `claude` / `codex` / `gemini` via the existing
     `auto._invoke_llm_cli` helper
  3. parse the first JSON object from the response
  4. validate each summary entry against the cluster's actual paper slugs
  5. write Obsidian markdown blocks + an explicitly owned Zotero summary
     note (attempt local rollback if Zotero write is not confirmed)

Design choices
--------------
- Separate command (NOT auto-on-ingest) so a single LLM failure doesn't
  abort an ingest batch and so users can re-run on subset of papers.
- Both write targets must succeed for an entry to count as applied;
  an uncertain remote response is reported for reconciliation, not retried.
  This is not a distributed transaction or a cross-process write lock.
- No PDF parsing: the LLM only sees the abstract. Methodology / Relevance
  are inferences, marked as such in the prompt.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from functools import partial
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Optional

from research_hub.paper_summarize import (
    _callout, _upsert_section, _write_note_text,
    mark_summary_content_done, sections_are_substantive,
)
from research_hub.zotero.summary_note import SUMMARY_NOTE_TAG, SUMMARY_NOTE_TAG_PREFIX


# -- data model ---------------------------------------------------------


@dataclass
class PaperSummary:
    """One LLM-generated summary entry for a single paper."""

    paper_slug: str
    summary: str = ""           # v0.81: 1-2 sentence TL;DR for `## Summary` block
    key_findings: list[str] = field(default_factory=list)
    methodology: str = ""
    relevance: str = ""


@dataclass
class SummaryApplyResult:
    cluster_slug: str
    applied: list[str] = field(default_factory=list)         # paper slugs
    skipped: list[str] = field(default_factory=list)         # "<slug>: <reason>"
    errors: list[str] = field(default_factory=list)          # "<slug>: <error>"
    obsidian_writes: int = 0
    zotero_writes: int = 0
    warnings: list[str] = field(default_factory=list)
    receipts: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = {
            "cluster_slug": self.cluster_slug,
            "applied": list(self.applied),
            "skipped": list(self.skipped),
            "errors": list(self.errors),
            "obsidian_writes": self.obsidian_writes,
            "zotero_writes": self.zotero_writes,
        }
        if self.receipts:
            result["receipts"] = list(self.receipts)
        if self.warnings:
            result["warnings"] = list(self.warnings)
        return result


def receipt_lines(receipts):
    """Small human-readable companion to structured receipts; no source text."""
    for receipt in receipts:
        states = ', '.join(f"{sink}={value['state']}" for sink, value in receipt.get('sinks', {}).items())
        observations = ', '.join(f"{item['sink']}={item['status']}" for item in receipt.get('observations', []))
        if receipt.get('status') == 'receipt_unavailable':
            confirmed = ', '.join(f'{sink}=confirmed' for sink in receipt.get('confirmed_sinks', []))
            detail = 'receipt_unavailable' + (f'; {confirmed}' if confirmed else '')
        else:
            detail = states or receipt.get('status', 'unknown')
        yield f"receipt {receipt['operation_id']}: {detail}" + (f"; observations: {observations}" if observations else '')


@dataclass
class SummaryReport:
    cluster_slug: str
    ok: bool = True
    error: str = ""
    cli_used: str = ""
    prompt_path: Optional[Path] = None  # set when CLI not on PATH
    apply_result: Optional[SummaryApplyResult] = None

    def to_dict(self) -> dict:
        return {
            "cluster_slug": self.cluster_slug,
            "ok": self.ok,
            "error": self.error,
            "cli_used": self.cli_used,
            "prompt_path": str(self.prompt_path) if self.prompt_path else None,
            "apply_result": self.apply_result.to_dict() if self.apply_result else None,
        }


@dataclass
class _PerPaperOutcome:
    slug: str
    applied: bool = False
    skipped_reason: str = ""
    error: str = ""
    obsidian_written: bool = False
    zotero_written: bool = False
    warning: str = ""
    receipt: dict | None = None


# -- prompt building ----------------------------------------------------


def _read_cluster_papers_with_abstracts(
    cfg,
    cluster_slug: str,
    *,
    paper_keys: list[str] | None = None,
    skip_existing: bool = False,
) -> list[dict]:
    """Walk raw/<slug>/*.md, return list of dicts with slug + frontmatter
    fields + abstract text. Reuses the same exclusion rules as crystal."""
    papers: list[dict] = []
    allowed_keys = {str(key).strip() for key in (paper_keys or []) if str(key).strip()}
    raw_dir = Path(cfg.raw) / cluster_slug
    if not raw_dir.exists():
        return []
    for note_path in sorted(raw_dir.glob("*.md")):
        if note_path.name in {"00_overview.md", "index.md"}:
            continue
        text = note_path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            continue
        try:
            end = text.index("\n---\n", 4)
        except ValueError:
            continue
        # Naive YAML scalar extraction: research-hub frontmatter never
        # nests for the fields we care about.
        fm: dict[str, str] = {}
        for line in text[4:end].splitlines():
            if ":" not in line or line.startswith(("  ", "\t")):
                continue
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip().strip('"').strip("'")
        zotero_key = fm.get("zotero-key", "")
        if allowed_keys and zotero_key not in allowed_keys:
            continue
        if skip_existing and sections_are_substantive(text):
            continue
        abstract = _extract_section(text, "Abstract")
        papers.append({
            "slug": note_path.stem,
            "title": fm.get("title", note_path.stem),
            "doi": fm.get("doi", ""),
            "year": fm.get("year", ""),
            "zotero_key": zotero_key,
            "abstract": abstract,
            "path": note_path,
        })
    return papers


def _extract_section(md_text: str, header: str) -> str:
    """Return body of a `## <header>` section, stripping callout markers."""
    pattern = rf"##\s+{re.escape(header)}\n+([^\n].*?)(?=\n---|\n##\s)"
    match = re.search(pattern, md_text, re.DOTALL)
    if not match:
        return ""
    body = match.group(1).strip()
    # Strip Obsidian callout prefix `> [!type]\n> ` if present
    if body.startswith("> [!"):
        lines = [line[2:] if line.startswith("> ") else line
                 for line in body.split("\n")[1:]]
        body = "\n".join(lines).strip()
    return body


def build_summarize_prompt(
    cfg,
    cluster_slug: str,
    *,
    paper_keys: list[str] | None = None,
) -> str:
    """Build the LLM prompt requesting per-paper summaries as JSON."""
    papers = _read_cluster_papers_with_abstracts(cfg, cluster_slug, paper_keys=paper_keys)
    return _build_summarize_prompt(papers, cluster_slug, paper_keys=paper_keys)


def _build_summarize_prompt(papers: list[dict], cluster_slug: str, *, paper_keys=None) -> str:
    if not papers:
        if paper_keys:
            raise ValueError(f"no papers found in cluster '{cluster_slug}' for the requested paper keys")
        raise ValueError(f"no papers found in cluster '{cluster_slug}'")

    lines = [
        f'# Paper-level summarize for cluster "{cluster_slug}" ({len(papers)} papers)',
        "",
        "Generate Key Findings, Methodology, and Relevance for each paper",
        "based on its abstract. The output JSON will be parsed and written",
        "to Obsidian markdown + Zotero child notes.",
        "",
        "## Rules",
        "",
        "- Findings-first: state the result, not 'The paper shows that...'",
        "- Each Key Finding is one sentence, anchored in something the abstract claims.",
        "- Aim for 3-5 findings per paper. If the abstract is too thin, say so explicitly: ['[abstract too thin to extract findings]'].",
        "- Methodology: one sentence. If the abstract names a method (survey, ABM, regression, etc.) use it.",
        "- Relevance: 1-2 sentences linking this paper to the cluster topic.",
        "- Do not invent claims the abstract does not support. When uncertain, mark with '[likely]'.",
        "",
        "## Cluster topic",
        "",
        cluster_slug.replace("-", " "),
        "",
        f"## Papers ({len(papers)})",
        "",
    ]
    for index, paper in enumerate(papers, start=1):
        abstract = paper["abstract"] or "(no abstract — flag in findings as 'PDF needed')"
        lines.extend([
            f"### {index}. {paper['title']}",
            f"- slug: `{paper['slug']}`",
            f"- year: {paper['year'] or '????'}",
            f"- abstract: {abstract}",
            "",
        ])

    lines.extend([
        "## Output JSON schema",
        "",
        "Return ONE JSON object, nothing else:",
        "",
        "```json",
        json.dumps({
            "summaries": [
                {
                    "paper_slug": papers[0]["slug"],
                    "summary": "1-2 sentence TL;DR (what the paper does + the headline finding).",
                    "key_findings": [
                        "Finding 1, one sentence.",
                        "Finding 2, one sentence.",
                        "Finding 3, one sentence.",
                    ],
                    "methodology": "One sentence on the method.",
                    "relevance": "1-2 sentences on cluster fit.",
                }
            ]
        }, indent=2, ensure_ascii=False),
        "```",
    ])
    return "\n".join(lines)


# -- payload validation -------------------------------------------------


def _validate_entry(entry: dict, valid_slugs: set[str]) -> tuple[Optional[PaperSummary], Optional[str]]:
    """Return (summary, None) on success or (None, reason) on rejection."""
    slug = str(entry.get("paper_slug", "") or "").strip()
    if not slug:
        return None, "missing paper_slug"
    if slug not in valid_slugs:
        return None, f"unknown paper_slug (not in cluster): {slug}"
    raw_findings = entry.get("key_findings") or []
    if not isinstance(raw_findings, list):
        return None, "key_findings must be a list"
    findings = [str(f).strip() for f in raw_findings if str(f).strip()]
    if not findings:
        return None, "key_findings is empty"
    methodology = str(entry.get("methodology", "") or "").strip()
    relevance = str(entry.get("relevance", "") or "").strip()
    summary = str(entry.get("summary", "") or "").strip()
    if not methodology:
        return None, "methodology is empty"
    if not relevance:
        return None, "relevance is empty"
    # v0.81: summary is OPTIONAL (older LLM outputs and abstract-too-thin
    # cases may legitimately produce only findings/methodology/relevance).
    # When present, it fills the `## Summary` block instead of leaving [TODO].
    return PaperSummary(
        paper_slug=slug,
        summary=summary,
        key_findings=findings,
        methodology=methodology,
        relevance=relevance,
    ), None


# -- write back ---------------------------------------------------------


def _replace_obsidian_block(text: str, summary: PaperSummary) -> str:
    blocks = [
        ("Key Findings", "success", "\n".join(f"- {f}" for f in summary.key_findings), "findings"),
        ("Methodology", "info", summary.methodology, "methodology"),
        ("Relevance", "note", summary.relevance, "relevance"),
    ]
    if summary.summary:
        blocks.insert(0, ("Summary", "abstract", summary.summary, "summary"))
    newline = "\r\n" if "\r\n" in text else "\n"
    for header, kind, content, block_id in blocks:
        text = _upsert_section(
            text, header, _callout(kind, content, block_id), newline, preserve_manual=True
        )
    return mark_summary_content_done(text)


def _build_zotero_note_html(paper_meta: dict, summary: PaperSummary) -> str:
    title = paper_meta.get("title", "(no title)")
    abstract = paper_meta.get("abstract", "")
    findings_html = "".join(f"<li>{f}</li>" for f in summary.key_findings)
    # v0.81: include the explicit summary if claude returned one.
    summary_html = f"<p>{summary.summary}</p>" if summary.summary else f"<p>{title}</p>"
    html = f"<h1>Summary</h1>{summary_html}"
    if abstract:
        html += f"<h2>Abstract</h2><p>{abstract}</p>"
    html += "<h2>Key Findings</h2><ul>" + findings_html + "</ul>"
    html += f"<h2>Methodology</h2><p>{summary.methodology}</p>"
    html += f"<h2>Relevance to cluster</h2><p>{summary.relevance}</p>"
    return html


# Pyzotero pagination uses mutable client.links. Keep each read/decision/write
# together even when apply_summaries shares one client across paper workers.
# This is process-local, not a lock against Zotero users or other Hub processes.
_ZOTERO_SUMMARY_WRITE_LOCK = Lock()


class _ZoteroWriteUncertain(RuntimeError):
    """A remote write may have committed; never infer failure from a lost reply."""


class _ZoteroCreateUncertain(_ZoteroWriteUncertain):
    """A create may have committed remotely; it must not be retried blindly."""


def _write_zotero_child_note(zot, parent_key: str, html: str, *, before_write=None) -> str:
    """Update one explicitly owned summary, or create one preserving other notes.

    Return a warning when creation leaves unmarked (possibly legacy) notes.
    Never adopt a note by its content. No write retries or create fallback after
    a failed update. The existing note version is passed through to pyzotero's
    If-Unmodified-Since-Version guard; a conflict is left for human review.
    """
    with _ZOTERO_SUMMARY_WRITE_LOCK:
        children = zot.everything(zot.children(parent_key))
        notes = []
        managed = []
        for child in children:
            data = child["data"]
            if data.get("itemType") != "note":
                continue
            notes.append(data)
            tags = data.get("tags", [])
            if not isinstance(tags, list) or any(not isinstance(tag, dict) for tag in tags):
                raise RuntimeError("invalid Zotero note tags; ownership cannot be established")
            reserved = {tag.get("tag") for tag in tags
                        if isinstance(tag.get("tag"), str)
                        and tag["tag"].startswith(SUMMARY_NOTE_TAG_PREFIX)}
            if reserved and reserved != {SUMMARY_NOTE_TAG}:
                raise RuntimeError("unsupported Hub summary ownership marker; review notes before writing")
            if SUMMARY_NOTE_TAG in reserved:
                managed.append(child)
        if len(managed) > 1:
            raise RuntimeError("multiple Hub summary notes; review ownership before writing")
        if managed:
            child = managed[0]
            data = child["data"]
            version = data.get("version")
            if (data.get("parentItem") != parent_key
                    or not isinstance(data.get("key"), str) or not data["key"]
                    or ("key" in child and child["key"] != data["key"])
                    or type(version) is not int or version < 1
                    or ("version" in child and child["version"] != version)
                    or data.get("deleted")):
                raise RuntimeError("invalid Hub summary note identity/version; refusing an unguarded update")
            payload = deepcopy(data)
            payload["note"] = html
            if before_write is not None:
                before_write()
            try:
                confirmed = zot.update_item(payload)
            except Exception as exc:
                raise _ZoteroWriteUncertain(
                    f"Hub summary update may already have committed; inspect Zotero before retrying (no automatic retry): {exc}"
                ) from exc
            if not confirmed:
                raise _ZoteroWriteUncertain(
                    "Hub summary update was not confirmed; inspect Zotero before retrying (no automatic retry)"
                )
            return ""

        template = deepcopy(zot.item_template("note"))
        template["note"] = html
        template["parentItem"] = parent_key
        template["tags"] = [{"tag": SUMMARY_NOTE_TAG}]
        if before_write is not None:
            before_write()
        try:
            resp = zot.create_items([template])
        except Exception as exc:
            raise _ZoteroCreateUncertain(
                "new Hub summary may already exist; inspect Zotero before retrying (no automatic retry)"
            ) from exc
        successful = resp.get("successful", {}) if isinstance(resp, dict) else {}
        created = successful.get("0", {}) if isinstance(successful, dict) else {}
        if (not isinstance(created, dict)
                or not isinstance(created.get("key"), str) or not created["key"]):
            if isinstance(resp, dict) and resp.get("failed"):
                raise RuntimeError("Zotero rejected summary note creation; existing notes were preserved")
            raise _ZoteroCreateUncertain(
                "new Hub summary creation was not confirmed; inspect Zotero before retrying (no automatic retry)"
            )
        if notes:
            return (f"created a Hub summary note; preserved {len(notes)} unmarked note(s), "
                    "including possible legacy Hub summaries; a legacy duplicate may remain")
        return ""


def _rollback_summary_note(note_path: Path, original_text: str, written_text: str) -> str:
    """Best-effort compensation, not a distributed/cross-process transaction.

    Never overwrite a change already observable after the remote operation.
    The check does not lock out another writer racing after it; callers must
    retain an explicit reconciliation outcome rather than claim atomicity.
    """
    try:
        with note_path.open("r", encoding="utf-8", newline="") as handle:
            current = handle.read()
        if current != written_text:
            return "local rollback skipped: note changed after this write; newer content preserved; inspect both destinations"
        _write_note_text(note_path, original_text)
        return "local note restored; remote outcome remains as reported"
    except (OSError, ValueError) as exc:
        return f"local rollback unavailable; inspect local note and remote destination before retrying: {exc}"


def _apply_one_entry(
    entry: dict,
    paper_by_slug: dict[str, dict],
    valid_slugs: set[str],
    zot,
    write_obsidian: bool,
    write_zotero: bool,
    cfg,
    provenance: str,
) -> _PerPaperOutcome:
    summary, reason = _validate_entry(entry, valid_slugs)
    if summary is None:
        return _PerPaperOutcome(
            slug=str(entry.get("paper_slug", "?")),
            skipped_reason=reason or "invalid entry",
        )

    from .summary_apply_journal import apply_entry
    return apply_entry(cfg, paper_by_slug[summary.paper_slug], summary, zot,
                       write_obsidian, write_zotero, provenance=provenance)


def apply_summaries(
    cfg,
    cluster_slug: str,
    payload: dict | list,
    *,
    write_zotero: bool = True,
    write_obsidian: bool = True,
    zot=None,
    selected_slugs: set[str] | None = None,
    provenance: str = "legacy_parent_apply_invocation",
) -> SummaryApplyResult:
    """Validate entries and apply writes, with best-effort local rollback.

    `payload` is the parsed LLM JSON ({"summaries": [...]} or [...] directly).
    `zot` may be injected for tests; production passes None and we resolve via
    `research_hub.zotero.client.get_client()`.
    """
    entries = payload.get("summaries", []) if isinstance(payload, dict) else payload
    entries = entries if isinstance(entries, list) else []

    papers = _read_cluster_papers_with_abstracts(cfg, cluster_slug)
    # Generation may select only missing summaries or explicit paper keys.
    # Do not let an unsolicited response expand that selection at apply time.
    paper_by_slug = {
        p["slug"]: p for p in papers
        if selected_slugs is None or p["slug"] in selected_slugs
    }
    valid_slugs = set(paper_by_slug.keys())

    result = SummaryApplyResult(cluster_slug=cluster_slug)

    if write_zotero and zot is None:
        try:
            from research_hub.zotero.client import get_client
            zot = get_client()
        except Exception as exc:
            return SummaryApplyResult(
                cluster_slug=cluster_slug,
                errors=[f"(all): could not load Zotero client: {exc}"],
            )

    if write_zotero:
        # Repeated entries must not become an automatic retry after an uncertain
        # create. Include distinct slugs that point at the same Zotero parent.
        seen_parents: set[str] = set()
        unique_entries = []
        for entry in entries:
            slug = str(entry.get("paper_slug", "") or "").strip()
            parent = paper_by_slug.get(slug, {}).get("zotero_key", "")
            if parent and parent in seen_parents:
                result.skipped.append(f"{slug}: duplicate Zotero parent in payload (not retried)")
                continue
            if parent:
                seen_parents.add(parent)
            unique_entries.append(entry)
        entries = unique_entries

    worker = partial(
        _apply_one_entry,
        cfg=cfg,
        provenance=provenance,
        paper_by_slug=paper_by_slug,
        valid_slugs=valid_slugs,
        zot=zot,
        write_obsidian=write_obsidian,
        write_zotero=write_zotero,
    )
    with ThreadPoolExecutor(max_workers=4) as executor:
        outcomes = list(executor.map(worker, entries))

    for outcome in outcomes:
        if outcome.receipt is not None:
            result.receipts.append(outcome.receipt)
        if outcome.warning:
            result.warnings.append(f"{outcome.slug}: {outcome.warning}")
        if outcome.applied:
            result.applied.append(outcome.slug)
        if outcome.obsidian_written:
            result.obsidian_writes += 1
        if outcome.zotero_written:
            result.zotero_writes += 1
        if outcome.error:
            result.errors.append(f"{outcome.slug}: {outcome.error}")
        elif outcome.skipped_reason:
            result.skipped.append(f"{outcome.slug}: {outcome.skipped_reason}")

    return result


# -- orchestration ------------------------------------------------------


def summarize_cluster(
    cfg,
    cluster_slug: str,
    *,
    llm_cli: Optional[str] = None,
    apply: bool = False,
    write_zotero: bool = True,
    write_obsidian: bool = True,
    paper_keys: list[str] | None = None,
    skip_existing: bool = True,
    provenance: str = "legacy_parent_apply_invocation",
) -> SummaryReport:
    """End-to-end: emit prompt → invoke LLM → parse → optionally apply.

    `apply=False` (default) just emits the prompt + invokes the LLM and
    returns the parsed payload. `apply=True` also writes back to Obsidian
    + Zotero. The split keeps the dry-run path safe.

    Existing substantive sections are preserved by default, including notes
    with a stale pending status. ``skip_existing=False`` requests regeneration.

    `llm_cli` overrides auto-detection. None = use the first supported LLM CLI
    on PATH. If no CLI is available, the prompt is saved to
    `<cfg.research_hub_dir>/artifacts/<slug>/summarize-prompt.md` and
    `report.ok=True` (best-effort, never raises).
    """
    from research_hub.llm_cli import (
        _extract_first_json,
        detect_llm_cli,
        invoke_llm_cli as _invoke_llm_cli,
    )

    report = SummaryReport(cluster_slug=cluster_slug)

    papers = _read_cluster_papers_with_abstracts(
        cfg, cluster_slug, paper_keys=paper_keys, skip_existing=skip_existing,
    )
    if skip_existing and not papers and _read_cluster_papers_with_abstracts(
        cfg, cluster_slug, paper_keys=paper_keys,
    ):
        if apply:
            report.apply_result = SummaryApplyResult(cluster_slug=cluster_slug)
        return report

    try:
        prompt = _build_summarize_prompt(papers, cluster_slug, paper_keys=paper_keys)
    except ValueError as exc:
        report.ok = False
        report.error = str(exc)
        return report

    cli = llm_cli or detect_llm_cli()
    if not cli:
        # Save prompt for the user to pipe through their LLM manually
        prompt_dir = Path(cfg.research_hub_dir) / "artifacts" / cluster_slug
        prompt_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = prompt_dir / "summarize-prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        report.prompt_path = prompt_path
        report.ok = True  # best-effort fallback
        return report

    report.cli_used = cli
    try:
        raw = _invoke_llm_cli(cli, prompt)
    except Exception as exc:
        report.ok = False
        report.error = f"LLM CLI {cli!r} invocation failed: {exc}"
        return report

    payload = _extract_first_json(raw)
    if payload is None:
        report.ok = False
        report.error = "LLM response had no parseable JSON object"
        return report

    if apply:
        report.apply_result = apply_summaries(
            cfg,
            cluster_slug,
            payload,
            write_zotero=write_zotero,
            write_obsidian=write_obsidian,
            selected_slugs={paper["slug"] for paper in papers},
            provenance=provenance,
        )
        if report.apply_result.errors:
            report.ok = False
            report.error = (
                f"{len(report.apply_result.errors)} summary entry/entries failed "
                f"({len(report.apply_result.applied)} applied): {report.apply_result.errors[0]}"
            )

    return report

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
  5. write Obsidian markdown blocks + Zotero child note HTML atomically
     per paper (rollback the markdown change if Zotero write fails)

Design choices
--------------
- Separate command (NOT auto-on-ingest) so a single LLM failure doesn't
  abort an ingest batch and so users can re-run on subset of papers.
- Both write targets must succeed for an entry to count as applied;
  the two systems stay in sync.
- No PDF parsing: the LLM only sees the abstract. Methodology / Relevance
  are inferences, marked as such in the prompt.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import partial
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# -- data model ---------------------------------------------------------


@dataclass
class PaperSummary:
    """One LLM-generated summary entry for a single paper."""

    paper_slug: str
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

    def to_dict(self) -> dict:
        return {
            "cluster_slug": self.cluster_slug,
            "applied": list(self.applied),
            "skipped": list(self.skipped),
            "errors": list(self.errors),
            "obsidian_writes": self.obsidian_writes,
            "zotero_writes": self.zotero_writes,
        }


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


# -- prompt building ----------------------------------------------------


def _read_cluster_papers_with_abstracts(cfg, cluster_slug: str) -> list[dict]:
    """Walk raw/<slug>/*.md, return list of dicts with slug + frontmatter
    fields + abstract text. Reuses the same exclusion rules as crystal."""
    papers: list[dict] = []
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
        abstract = _extract_section(text, "Abstract")
        papers.append({
            "slug": note_path.stem,
            "title": fm.get("title", note_path.stem),
            "doi": fm.get("doi", ""),
            "year": fm.get("year", ""),
            "zotero_key": fm.get("zotero-key", ""),
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


def build_summarize_prompt(cfg, cluster_slug: str) -> str:
    """Build the LLM prompt requesting per-paper summaries as JSON."""
    papers = _read_cluster_papers_with_abstracts(cfg, cluster_slug)
    if not papers:
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
    if not methodology:
        return None, "methodology is empty"
    if not relevance:
        return None, "relevance is empty"
    return PaperSummary(
        paper_slug=slug,
        key_findings=findings,
        methodology=methodology,
        relevance=relevance,
    ), None


# -- write back ---------------------------------------------------------


_FINDINGS_BLOCK_RE = re.compile(
    r"(##\s+Key Findings\n\n>\s+\[!success\]\n)(?:>[^\n]*\n)+(\^findings)",
    re.MULTILINE,
)
_METHODOLOGY_BLOCK_RE = re.compile(
    r"(##\s+Methodology\n\n>\s+\[!info\]\n)(?:>[^\n]*\n)+(\^methodology)",
    re.MULTILINE,
)
_RELEVANCE_BLOCK_RE = re.compile(
    r"(##\s+Relevance\n\n>\s+\[!note\]\n)(?:>[^\n]*\n)+(\^relevance)",
    re.MULTILINE,
)


def _replace_obsidian_block(text: str, summary: PaperSummary) -> str:
    findings_block = "".join(f"> - {f}\n" for f in summary.key_findings)
    text = _FINDINGS_BLOCK_RE.sub(rf"\1{findings_block}\2", text)
    text = _METHODOLOGY_BLOCK_RE.sub(rf"\1> {summary.methodology}\n\2", text)
    text = _RELEVANCE_BLOCK_RE.sub(rf"\1> {summary.relevance}\n\2", text)
    return text


def _build_zotero_note_html(paper_meta: dict, summary: PaperSummary) -> str:
    title = paper_meta.get("title", "(no title)")
    abstract = paper_meta.get("abstract", "")
    findings_html = "".join(f"<li>{f}</li>" for f in summary.key_findings)
    html = f"<h1>Summary</h1><p>{title}</p>"
    if abstract:
        html += f"<h2>Abstract</h2><p>{abstract}</p>"
    html += "<h2>Key Findings</h2><ul>" + findings_html + "</ul>"
    html += f"<h2>Methodology</h2><p>{summary.methodology}</p>"
    html += f"<h2>Relevance to cluster</h2><p>{summary.relevance}</p>"
    return html


def _write_zotero_child_note(zot, parent_key: str, html: str) -> None:
    """Find the first child note attached to parent_key and overwrite its HTML.
    Raises on failure so the caller can rollback the Obsidian write."""
    children = zot.children(parent_key)
    notes = [c for c in children if c.get("data", {}).get("itemType") == "note"]
    if not notes:
        # Create a new note
        template = zot.item_template("note")
        template["note"] = html
        template["parentItem"] = parent_key
        resp = zot.create_items([template])
        if not (resp or {}).get("successful"):
            raise RuntimeError(f"Zotero create_items returned no successful: {resp}")
        return
    note = notes[0]
    note["data"]["note"] = html
    zot.update_item(note["data"])


def _apply_one_entry(
    entry: dict,
    paper_by_slug: dict[str, dict],
    valid_slugs: set[str],
    zot,
    write_obsidian: bool,
    write_zotero: bool,
) -> _PerPaperOutcome:
    summary, reason = _validate_entry(entry, valid_slugs)
    if summary is None:
        return _PerPaperOutcome(
            slug=str(entry.get("paper_slug", "?")),
            skipped_reason=reason or "invalid entry",
        )

    paper = paper_by_slug[summary.paper_slug]
    note_path = paper["path"]
    original_text = note_path.read_text(encoding="utf-8") if write_obsidian else None
    new_text = _replace_obsidian_block(original_text, summary) if write_obsidian else None

    if write_obsidian and new_text is not None:
        note_path.write_text(new_text, encoding="utf-8")

    obsidian_written = bool(write_obsidian)
    zotero_written = False
    if write_zotero:
        parent_key = paper.get("zotero_key", "")
        if not parent_key:
            if write_obsidian and original_text is not None:
                note_path.write_text(original_text, encoding="utf-8")
                obsidian_written = False
            return _PerPaperOutcome(slug=summary.paper_slug, error="no zotero-key in frontmatter")
        html = _build_zotero_note_html(paper, summary)
        try:
            _write_zotero_child_note(zot, parent_key, html)
            zotero_written = True
        except Exception as exc:
            if write_obsidian and original_text is not None:
                note_path.write_text(original_text, encoding="utf-8")
                obsidian_written = False
            return _PerPaperOutcome(slug=summary.paper_slug, error=f"zotero write failed: {exc}")

    return _PerPaperOutcome(
        slug=summary.paper_slug,
        applied=True,
        obsidian_written=obsidian_written,
        zotero_written=zotero_written,
    )


def apply_summaries(
    cfg,
    cluster_slug: str,
    payload: dict | list,
    *,
    write_zotero: bool = True,
    write_obsidian: bool = True,
    zot=None,
) -> SummaryApplyResult:
    """Validate each entry + write to Obsidian + Zotero atomically per paper.

    `payload` is the parsed LLM JSON ({"summaries": [...]} or [...] directly).
    `zot` may be injected for tests; production passes None and we resolve via
    `research_hub.zotero.client.get_client()`.
    """
    entries = payload.get("summaries", []) if isinstance(payload, dict) else payload
    entries = entries if isinstance(entries, list) else []

    papers = _read_cluster_papers_with_abstracts(cfg, cluster_slug)
    paper_by_slug = {p["slug"]: p for p in papers}
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

    worker = partial(
        _apply_one_entry,
        paper_by_slug=paper_by_slug,
        valid_slugs=valid_slugs,
        zot=zot,
        write_obsidian=write_obsidian,
        write_zotero=write_zotero,
    )
    with ThreadPoolExecutor(max_workers=4) as executor:
        outcomes = list(executor.map(worker, entries))

    for outcome in outcomes:
        if outcome.error:
            result.errors.append(f"{outcome.slug}: {outcome.error}")
        elif outcome.skipped_reason:
            result.skipped.append(f"{outcome.slug}: {outcome.skipped_reason}")
        elif outcome.applied:
            result.applied.append(outcome.slug)
            if outcome.obsidian_written:
                result.obsidian_writes += 1
            if outcome.zotero_written:
                result.zotero_writes += 1

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
) -> SummaryReport:
    """End-to-end: emit prompt → invoke LLM → parse → optionally apply.

    `apply=False` (default) just emits the prompt + invokes the LLM and
    returns the parsed payload. `apply=True` also writes back to Obsidian
    + Zotero. The split keeps the dry-run path safe.

    `llm_cli` overrides auto-detection. None = use first claude/codex/gemini
    on PATH. If no CLI is available, the prompt is saved to
    `<cfg.research_hub_dir>/artifacts/<slug>/summarize-prompt.md` and
    `report.ok=True` (best-effort, never raises).
    """
    from research_hub.auto import detect_llm_cli, _invoke_llm_cli, _extract_first_json

    report = SummaryReport(cluster_slug=cluster_slug)

    try:
        prompt = build_summarize_prompt(cfg, cluster_slug)
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
        )

    return report

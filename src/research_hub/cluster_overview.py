"""Cluster overview auto-fill via LLM CLI.

Mirrors the summarize flow:
  1. build a JSON-output prompt from ingested paper abstracts
  2. invoke a detected LLM CLI via research_hub.auto helpers
  3. parse the first JSON object in the response
  4. validate/coerce payload fields
  5. optionally write hub/<cluster>/00_overview.md
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from research_hub.summarize import _read_cluster_papers_with_abstracts


# The Chinese scaffold written by topic.py for a new cluster opens its
# TL;DR with this exact phrase. Both the cluster and sub-topic variants
# start with the same five characters, so this prefix is a reliable
# "still untouched placeholder" sentinel — keep it in sync with the
# template in topic.py (lines ~29 / ~101). Historical note: this
# constant previously stored mojibake from a cp950/UTF-8 round-trip,
# which never matched the real placeholder, so the auto-fill step
# always saw the scaffold as hand-curated and silently skipped
# LLM enrichment.
_CHINESE_TEMPLATE_MARKER = "一到兩句話"

# Other scaffold sentinels written by `vault/hub_overview.py:_render_tldr`
# when `populate_overview` runs BEFORE this `apply_overview` step in the
# `auto` flow. populate_overview overwrites the Chinese scaffold with one
# of these fallbacks, so the Chinese marker alone is not enough — without
# these we'd silently classify a populate_overview-mangled scaffold as
# "hand-curated" and never call the LLM.
_ENGLISH_FALLBACK_TLDR = "No cluster summary available yet."


def _is_scaffold_tldr(text: str, cluster_query: str, cluster_slug: str) -> bool:
    """Return True if the TL;DR is still scaffold content, not user-curated.

    Recognises:
      * empty string
      * the Chinese scaffold from topic.py (`一到兩句話...`)
      * the English fallback string from `_render_tldr` when
        `_overview_tldr` returns nothing usable
      * an exact match against the cluster's query string (the most common
        populate_overview fallback — `_overview_tldr` returns the query
        when no NLM brief is available)
      * an exact match (case-insensitive) against the slug humanised — the
        last-resort fallback in `_overview_tldr`
    """
    text = (text or "").strip()
    if not text:
        return True
    if text.startswith(_CHINESE_TEMPLATE_MARKER):
        return True
    if text == _ENGLISH_FALLBACK_TLDR:
        return True
    if cluster_query and text.strip() == cluster_query.strip():
        return True
    slug_humanised = cluster_slug.replace("-", " ").strip()
    if slug_humanised and text.lower() == slug_humanised.lower():
        return True
    return False


@dataclass
class ClusterOverview:
    cluster_slug: str
    tldr: str = ""
    core_question: str = ""
    scope_covers: list[str] = field(default_factory=list)
    scope_excludes: list[str] = field(default_factory=list)
    themes: list[dict] = field(default_factory=list)


@dataclass
class OverviewApplyResult:
    cluster_slug: str
    ok: bool = True
    error: str = ""
    written: bool = False
    overview_path: Optional[Path] = None
    # v0.88.9: distinguish "no-op because user already curated this
    # overview" from "operation failed". Without this, the auto step
    # logs FAIL "overview already filled; use force=True to overwrite"
    # on every successful re-ingest of an existing cluster — pure
    # noise that hides real failures in the same column.
    skipped: bool = False
    skip_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "cluster_slug": self.cluster_slug,
            "ok": self.ok,
            "error": self.error,
            "written": self.written,
            "overview_path": str(self.overview_path) if self.overview_path else None,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }


@dataclass
class OverviewReport:
    cluster_slug: str
    ok: bool = True
    error: str = ""
    cli_used: str = ""
    prompt_path: Optional[Path] = None
    apply_result: Optional[OverviewApplyResult] = None

    def to_dict(self) -> dict:
        return {
            "cluster_slug": self.cluster_slug,
            "ok": self.ok,
            "error": self.error,
            "cli_used": self.cli_used,
            "prompt_path": str(self.prompt_path) if self.prompt_path else None,
            "apply_result": self.apply_result.to_dict() if self.apply_result else None,
        }


def _humanize_slug(cluster_slug: str) -> str:
    return cluster_slug.replace("-", " ").strip().title()


def _callout_lines(text: str) -> list[str]:
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    return [f"> {line}" for line in lines] or [">"]


def _extract_title_from_frontmatter(frontmatter: str, default: str) -> str:
    for line in frontmatter.splitlines():
        if line.startswith("title:"):
            return line.partition(":")[2].strip().strip('"').strip("'") or default
    return default


def _extract_frontmatter(text: str) -> tuple[Optional[str], str]:
    if not text.startswith("---\n"):
        return None, text
    try:
        end = text.index("\n---\n", 4)
    except ValueError:
        return None, text
    frontmatter = text[: end + 5]
    body = text[end + 5 :].lstrip("\n")
    return frontmatter, body


def _extract_tldr_text(md_text: str) -> str:
    match = re.search(
        r"##\s+TL;DR\s*\n\s*\n>\s+\[!abstract\]\n(?P<body>(?:>.*\n)+?)\^tldr",
        md_text,
        re.MULTILINE,
    )
    if not match:
        return ""
    lines = []
    for line in match.group("body").splitlines():
        if line.startswith("> "):
            lines.append(line[2:].strip())
        elif line.startswith(">"):
            lines.append(line[1:].strip())
    return "\n".join(line for line in lines if line).strip()


def _render_overview_markdown(cluster_slug: str, title: str, overview: ClusterOverview) -> str:
    covers = overview.scope_covers or ["[scope not provided]"]
    excludes = overview.scope_excludes or ["[scope not provided]"]
    themes = overview.themes or [{"name": "Theme", "summary": "[theme summary not provided]"}]

    lines = [
        f"# {title}",
        "",
        "## TL;DR",
        "",
        "> [!abstract]",
        *_callout_lines(overview.tldr),
        "^tldr",
        "",
        "## Core Question",
        "",
        "> [!question]",
        *_callout_lines(overview.core_question),
        "^core-question",
        "",
        "## Scope",
        "",
        "**Covers:**",
    ]
    lines.extend([f"- {item}" for item in covers])
    lines.extend([
        "",
        "**Excludes:**",
    ])
    lines.extend([f"- {item}" for item in excludes])
    lines.extend([
        "",
        "## Major Themes",
        "",
        "| Theme | Summary |",
        "|---|---|",
    ])
    for theme in themes:
        name = str(theme.get("name", "") or "").replace("\n", " ").strip() or "Untitled theme"
        summary = str(theme.get("summary", "") or "").replace("\n", " ").strip() or "[summary missing]"
        lines.append(f"| {name} | {summary} |")
    lines.extend([
        "",
        "## Notes",
        "",
        f"- Auto-generated from {cluster_slug.replace('-', ' ')} paper abstracts.",
        "- Review and refine after reading the full papers.",
        "",
    ])
    return "\n".join(lines)


def build_overview_prompt(cfg, cluster_slug: str) -> str:
    papers = _read_cluster_papers_with_abstracts(cfg, cluster_slug)
    if not papers:
        raise ValueError(f"no papers in cluster '{cluster_slug}'")

    humanized = _humanize_slug(cluster_slug)
    lines = [
        f'# Cluster overview for "{humanized}"',
        "",
        "Write a concise English synthesis of this research cluster using only",
        "the paper titles, years, and abstract snippets below.",
        "",
        "## Requirements",
        "",
        "- Return ONE JSON object and nothing else.",
        "- TL;DR: 2-3 sentences synthesizing what this cluster studies.",
        "- Core question: 1-2 sentences on the central unresolved question.",
        "- scope_covers: 3-5 short bullets.",
        "- scope_excludes: 2-4 short bullets.",
        "- themes: 3-5 items; each summary should be 2-3 sentences.",
        "- Stay grounded in the supplied abstracts. Do not invent details.",
        "",
        "## Cluster topic",
        "",
        humanized,
        "",
        f"## Papers ({len(papers)})",
        "",
    ]
    for index, paper in enumerate(papers, start=1):
        abstract = (paper.get("abstract") or "").strip()
        snippet = abstract[:300] if abstract else "(no abstract available)"
        lines.extend([
            f"### {index}. {paper['title']}",
            f"- year: {paper.get('year') or 'unknown'}",
            f"- abstract snippet: {snippet}",
            "",
        ])

    schema = {
        "tldr": "2-3 sentences synthesizing what this cluster studies",
        "core_question": "1-2 sentences on the central unresolved question",
        "scope_covers": ["bullet 1", "bullet 2", "bullet 3"],
        "scope_excludes": ["bullet 1", "bullet 2"],
        "themes": [
            {"name": "Theme 1", "summary": "2-3 sentences"},
            {"name": "Theme 2", "summary": "2-3 sentences"},
        ],
    }
    lines.extend([
        "## Output JSON schema",
        "",
        "```json",
        json.dumps(schema, indent=2, ensure_ascii=False),
        "```",
    ])
    return "\n".join(lines)


def _validate_payload(payload: dict) -> tuple[Optional[ClusterOverview], Optional[str]]:
    if not isinstance(payload, dict):
        return None, "payload must be a JSON object"

    tldr = str(payload.get("tldr", "") or "").strip()
    if not tldr:
        return None, "tldr is empty"

    core_question = str(payload.get("core_question", "") or "").strip()
    if not core_question:
        return None, "core_question is empty"

    scope_covers_raw = payload.get("scope_covers", [])
    if not isinstance(scope_covers_raw, list):
        return None, "scope_covers must be a list"
    scope_excludes_raw = payload.get("scope_excludes", [])
    if not isinstance(scope_excludes_raw, list):
        return None, "scope_excludes must be a list"

    themes_raw = payload.get("themes", [])
    if not isinstance(themes_raw, list):
        return None, "themes must be a list"

    themes: list[dict] = []
    for theme in themes_raw:
        if not isinstance(theme, dict):
            return None, "themes entries must be objects"
        name = str(theme.get("name", "") or "").strip()
        summary = str(theme.get("summary", "") or "").strip()
        if not name or not summary:
            return None, "themes entries require non-empty name and summary"
        themes.append({"name": name, "summary": summary})

    overview = ClusterOverview(
        cluster_slug=str(payload.get("cluster_slug", "") or "").strip(),
        tldr=tldr,
        core_question=core_question,
        scope_covers=[str(item).strip() for item in scope_covers_raw if str(item).strip()],
        scope_excludes=[str(item).strip() for item in scope_excludes_raw if str(item).strip()],
        themes=themes,
    )
    return overview, None


def apply_overview(cfg, cluster_slug, payload, *, force: bool = False) -> OverviewApplyResult:
    overview, reason = _validate_payload(payload)
    if overview is None:
        return OverviewApplyResult(cluster_slug=cluster_slug, ok=False, error=reason or "invalid payload")
    overview.cluster_slug = cluster_slug

    overview_path = Path(cfg.hub) / cluster_slug / "00_overview.md"
    overview_path.parent.mkdir(parents=True, exist_ok=True)

    title_default = _humanize_slug(cluster_slug)
    frontmatter = (
        f"---\n"
        f"type: topic-overview\n"
        f"cluster: {cluster_slug}\n"
        f"title: {title_default}\n"
        f"status: draft\n"
        f"---\n"
    )
    title = title_default

    if overview_path.exists():
        existing_text = overview_path.read_text(encoding="utf-8")
        existing_frontmatter, _ = _extract_frontmatter(existing_text)
        if existing_frontmatter:
            frontmatter = existing_frontmatter
            title = _extract_title_from_frontmatter(existing_frontmatter, title_default)
        existing_tldr = _extract_tldr_text(existing_text)
        # Look up the cluster's query so the topic-string fallback that
        # `populate_overview` writes can be recognised as scaffold (PR #91
        # was half-fix — see _is_scaffold_tldr docstring).
        try:
            from research_hub.clusters import ClusterRegistry
            _reg = ClusterRegistry(getattr(cfg, "clusters_file", Path(cfg.research_hub_dir) / "clusters.yaml"))
            _cluster_obj = _reg.get(cluster_slug)
            # NOTE: the Cluster dataclass field is `first_query`, NOT `query`
            # — `create(query=...)` stores it as `first_query`. Reading the
            # wrong attribute returns "" silently and the topic-string
            # scaffold check below never fires.
            _cluster_query = (getattr(_cluster_obj, "first_query", "") or "") if _cluster_obj else ""
        except Exception:
            _cluster_query = ""
        if existing_tldr and not _is_scaffold_tldr(existing_tldr, _cluster_query, cluster_slug) and not force:
            # v0.88.9: this is a deliberate idempotent skip protecting
            # the user's hand-curated TL;DR. Report ``ok=True``,
            # ``skipped=True`` so the auto step can render it as a
            # success-with-skip ("preserved hand-curated overview")
            # instead of FAIL.
            return OverviewApplyResult(
                cluster_slug=cluster_slug,
                ok=True,
                error="",
                written=False,
                overview_path=overview_path,
                skipped=True,
                skip_reason="overview already hand-curated; use force=True to overwrite",
            )

    body = _render_overview_markdown(cluster_slug, title, overview)
    overview_path.write_text(frontmatter.rstrip() + "\n\n" + body + "\n", encoding="utf-8")
    return OverviewApplyResult(
        cluster_slug=cluster_slug,
        ok=True,
        error="",
        written=True,
        overview_path=overview_path,
    )


def overview_cluster(cfg, cluster_slug, *, llm_cli=None, apply=False, force=False) -> OverviewReport:
    from research_hub.llm_cli import (
        _extract_first_json,
        detect_llm_cli,
        invoke_llm_cli as _invoke_llm_cli,
    )

    report = OverviewReport(cluster_slug=cluster_slug)
    try:
        prompt = build_overview_prompt(cfg, cluster_slug)
    except ValueError as exc:
        report.ok = False
        report.error = str(exc)
        return report

    cli = llm_cli or detect_llm_cli()
    if not cli:
        prompt_dir = Path(cfg.research_hub_dir) / "artifacts" / cluster_slug
        prompt_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = prompt_dir / "cluster-overview-prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        report.prompt_path = prompt_path
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

    overview, reason = _validate_payload(payload)
    if overview is None:
        report.ok = False
        report.error = reason or "invalid overview payload"
        return report

    if apply:
        report.apply_result = apply_overview(cfg, cluster_slug, payload, force=force)
        if not report.apply_result.ok:
            report.ok = False
            report.error = report.apply_result.error

    return report

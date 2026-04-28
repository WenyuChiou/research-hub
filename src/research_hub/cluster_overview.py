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


_CHINESE_TEMPLATE_MARKER = "銝?啣?亥店"


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

    def to_dict(self) -> dict:
        return {
            "cluster_slug": self.cluster_slug,
            "ok": self.ok,
            "error": self.error,
            "written": self.written,
            "overview_path": str(self.overview_path) if self.overview_path else None,
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
        if existing_tldr and not existing_tldr.startswith(_CHINESE_TEMPLATE_MARKER) and not force:
            return OverviewApplyResult(
                cluster_slug=cluster_slug,
                ok=False,
                error="overview already filled; use force=True to overwrite",
                written=False,
                overview_path=overview_path,
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
    from research_hub.auto import detect_llm_cli, _extract_first_json, _invoke_llm_cli

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

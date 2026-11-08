"""Queue worker for filling pending paper summaries from abstracts."""

from __future__ import annotations

import re
import os
import stat
import tempfile
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from research_hub.paper import _parse_frontmatter, _split_frontmatter
from research_hub.search.abstract_recovery import _PLACEHOLDER_PATTERNS


SUMMARY_PENDING_CALLOUT = (
    "> [!warning] Summary pending\n"
    "> Run `research-hub paper summarize --pending` to fill this\n"
    "> section from the abstract via paper-summarize."
)

SECTION_BLOCK_IDS = {
    "Summary": "summary",
    "Key Findings": "findings",
    "Methodology": "methodology",
    "Relevance": "relevance",
}

STICKY_PLACEHOLDER_TEXTS = (
    "[review and extract from Abstract section above]",
    "[review abstract; refine after reading PDF]",
    "[TODO: fill relevance to cluster]",
    "[TODO: fill from abstract]",
)

PROMPT_TEMPLATE = """You are summarizing an academic paper for an Obsidian vault entry.
Use ONLY the abstract below \u2014 do not invent results.

Abstract: {abstract}
Title: {title}
Cluster: {topic_cluster}

Output exactly four sections in markdown:
1. SUMMARY: 1-2 sentences using the paper's own terminology.
2. KEY_FINDINGS: 3-5 bullets, each starting with a concrete claim.
3. METHODOLOGY: 1 paragraph (study type, dataset, sample, primary metric).
4. RELEVANCE: 1 sentence naming the SPECIFIC dimension this paper contributes
   to "{topic_cluster}" — e.g. a new method, an empirical context, a finding
   that confirms or challenges prior work.  Do NOT write a generic
   "This paper is relevant to [cluster]" sentence.

If abstract is <100 chars or says "(no abstract)", output
`[no-abstract-fallback]` for all four sections. Do NOT hallucinate
from the title alone.
"""

_MAX_BACKEND_OUTPUT_CHARS = 80_000
_BACKEND_TIMEOUT_SECONDS = 300


@dataclass
class ParsedSummary:
    summary: str
    key_findings: str
    methodology: str
    relevance: str


@dataclass
class SummarizeResult:
    path: Path
    action: str
    backend: str = ""
    error: str = ""


def summarize_pending(
    cfg,
    *,
    cluster_slug_filter: str | None = None,
    backend: str = "claude",
    max_papers: int | None = None,
    dry_run: bool = False,
) -> list[SummarizeResult]:
    """Summarize notes whose frontmatter status is pending.

    Notes marked ``failed_no_abstract`` are also retried, because a later
    abstract recovery run may have filled the body.
    """

    if backend not in {"claude", "codex", "gemini"}:
        raise ValueError("backend must be one of: claude, codex, gemini")

    results: list[SummarizeResult] = []
    processed = 0
    for note_path in _iter_candidate_notes(Path(cfg.raw), cluster_slug_filter):
        with note_path.open("r", encoding="utf-8", newline="") as handle:
            text = handle.read()
        meta = _parse_frontmatter(text)
        status = str(meta.get("summarize_status", "") or "").strip()
        if status not in {"pending", "failed_no_abstract"}:
            continue
        # Older ingest/apply writers could leave a supplied summary pending.
        # Preserve its content and provenance without invoking another backend.
        if sections_are_substantive(text):
            continue
        if max_papers is not None and processed >= max_papers:
            break

        abstract = extract_markdown_section(text, "Abstract")
        if is_bad_abstract(abstract):
            if dry_run:
                results.append(SummarizeResult(note_path, "would_fail_no_abstract"))
            else:
                _write_note_text(note_path, set_frontmatter_fields(text, {"summarize_status": "failed_no_abstract"}))
                results.append(SummarizeResult(note_path, "failed_no_abstract"))
            processed += 1
            continue

        if dry_run:
            results.append(SummarizeResult(note_path, "would_summarize", backend=backend))
            processed += 1
            continue

        prompt = build_paper_prompt(
            abstract=abstract,
            title=str(meta.get("title", note_path.stem) or note_path.stem),
            topic_cluster=str(meta.get("topic_cluster", "") or note_path.parent.name),
        )
        try:
            raw_response = _invoke_backend(backend, prompt)
            parsed = parse_summary_response(raw_response)
        except Exception as exc:
            results.append(SummarizeResult(note_path, "error", backend=backend, error=str(exc)))
            processed += 1
            continue

        if parsed is None:
            updated = set_frontmatter_fields(text, {"summarize_status": "failed_no_abstract"})
            _write_note_text(note_path, updated)
            results.append(SummarizeResult(note_path, "failed_no_abstract", backend=backend))
            processed += 1
            continue

        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            updated_text = apply_parsed_summary_to_note(text, parsed)
            updated_text = set_frontmatter_fields(
                updated_text,
                {
                    "summarize_status": "done",
                    "summarize_source": backend,
                    "summarized_at": now,
                },
            )
            _write_note_text(note_path, updated_text)
        except (OSError, ValueError) as exc:
            results.append(SummarizeResult(note_path, "error", backend=backend, error=str(exc)))
        else:
            results.append(SummarizeResult(note_path, "done", backend=backend))
        processed += 1

    return results


def build_paper_prompt(*, abstract: str, title: str, topic_cluster: str) -> str:
    """Return the locked V3 prompt template with note-specific values."""

    return PROMPT_TEMPLATE.format(
        abstract=abstract.strip(),
        title=title.strip(),
        topic_cluster=topic_cluster.strip(),
    )


def parse_summary_response(response: str) -> ParsedSummary | None:
    """Parse the four-section markdown response from a backend.

    Returns ``None`` when the backend emitted the explicit no-abstract
    fallback.
    """

    stripped = response.strip()
    if not stripped:
        raise ValueError("backend returned empty response")
    if "[no-abstract-fallback]" in stripped.lower():
        return None

    sections = _split_backend_sections(stripped)
    missing = [name for name in ("SUMMARY", "KEY_FINDINGS", "METHODOLOGY", "RELEVANCE") if not sections.get(name)]
    if missing:
        raise ValueError("backend response missing section(s): " + ", ".join(missing))
    return ParsedSummary(
        summary=sections["SUMMARY"].strip(),
        key_findings=_normalize_key_findings(sections["KEY_FINDINGS"]),
        methodology=sections["METHODOLOGY"].strip(),
        relevance=sections["RELEVANCE"].strip(),
    )


def apply_parsed_summary_to_note(text: str, parsed: ParsedSummary) -> str:
    """Replace summary-related sections while preserving unrelated content."""

    split = _split_frontmatter(text)
    if split is None:
        raise ValueError("note is missing YAML frontmatter")
    opening, frontmatter, body, newline = split
    body = _upsert_section(body, "Summary", _callout("abstract", parsed.summary, "summary"), newline, preserve_manual=True)
    body = _upsert_section(
        body,
        "Key Findings",
        _callout("success", parsed.key_findings, "findings"),
        newline,
        preserve_manual=True,
    )
    body = _upsert_section(body, "Methodology", _callout("info", parsed.methodology, "methodology"), newline, preserve_manual=True)
    body = _upsert_section(body, "Relevance", _callout("note", parsed.relevance, "relevance"), newline, preserve_manual=True)
    return f"{opening}{frontmatter}{newline}---{newline}{body}"


def pending_section_callout(header: str) -> str:
    block_id = SECTION_BLOCK_IDS.get(header)
    suffix = f"\n^{block_id}" if block_id else ""
    return SUMMARY_PENDING_CALLOUT + suffix


def pending_sections_markdown(newline: str = "\n") -> str:
    parts: list[str] = []
    for header in ("Key Findings", "Methodology", "Relevance"):
        parts.append(f"## {header}{newline}{newline}{pending_section_callout(header)}{newline}")
    return (newline * 2).join(parts)


def replace_summary_sections_with_pending_callouts(text: str) -> str:
    split = _split_frontmatter(text)
    if split is None:
        return text
    opening, frontmatter, body, newline = split
    for header in ("Key Findings", "Methodology", "Relevance"):
        body = _upsert_section(body, header, pending_section_callout(header), newline)
    return f"{opening}{frontmatter}{newline}---{newline}{body}"


def has_sticky_placeholder(text: str) -> bool:
    lowered = text.lower()
    return any(placeholder.lower() in lowered for placeholder in STICKY_PLACEHOLDER_TEXTS)


def sections_are_substantive(text: str) -> bool:
    for header in ("Key Findings", "Methodology", "Relevance"):
        section = extract_markdown_section(text, header)
        if not _is_substantive_section(section):
            return False
    return True


def mark_summary_content_done(text: str) -> str:
    """Reuse the migration's ``done`` state for present structured sections.

    This is a content-presence heuristic, not attestation of generation,
    reading coverage, bibliographic verification, review, or remote writes.
    Leave provenance and generation-specific fields exactly as supplied.
    """
    if sections_are_substantive(text) and _split_frontmatter(text) is not None:
        return set_frontmatter_fields(text, {"summarize_status": "done"})
    return text


def extract_markdown_section(text: str, header: str) -> str:
    pattern = re.compile(
        rf"^##[ \t]+{re.escape(header)}[ \t]*\r?\n+(.*?)(?=^\s*---\s*$|^##[ \t]+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def is_bad_abstract(abstract: str) -> bool:
    stripped = (abstract or "").strip()
    if len(stripped) < 100:
        return True
    lowered = stripped.lower()
    return any(pattern in lowered for pattern in _PLACEHOLDER_PATTERNS)


def set_frontmatter_fields(text: str, updates: dict[str, str]) -> str:
    """Set scalar frontmatter fields without re-rendering unrelated fields."""

    split = _split_frontmatter(text)
    if split is None:
        raise ValueError("note is missing YAML frontmatter")
    opening, frontmatter, body, newline = split
    lines = frontmatter.splitlines()
    for key, value in updates.items():
        rendered = f"{key}: {value}"
        pattern = re.compile(rf"^{re.escape(key)}\s*:")
        for index, line in enumerate(lines):
            if pattern.match(line):
                lines[index] = rendered
                break
        else:
            lines.append(rendered)
    rendered_frontmatter = newline.join(lines)
    return f"{opening}{rendered_frontmatter}{newline}---{newline}{body}"


def _iter_candidate_notes(raw_root: Path, cluster_slug_filter: str | None) -> list[Path]:
    if not raw_root.exists():
        return []
    clusters = [raw_root / cluster_slug_filter] if cluster_slug_filter else sorted(raw_root.iterdir())
    notes: list[Path] = []
    for cluster_dir in clusters:
        if not cluster_dir.is_dir() or cluster_dir.name.startswith("_"):
            continue
        for note_path in sorted(cluster_dir.glob("*.md")):
            if note_path.name in {"00_overview.md", "index.md"}:
                continue
            notes.append(note_path)
    return notes


def _split_backend_sections(text: str) -> dict[str, str]:
    marker = re.compile(
        r"^\s*(?:#{1,6}\s*)?(?:\d+\.\s*)?"
        r"(SUMMARY|KEY_FINDINGS|METHODOLOGY|RELEVANCE)\s*:?\s*(.*)$",
        re.IGNORECASE,
    )
    current: str | None = None
    sections: dict[str, list[str]] = {}
    for line in text.splitlines():
        match = marker.match(line)
        if match:
            current = match.group(1).upper()
            sections.setdefault(current, [])
            inline = match.group(2).strip()
            if inline:
                sections[current].append(inline)
            continue
        if current:
            sections[current].append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def _normalize_key_findings(value: str) -> str:
    lines = [line.rstrip() for line in value.strip().splitlines() if line.strip()]
    if not lines:
        return ""
    normalized: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            normalized.append("- " + stripped[2:].strip())
        elif re.match(r"^\d+[.)]\s+", stripped):
            normalized.append("- " + re.sub(r"^\d+[.)]\s+", "", stripped).strip())
        else:
            normalized.append("- " + stripped)
    return "\n".join(normalized)


def _is_substantive_section(section: str) -> bool:
    # Inspect the title before stripping callout markup: pending warnings carry
    # their marker in that title, followed by a lengthy instructional body.
    if "summary pending" in section.lower():
        return False
    stripped = _strip_callout_markup(section).strip()
    if len(stripped) < 20:
        return False
    lowered = stripped.lower()
    if re.search(r"\[(?:todo\b|abstract too thin\b|no-abstract-fallback\b|pdf needed\b)", lowered):
        return False
    return not any(placeholder.lower() in lowered for placeholder in STICKY_PLACEHOLDER_TEXTS)


def _strip_callout_markup(section: str) -> str:
    lines: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("^") or stripped.startswith("> [!"):
            continue
        if stripped.startswith("> "):
            stripped = stripped[2:].strip()
        lines.append(stripped)
    return "\n".join(lines)


def _upsert_section(
    body: str, header: str, content: str, newline: str, *, preserve_manual: bool = False
) -> str:
    content = content.replace("\r\n", "\n").replace("\n", newline)
    rendered = f"## {header}{newline}{newline}{content.rstrip()}{newline}"
    pattern = re.compile(
        rf"^##[ \t]+{re.escape(header)}[ \t]*\r?\n+.*?(?=^##[ \t]+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    matches = list(pattern.finditer(body))
    if matches:
        if preserve_manual:
            if len(matches) != 1:
                raise ValueError(f"ambiguous summary section: {header}")
            section = matches[0]
            block_id = SECTION_BLOCK_IDS[header]
            managed = re.compile(
                rf"^>[ \t]+\[!(?:abstract|success|info|note|warning)\][^\r\n]*\r?\n"
                rf"(?:>[^\n]*\n)+(\^{block_id})[ \t]*(?=\r?$)",
                re.MULTILINE,
            )
            callouts = list(managed.finditer(section.group()))
            if len(callouts) != 1:
                raise ValueError(f"no unambiguous managed callout in summary section: {header}")
            callout = callouts[0]
            start = section.start() + callout.start()
            end = section.start() + callout.end()
            # Only replace the owned callout. Preserve personal prose, source
            # footers, headings, and whitespace before/after its block anchor.
            return body[:start] + content.rstrip("\r\n") + body[end:]
        # Legacy placeholder migration has its own explicit replacement policy.
        return pattern.sub(lambda _match: rendered + newline, body, count=1)

    abstract_pattern = re.compile(
        r"^##[ \t]+Abstract[ \t]*\r?\n+.*?(?=^\s*---\s*$|^##[ \t]+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    if header == "Summary":
        match = abstract_pattern.search(body)
        if match:
            return body[: match.start()] + rendered + newline + body[match.start():]
    if not body.endswith(("\n", "\r\n")):
        body += newline
    return body.rstrip("\r\n") + newline + newline + rendered


def _callout(kind: str, content: str, block_id: str) -> str:
    lines = [f"> [!{kind}]"]
    for line in content.rstrip().splitlines():
        if line.strip():
            lines.append("> " + line)
        else:
            lines.append(">")
    lines.append(f"^{block_id}")
    return "\n".join(lines)


def _invoke_backend(backend: str, prompt: str) -> str:
    if backend == "claude":
        return _invoke_claude(prompt)
    if backend == "codex":
        return _invoke_codex(prompt)
    if backend == "gemini":
        return _invoke_gemini(prompt)
    raise ValueError(f"unknown backend: {backend}")


def _invoke_claude(prompt: str) -> str:
    """v0.87.2.1: feed prompt via stdin (not argv) to avoid Windows cmd.exe's
    ~8 KB argv length limit and shell-escape issues. Skill context is dropped
    from the prompt — Claude Code's `claude --print` mode does NOT activate
    Skills (those are interactive-mode only), and including the long skill
    markdown was confusing the model into echoing skill descriptions
    instead of summarizing the paper.
    """
    executable = _require_executable("claude", "claude")
    return _run_backend_command(
        [executable, "--print"],
        "claude",
        stdin_input=prompt,
    )


def _invoke_codex(prompt: str) -> str:
    executable = _require_executable("codex", "codex")
    return _run_backend_command([executable, "exec", "--full-auto", prompt], "codex")


def _invoke_gemini(prompt: str) -> str:
    executable = _require_executable("gemini-cli", "gemini")
    return _run_backend_command([executable, prompt], "gemini")


def _require_executable(executable: str, backend: str) -> str:
    resolved = shutil.which(executable)
    if not resolved:
        raise RuntimeError(f"install backend {backend}: `{executable}` was not found on PATH")
    return resolved


def _run_backend_command(argv: list[str], backend: str, *, stdin_input: str | None = None) -> str:
    # v0.87.2.1: subprocess.run(text=True) on Windows defaults to the locale
    # codec (cp950 in zh_TW locales), which cannot decode UTF-8 LLM output
    # containing characters like en-dash, smart quotes, em-dash, etc. Force
    # utf-8 + replace-error decoding so the chain never falls over on a
    # cosmetic glyph the LLM emits.
    #
    # When `stdin_input` is provided, feed it via stdin instead of argv —
    # avoids Windows cmd.exe's ~8 KB command-line length limit for long
    # prompts (skill_context + abstract + template can easily exceed it).
    completed = subprocess.run(
        argv,
        input=stdin_input,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_BACKEND_TIMEOUT_SECONDS,
        check=False,
    )
    stdout = (completed.stdout or "")[:_MAX_BACKEND_OUTPUT_CHARS]
    stderr = (completed.stderr or "")[:2000]
    if completed.returncode != 0:
        detail = f": {stderr.strip()}" if stderr.strip() else ""
        raise RuntimeError(f"{backend} backend failed with exit code {completed.returncode}{detail}")
    return stdout


def _read_claude_paper_summarize_skill() -> str:
    path = Path.home() / ".claude" / "skills" / "paper-summarize" / "SKILL.md"
    try:
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""
    except OSError:
        return ""


def _write_note_text(path: Path, text: str) -> None:
    """Atomically replace one note, preserving its mode and literal newlines.

    An exclusive per-write temporary avoids collisions between parallel
    summary entries. Keep temporary content private until the final mode is
    applied; a failed write never truncates the existing note.
    """
    path = Path(path)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

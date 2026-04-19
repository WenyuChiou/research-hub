"""Obsidian markdown conventions — callouts, block IDs, callout round-trip.

Adopted from [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills)
(MIT, by Steph Ango / Obsidian CEO). Callouts and block IDs are the
native Obsidian affordances for making rendered notes readable and
linkable, so research-hub paper notes, cluster overviews, and crystals
all emit them.

Public API:

- ``wrap_callout(kind, body, block_id=None)`` — wrap a string in a
  ``> [!kind]`` callout, optionally tagged with a ``^block_id``.
- ``unwrap_callout(body)`` — strip ``> [!kind]`` prefix lines from a
  callout block, returning the plain text inside. Idempotent: if the
  input is already plain text (no callout), it is returned unchanged.
- ``upgrade_paper_body(body)`` — rewrite the ``## Summary`` / ``## Key
  Findings`` / ``## Methodology`` / ``## Relevance`` sections of a
  paper note body to use callouts + block IDs. Idempotent.

The conversion keeps the underlying ``## Heading`` intact so existing
regex-based extractors (``autofill._replace_body_sections``,
``topic._read_cluster_definition``) keep working. Only the section
body is wrapped in the callout — the structural marker stays.
"""
from __future__ import annotations

import re
from typing import Iterable


CALLOUT_KIND_BY_SECTION = {
    "Summary": "abstract",
    "Abstract": "abstract",
    "TL;DR": "abstract",
    "Key Findings": "success",
    "Methodology": "info",
    "Relevance": "note",
    "Limitations": "warning",
    "Open problems": "warning",
    "Core question": "question",
    "核心問題": "question",
}

BLOCK_ID_BY_SECTION = {
    "Summary": "summary",
    "Abstract": "summary",
    "TL;DR": "tldr",
    "Key Findings": "findings",
    "Methodology": "methodology",
    "Relevance": "relevance",
    "Limitations": "limitations",
    "Open problems": "open-problems",
    "Core question": "core-question",
    "核心問題": "core-question",
}


def wrap_callout(kind: str, body: str, *, block_id: str | None = None) -> str:
    """Wrap ``body`` in a ``> [!kind]`` Obsidian callout.

    Each non-empty line is prefixed with ``> ``. Blank lines become a
    lone ``>`` to keep the callout block contiguous in Obsidian's
    renderer. If ``block_id`` is given, a trailing ``^block_id`` line
    is appended after the callout so the section is linkable.
    """
    stripped = body.rstrip()
    if not stripped:
        header = "> [!" + kind + "]"
        return header + "\n^" + block_id + "\n" if block_id else header + "\n"

    lines = ["> [!" + kind + "]"]
    for line in stripped.splitlines():
        if line.strip() == "":
            lines.append(">")
        else:
            lines.append("> " + line)
    if block_id:
        lines.append("^" + block_id)
    lines.append("")
    return "\n".join(lines)


_CALLOUT_LINE = re.compile(r"^>\s?\[![^\]]+\]\s*$")
_BLOCK_ID_LINE = re.compile(r"^\^[A-Za-z0-9_-]+\s*$")


def unwrap_callout(body: str) -> str:
    """Strip ``> [!kind]`` wrapping + ``^block_id`` suffix from ``body``.

    Returns the plain text of the callout body. If ``body`` is not a
    callout (or only partially so), returns ``body`` unchanged so the
    function is idempotent.
    """
    lines = body.splitlines()
    if not lines:
        return body
    # Drop trailing ^block_id and blank lines.
    while lines and (not lines[-1].strip() or _BLOCK_ID_LINE.match(lines[-1].strip())):
        lines.pop()
    if not lines or not _CALLOUT_LINE.match(lines[0].strip()):
        return body
    out: list[str] = []
    for line in lines[1:]:
        if line.startswith("> "):
            out.append(line[2:])
        elif line.rstrip() == ">":
            out.append("")
        else:
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def _is_already_callout(section_body: str) -> bool:
    for line in section_body.splitlines():
        if line.strip() == "":
            continue
        return bool(_CALLOUT_LINE.match(line.strip()))
    return False


_SECTION_HEADING = re.compile(
    r"^(##[ \t]+(?P<heading>[^\n^]+?))(?:[ \t]+\^(?P<block_id>[A-Za-z0-9_-]+))?[ \t]*$",
    re.MULTILINE,
)


def upgrade_paper_body(body: str) -> str:
    """Rewrite ``## Summary`` / ``## Key Findings`` / etc. to callouts.

    Idempotent: already-converted sections pass through untouched.
    Only the section body is wrapped — the ``## Heading`` anchor stays
    so regex-based extractors (autofill, topic) keep working.
    """
    matches = list(_SECTION_HEADING.finditer(body))
    if not matches:
        return body
    out_parts: list[str] = []
    cursor = 0
    for index, match in enumerate(matches):
        heading = match.group("heading").strip()
        existing_block_id = match.group("block_id")
        kind = CALLOUT_KIND_BY_SECTION.get(heading)
        # Keep any leading text unchanged.
        out_parts.append(body[cursor:match.start()])
        # Decide where this section ends.
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        heading_line = match.group(0)
        raw_section = body[match.end():end]
        section_body = raw_section.strip("\n")
        if kind is None:
            # Not a known upgradable section — pass through verbatim, but
            # normalize the leading separator to a single blank line so
            # repeated runs don't accumulate whitespace.
            out_parts.append(heading_line + "\n")
            if section_body:
                out_parts.append("\n" + section_body + "\n\n")
            else:
                out_parts.append("\n")
            cursor = end
            continue
        block_id = existing_block_id or BLOCK_ID_BY_SECTION.get(heading)
        # Keep heading anchor plain so regex extractors continue to match
        # ``^##\s+Heading\s*$``. Block IDs go on their own line inside
        # the callout (both forms link equivalently in Obsidian).
        plain_heading = "## " + heading
        if _is_already_callout(section_body):
            out_parts.append(plain_heading + "\n\n" + section_body + "\n\n")
            cursor = end
            continue
        if section_body.strip():
            wrapped = wrap_callout(kind, section_body, block_id=block_id).rstrip() + "\n"
        else:
            wrapped = "> [!" + kind + "]\n"
            if block_id:
                wrapped += "^" + block_id + "\n"
        out_parts.append(plain_heading + "\n\n" + wrapped + "\n")
        cursor = end
    out_parts.append(body[cursor:])
    return "".join(out_parts)


def summary_section_to_callout(
    summary: str,
    key_findings: Iterable[str],
    methodology: str,
    relevance: str,
) -> str:
    """Render the canonical 4-section paper body in callout form.

    Used by ``pipeline.make_raw_md`` + ``autofill._replace_body_sections``
    so fresh notes ship in v0.42 callout format without going through
    the migration script.
    """
    def _bullets(items: Iterable[str]) -> str:
        lines = [str(item).strip() for item in items if str(item).strip()]
        if not lines:
            return "- (none supplied)"
        return "\n".join("- " + line for line in lines)

    parts: list[str] = []
    parts.append("## Summary\n\n")
    parts.append(wrap_callout("abstract", (summary or "(no summary)").strip(), block_id="summary"))
    parts.append("\n")
    parts.append("## Key Findings\n\n")
    parts.append(wrap_callout("success", _bullets(key_findings), block_id="findings"))
    parts.append("\n")
    parts.append("## Methodology\n\n")
    parts.append(wrap_callout("info", (methodology or "(no methodology)").strip(), block_id="methodology"))
    parts.append("\n")
    parts.append("## Relevance\n\n")
    parts.append(wrap_callout("note", (relevance or "(no relevance)").strip(), block_id="relevance"))
    return "".join(parts)


# ---------------------------------------------------------------------------
# v0.43 Obsidian Flavored Markdown extensions
# (wikilinks, embeds, properties, highlight)
#
# Spec reference: kepano/obsidian-skills/obsidian-markdown
#   https://github.com/kepano/obsidian-skills/tree/main/skills/obsidian-markdown
# ---------------------------------------------------------------------------


def wikilink(
    target: str,
    *,
    display: str | None = None,
    heading: str | None = None,
    block_id: str | None = None,
) -> str:
    """Render an Obsidian wikilink ``[[target]]`` with optional modifiers."""
    if not target or not target.strip():
        raise ValueError("wikilink target cannot be empty")
    if heading and block_id:
        raise ValueError("wikilink cannot have both heading and block_id")
    inner = target.strip()
    if heading:
        inner += "#" + heading.strip()
    elif block_id:
        inner += "^" + block_id.strip()
    if display:
        inner += "|" + display.strip()
    return "[[" + inner + "]]"


def embed(
    target: str,
    *,
    size: int | None = None,
    page: int | None = None,
    display: str | None = None,
) -> str:
    """Render an Obsidian embed ``![[target]]`` with optional modifiers."""
    if not target or not target.strip():
        raise ValueError("embed target cannot be empty")
    inner = target.strip()
    if page is not None:
        inner += "#page=" + str(page)
    if size is not None:
        inner += "|" + str(size)
    elif display is not None:
        inner += "|" + display.strip()
    return "![[" + inner + "]]"


def highlight(text: str) -> str:
    """Wrap ``text`` in Obsidian inline highlight ``==text==``."""
    if not text:
        return ""
    return "==" + text + "=="


def property_block(**fields) -> str:
    """Render Obsidian-style property frontmatter (YAML) from kwargs."""
    if not fields:
        return ""
    import json as _json

    lines: list[str] = []
    for key, value in fields.items():
        if isinstance(value, list):
            rendered = _json.dumps(value, ensure_ascii=False)
            lines.append(f"{key}: {rendered}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif value is None:
            lines.append(f"{key}: null")
        elif isinstance(value, (int, float)):
            lines.append(f"{key}: {value}")
        else:
            escaped = str(value).replace('"', '\\"')
            lines.append(f'{key}: "{escaped}"')
    return "\n".join(lines)

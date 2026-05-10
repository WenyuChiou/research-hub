---
name: research-design-helper
description: Guide a researcher through 5 Socratic segments — research question sharpening, expected mechanism, identifiability check, validation plan, risk register — and produce `.research/design_brief.md`. Use when the user asks to "frame this research question", "design my study", "help me think through what model to build", "sharpen my hypothesis", or "before I start coding, walk me through the design". Does NOT write the model spec; does NOT invent the research question — guides the human to articulate them.
---

# research-design-helper

Stage 3a (sharp problem framing) and front-of-Stage 4 (model design) helper. Part of the research-hub skill pack — works alongside Zotero, Obsidian, and NotebookLM workflows but does not require any of them. Domain-agnostic Socratic guide that walks a researcher through 5 short segments and saves the result as `.research/design_brief.md`.

The skill **does not invent your research question or model design**. Like `research-context-compressor`, it leaves blanks rather than guess. Its value is structured prompting: forcing you to articulate what you'd otherwise leave implicit, before you spend weeks coding.

## When to use

Trigger phrases:

- "Frame this research question."
- "Design my study before I start coding."
- "Help me think through what model to build."
- "Sharpen my hypothesis."
- "Walk me through the design."
- "Build a design brief."

Not for:

- Writing actual model code (that's the user's work, optionally with `codex-delegate` for boilerplate).
- Project context manifests (that's `research-context-compressor`).
- Literature comparison (that's `literature-triage-matrix`).
- Manuscript writing (that's `academic-writing-skills`).

## Inputs

In priority order:

1. `.research/project_manifest.yml` if it exists — for project context (research_question may already be partially filled).
2. `.research/design_brief.md` if it exists — for refresh, not first-run.
3. `.research/literature_matrix.md` if it exists — for prior-art context when discussing identifiability.
4. The user's free-text answers during the conversation.

Do NOT scan code, data, or PDFs. This is a conversational skill.

## Workflow

Run the 5 Socratic segments **in order**, one at a time. For each, ask the listed questions, capture the user's answer, then save verbatim to the corresponding section of `.research/design_brief.md`. If the user can't answer a segment yet, write `_TODO: <reason>_` and move on; do not fabricate.

Segments + their prompts: `references/socratic-segments.md`.

| # | Segment | What it produces |
|---|---|---|
| 1 | Research question sharpening | falsifiable RQ + falsification condition |
| 2 | Expected mechanism | causal chain + uncertainty annotations |
| 3 | Identifiability check | discriminating condition + confounders + missing-data plan |
| 4 | Validation plan | metric + baseline + negative control |
| 5 | Risk register | 3–5 risks each with early-warning + mitigation |

## Output: `.research/design_brief.md`

Use the template at `references/design_brief_template.md` (sibling file in this skill). Fill the 5 sections with the user's answers verbatim. Frontmatter is required:

```yaml
project: <from project_manifest.yml or asked at start>
last_updated: <ISO date>
stage: design
status: draft     # draft | reviewed | locked
```

If the file already exists, **update don't replace**: keep human-edited sections intact, only fill blanks unless the user explicitly says "regenerate from scratch".

After saving, print a short report:

```
[research-design-helper]
  Wrote: .research/design_brief.md
  Sections completed: 4 / 5 (Risk register marked _TODO_ — circle back)
  Strongest spot: Identifiability check — clear discrimination via negative control.
  Weakest spot: Validation plan — baseline not yet specified.
  Suggested next: refine the validation baseline, then re-run with "regenerate from scratch" to lock the brief.
```

## Token-saving behavior

- Don't repeat the user's answers back at length — quote in the written brief, summarize one sentence in chat.
- Don't dump the whole template into the chat — write the file, then report which sections were filled.
- Skip segments the user can't answer; record `_TODO_` and move on. The point is not to complete every section in one session — it's to surface the gaps.

## What NOT to do

- **Do NOT invent the research question.** If the user is vague, surface the vagueness; do not fill it in for them.
- **Do NOT propose model architectures or technologies.** That's Stage 4 implementation work, owned by the user with help from `codex-delegate` for boilerplate. This skill stops at the spec.
- **Do NOT write to `.paper/`** — that's `paper-memory-builder`.
- **Do NOT touch `.research/project_manifest.yml`** — that's `research-context-compressor`. The two are complementary; the manifest captures STATE, the brief captures DESIGN INTENT.
- **Do NOT skip segments silently.** If a segment is blank, the brief must say `_TODO_` so future sessions (or the orienter) can flag it.

## See also

- `references/socratic-segments.md` — full prompts for each of the 5 segments
- `references/design_brief_template.md` — Markdown template for the output file

---
name: research-design-helper
description: Guide a researcher through 5 Socratic segments — research question sharpening, expected mechanism, identifiability check, validation plan, risk register — and produce `.research/design_brief.md`. Use when the user asks to "frame this research question", "design my study", "help me think through what model to build", "sharpen my hypothesis", "is my research question sharp enough to be falsifiable?", or "before I start coding, walk me through the design". Runs AFTER a topic is chosen — it designs the study for a given question; to decide whether a research gap is worth pursuing at all (open / a contribution / feasible), use `gap-to-topic`. Does NOT write the model spec; does NOT invent the research question — guides the human to articulate them.
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
2. `.research/topic_dossier.gaps.yml` if it exists — Stage 2 handoff from `gap-to-topic` (plugin v0.3.12+). Read only the chosen `gaps[]` entry plus the top-level `open_questions[]`, NOT the full file. The chosen entry is identified by `verdict: conditional-go` (or `verdict: go`); the workflow §0 step pre-fills segment 1 (RQ) from `gaps[].statement` and segment 5 (risks) from `open_questions[]` + the specific concern hinted by `gaps[].feasibility`. This satisfies the conversational-skill rule below — no whole-corpus scan, only one structured handoff record.
3. `.research/design_brief.md` if it exists — for refresh, not first-run.
4. `.research/literature_matrix.md` if it exists — for prior-art context when discussing identifiability.
5. The user's free-text answers during the conversation.

Do NOT scan code, data, or PDFs. This is a conversational skill.

## Workflow

### §0 — Detect Stage 2 handoff (gap-to-topic)

Before starting the Socratic dialog, check whether `.research/topic_dossier.gaps.yml` exists.

- **If absent** → behave exactly as before (skip to the 5-segment table below; no regression for users who run this skill standalone).
- **If present** → filter `gaps[]` to entries with `verdict` in `{conditional-go, go}` (no-go verdicts are out of scope for Stage 3a; the user already decided not to pursue them). Then:
  - **Filtered list has exactly one entry** → that's the chosen candidate. Auto-pre-fill:
    - **Segment 1 (RQ)** ← write `gaps[].statement` **verbatim** into the *Sharpened RQ* field, replacing the template's `_TODO_` placeholder. **Do not add any `_PRE-FILL_`-style annotation inside the file content** — the chat message below is where you signal "this is pre-fill, sharpen me". Keeping the file content clean means segment 1 dialog can simply overwrite the statement with the sharpened RQ; no later cleanup step is needed. The *Falsification condition* and *Smallest answerable version* sub-fields stay `_TODO_` — those only get filled during segment 1 dialog.
    - **Segment 5 (Risk register)** ← one row per entry in `open_questions[]`, plus a row for the specific concern indicated by `gaps[].feasibility` (e.g. `feasible-with-effort` → a "binding constraint" risk row).
    - Tell the user (chat message, not in the file): *"I pre-filled segment 1 (RQ) from `gaps[<id>].statement` and segment 5 (risks) from `open_questions[]` + the `feasibility: <value>` hint. Segment 1's *Sharpened RQ* is a starting point — segment 1 dialog will sharpen it into a falsifiable form. Review and revise as we walk through."*
  - **Filtered list has 2+ entries** → ask the user *"Which candidate are we designing for?"* before pre-filling. Use the user's answer as the chosen `gaps[]` entry. Do not assume.
  - **Filtered list is empty** (every gap is `no-go`) → tell the user *"No viable candidate in this dossier — every gap is `no-go`. Nothing for Stage 3a to frame."* and stop. Do NOT proceed to the 5-segment dialog on a topic the dossier rejected.
- **Segments 2 (mechanism), 3 (identifiability), 4 (validation) are NEVER pre-filled.** The `.gaps.yml` doesn't carry that material; pre-filling those segments with non-content corrupts the Socratic dialog. Leave them blank → `_TODO_` until the segment runs.
- **Provenance.** When you write `.research/design_brief.md`, fill the frontmatter `source:` field with `topic_dossier.gaps.yml#<gap-id>` (e.g. `topic_dossier.gaps.yml#G2`) and the `gap_verdict:` field with a frozen snapshot of `verdict` + the first 60 chars of `verdict_reason`. This makes the brief self-contained — a future reader sees which dossier candidate this design was framed for.

### §1 to §5 — the 5 Socratic segments

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

**Provenance protection (v0.3.12+).** If the existing `design_brief.md` has frontmatter `source: topic_dossier.gaps.yml#<old-id>` and a different `gaps[]` entry is now being chosen (different id, OR `.gaps.yml` `generated:` date differs), ASK the user before refreshing — do not silently overwrite provenance. Phrasing: *"This brief was originally framed for `<old-id>` (`<old-verdict>`). The current `.gaps.yml` chooses `<new-id>` (`<new-verdict>`). Refresh and replace the provenance, or keep the old brief and start a new one?"*

After saving, print a short report:

```
[research-design-helper]
  Wrote: .research/design_brief.md
  Sections completed: 4 / 5 (Risk register marked _TODO_ — circle back)
  Strongest spot: Identifiability check — clear discrimination via negative control.
  Weakest spot: Validation plan — baseline not yet specified.
  Suggested next: refine the validation baseline, then re-run with "regenerate from scratch" to lock the brief.
```

## Generate .docx (optional, plugin v0.3.14+)

After writing `.research/design_brief.md`, an **optional** Word version
can be generated via the sister script at
`scripts/brief_to_docx.js`. The `.docx` is a convenience for sharing the
brief with advisors / committee members who prefer Word — it is NOT
part of the contracted Stage 3a output and is not consumed by
downstream skills (Stage 3b reads `design_brief.md` frontmatter + §1
directly).

```bash
# From the directory that contains design_brief.md:
node /path/to/skills/research-design-helper/scripts/brief_to_docx.js design_brief --no-toc

# zh-TW variant (auto-selects Microsoft JhengHei):
node /path/to/skills/research-design-helper/scripts/brief_to_docx.js design_brief.zh-TW --no-toc
```

Prerequisite: `npm install -g docx` (one-time). The `--no-toc` flag is
recommended for design briefs — they're typically short enough that
Word's auto-generated empty TOC field is more distracting than useful.

The script is a near-byte copy of the `gap-to-topic`
`scripts/dossier_to_docx.js` generator (same Markdown → Word logic,
same font auto-selection, same separator-row skip). The dossier's
verdict-colour regex is inherited verbatim but does not fire on design
brief content — see `scripts/README.md` for the rationale.

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

---
name: paper-memory-builder
description: Convert a paper draft + figures + Zotero metadata into reusable .paper/claims.yml and .paper/figures.yml files so the academic-writing-skills skill can do writing, revision, and audit passes without re-reading the manuscript every time. Use when the user asks to "build paper memory", "extract claims from this manuscript", or "prepare this paper for AI-assisted writing".
---

# paper-memory-builder

Bridge between research-hub and `academic-writing-skills`. Reads a
manuscript draft (Word, LaTeX, Markdown, Obsidian paper folder) plus the
figures it references, and writes structured `.paper/claims.yml` +
`.paper/figures.yml` so the writing skill can reason about the paper
without parsing the manuscript on every call.

This skill **does not edit the manuscript itself**. That's the writing
skill's job. We just produce the memory layer it consumes.

## When to use

Trigger phrases:

- "Build paper memory for this manuscript."
- "Extract claims, figures, and evidence from this paper folder."
- "Prepare reusable memory for writing and revision."
- "I'm starting a rebuttal — give me the claims layer first."

Not for:

- Writing the rebuttal itself — `academic-writing-skills`.
- Building the orientation memo — `research-project-orienter`.
- Comparing papers — `literature-triage-matrix`.
- Verifying a NotebookLM brief — `notebooklm-brief-verifier`.

## Inputs

In priority order:

1. **`.paper/` existing files** — if `claims.yml` already exists, parse
   it; this run should refresh, not replace human edits.
2. **The manuscript file** — usually one of:
   - `paper/manuscript.docx` / `manuscript.tex` / `manuscript.md`
   - Obsidian paper note under `raw/<paper-cluster>/manuscript.md`
   - Word/LaTeX in a sibling repo specified by the user
3. **Figure files** under `figures/` or `outputs/figures/` — read
   filenames + captions; don't OCR images.
4. **`.research/project_manifest.yml`** — for project context (research
   question, datasets, current_stage). Use to anchor claims in the
   project's overall question.
5. **`.research/literature_matrix.md`** — for citation key lookup if the
   manuscript references "Smith 2024" but you need to disambiguate.

## Outputs

Write to `<project-root>/.paper/`:

- `claims.yml` — every paper-level claim, with evidence pointers + status.
- `figures.yml` — every figure inventory, with key numbers + supported
  claims.
- `revision_history.yml` — append-only log of revision rounds (when a
  claim or figure changed, in which round, why). See
  `references/revision_history_schema.md` for the schema and the
  append-vs-overwrite rules.

Do **not** touch `journal_format.md`, `reviewer_comments.md`, or
`style_overrides.md` — those belong to `academic-writing-skills`.

### `.paper/claims.yml` structure

```yaml
claims:
  - id: C1
    text: "Coupled ABM-CAT reduces flood-impact RMSE by 22%."
    evidence_artifacts:
      - "outputs/E2/calibration.csv"
      - "outputs/E2/figure3.png"
    figure_or_table: ["Fig3"]
    status: "draft"          # draft | supported | rejected
    risk: "Reviewer R2 may push back on calibration window."
    sentence_in_manuscript: "...we observe a 22% reduction in RMSE..."
```

Required per claim: `id`, `text`, `status`. Numbering: `C1, C2, ...`
contiguous; if you regenerate, preserve human-assigned IDs.

### `.paper/figures.yml` structure

```yaml
figures:
  - id: "Fig1"
    file: "outputs/figures/Fig1_study_area.png"
    panels: ["a) site map", "b) gauge locations"]
    key_numbers: ["12 gauges", "1985-2024 record length"]
    supports_claims: []
    caption_in_manuscript: "Figure 1. Study area..."
```

Required per figure: `id`, `file`, `supports_claims` (may be `[]`).

### `.paper/revision_history.yml` structure

```yaml
revisions:
  - round: 1
    date: "2026-04-15"
    trigger: "Initial draft v1"
    changed_claims: []          # all claims new
    changed_figures: []
    summary: "First complete draft."
  - round: 2
    date: "2026-05-02"
    trigger: "Reviewer 2 round 1: doubt on calibration window"
    changed_claims: ["C1", "C4"]
    changed_figures: ["Fig3"]
    summary: "Tightened calibration window claim, added robustness check (Fig S3), softened C4 claim wording."
```

Required per revision: `round`, `date`, `trigger`, `summary`.
`changed_claims` and `changed_figures` may be `[]` for fresh drafts.

**Append, do not overwrite.** Each new revision round appends a new
list entry. Past rounds stay verbatim — they're the audit trail. The
full schema is in `references/revision_history_schema.md`.

## Token-saving behavior

- Read manuscript ONCE per session, extract claims + figures, then
  reference `.paper/*.yml` in subsequent writing turns.
- Pass-through claim text exactly as in the manuscript; do not rephrase.
  The writing skill will polish later.
- For figures, read just the caption + filename; don't OCR or describe
  visual content.
- After running, hand off cleanly: tell the user "claims.yml and
  figures.yml ready. Load `academic-writing-skills` next for any
  writing/revision/audit pass."

## Output format for the user

```
[paper-memory-builder]
  Read manuscript: paper/manuscript.docx (8 pages, 12 figures)
  Wrote: .paper/claims.yml (9 claims; 2 marked at risk)
  Wrote: .paper/figures.yml (12 figures; 8 mapped to claims, 4 are context)
  Suggested next: load academic-writing-skills for revision/audit passes.
```

## What NOT to do

- Don't edit the manuscript file. Read-only.
- Don't paraphrase claim text. Copy exactly from the manuscript.
- Don't fabricate figures or claims that aren't in the source.
- Don't write to `.paper/journal_format.md`, `reviewer_comments.md`, or
  `style_overrides.md`. Those are owned by `academic-writing-skills`.
- Don't write to `.research/` — that's the workspace layer, not the
  paper layer.
- Don't extract claims from cited works — only from THIS paper.

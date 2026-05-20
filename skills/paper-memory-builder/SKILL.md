---
name: paper-memory-builder
description: Convert a paper draft + figures + Zotero metadata into reusable .paper/claims.yml and .paper/figures.yml files so the academic-writing-skills skill can do writing, revision, and audit passes without re-reading the manuscript every time. Use when the user asks to "build paper memory", "extract claims from this manuscript", "extract claims, supporting evidence, and figure key numbers", or "prepare this paper for AI-assisted writing". NOT for summarizing cited papers in a literature cluster — that's `paper-summarize`. This skill is for the user's own manuscript draft only.
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

- `claims.yml` — every paper-level claim, with evidence pointers + status. Schema: `references/yaml-schemas.md`.
- `figures.yml` — every figure inventory, with key numbers + supported claims. Schema: `references/yaml-schemas.md`.
- `revision_history.yml` — append-only log of revision rounds. Schema + append-vs-overwrite rules: `references/revision_history_schema.md`.

Do **not** touch `journal_format.md`, `reviewer_comments.md`, or `style_overrides.md` — those belong to `academic-writing-skills`.

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
- Don't emit an unsupported claim as `status: draft` — see the
  anti-leakage rule below.
- Don't write to `.paper/journal_format.md`, `reviewer_comments.md`, or
  `style_overrides.md`. Those are owned by `academic-writing-skills`.
- Don't write to `.research/` — that's the workspace layer, not the
  paper layer.
- Don't extract claims from cited works — only from THIS paper.

## Anti-leakage rule (binding contract)

> A claim with empty or absent `evidence_artifacts` MUST have
> `status: gap` plus a one-line `gap_reason`. Never emit such a claim as
> `status: draft` or `status: supported`.

This is the contract that prevents an unsupported claim from leaking
into the downstream writing/audit pipeline as if it were evidenced.

How it manifests in normal use:

- The manuscript intro asserts something the experiment section never
  backs up → emit it as `status: gap` with a `gap_reason` like
  "intro claim with no matching E-run output". The writing skill then
  surfaces it as `[MATERIAL GAP]` rather than treating it as evidenced
  prose.
- A claim has evidence pointers but you're not yet sure they back it
  fully → still `status: draft`; document the doubt in `risk:` rather
  than emptying `evidence_artifacts`.
- A claim was dropped from the latest revision → keep the row,
  flip `status: rejected`; do not delete (audit trail).

The contract is enforced by `scripts/check_claims_schema.py` against
the JSON Schema at `references/claims.schema.json`. Run the validator
manually after editing `.paper/claims.yml` by hand:

```bash
python scripts/check_claims_schema.py <path-to-claims.yml>
```

## See also

- `references/yaml-schemas.md` — `.paper/claims.yml` and `.paper/figures.yml` schemas
- `references/revision_history_schema.md` — `.paper/revision_history.yml` schema + append-only audit-trail rules

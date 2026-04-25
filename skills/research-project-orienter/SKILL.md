---
name: research-project-orienter
description: Read the .research/ manifest files at a project root and produce a single orientation memo (research question, datasets, current stage, key entrypoints, evidence artifacts, open questions). Use when the user asks to "orient me in this project", "what is this repo about", or "build a context map for this paper" — and the project already has .research/ manifests (or trigger research-context-compressor first).
---

# research-project-orienter

Quickly orient an AI assistant inside a research workspace **without
scanning the whole repository**. Reads the `.research/` manifest files
written by `research-context-compressor` and produces a single
in-conversation orientation memo.

Part of the research-hub skill pack; works alongside Zotero, Obsidian,
and NotebookLM workflows but does not require any of them.

This skill is fast and read-only. If `.research/` doesn't exist yet,
defer to `research-context-compressor` first.

## When to use

Trigger phrases:

- "Understand this research project before helping me."
- "Summarize this repo's research question, data, experiments, and outputs."
- "Build a context map for this paper/project."
- "Orient me in this codebase."
- "What is this repo about?"

Not for:

- Detailed code review — that's a code task.
- Generating new manifests — use `research-context-compressor` first.
- Literature review — use `literature-triage-matrix`.

## Inputs

Read in this order:

1. `.research/project_manifest.yml` — top-level orientation. **Required.**
2. `.research/experiment_matrix.yml` — experiment status. Read if present.
3. `.research/data_dictionary.yml` — datasets. Read if present.
4. `.research/decisions.md` — recent ADRs. Read last 5 if present.
5. `.research/open_questions.md` — known unknowns. Read all.
6. `.research/run_log.md` — last 3 entries for context.

Do **not** read source code, data files, or PDFs unless the manifest
points you at a specific path AND the user's question requires it.

## What if `.research/` doesn't exist?

Tell the user:

> This project doesn't have a `.research/` manifest yet. I can create one
> first (loads `research-context-compressor` skill, takes ~30 seconds and
> writes 3 small YAML files), or I can fall back to scanning the repo
> directly (slower, more tokens). Which?

Don't auto-fall-back — ask first. If they pick "scan", read README.md +
`docs/` + the top-level entrypoint, and produce the memo from that, but
caveat: "this orientation came from a one-shot scan; for more reliable
future sessions, run `research-context-compressor` once."

## Output: orientation memo

Single message in this exact structure:

```
## Project orientation: <project_name>

**Research question**: <one sentence from manifest>

**Stage**: <current_stage>  ·  **Last updated**: <last_updated>

**Datasets** (<count>):
- `<id>`: <description>
- ...

**Experiments** (<count>, by status):
- <status>: <id> — <hypothesis (one line)>
- ...

**Main entrypoints**:
- `<path>` — <one-line purpose>
- ...

**Recent decisions** (<count>):
- <date>: <decision title>

**Open questions** (<count>):
- <question text>
- ...

**Evidence artifacts**:
- `<path>` — supports claim/figure
- ...

**Suggested next action**: <based on current_stage>
```

Length budget: ~200-400 tokens for typical project. Don't pad.

## Token-saving behavior

- The whole point of this skill is to save tokens. If you find yourself
  reading > 5 files outside `.research/`, stop and tell the user the
  manifest is incomplete — they should refresh with
  `research-context-compressor`.
- Cache-friendly: the orientation memo is identical between sessions if
  the manifests don't change. Future sessions can paste it back as
  context.

## What NOT to do

- Don't summarize the manuscript — `paper-memory-builder` does that.
- Don't compare papers — `literature-triage-matrix` does that.
- Don't propose code changes — that's a separate task.
- Don't invent missing fields. If `research_question` is empty in the
  manifest, say "no research question recorded; please add one to
  .research/project_manifest.yml" rather than guessing.
- Don't read PDFs in `data/` or `outputs/` unless directly asked.

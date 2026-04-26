---
name: research-context-compressor
description: Inspect a research repository and write a compact `.research/` workspace manifest (project_manifest.yml, experiment_matrix.yml, data_dictionary.yml) so future AI sessions can orient themselves without rescanning the whole repo. Use when the user asks to "compress this project context", "create a research manifest", or "save the project context for future agents".
---

# research-context-compressor

Build a compact, machine-readable workspace memory at the **project root**
under `.research/`. Other research-hub skills (project-orienter,
literature-triage-matrix, paper-memory-builder) read these files instead of
rescanning the repo every session, which is where the token savings come from.

This is the **foundation** skill. Run it once per project and refresh when
the project's research question, datasets, or experiment set changes.

## When to use

Trigger phrases:

- "Compress this project context for future agents."
- "Create a research manifest so future sessions don't reread everything."
- "Save the key project context before we continue."
- "Build a `.research/` folder for this repo."

Not for:

- Compressing source code or generating doc strings — that's a code task.
- Running experiments or analyzing results — those write to `outputs/`,
  not `.research/`.
- Writing the manuscript itself.

## Inputs you should read (priority order over inputs you may have)

This is a **priority list, not a requirements list**. Many research
projects don't have all of these — humanities work might be a folder of
PDFs + a single Markdown outline; an early-stage qualitative study might
just have field notes and a Zotero collection. Read whatever EXISTS in
the priority order below, skip the rest, and DON'T pad the manifest with
fields you can't substantiate from real artifacts.

1. `README.md` at the repo root — project overview, if present.
2. `pyproject.toml` / `package.json` / `requirements.txt` — primary tools, if a code project.
3. `docs/` directory — long-form descriptions, if present.
4. `scripts/` and `notebooks/` — main entrypoints, if a code project.
5. `data/` and `outputs/` directory listings — datasets and artifacts, if present.
6. `.git/HEAD` and `git log --oneline -20` — current branch and recent activity, if a git repo.
7. `.research/` (if it already exists) — for refresh, not first-time create.
8. **For humanities / qualitative projects** — substitute: a primary
   sources folder (PDFs / images / transcripts), an Obsidian vault, a
   Zotero collection. The manifest still applies; just leave
   `primary_tools / scripts / outputs` empty and put the source
   collection name in `data_sources` instead.

Skim, do not deep-read. The point is orientation, not analysis.

### Humanities use case example

A literary scholar studying 19th-century travel writing might have:
- 40 PDFs of primary sources in a single folder
- A Zotero collection of secondary literature
- One outline.md with their argument

The compressor should write `project_manifest.yml` like:

```yaml
project_name: "Travel writing in 19th-century Korea"
research_area: "Korean studies / comparative literature"
research_question: "How did Western travelers' framing of Korea shift after 1882?"
current_stage: "exploration"
primary_tools: []          # not a code project
key_repositories: []
data_sources:
  - id: "primary-pdfs"
    description: "40 travel-account PDFs (1850-1910)"
    location: "primary-sources/"
  - id: "zotero-secondary"
    description: "Secondary literature in Zotero collection 'Korea-1882'"
    location: "Zotero://collection/Korea-1882"
model_components: []       # no model
main_entrypoints: []
important_outputs: ["outline.md"]
paper_or_deliverable: "Journal article in Korean Studies, target 2027"
last_updated: "..."
```

Empty lists are honest signals, not gaps to fill.

## Outputs you must produce

Write these to `<project-root>/.research/`:

- `project_manifest.yml` — top-level orientation. **Required.**
- `experiment_matrix.yml` — per-experiment status. **Required if `scripts/` or `notebooks/` exist.**
- `data_dictionary.yml` — datasets and schemas. **Required if `data/` exists.**
- `run_log.md` — append a single entry recording this run.
- `decisions.md` — leave empty if no ADRs yet; do not invent decisions.
- `open_questions.md` — list any obvious unknowns you spotted (e.g.
  undocumented dataset, missing license, ambiguous entrypoint).

If a file already exists, **update don't replace**: keep human-edited
fields, fill in only the empty ones unless the user said "regenerate from
scratch".

## Schema reference

Full schema lives in
[docs/research-workspace-manifest.md](../../docs/research-workspace-manifest.md).
Quick reminder of `project_manifest.yml` required fields:

- `project_name`
- `research_area`
- `research_question`
- `current_stage` (one of `discovery / exploration / experiments / writing / rebuttal / submission`)
- `last_updated` (today's date in ISO format)

If you don't know a field, leave it empty (`""` or `[]`). Do **not** guess
research questions, hypotheses, or claims.

## Token-saving behavior

- Read manifest files first if they exist; only inspect code/data when the
  manifest doesn't already cover what you need.
- For large directories, list contents and pick representative entrypoints
  rather than reading every file.
- After running, tell the user: "Wrote `.research/project_manifest.yml`
  (and N other files). Future agents loading the `research-project-orienter`
  skill can now orient themselves without re-reading the whole repo."

## Output format for the user

After writing the files, print a 5-line summary:

```
[research-context-compressor]
  Wrote: .research/project_manifest.yml (3 datasets, 2 entrypoints)
  Wrote: .research/experiment_matrix.yml (2 experiments)
  Wrote: .research/data_dictionary.yml (3 datasets)
  Open questions surfaced: 2 — see .research/open_questions.md
  Refresh later: ask "compress this project context" again.
```

## What NOT to do

- Don't write to `.paper/` — that's `paper-memory-builder`'s job.
- Don't write `.research/literature_matrix.md` — that's
  `literature-triage-matrix`'s job.
- Don't write to `.research_hub/` — that's research-hub's internal cache,
  managed by the CLI.
- Don't invent fields not in the schema. Add a line to
  `.research/open_questions.md` instead.
- Don't overclaim: if the project has no clear research question yet, leave
  `research_question` empty and add a question to `open_questions.md`.

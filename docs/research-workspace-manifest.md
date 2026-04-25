# Research workspace manifest schema

This document defines the `.research/` and `.paper/` conventions that
research-hub's v0.66+ skills produce and consume.

The goal is a small set of structured files at the **project root** that
let an AI assistant orient itself in a research workspace without reading
the whole repository every session.

## Why this exists

Research projects accumulate context fast — datasets, experiment runs,
decisions, open questions, paper drafts. Asking an AI to "understand this
project" usually triggers a full repo scan that costs tokens and produces
inconsistent answers between sessions.

The `.research/` and `.paper/` directories give the project a single
"manifest layer" that:

- Captures the project state in a few small YAML files.
- Acts as the canonical entry point for any AI session: read the manifests
  first, only descend into code/data when needed.
- Lets later skills (literature triage, paper memory, NotebookLM
  verification) build on a shared context without redoing the orientation.

## Directory layout

```text
<project-root>/
  .research/                              # Project-level research context
    project_manifest.yml                  # Top-level orientation
    experiment_matrix.yml                 # All experiments + status
    data_dictionary.yml                   # Datasets + schemas
    run_log.md                            # Append-only run history
    decisions.md                          # ADR-style decision log
    open_questions.md                     # Unresolved questions
    literature_matrix.md                  # Output of literature-triage-matrix

  .paper/                                 # Manuscript-specific context
    journal_format.md                     # Journal style (owned by academic-writing-skills)
    claims.yml                            # Paper claims + supporting evidence
    figures.yml                           # Figure inventory + key numbers
    reviewer_comments.md                  # (owned by academic-writing-skills)
    style_overrides.md                    # (owned by academic-writing-skills)
```

## Ownership table

The same `.paper/` folder is shared with the existing
`academic-writing-skills` skill. To prevent stepping on each other:

| File | Owner | Producer | Consumer |
|---|---|---|---|
| `.research/project_manifest.yml` | research-hub | `research-context-compressor` | `research-project-orienter`, all other skills |
| `.research/experiment_matrix.yml` | research-hub | `research-context-compressor` | `research-project-orienter` |
| `.research/data_dictionary.yml` | research-hub | `research-context-compressor` | `research-project-orienter` |
| `.research/run_log.md` | shared | humans + skills append | humans + skills read |
| `.research/decisions.md` | shared | humans + skills append | humans + skills read |
| `.research/open_questions.md` | shared | humans + skills append | humans + skills read |
| `.research/literature_matrix.md` | research-hub | `literature-triage-matrix` | humans + writing skills |
| `.paper/journal_format.md` | `academic-writing-skills` | writing skill | writing skill |
| `.paper/claims.yml` | research-hub | `paper-memory-builder` | `academic-writing-skills` |
| `.paper/figures.yml` | research-hub | `paper-memory-builder` | `academic-writing-skills` |
| `.paper/reviewer_comments.md` | `academic-writing-skills` | writing skill | writing skill |
| `.paper/style_overrides.md` | `academic-writing-skills` | writing skill | writing skill |

If a future skill wants a new file under either folder, add a row here
first. Cross-skill files (run_log, decisions, open_questions) are append-only.

## Schema: `.research/project_manifest.yml`

Top-level orientation. Every `.research/` folder must have this file.

```yaml
project_name: "ABM-CAT flood adaptation coupling"
research_area: "civil & environmental engineering / hydrology"
research_question: |
  Does coupling agent-based behavioral adaptation with the CAT
  hydrodynamic model meaningfully change projected flood impact?
current_stage: "second-revision rebuttal"          # discovery | exploration | rebuttal | submission
primary_tools:
  - python
  - mesa
  - cat
key_repositories:
  - "https://github.com/yang-group/abm-cat"
data_sources:
  - id: "harvey-2017"
    description: "Hurricane Harvey flood depth grids (FEMA)"
    location: "data/harvey/"
  - id: "acs-2022"
    description: "ACS 5-year demographic data, Houston census tracts"
    location: "data/acs/"
model_components:
  - "ABM (mesa)"
  - "CAT hydrodynamic engine"
  - "coupling layer (Python)"
main_entrypoints:
  - "scripts/run_baseline.py"
  - "scripts/run_coupled.py"
  - "scripts/build_figures.py"
important_outputs:
  - "outputs/figures/Fig3_coupled_vs_baseline.png"
  - "outputs/tables/Table1_calibration.csv"
paper_or_deliverable: "JOH 2026 second revision"
last_updated: "2026-04-25"
```

**Required fields**: `project_name`, `research_area`, `research_question`,
`current_stage`, `last_updated`.

**Optional fields**: everything else. Empty list `[]` means "not applicable
yet". `current_stage` is free-form but conventionally one of
`discovery / exploration / experiments / writing / rebuttal / submission`.

## Schema: `.research/experiment_matrix.yml`

Tracks every experiment a project has run. Append-only by convention.

```yaml
experiments:
  - id: "E1-baseline"
    hypothesis: "ABM without behavioral adaptation matches FEMA depth grids."
    method: "baseline ABM run, no adaptation layer"
    inputs: ["data/harvey/", "config/baseline.yaml"]
    outputs: ["outputs/E1/"]
    status: "complete"                       # planned | running | complete | abandoned
    finding: "RMSE 0.42 m vs FEMA. Acceptable baseline."
    notes: "see decisions.md 2026-02-14"
  - id: "E2-coupled"
    hypothesis: "Coupling reduces RMSE by >15%."
    method: "ABM + CAT, daily exchange"
    inputs: ["data/harvey/", "config/coupled.yaml"]
    outputs: ["outputs/E2/"]
    status: "running"
    finding: ""
    notes: ""
```

**Required fields per row**: `id`, `hypothesis`, `status`.

## Schema: `.research/data_dictionary.yml`

Single source of truth for datasets the project uses.

```yaml
datasets:
  - id: "harvey-2017"
    description: "Hurricane Harvey flood depth grids"
    source: "FEMA flood maps + Harvey post-event survey"
    format: "GeoTIFF"
    units: "meters above local datum"
    location: "data/harvey/"
    license: "public domain"
    notes: "30 m resolution; downsampled to 90 m for ABM grid"
  - id: "acs-2022"
    description: "American Community Survey 5-year"
    source: "US Census Bureau"
    format: "CSV"
    units: "various; see column descriptions"
    location: "data/acs/"
    license: "public domain"
```

## Schema: `.research/run_log.md`

Append-only Markdown log. Each entry: timestamp + one-paragraph summary.
Skills MAY append; humans MAY append; nobody rewrites past entries.

```markdown
## 2026-04-25 (research-context-compressor)
Initial manifest generated. Detected 2 datasets, 2 entrypoints, 1 paper draft.

## 2026-04-26 (Wenyu)
Reviewed manifest, fixed dataset description for ACS, marked E2 as running.
```

## Schema: `.research/decisions.md`

ADR-style. Every architectural / methodological decision gets a heading.

```markdown
## 2026-02-14 — Use mesa over abmpy for ABM core

**Status**: accepted
**Context**: needed agent scheduler with built-in batch_run.
**Decision**: mesa 2.x.
**Consequences**: gives us batch_run + DataCollector for free; pinned to
mesa <3 because 3.0 changed Agent.unique_id semantics.
```

## Schema: `.research/open_questions.md`

Bullet list of unresolved questions. Skills SHOULD add when they detect a
gap; humans cross off as they resolve.

```markdown
- [ ] Calibration constant for CAT roughness — empirical literature varies 0.025–0.040
- [x] Whether to use ACS 1-year or 5-year — resolved 2026-03-10, picked 5-year for stability
- [ ] Reviewer comment R2.3 about boundary conditions still unaddressed
```

## Schema: `.research/literature_matrix.md`

Output of `literature-triage-matrix`. A markdown table comparing papers.

```markdown
| Citation | Question | Method | Data | Claim | Limitation | Relevance |
|---|---|---|---|---|---|---|
| Smith 2024 | Adaptation in flood ABMs | mesa-based ABM | Houston synthetic | Adaptation cuts loss 18% | Single basin | High — direct precedent |
```

## Schema: `.paper/claims.yml`

Used by `paper-memory-builder` (research-hub) and consumed by
`academic-writing-skills` for writing/revision passes.

```yaml
claims:
  - id: C1
    text: "Coupled ABM-CAT reduces flood-impact RMSE by 22%."
    evidence_artifacts:
      - "outputs/E2/calibration.csv"
      - "outputs/E2/figure3.png"
    figure_or_table: ["Fig3"]
    status: "draft"                          # draft | supported | rejected
    risk: "Reviewer R2 may push back on calibration window."
  - id: C2
    text: "Behavioral adaptation matters more in repeated-event basins."
    evidence_artifacts:
      - "outputs/E2/repeated_event_analysis.csv"
    figure_or_table: ["Fig5", "Table2"]
    status: "draft"
    risk: ""
```

**Required per claim**: `id`, `text`, `status`.

## Schema: `.paper/figures.yml`

```yaml
figures:
  - id: "Fig1"
    file: "outputs/figures/Fig1_study_area.png"
    panels: ["a) site map", "b) gauge locations"]
    key_numbers: ["12 gauges", "1985-2024 record length"]
    supports_claims: []                      # context figure
  - id: "Fig3"
    file: "outputs/figures/Fig3_coupled_vs_baseline.png"
    panels: ["a) baseline RMSE", "b) coupled RMSE", "c) difference map"]
    key_numbers: ["baseline 0.42 m", "coupled 0.33 m", "22% reduction"]
    supports_claims: ["C1"]
```

**Required per figure**: `id`, `file`, `supports_claims` (may be `[]`).

## Skill ↔ schema mapping

Which file does which skill read or write:

| Skill | Reads | Writes |
|---|---|---|
| `research-context-compressor` | repo files (README, code, data) | `.research/project_manifest.yml`, `.research/experiment_matrix.yml`, `.research/data_dictionary.yml` |
| `research-project-orienter` | all `.research/*.yml` | orientation memo (in-conversation, no file written by default) |
| `literature-triage-matrix` | Zotero/Obsidian/cluster notes | `.research/literature_matrix.md` |
| `paper-memory-builder` | manuscript + Obsidian notes | `.paper/claims.yml`, `.paper/figures.yml` |
| `notebooklm-brief-verifier` | NLM bundle manifest + downloaded brief | none (returns report in conversation) |

Skills that append (run_log, decisions, open_questions) MAY do so; the
schemas don't require it.

## Bootstrapping a new project

The fastest way is to ask an AI session that has `research-context-compressor`
loaded:

> Compress this project context for future agents.

The skill will inspect the repo, write the manifest files, and report what
it filled in vs what it left blank. You can then edit by hand.

If you want to start fully manually, copy the example blocks above and
replace the values.

## Versioning

The schemas above are **v1**. Forward-compatible additions (new optional
fields) are non-breaking. Renames or required-field changes will bump to
v2 and document migration in CHANGELOG.

## What goes elsewhere

These conventions deliberately don't cover:

- **Source-code structure or build config** — that's the project's own concern.
- **Citation databases** — Zotero is the source of truth; this manifest only
  references citations indirectly via the literature matrix.
- **Manuscript content** — the manuscript itself lives wherever the journal
  workflow expects (Word doc, LaTeX repo, etc.). `.paper/` only holds
  AI-readable companion structure.
- **Domain-specific governance, audit traces, or model-coupling contracts** —
  handled by the relevant model repository, not here.

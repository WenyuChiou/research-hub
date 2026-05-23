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
    design_brief.md                       # Output of research-design-helper (v0.68)

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
| `.research/design_brief.md` | research-hub | `research-design-helper` (v0.68; v0.3.12+ writes Stage 2 provenance to frontmatter) | `research-context-compressor` (v0.3.12+ reads frontmatter + section 1; copies `source` gap-id to manifest `provenance.from_gap`), `research-project-orienter` (cites), humans |
| `.paper/journal_format.md` | `academic-writing-skills` | writing skill | writing skill |
| `.paper/claims.yml` | research-hub | `paper-memory-builder` | `academic-writing-skills` |
| `.paper/figures.yml` | research-hub | `paper-memory-builder` | `academic-writing-skills` |
| `.paper/reviewer_comments.md` | `academic-writing-skills` | writing skill | writing skill |
| `.paper/style_overrides.md` | `academic-writing-skills` | writing skill | writing skill |

If a future skill wants a new file under either folder, add a row here
first. Cross-skill files (run_log, decisions, open_questions) are append-only.

## Schema: `.research/project_manifest.yml`

Top-level orientation. Every `.research/` folder must have this file.

The schema is **permissive**: writers may emit additional descriptive
fields beyond those listed here, and readers must treat unknown fields
as informational rather than erroring. Two field-naming conventions are
both accepted (the second is what `research-context-compressor` v0.6+
emits in practice; the first is the original 2025 spec, kept for
compatibility with older repos).

```yaml
project_name: "ABM-CAT flood adaptation coupling"
research_area: "civil & environmental engineering / hydrology"
research_question: |
  Does coupling agent-based behavioral adaptation with the CAT
  hydrodynamic model meaningfully change projected flood impact?
current_stage: "second-revision rebuttal"
last_updated: "2026-04-25"

# Optional: free-form description of what this repo IS
project_kind: "applied-modelling"          # applied-modelling | umbrella-catalog | survey | etc.
description: |
  Coupled ABM + hydrodynamic model for flood-impact projection under
  behavioral adaptation. Modelling work for JOH 2026 revision.

# Tools / runtime: prefer `tools` (current) or `primary_tools` (legacy alias)
tools:
  - python
  - mesa
  - cat
# primary_tools: [python, mesa, cat]      # legacy alias, still accepted

# Repos: prefer `canonical_repos[]` (current, with structure) or
# `key_repositories[]` (legacy, just URL list)
canonical_repos:
  - id: abm-cat
    url: "https://github.com/yang-group/abm-cat"
    owns: "ABM + CAT coupling layer"
# key_repositories: ["https://github.com/yang-group/abm-cat"]   # legacy alias

# Datasets: prefer `datasets[]` (current, with `name/path/schema/purpose`)
# or `data_sources[]` (legacy, with `id/description/location`)
datasets:
  - name: "harvey-2017"
    path: "data/harvey/"
    schema: "FEMA depth grids, GeoTIFF, 30 m → downsampled to 90 m"
    purpose: "calibration target for ABM baseline run"
  - name: "acs-2022"
    path: "data/acs/"
    schema: "ACS 5-year demographic, Houston census tracts (CSV)"
    purpose: "agent attribute distribution"
# data_sources: ...                        # legacy alias

# Entrypoints: prefer `entrypoints` (current, object) or
# `main_entrypoints` (legacy, list)
entrypoints:
  baseline_run: "scripts/run_baseline.py"
  coupled_run: "scripts/run_coupled.py"
  build_figures: "scripts/build_figures.py"
# main_entrypoints: [scripts/run_baseline.py, ...]   # legacy alias

# Outputs the user cares about
important_outputs:
  - "outputs/figures/Fig3_coupled_vs_baseline.png"
  - "outputs/tables/Table1_calibration.csv"

# Optional fields
model_components: ["ABM (mesa)", "CAT hydrodynamic engine", "coupling layer (Python)"]
paper_or_deliverable: "JOH 2026 second revision"
recent_activity:                            # `git log --oneline -10` output, optional
  - "abc1234 Refactor CAT coupling layer"
  - "def5678 Add Harvey calibration robustness check"

# Optional: Stage 2 → 3a provenance (written by research-context-compressor v0.3.12+)
# When .research/design_brief.md frontmatter carries
# `source: topic_dossier.gaps.yml#<gap-id>`, the compressor copies that
# pointer here so downstream tools (project-orienter, future audit
# scripts) can trace the manifest back to the gap-to-topic candidate
# it was framed for.
provenance:
  from_gap: "topic_dossier.gaps.yml#G2"     # gap-id (URI-fragment) from the chosen gap-to-topic candidate
```

**Required fields**: `project_name`, `research_area`, `research_question`,
`current_stage`, `last_updated`.

**Optional fields**: everything else. Empty list `[]` means "not applicable
yet". `current_stage` is free-form but conventionally one of
`discovery / exploration / experiments / writing / rebuttal / submission`.

**Field aliases**: writers may emit either current or legacy spelling
(both rows below are valid; readers accept either):

| Current (preferred) | Legacy alias | Notes |
|---|---|---|
| `tools` | `primary_tools` | flat list of tool names |
| `canonical_repos[]` | `key_repositories[]` | current adds structured `id/url/owns` per row |
| `datasets[]` | `data_sources[]` | current uses `name/path/schema/purpose`; legacy uses `id/description/location` |
| `entrypoints` (object map) | `main_entrypoints` (list) | current map allows symbolic keys (`baseline_run: scripts/...`) |

## Schema: `.research/experiment_matrix.yml`

Tracks every experiment OR verification run a project has executed.
Append-only by convention. Two row shapes are accepted: hypothesis-driven
experiment rows (modelling work) and verification rows (skill / tooling
validation). Pick whichever fits the project; mixing both shapes in one
matrix is also fine.

```yaml
experiments:
  # Hypothesis-driven experiment row
  - id: "E1-baseline"
    hypothesis: "ABM without behavioral adaptation matches FEMA depth grids."
    method: "baseline ABM run, no adaptation layer"
    inputs: ["data/harvey/", "config/baseline.yaml"]
    outputs: ["outputs/E1/"]
    status: "complete"
    finding: "RMSE 0.42 m vs FEMA. Acceptable baseline."
    notes: "see decisions.md 2026-02-14"

  # Verification row (e.g. skill smoke test, tooling validation)
  - id: "research-hub"
    status: "pass"
    tier: "T1"
    method: "doctor health check + search 'agent-based modeling' --limit 3"
    artifacts: "docs/verification.md (per-skill detail)"
    last_run: "2026-04-25"
```

**Required fields per row:** `id`, `status`.

**Optional fields:**

- `hypothesis` — include for hypothesis-driven rows; omit for verification rows.
- `method`, `inputs`, `outputs`, `finding`, `notes` — typical for experiment rows.
- `tier` (T1 / T2 / T3), `artifacts`, `last_run` (YYYY-MM-DD) — typical for verification rows.

**`status` enum:** `planned | running | complete | abandoned` for experiments;
`pass | caveat | pending | not_yet | fail` for verification runs. Readers
should treat any unknown value as informational rather than erroring.

## Schema: `.research/data_dictionary.yml`

Single source of truth for datasets the project uses. Two row shapes
are accepted (per-dataset). The current `research-context-compressor`
v0.6+ writer emits the **structured** form; the **descriptive** form
is the original 2025 spec, kept for compatibility with older repos.

```yaml
datasets:
  # Structured form (current writer output)
  - name: "harvey-2017"
    path: "data/harvey/"
    rows: "FEMA depth grid, ~12k cells after 90 m downsample"
    schema: "GeoTIFF, meters above local datum"
    purpose: "calibration target for ABM baseline run"

  # Descriptive form (legacy 2025 spec, still accepted)
  - id: "acs-2022"
    description: "American Community Survey 5-year"
    source: "US Census Bureau"
    format: "CSV"
    units: "various; see column descriptions"
    location: "data/acs/"
    license: "public domain"
    notes: "Houston census tracts only"
```

**Field aliases** (a row may use either set; mixing across rows is
also fine):

| Structured (current) | Descriptive (legacy) | Notes |
|---|---|---|
| `name` | `id` | dataset identifier |
| `path` | `location` | filesystem path or URL |
| `schema` | combine `format` + `units` + `notes` | concise machine-readable shape |
| `purpose` | `description` | why the project uses it |
| `rows` | — | optional row-count or unit-count summary |
| — | `source`, `license` | provenance metadata, descriptive form only |

Readers (e.g. `research-project-orienter`) must render either shape,
falling back to a `(no description)` placeholder if neither
`purpose` nor `description` is set.

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

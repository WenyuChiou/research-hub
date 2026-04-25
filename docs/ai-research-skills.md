# AI research skills index

research-hub ships a small set of skills that an AI assistant can load to
operate a research workspace. This page is the directory: which skill to
use when, what it reads, what it writes, and what it deliberately doesn't
cover.

## When to use which skill

| Situation | Skill | Effort |
|---|---|---|
| New repo, AI asked to "understand this project" | `research-context-compressor` then `research-project-orienter` | one-time setup |
| Project already has `.research/` manifests, just need orientation | `research-project-orienter` | seconds |
| Comparing 5–30 papers for a literature review | `literature-triage-matrix` | minutes |
| Preparing a manuscript for AI-assisted writing/revision | `paper-memory-builder` | minutes |
| Just downloaded a NotebookLM brief, want to verify it | `notebooklm-brief-verifier` | minutes |
| General research workflow (search → ingest → organize) | `research-hub` (the original CLI-operating skill) | continuous |
| Multi-AI handoff (Claude ↔ Codex ↔ Gemini) | `research-hub-multi-ai` | as needed |

## All packaged skills

### `research-hub`
The CLI-operating skill — drives `research-hub auto`, `import-folder`,
`zotero backfill`, `notebooklm bundle/upload/generate/download`, `dashboard`,
and maintenance commands. **Reads**: user intent + Zotero/Obsidian/NotebookLM
state. **Writes**: through the CLI; no direct file output.

Trigger phrases: "find papers about X", "ingest this folder", "build a
notebook for cluster X", "show me the dashboard".

### `research-hub-multi-ai`
Multi-AI delegation playbook. Tells Claude when to hand a task to Codex
(token-heavy code, batch edits) or Gemini (long CJK prose, summaries) and
how. **Reads**: nothing from disk. **Writes**: nothing.

Trigger phrases: "delegate this to Codex/Gemini", "this is a heavy task",
"who should write this section?".

### `research-context-compressor` (v0.66)
Inspects the repository and produces `.research/project_manifest.yml`,
`.research/experiment_matrix.yml`, `.research/data_dictionary.yml`. Future
sessions read these instead of rescanning the repo.

**Reads**: README, top-level docs, scripts, notebooks, data dirs.
**Writes**: `.research/*.yml` and an entry in `.research/run_log.md`.

Trigger phrases: "compress this project context for future agents",
"create a research manifest", "save the project context".

See: [research-workspace-manifest.md](research-workspace-manifest.md) for
the full schema.

### `research-project-orienter` (v0.66)
Reads the `.research/` manifests and produces a single orientation memo:
research question, datasets, current stage, key entrypoints, open
questions, where the live work is happening.

**Reads**: `.research/project_manifest.yml` and siblings.
**Writes**: nothing by default; the orientation memo lives in the
conversation.

Trigger phrases: "orient me in this project", "what is this repo about",
"build a context map for this paper".

### `literature-triage-matrix` (v0.66)
Turns a list of papers (Zotero collection, Obsidian cluster, manual list)
into a comparison matrix instead of generic per-paper summaries. Output is
a Markdown table at `.research/literature_matrix.md`.

**Reads**: Zotero metadata via local API or web API; Obsidian paper notes
under `raw/<cluster>/`; research-hub cluster manifests; NotebookLM
downloaded briefs if present.
**Writes**: `.research/literature_matrix.md`.

Trigger phrases: "make a literature matrix", "compare these papers by
method/data/limitations", "help me decide which papers are central".

### `paper-memory-builder` (v0.66)
Bridge between research-hub and `academic-writing-skills`. Reads the
manuscript (or Obsidian paper folder) plus relevant figures and
emits structured `.paper/claims.yml` and `.paper/figures.yml` so the
writing skill can do its work without re-reading the whole paper.

**Reads**: manuscript files; figure files; existing Obsidian notes about
the paper.
**Writes**: `.paper/claims.yml`, `.paper/figures.yml`.

Trigger phrases: "build paper memory for this manuscript", "extract the
claims and supporting evidence", "prepare this paper for AI-assisted
writing".

### `notebooklm-brief-verifier` (v0.66)
After `research-hub notebooklm download` produces a brief, this skill
verifies the brief faithfully reflects the source bundle research-hub
uploaded. Catches missed sources and unsupported claims.

**Reads**: `research-hub` bundle manifest, downloaded NotebookLM brief,
underlying source files only when needed for spot-checks.
**Writes**: nothing on disk; returns a structured report in the conversation
listing source coverage, missing sources, unsupported claims, contradictions,
and recommended follow-up prompts.

Trigger phrases: "verify this NotebookLM brief", "does the brief miss
anything", "compare the downloaded notes to the cluster papers".

## What these skills deliberately don't cover

The boundary is important enough to repeat from the brief
(`docs/research-hub-research-skills-brief.md`):

- **Domain-specific model governance, audit traces, or coupling contracts** —
  those live in the model repositories, not in the public research-hub skill
  pack.
- **Manuscript editing without research-workspace context** — handled by
  the standalone `academic-writing-skills` skill.
- **Full Zotero CRUD** — handled by the standalone `zotero-skills` repo.
  research-hub's Zotero integration is the lightweight, pipeline-aware
  half (tags, notes, collection sync); deep CRUD (item-level edit, batch
  rename, tag merge) belongs elsewhere.

## Installation

All packaged skills install together:

```bash
research-hub install --platform claude-code
research-hub install --platform cursor
research-hub install --platform codex
research-hub install --platform gemini
```

Each platform gets every skill under its respective skills directory
(`~/.claude/skills/<name>/SKILL.md`, `~/.cursor/skills/<name>/SKILL.md`,
etc). `research-hub install --list` shows install status per platform.

## Combinations that work well

- **Cold start a new repo** — load `research-context-compressor`, then
  `research-project-orienter` in the same session. Compressor writes
  manifests, orienter immediately reads them and gives a memo.
- **Literature review** — load `research-context-compressor` first so
  the project knows its own scope, then `literature-triage-matrix` to
  pull in candidate papers and produce the matrix.
- **Pre-submission check** — load `paper-memory-builder` to extract
  claims, then call `academic-writing-skills` to do the audit / banned
  word / mechanism-for-every-result checks.
- **Post-NLM-run sanity check** — after `research-hub notebooklm
  generate brief && download brief`, load `notebooklm-brief-verifier`
  to confirm coverage before sharing the brief with collaborators.

## Versioning

These skills are versioned alongside the research-hub package. v0.66
adds `research-context-compressor`, `research-project-orienter`,
`literature-triage-matrix`, `paper-memory-builder`, and
`notebooklm-brief-verifier`. Future versions may add `zotero-library-curator`
once we confirm it doesn't duplicate the standalone `zotero-skills` repo.

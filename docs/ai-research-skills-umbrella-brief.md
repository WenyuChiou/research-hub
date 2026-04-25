# AI Research Skills Umbrella Brief

This brief proposes a public-facing umbrella package for sharing the user's academic, research-workflow, and AI-application skills as one coherent ecosystem.

## Executive Decision

Create an umbrella project, tentatively named `ai-research-skills`, that acts as a catalog and installer hub for the user's research skills. It should not replace the existing repositories. It should route users to the right skill pack.

The umbrella should answer:

- I am a researcher. Which skills should I install?
- I use Zotero, Obsidian, or NotebookLM. What helps me?
- I am writing or revising a paper. What helps me?
- I want multi-model AI assistance with Claude, Codex, or Gemini. What helps me?

## Recommended Product Architecture

Keep three first-phase layers:

### 1. Research Workspace Layer

Primary repo: `research-hub`

Owns:

- Literature triage.
- Zotero/Obsidian/NotebookLM handoffs.
- Research context compression.
- Paper memory files.
- NotebookLM brief verification.

Audience:

- Researchers managing many papers and notes.
- Students building literature review workflows.
- AI assistant users who want a local-first research memory layer.

### 2. Academic Writing Layer

Primary repo: `academic-writing-skills`

Owns:

- Manuscript structure.
- Journal format compliance.
- Reviewer response workflows.
- Claim/evidence/figure consistency.
- Banned GPT-style and overclaim language checks.
- Submission checklist.

Audience:

- Graduate students and researchers writing papers.
- Users who may not use `research-hub`.

### 3. Multi-Model AI Workflow Layer

Primary repos:

- `codex-delegate`
- `gemini-delegate-skill`

Owns:

- Delegating implementation-heavy tasks to Codex.
- Delegating large-context synthesis and bilingual writing to Gemini.
- Keeping Claude as planner, reviewer, and acceptance gate.

Audience:

- Power users who want AI-agent orchestration across models.

## Umbrella Repository Scope

Suggested repo name:

```text
ai-research-skills
```

This repo should contain:

```text
ai-research-skills/
  README.md
  LICENSE
  packs/
    research-workspace-pack.md
    academic-writing-pack.md
    multi-model-ai-pack.md
    full-researcher-pack.md
  catalog/
    skills.yml
    repos.yml
  docs/
    choosing-a-pack.md
    installation.md
    examples.md
    compatibility.md
```

Avoid copying full skill bodies at first. Link to the canonical repositories. Copying too early creates version drift.

## Public Pack Definitions

### Pack A: Research Workspace Pack

For users who manage literature, notes, and AI-readable research memory.

Includes:

- `research-hub`
- `research-context-compressor`
- `research-project-orienter`
- `literature-triage-matrix`
- `paper-memory-builder`
- `notebooklm-brief-verifier`
- `zotero-library-curator`

Best for:

- Zotero + Obsidian.
- Obsidian + NotebookLM.
- Zotero + NotebookLM.
- All three together.

### Pack B: Academic Writing Pack

For users writing, revising, or submitting manuscripts.

Includes:

- `academic-writing-skills`
- `claim-evidence-auditor`
- `reviewer-response-builder`
- `journal-format-capture`
- `figure-caption-auditor`

Best for:

- Paper drafts.
- Reviewer responses.
- Submission preparation.
- Figure/prose consistency.

### Pack C: Multi-Model AI Pack

For users who want Claude, Codex, and Gemini to cooperate.

Includes:

- `codex-delegate`
- `gemini-delegate-skill`

Best for:

- Claude as supervisor.
- Codex for implementation-heavy coding.
- Gemini for long-context synthesis and bilingual/CJK drafting.

### Pack D: Full Researcher Pack

For power users.

Includes:

- Research Workspace Pack.
- Academic Writing Pack.
- Multi-Model AI Pack.

## Skills That Should Be Created Or Improved

### Existing skills to improve

`academic-writing-skills`:

- Add eval prompts.
- Add reviewer-response workflow.
- Add claim/evidence/figure audit workflow.
- Add sample `.paper/` folder.
- Add tests checking frontmatter and reference availability.

`zotero-skills`:

- Clarify boundary with `research-hub`.
- Keep full CRUD here.
- Let `research-hub` include only curation/backfill workflows.

`gemini-delegate-skill`:

- Keep English, zh-TW, and bilingual support explicit.
- Add examples for academic synthesis and reviewer-response drafting.

`codex-delegate`:

- Keep as implementation specialist.
- Add examples for research repo cleanup, tests, and reproducibility packaging.

### New general academic skills

`claim-evidence-auditor`:

- Checks whether each manuscript claim is supported by figures, tables, outputs, or citations.
- Should live in `academic-writing-skills` or the umbrella pack.

`reviewer-response-builder`:

- Converts reviewer comments into a response table, manuscript edit plan, and rebuttal letter draft.
- Should live in `academic-writing-skills`.

`journal-format-capture`:

- Creates `.paper/journal_format.md`.
- Could live in `academic-writing-skills`.

`figure-caption-auditor`:

- Checks figure captions, panel labels, key numbers, and prose references.
- Could live in `academic-writing-skills`.

`research-project-orienter`:

- Should live in `research-hub`.

`research-context-compressor`:

- Should live in `research-hub`.

`literature-triage-matrix`:

- Should live in `research-hub`.

## Token-Saving Design Standard

Every skill should prefer small durable context files before large source files.

Recommended shared conventions:

```text
.research/
  project_manifest.yml
  experiment_matrix.yml
  data_dictionary.yml
  run_log.md
  decisions.md
  open_questions.md

.paper/
  journal_format.md
  claims.yml
  figures.yml
  reviewer_comments.md
  style_overrides.md
```

Rule:

1. Read `.research/` and `.paper/` first.
2. Only inspect raw source files when the manifest is missing or points to a specific artifact.
3. Update manifests after major discoveries.
4. Prefer stable IDs for claims, figures, experiments, papers, and outputs.

This is the main value proposition: skills reduce repeated context loading and make AI sessions more reliable.

## Public Positioning

Suggested tagline:

```text
AI research skills for literature, writing, research memory, and multi-model AI workflows.
```

Short description:

```text
A curated set of skills and tools for researchers using AI assistants across the academic workflow: reading papers, managing Zotero/Obsidian/NotebookLM workspaces, writing manuscripts, preserving reusable research context, and coordinating Claude, Codex, and Gemini.
```

Avoid positioning it as "one giant framework." It should be a catalog of focused packs.

## Recommended README Structure

```markdown
# AI Research Skills

## Choose Your Pack

| If you want to... | Install this |
|---|---|
| Manage papers and notes | Research Workspace Pack |
| Write or revise manuscripts | Academic Writing Pack |
| Use Claude + Codex + Gemini together | Multi-Model AI Pack |
| Use everything | Full Researcher Pack |

## Quick Start

## Packs

## Skill Catalog

## Token-Saving Conventions

## Compatibility

## Roadmap
```

## Implementation Recommendation

Phase 1:

- Create the umbrella repo with catalog only.
- Do not duplicate skill bodies.
- Link to current canonical repos.
- Add pack docs and installation instructions.

Phase 2:

- Improve `academic-writing-skills`.
- Add research-hub research workspace skills.

Phase 3:

- Add automated packaging or installer scripts.
- Add trigger evals for each skill description.
- Add example workspaces.

## Acceptance Criteria

The umbrella project is ready when:

- A new researcher can choose a pack in under 60 seconds.
- Each pack links to real installable repos.
- The README clearly explains what belongs where.
- No skill exists in two canonical locations.
- The shared `.research/` and `.paper/` conventions are documented.
- Specialized domain frameworks can be linked later without blocking the first public launch.

## Suggested Next Actions For Claude Code

1. Create or update `academic-writing-skills` with evals and reviewer-response support.
2. Create the umbrella repo skeleton: `ai-research-skills`.
3. Add `catalog/skills.yml` and `catalog/repos.yml`.
4. Add pack documentation.
5. Add links to `research-hub`, `academic-writing-skills`, `zotero-skills`, `codex-delegate`, and `gemini-delegate-skill`.
6. Do not move canonical skill bodies until versioning and packaging are decided.

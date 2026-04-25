# Research-Hub Research Skills Integration Brief

This brief defines the recommended `research-hub` scope for academic and AI-research skills. It is intended as an implementation handoff for Claude Code.

## Executive Decision

`research-hub` should become the AI-operable research workspace layer. It should own skills that help an AI assistant understand a research workspace, triage literature, compress context, build reusable research memory, and verify NotebookLM or Zotero handoffs.

Do not put WAGF-specific governance, domain-pack, audit-trace, or ABM-model-coupling skills here. Those belong in WAGF. `research-hub` should stay useful to researchers even if they do not use WAGF.

## Product Boundary

Put a skill in `research-hub` if it depends on at least one of:

- Zotero metadata, collections, tags, notes, or citation records.
- Obsidian Markdown vaults, paper notes, clusters, Bases dashboards, or crystals.
- NotebookLM bundles, generated briefs, downloaded notes, or source handoff verification.
- Local research workspace manifests under `.research/` or `.paper/`.
- Repeated context compression for literature and project-orientation workflows.

Do not put a skill in `research-hub` if it primarily depends on:

- WAGF `skill_registry.yaml`, `agent_types.yaml`, `lifecycle_hooks.py`, or governance modes.
- LLM-agent simulation audit traces such as rejection rate, retry rate, or logic-action gap.
- ABM/CAT/hydrology/seismic model coupling contracts.
- Manuscript-only editing without any research-workspace context.

Those should live in WAGF, FLOODABM/Cat_framework, or `academic-writing-skills`.

## Recommended Skills For Research-Hub

### 1. `research-project-orienter`

Purpose: quickly orient an AI assistant inside a research workspace without scanning the whole repository.

Trigger examples:

- "Understand this research project before helping me."
- "Summarize this repo's research question, data, experiments, and outputs."
- "Build a context map for this paper/project."

Inputs to prioritize:

- `.research/project_manifest.yml`
- `.research/experiment_matrix.yml`
- `.research/data_dictionary.yml`
- `.research/run_log.md`
- `README.md`
- `docs/`
- `paper/`
- `notebooks/`
- `outputs/`

Output:

- Research objective.
- Core datasets.
- Model or method summary.
- Experiment matrix.
- Main entrypoints and commands.
- Current evidence artifacts.
- Open questions and risks.

Token-saving behavior:

- Read manifest files first.
- Only inspect code or large output folders when the manifest points to them.
- Produce an orientation memo that later agents can reuse.

### 2. `literature-triage-matrix`

Purpose: turn literature sources into a compact comparison matrix rather than generic summaries.

Trigger examples:

- "Make a literature matrix for these papers."
- "Compare these papers by method, data, claims, and limitations."
- "Help me decide which papers are central to my review."

Inputs:

- Zotero export or search results.
- Obsidian paper notes.
- `research-hub` cluster notes.
- NotebookLM downloaded briefs.
- Local PDF/DOCX/MD/TXT sources already imported by `research-hub`.

Output columns:

- Citation key or short reference.
- Research question.
- Method/model.
- Data and study area.
- Main claim.
- Evidence type.
- Limitations.
- Relevance to current project.
- How to cite or use it.

Token-saving behavior:

- Prefer existing paper notes and metadata before raw PDFs.
- Store reusable matrix output under `.research/literature_matrix.md` or the vault cluster.
- Use stable paper identifiers so future calls can reference rows instead of rereading papers.

### 3. `research-context-compressor`

Purpose: build a compact machine-readable project memory for future AI sessions.

Trigger examples:

- "Compress this project context for future agents."
- "Create a research manifest so future sessions don't need to reread everything."
- "Save the key project context before we continue."

Outputs:

```text
.research/
  project_manifest.yml
  experiment_matrix.yml
  data_dictionary.yml
  run_log.md
  decisions.md
  open_questions.md
```

Minimum `project_manifest.yml` fields:

```yaml
project_name: ""
research_area: ""
research_question: ""
current_stage: ""
primary_tools: []
key_repositories: []
data_sources: []
model_components: []
main_entrypoints: []
important_outputs: []
paper_or_deliverable: ""
last_updated: ""
```

Token-saving behavior:

- This is the core skill for reducing repeated context loading.
- Future skills should read `.research/project_manifest.yml` before scanning the repo.
- If source files are large, summarize them once and link to paths.

### 4. `paper-memory-builder`

Purpose: convert paper notes, figures, claims, quotes, and Zotero metadata into a reusable paper memory layer.

Trigger examples:

- "Build paper memory for this manuscript."
- "Extract claims, figures, and evidence from this paper folder."
- "Prepare reusable memory for writing and revision."

Outputs:

```text
.paper/
  journal_format.md
  claims.yml
  figures.yml
  reviewer_comments.md
  style_overrides.md
```

Minimum `claims.yml` fields:

```yaml
claims:
  - id: C1
    text: ""
    evidence_artifacts: []
    figure_or_table: []
    status: draft
    risk: ""
```

Minimum `figures.yml` fields:

```yaml
figures:
  - id: Fig1
    file: ""
    panels: []
    key_numbers: []
    supports_claims: []
```

Token-saving behavior:

- Later writing skills can read `claims.yml` and `figures.yml` instead of rereading the manuscript.
- This should bridge `research-hub` and `academic-writing-skills`, but not replace the writing skill.

### 5. `notebooklm-brief-verifier`

Purpose: verify that a NotebookLM brief or downloaded note faithfully reflects the sources selected by `research-hub`.

Trigger examples:

- "Check this NotebookLM brief against the source bundle."
- "Verify whether NotebookLM missed or hallucinated anything important."
- "Compare downloaded NotebookLM notes to the cluster papers."

Inputs:

- `research-hub` bundle manifest.
- NotebookLM downloaded brief.
- Obsidian cluster notes.
- Zotero metadata.

Output:

- Source coverage summary.
- Missing sources.
- Unsupported claims.
- Contradictions or overstatements.
- Recommended follow-up prompts for NotebookLM.

Token-saving behavior:

- Compare against bundle manifest and note metadata first.
- Only open full source files for suspicious claims.

### 6. `zotero-library-curator`

Purpose: provide a lightweight, research-hub-native Zotero curation layer.

Trigger examples:

- "Clean up Zotero tags for this cluster."
- "Find duplicate or misclassified papers."
- "Backfill research-hub tags and notes."

Scope:

- Prefer integrating common `zotero-skills` behavior rather than duplicating the full standalone CRUD skill.
- Keep advanced Zotero CRUD in the separate `zotero-skills` repository.

Output:

- Preview-first cleanup plan.
- Tag/collection backfill plan.
- Duplicate/missing metadata report.
- Optional apply step through existing `research-hub zotero` commands.

## Recommended Repository Structure

Add new skills under:

```text
skills/
  research-project-orienter/
    SKILL.md
    evals/evals.json
  literature-triage-matrix/
    SKILL.md
    evals/evals.json
  research-context-compressor/
    SKILL.md
    evals/evals.json
  paper-memory-builder/
    SKILL.md
    evals/evals.json
  notebooklm-brief-verifier/
    SKILL.md
    evals/evals.json
  zotero-library-curator/
    SKILL.md
    evals/evals.json
```

Mirror packaged skill copies under:

```text
src/research_hub/skills_data/
  research-project-orienter/
  literature-triage-matrix/
  research-context-compressor/
  paper-memory-builder/
  notebooklm-brief-verifier/
  zotero-library-curator/
```

If the installer currently hardcodes skill names, update it to discover bundled skill directories automatically or add these names explicitly.

## Documentation To Add

Add:

```text
docs/research-workspace-manifest.md
docs/ai-research-skills.md
```

`docs/research-workspace-manifest.md` should document:

- `.research/` schema.
- `.paper/` schema.
- How skills use these files to save tokens.
- How to regenerate or update them.

`docs/ai-research-skills.md` should document:

- Which skill to use for each workflow.
- How they interact with Zotero, Obsidian, and NotebookLM.
- Which workflows belong outside `research-hub`.

Add README links only after the skill files and tests exist.

## Suggested CLI Extensions

Phase 1 can be skills-only. Do not block on new CLI commands.

Phase 2 can add:

```bash
research-hub context init
research-hub context audit
research-hub context compress
research-hub paper-memory init
research-hub paper-memory audit
```

These commands should be preview-first. Any write operation should show target paths and require an apply flag unless it is purely creating empty templates.

## Testing Requirements

Add tests for:

- Bundled skill availability.
- Packaged skill copies match root skill copies.
- No stale or mojibake text in bundled skills.
- All new skills include frontmatter with `name` and `description`.
- All new skills include at least 3 realistic eval prompts.
- Installer can install the new skills for Codex/Gemini/Claude/Cursor paths if those platforms are supported.

Recommended test file:

```text
tests/test_research_skills_packaging.py
```

Minimum assertions:

- Every skill under `skills/` has a matching copy under `src/research_hub/skills_data/`.
- `SKILL.md` contents match or differ only by intentional generated metadata.
- No skill references invalid commands.
- Research-hub README or docs do not claim skills exist before files exist.

Run:

```bash
python -m pytest tests/test_skill_installer.py tests/test_research_skills_packaging.py -q
python -m pytest tests/test_consistency.py tests/test_onboarding_ux.py -q
```

## Acceptance Criteria

Claude Code should consider the research-hub part complete when:

- The new skill set is present and installable.
- `.research/` and `.paper/` manifest conventions are documented.
- The skill installer packages the new skills correctly.
- Tests verify root skills and packaged copies stay synchronized.
- README points to the skills without overclaiming.
- No WAGF-specific domain-pack or governance-analysis logic has been added to `research-hub`.

## Recommended Implementation Order

1. Add `docs/research-workspace-manifest.md`.
2. Add `docs/ai-research-skills.md`.
3. Add `research-context-compressor` first, because other skills depend on `.research/`.
4. Add `research-project-orienter`.
5. Add `literature-triage-matrix`.
6. Add `paper-memory-builder`.
7. Add `notebooklm-brief-verifier`.
8. Add `zotero-library-curator` only after confirming it does not duplicate the standalone `zotero-skills` repo.
9. Update installer packaging.
10. Add packaging and consistency tests.

## Explicit Non-Goals

- Do not implement WAGF domain-pack generation here.
- Do not analyze WAGF audit traces here.
- Do not add ABM/CAT coupling contracts here.
- Do not turn `research-hub` into a manuscript-writing package.
- Do not require Zotero, Obsidian, and NotebookLM all at once.

The public message should remain: use any two of Zotero, Obsidian, and NotebookLM, or all three if available.

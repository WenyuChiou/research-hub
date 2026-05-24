---
name: research-hub
description: Operate research-hub workflows for literature discovery, source ingest into Zotero/Obsidian/NotebookLM, dashboard inspection, and vault maintenance. Use when the user asks to find papers and organize them, build a knowledge base, ingest a folder of PDFs, upload to NotebookLM, generate research briefs, inspect clusters, or maintain a research vault. NOT for auditing or cleaning up an existing Zotero library — that's `zotero-library-curator` (read-only audit) plus `zotero-skills` (for CRUD).
---

# research-hub

research-hub turns Zotero, Obsidian, and NotebookLM into an AI-operable research workspace. It works best with any two of the three tools, and unlocks the full loop when all three are connected.

## Runtime contract (do this first)

This is a runtime-backed skill. The `SKILL.md` instructions teach the
AI workflow, but the actual search, Zotero writes, Obsidian vault
updates, NotebookLM bundle/upload/download, dashboard, and MCP tools
come from the `research-hub` Python CLI.

Before running any workflow command from this skill, check the runtime:

```bash
research-hub describe --json
research-hub doctor
```

If `research-hub` is **not found**, the host has loaded the skill
instructions but the executable runtime is missing. This can happen
after a marketplace/manual skill install without the Python package.
Stop and tell them:

> This skill needs the `research-hub` CLI. Please run:
>
> ```bash
> pip install research-hub-pipeline
> research-hub setup --persona researcher   # or analyst | humanities | internal
> ```
>
> Then re-run your request. If you only need to compare papers, sharpen
> a research question, or build a project / paper memory file (no
> automated search, no NotebookLM upload), a lightweight prompt-only
> skill may be enough; this workflow needs the CLI for tool execution.

If `doctor` runs but reports missing Zotero credentials, missing
NotebookLM auth, or no supported LLM CLI, adapt instead of pretending
the full path is ready:

- Missing Zotero: use `import-folder`, sample/dashboard mode, or ask
  the user to set `ZOTERO_API_KEY` / `ZOTERO_LIBRARY_ID`.
- Missing NotebookLM auth: run the first search with `--no-nlm`, then
  ask the user to complete `research-hub notebooklm login --auto-detect`.
- Missing LLM CLI for the relevance judge: either install/configure a
  supported CLI (`claude`, `codex`, `gemini`, `opencode`, `aichat`,
  `cursor`, or a custom adapter) or add `--no-fit-check` and clearly
  state that relevance filtering was skipped.

Do **not** invent or simulate `research-hub` output if the CLI is
missing.

Default language policy: answer the user in their language. Generate durable research notes, metadata, and citations in English unless the user explicitly asks for another language.

## Agent preflight protocol

For AI hosts such as Claude Code, Codex, Gemini CLI, Cursor, OpenClaw,
Hermes, or generic API clients, use this sequence unless the user gives
a narrower command:

1. Capability check:

   ```bash
   research-hub describe --json
   research-hub doctor
   ```

2. First safe literature run, without NotebookLM:

   ```bash
   research-hub auto "TOPIC" --max-papers 3 --no-nlm
   ```

3. If the run stops before search because no relevance judge is on
   PATH, choose one of these explicit paths:

   ```bash
   research-hub auto "TOPIC" --max-papers 3 --no-nlm --no-fit-check
   research-hub auto "TOPIC" --max-papers 3 --no-nlm --llm-cli codex
   research-hub auto "TOPIC" --max-papers 3 --no-nlm --llm-cli gemini
   ```

4. Add NotebookLM only after the local Zotero/Obsidian path works:

   ```bash
   research-hub notebooklm login --auto-detect
   research-hub notebooklm bundle --cluster <slug>
   research-hub notebooklm upload --cluster <slug>
   research-hub notebooklm generate --cluster <slug> --type brief
   research-hub notebooklm download --cluster <slug>
   ```

5. For machine-readable automation, prefer commands with `--json` when
   available, or use the MCP/REST surfaces exposed by `research-hub serve`.

This protocol is intentionally staged: verify runtime first, ingest a
small cluster second, then add browser-dependent NotebookLM work last.

## Pick The Right Entry Point

| User setup | Recommended path |
|---|---|
| Zotero + Obsidian + NotebookLM | `research-hub auto "topic"` |
| Zotero + Obsidian only | `research-hub auto "topic" --no-nlm`, `zotero backfill`, Obsidian dashboard output |
| Obsidian + NotebookLM only | `research-hub import-folder <folder> --cluster <slug>`, then NotebookLM bundle/upload |
| Zotero + NotebookLM only | Zotero-backed search and NotebookLM operations |
| No accounts yet | `research-hub dashboard --sample` |

## Setup Commands

```bash
pip install research-hub-pipeline[playwright,secrets]
research-hub setup
research-hub doctor
```

For local files without Zotero:

```bash
pip install research-hub-pipeline[import,secrets]
research-hub setup --persona analyst
research-hub import-folder ./papers --cluster my-local-review
```

## Core Workflows

### Preview

```bash
research-hub dashboard --sample
```

### Research Topic

```bash
research-hub plan "TOPIC"
research-hub auto "TOPIC" --no-nlm
research-hub serve --dashboard
```

Use `--no-nlm` for first-run smoke tests or when NotebookLM browser automation is not configured.

### Discover (search + AI fit-check)

Two-phase interactive flow when you want a human / AI in the loop on which papers actually belong in a cluster. Replaces the `auto` one-shot ingest when topic boundaries are fuzzy.

```bash
research-hub discover new --cluster project-topic --query "agent-based modeling flood adaptation"
# → emits search results + a fit-check scoring prompt; stashes state

# Run the fit-check prompt through your AI of choice, paste the scores back
research-hub discover continue --cluster project-topic --scores scores.json
# → applies scores, emits papers_input.json for ingest
```

`research-hub fit-check {emit|apply|audit|drift}` exposes the underlying gates separately when you want to re-score an existing cluster or audit drift over time. `discover variants` emits a query-variation prompt to widen recall before fit-check narrows it.

### Local Source Folder

```bash
research-hub import-folder ./sources --cluster project-topic
research-hub serve --dashboard
research-hub crystal emit --cluster project-topic
```

### NotebookLM

```bash
research-hub notebooklm login --auto-detect
research-hub notebooklm bundle --cluster project-topic
research-hub notebooklm upload --cluster project-topic
research-hub notebooklm generate --cluster project-topic --type brief
research-hub notebooklm download --cluster project-topic
```

### Synthesize cluster pages

Generate or refresh per-cluster synthesis pages in the Obsidian vault (uses cluster memory + paper summaries to produce a navigable overview note).

```bash
research-hub synthesize --cluster project-topic
research-hub synthesize --cluster project-topic --graph-colors  # also paint the graph view
```

Run `synthesize` after `paper-summarize` has filled the per-paper notes; the synthesis page reads from those.

### Cluster memory

Maintain a structured memory registry per cluster — durable notes the AI can reload across sessions without re-reading every paper.

```bash
research-hub memory list --cluster project-topic
research-hub memory read --cluster project-topic
research-hub memory emit --cluster project-topic   # AI extraction prompt
research-hub memory apply --cluster project-topic --payload memory.json
```

Use `memory emit/apply` to refresh the registry after a major round of new papers; use `read` from another session to reload context cheaply.

### Maintenance

```bash
research-hub doctor --autofix
research-hub tidy
research-hub clusters rebind --emit
research-hub cleanup --all
```

## MCP Integration

For MCP hosts:

```json
{ "mcpServers": { "research-hub": { "command": "research-hub", "args": ["serve"] } } }
```

Install host-specific files for hosts with known default skill directories:

```bash
research-hub install --platform claude-code
research-hub install --platform cursor
research-hub install --platform codex
research-hub install --platform gemini
```

For Hermes, OpenClaw, or other hosts with `SKILL.md`/rules support,
copy the relevant `skills/<name>/` directories manually or inline this
file into the host's instructions. Use MCP/REST for tool calls when no
installer target exists.

## Guardrails

- Do not assume installing `ai-research-skills` or copying `SKILL.md`
  installed the `research-hub` CLI; check the runtime explicitly.
- Always run `research-hub doctor` when setup state is uncertain.
- Do not invent DOIs, citations, or paper metadata; use search/enrich/verify commands.
- Do not delete clusters without reviewing cascade impact.
- Treat the vault as user-owned local data; avoid overwriting notes unless asked.
- Prefer `import-folder` for non-academic or internal documents.
- Prefer Zotero-backed workflows for DOI/arXiv-heavy academic literature.

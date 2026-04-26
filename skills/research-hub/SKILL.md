---
name: research-hub
description: Operate research-hub workflows for literature discovery, source ingest, Zotero/Obsidian/NotebookLM organization, dashboard inspection, and vault maintenance. Use when the user asks to find papers, build a knowledge base, organize references, upload to NotebookLM, generate research briefs, inspect clusters, or maintain a research vault.
---

# research-hub

research-hub turns Zotero, Obsidian, and NotebookLM into an AI-operable research workspace. It works best with any two of the three tools, and unlocks the full loop when all three are connected.

## Prerequisite check (do this first)

This skill drives the `research-hub` Python CLI. Before running any
command from this skill, verify the CLI is installed:

```bash
research-hub --version
```

If that command is **not found**, the user installed only the Claude
Code marketplace plugin and is missing the Python CLI. Stop and tell
them:

> This skill needs the `research-hub` CLI. Please run:
>
> ```bash
> pip install research-hub-pipeline
> research-hub setup --persona researcher   # or analyst | humanities | internal
> ```
>
> Then re-run your request. If you only need to compare papers, sharpen
> a research question, or build a project / paper memory file (no
> automated search, no NotebookLM upload), the marketplace install
> alone is enough — you don't need this skill for those.

Do **not** invent or simulate `research-hub` output if the CLI is
missing.

Default language policy: answer the user in their language. Generate durable research notes, metadata, and citations in English unless the user explicitly asks for another language.

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

### Local Source Folder

```bash
research-hub import-folder ./sources --cluster project-topic
research-hub serve --dashboard
research-hub crystal emit --cluster project-topic
```

### NotebookLM

```bash
research-hub notebooklm login
research-hub notebooklm bundle --cluster project-topic
research-hub notebooklm upload --cluster project-topic
research-hub notebooklm generate --cluster project-topic --type brief
research-hub notebooklm download --cluster project-topic
```

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

Install host-specific files:

```bash
research-hub install --platform claude-code
research-hub install --platform cursor
research-hub install --platform codex
research-hub install --platform gemini
```

## Guardrails

- Always run `research-hub doctor` when setup state is uncertain.
- Do not invent DOIs, citations, or paper metadata; use search/enrich/verify commands.
- Do not delete clusters without reviewing cascade impact.
- Treat the vault as user-owned local data; avoid overwriting notes unless asked.
- Prefer `import-folder` for non-academic or internal documents.
- Prefer Zotero-backed workflows for DOI/arXiv-heavy academic literature.

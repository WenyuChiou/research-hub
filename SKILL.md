---
name: research-hub
description: Use research-hub to operate Zotero, Obsidian, and NotebookLM research workflows through CLI, MCP, REST, and dashboard. Trigger when the user asks to find papers, ingest sources, organize a literature review, build Obsidian research notes, upload sources to NotebookLM, inspect clusters, generate AI briefs, or maintain a research vault.
---

# research-hub

research-hub is an AI-operable research workspace. It can use Zotero, Obsidian, and NotebookLM together, but it is also useful when the user only has two of them.

Default language policy: respond in the user's language, but generate durable research notes and metadata in English unless the user asks otherwise.

## Choose The Workflow

| User has | Prefer this path |
|---|---|
| Zotero + Obsidian + NotebookLM | Full `research-hub auto "topic"` workflow |
| Zotero + Obsidian | Search/add/backfill papers, write Markdown notes, skip NotebookLM with `--no-nlm` |
| Obsidian + NotebookLM | `import-folder`, dashboard, NotebookLM bundle/upload/generate |
| Zotero + NotebookLM | Zotero-backed paper selection and NotebookLM operations |
| No accounts yet | `research-hub dashboard --sample` |

## First Commands

```bash
research-hub dashboard --sample
research-hub setup
research-hub auto "topic" --no-nlm
research-hub serve --dashboard
research-hub doctor --autofix
```

For local files without Zotero:

```bash
research-hub setup --persona analyst
research-hub import-folder ./papers --cluster my-local-review
research-hub serve --dashboard
```

## AI Host Integration

For MCP hosts, configure:

```json
{ "mcpServers": { "research-hub": { "command": "research-hub", "args": ["serve"] } } }
```

Install host-specific skill files when useful:

```bash
research-hub install --platform claude-code
research-hub install --platform cursor
research-hub install --platform codex
research-hub install --platform gemini
```

## Operating Rules

- Run `research-hub doctor` first when setup or runtime behavior is unclear.
- Use `--no-nlm` for smoke tests or when NotebookLM browser automation is not configured.
- Prefer `import-folder` for analysts, internal knowledge bases, local PDFs, DOCX, Markdown, TXT, and URL sources.
- Prefer Zotero-backed commands for DOI/arXiv-heavy academic literature workflows.
- Do not delete clusters without previewing cascade impact first.
- Treat the vault as user-owned local data; avoid overwriting notes unless the user explicitly asks.

## Useful Docs

- `README.md`: public project overview.
- `docs/first-10-minutes.md`: persona-based onboarding.
- `docs/mcp-tools.md`: MCP tool reference.
- `docs/ai-integrations.md`: Claude/Cursor/Codex/Gemini integration paths.
- `docs/import-folder.md`: local file ingest.
- `docs/notebooklm.md`: NotebookLM setup and automation.

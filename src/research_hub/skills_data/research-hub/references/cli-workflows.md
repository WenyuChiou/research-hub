# research-hub CLI & Headless Workflows Reference

Use this reference when an authorized Hub CLI workflow is explicitly selected, when no interactive AI host search tool is available, or for vault/library maintenance.

For interactive AI hosts (Claude Code, Codex, Gemini CLI, Cursor), prefer **host-native search & reading** -> **`research-hub ingest`** / **`project record`** -> **`paper-summarize`** -> **`notebooklm`**.

## Setup & Destination Checks

Only run setup when using Hub storage or external integrations:

```bash
pip install research-hub-pipeline[playwright,secrets]
research-hub setup --persona researcher   # or analyst | humanities | internal
research-hub doctor
```

For local files without Zotero:

```bash
pip install research-hub-pipeline[import,secrets]
research-hub setup --persona analyst
research-hub import-folder ./papers --cluster my-local-review
```

Missing credentials adapt per selected destination:
- **Missing Zotero:** use `import-folder`, sample/dashboard mode, or ask the user to set `ZOTERO_API_KEY` / `ZOTERO_LIBRARY_ID`.
- **Missing NotebookLM auth:** pass `--no-nlm`, or ask the user to complete `research-hub notebooklm login --auto-detect`.
- **Missing LLM CLI for batch relevance/summary:** pass `--no-fit-check` or use host-native evaluation/summarization instead of spawning a subprocess CLI (`claude`, `codex`, `gemini`, `opencode`, `aichat`, `cursor`).

## Headless / Batch CLI Discovery (`auto` & `discover`)

Use `auto` or `discover` only when the researcher explicitly asks for CLI-managed search or no interactive AI host is driving discovery:

```bash
research-hub plan "TOPIC"
research-hub auto "TOPIC" --max-papers 3 --no-nlm
research-hub auto "TOPIC" --max-papers 3 --no-nlm --no-fit-check
research-hub auto "TOPIC" --max-papers 3 --no-nlm --llm-cli codex
```

Interactive two-phase discovery with external relevance scoring:

```bash
research-hub discover new --cluster project-topic --query "agent-based modeling flood adaptation"
research-hub fit-check emit --cluster project-topic
# Evaluate prompt in host or chosen AI, then apply:
research-hub discover continue --cluster project-topic --scores scores.json
```

`research-hub fit-check {emit|apply|audit|drift}` re-scores or audits an existing cluster; `discover variants` widens recall before narrowing.

## Local Folder Import & Synthesis

```bash
research-hub import-folder ./sources --cluster project-topic
research-hub serve --dashboard
research-hub crystal emit --cluster project-topic
research-hub synthesize --cluster project-topic --graph-colors
```

Run `synthesize` after per-paper notes are populated; it reads cluster memory and paper summaries to refresh Obsidian overview notes.

## Cluster Memory & Vault Maintenance

```bash
research-hub memory list --cluster project-topic
research-hub memory read --cluster project-topic
research-hub memory emit --cluster project-topic
research-hub memory apply --cluster project-topic --payload memory.json

research-hub doctor --autofix
research-hub tidy
research-hub clusters rebind --emit
research-hub cleanup --all
```

## MCP Server & Host Skill Installers

MCP config for compatible STDIO hosts:

```json
{ "mcpServers": { "research-hub": { "command": "research-hub", "args": ["serve"] } } }
```

Built-in platform installers:

```bash
research-hub install --platform claude-code
research-hub install --platform codex
research-hub install --platform cursor
research-hub install --platform gemini
```

For hosts without a built-in installer (such as Hermes or OpenClaw), copy `skills/<name>/` manually or connect over MCP/REST.

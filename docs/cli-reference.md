# CLI Reference

Generated against research-hub v0.9.0. 35+ subcommands grouped by
workflow stage.

## Setup

### `init`
Interactive setup wizard.

```bash
research-hub init [--vault PATH] [--zotero-key KEY] [--zotero-library-id ID]
                  [--non-interactive] [--persona researcher|analyst]
```

| Flag | Description |
|---|---|
| `--vault PATH` | Vault root directory (default: ~/knowledge-base) |
| `--zotero-key KEY` | Zotero API key (researcher persona only) |
| `--zotero-library-id ID` | Zotero library ID |
| `--non-interactive` | Skip prompts; require values via flags |
| `--persona` | researcher (default) or analyst (skip Zotero) |

Example:
```bash
research-hub init --persona analyst --vault ~/my-vault
```

### `doctor`
Health check (config, vault, Zotero, dedup, Chrome, NLM session).

```bash
research-hub doctor
```

### `install`
Install AI assistant skill.

```bash
research-hub install --platform claude-code|codex|cursor|gemini
research-hub install --list
```

## Search & verification

### `search`
Query Semantic Scholar.

```bash
research-hub search "QUERY" [--limit N] [--verify]
```

### `verify`
Check paper exists via DOI / arXiv ID / fuzzy title match.

```bash
research-hub verify --doi 10.1234/x
research-hub verify --arxiv 2502.10978
research-hub verify --paper "Title" [--paper-year 2025] [--paper-author "Last"]
```

### `references`
List papers cited by the given paper (its bibliography).

```bash
research-hub references <doi-or-arxiv-id> [--limit 20] [--json]
```

### `cited-by`
List papers that cite the given paper.

```bash
research-hub cited-by <doi-or-arxiv-id> [--limit 20] [--json]
```

## Save & organize

### `add`
**The one-shot Search → Save command.**

```bash
research-hub add <doi-or-arxiv-id> [--cluster SLUG]
                                    [--no-zotero] [--no-verify]
```

### `ingest` / `run`
Run the full pipeline from `papers_input.json`.

```bash
research-hub ingest [--cluster SLUG] [--no-verify]
research-hub run    [--cluster SLUG]
```

### `suggest`
Cluster + related-paper suggestions.

```bash
research-hub suggest <doi-or-title> [--top 5] [--json]
```

### `find`
Search within vault notes.

```bash
research-hub find "QUERY" [--cluster SLUG] [--status STATUS]
                          [--full] [--json]
```

### `mark`
Update reading status.

```bash
research-hub mark <slug> --status unread|reading|deep-read|cited
research-hub mark --cluster SLUG --status STATUS    # bulk
```

### `move`
Move a paper between clusters.

```bash
research-hub move <slug> --to <cluster>
```

### `remove`
Remove a paper from the vault.

```bash
research-hub remove <doi-or-slug> [--zotero] [--dry-run]
```

### `cite`
Export citations.

```bash
research-hub cite <doi-or-slug> [--format bibtex|biblatex|ris|csljson] [--out FILE]
research-hub cite --cluster <slug> --format bibtex --out cluster.bib
```

## Cluster management

### `clusters list/show/new`

```bash
research-hub clusters list
research-hub clusters show <slug>
research-hub clusters new --query "topic" [--name "Display Name"]
```

### `clusters bind`
Link a cluster to Zotero collection / Obsidian folder / NotebookLM notebook.

```bash
research-hub clusters bind <slug> [--zotero KEY] [--obsidian PATH] [--notebooklm "Name"]
```

### `clusters rename / delete / merge / split`

```bash
research-hub clusters rename <slug> --name "New Name"
research-hub clusters delete <slug> [--dry-run]
research-hub clusters merge <source> --into <target>
research-hub clusters split <source> --query "keywords" --new-name "Name"
```

## Maintenance

### `dedup`

```bash
research-hub dedup invalidate [--doi DOI] [--path PATH]
research-hub dedup rebuild [--obsidian-only]
```

### `index`
Rebuild dedup_index.json from Zotero + Obsidian.

```bash
research-hub index
```

### `status`
Per-cluster reading progress.

```bash
research-hub status [--cluster SLUG]
```

### `sync`

```bash
research-hub sync status [--cluster SLUG]
research-hub sync reconcile --cluster SLUG [--dry-run] [--execute]
```

### `cleanup`
Deduplicate hub page wikilinks.

```bash
research-hub cleanup [--dry-run]
```

### `synthesize`
Generate cluster synthesis pages.

```bash
research-hub synthesize [--cluster SLUG] [--graph-colors]
```

### `migrate-yaml`
Patch legacy notes to current YAML spec.

```bash
research-hub migrate-yaml [--assign-cluster SLUG] [--folder PATH]
                          [--force] [--dry-run]
```

## NotebookLM

### `notebooklm login`

```bash
research-hub notebooklm login --cdp [--keep-open] [--timeout 300]
```

### `notebooklm bundle`

```bash
research-hub notebooklm bundle --cluster SLUG
```

### `notebooklm upload`

```bash
research-hub notebooklm upload --cluster SLUG [--dry-run] [--headless] [--visible]
```

### `notebooklm generate`

```bash
research-hub notebooklm generate --cluster SLUG --type brief|audio|mind-map|video|all
                                  [--headless] [--visible]
```

## AI integration

### `serve`
Start MCP stdio server for Claude Desktop / Cursor / Claude.ai.

```bash
research-hub serve
```

Add this to your Claude Desktop config:

```json
{
  "mcpServers": {
    "research-hub": {
      "command": "research-hub",
      "args": ["serve"]
    }
  }
}
```

18 MCP tools exposed. See [docs/mcp-tools.md](mcp-tools.md) for the
full list.

# CLI Reference

Generated against research-hub v1.x. 35+ subcommands grouped by
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
Install portable `SKILL.md` files for hosts with known default skill
directories.

```bash
research-hub install --platform claude-code|codex|cursor|gemini
research-hub install --list
```

OpenClaw, Hermes, and other agents can use research-hub through MCP/REST
or manual `SKILL.md` loading, but they are not built-in installer targets
yet.

### `dashboard`
Generate a personal HTML dashboard for the vault.

```bash
research-hub dashboard [--open]
```

| Flag | Description |
|---|---|
| `--open` | Open the dashboard in your default browser after generation |

Output: `<vault>/.research_hub/dashboard.html` — single self-contained
file with stat cards, cluster table, status badges, and NotebookLM
links. Works offline.

## Search & verification

### `source fetch`

Fetch credential-free public source evidence into a new output directory. At
least one of `--doi` or `--url` is required; both may be supplied to check the
retrieved identity against the expected DOI and title.

```bash
research-hub source fetch --doi 10.1234/example --title "Expected title" \
  --output-dir runs/example-source --json
research-hub source fetch --url https://example.org/public-article \
  --output-dir runs/example-html --json
research-hub source validate runs/example-html/source-fetch-result.json --json
```

The command preserves every HTTP response, extracted text, SHA-256 hashes,
page or section locators, and a versioned `source-fetch-result.json`. Its
receipt hash binds the normalized request to every response-body hash and the
extracted-text hash. `source validate` checks containment and all hashes, then
re-extracts the saved selected response without network access and verifies
every locator's exact `[start, end)` range. Metadata evidence identifies a work but is not full-text
claim evidence. The command uses
only public HTTP endpoints: no Zotero write, login, institutional proxy, or
authenticated session is attempted. Fetch sessions ignore netrc credentials,
environment proxies, and cookies; redirect targets and resolved IP addresses
must remain public. Responses are streamed only through the recorded size cap.
Existing output directories are rejected.

Full-text classification is conservative: HTML needs multiple substantive
sections and enough extracted content; short or abstract-marked PDFs remain
metadata/abstract evidence unless their structure supports a full-text label.

`search`, `enrich`, `verify`, `references`, and `cited-by` accept
`--audit-output NEW_DIRECTORY` to preserve versioned attempt events, raw
responses, result references and explicit failures. The directory cannot be
reused. See [the audit file contract](audit-output.md); a successful empty
response is different from HTTP 404, HTTP 429, timeout or parse failure.

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
research-hub notebooklm login --auto-detect [--wait-timeout 300]
research-hub notebooklm login [--wait-file PATH] [--wait-timeout 300]
research-hub notebooklm login --from-browser [chrome|edge|firefox|brave|auto]
research-hub notebooklm login --import-from VAULT_PATH [--overwrite]
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

### `notebooklm download`
Pull a generated briefing back to the vault as plain text. v0.9.0
supports `--type brief`; audio/mind-map/video downloads land in
v0.9.1.

```bash
research-hub notebooklm download --cluster SLUG [--type brief] [--visible]
```

Output: `<vault>/.research_hub/artifacts/<cluster_slug>/brief-<UTC>.txt`
with a small header (notebook name, source URL, timestamp, saved
briefing titles) followed by the briefing body.

### `notebooklm read-briefing`
Print the most recently downloaded briefing for a cluster.

```bash
research-hub notebooklm read-briefing --cluster SLUG
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

21 MCP tools exposed. See [docs/mcp-tools.md](mcp-tools.md) for the
full list.

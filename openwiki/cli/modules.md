# CLI module map

The `research_hub` CLI is a single argparse program with one entry point (`src/research_hub/cli.py`) and eleven extracted `cli_*` domain modules. The canonical invocation is `python -m research_hub <command> ...` (an installed `research-hub` console script behaves identically); prefixing `PYTHONPATH=src` is the dev/pytest variant for running against a checkout. The full flag-by-flag command reference lives in [docs/cli-reference.md](../../docs/cli-reference.md) — this page maps commands to source files so agents know where to read and where to edit.

## How dispatch works

`cli.py` owns the entire argparse surface and the routing; the `cli_*` modules own handler bodies only:

- `build_parser()` in `cli.py` registers **every** subparser (~167 `add_parser` calls). No `cli_*` module registers its own arguments — if you are looking for a flag definition, it is in `cli.py`.
- `main()` parses argv, then `_main_dispatch(args, parser)` routes on `args.command` through a flat `if args.command == ...` chain and calls a handler function, most of which are imported from the `cli_*` modules (import blocks at the top of `cli.py`).
- A bare `python -m research_hub` with no subcommand prints help and exits 0 *before* any config probing, so fresh installs without a `config.json` see the command list instead of a config error.
- Config gating: every command except the exempt set `{init, setup, doctor, install, examples, where, config, ezproxy, package-dxt, describe, context}` triggers `require_config()` before its handler runs.
- Dependency injection: the `cli_*` modules bind `get_config` / `ClusterRegistry` at import time, so `cli.py` re-assigns lambdas into each module (and `_sync_cli_dependencies()` repeats this at the top of `_main_dispatch`) so that test patches of `research_hub.cli.get_config` propagate into the extracted handlers. When extracting a new module, add a sync line there.
- Errors: `main()` catches `ResearchHubError`; with `--json` it emits a structured `{"ok": false, "error": ...}` payload and returns 1, otherwise it re-raises. `cli_common._emit_cli_json` is the shared success-path JSON emitter.

## Module map by workflow

Handler functions are private (`_search`, `_cmd_ingest`, ...); the tables list the user-facing subcommands each module implements.

### Discovery and ingest

- **`cli_search.py`** — finding papers before they enter the vault. Implements `search` (multi-backend academic search with year/citation/type filters and `--to-papers-input`), `websearch` (web-source search with optional `--ingest-into`), `enrich` (resolve bare titles/DOIs into full records), `references` / `cited-by` / `suggest` (citation-graph lookups around one identifier), and the staged `discover new | continue | status | clean | variants` flow (search → stashed fit-check prompt → apply scores → `papers_input.json`). Note: `cli.py` still resolves backends (`--region` / `--field` / `--backend` presets and `--peer-reviewed` adjustments) inline before calling `_search`.
- **`cli_pipeline.py`** — running the ingest machinery. Implements `doctor`, `ingest`, `auto` (the one-shot topic → search → fit-check → Zotero → Obsidian → NotebookLM pipeline), `import-folder` (plus its dependency precheck), `fit-check emit | apply | audit | drift`, `sync status | reconcile` (cross-system drift), `pipeline repair` (orphan repair for a cluster), and `migrate-yaml`. The top-level `run` command is dispatched inline in `cli.py` directly to `pipeline.run_pipeline`.
- **`cli_paper.py`** — per-paper CRUD and curation. Implements `add`, `remove`, `mark`, `move`, `find`, `label`, `label-bulk`, `verify`, `quarantine list | show | restore`, `autofill emit | apply`, `fit-check apply-labels`, and the whole `paper` subtree via `_paper_command`: `lookup-doi`, `find`, `add-to-cluster`, `gaps`, `prune`, `unarchive`, `bulk-relabel`, `bulk-move`, `bulk-delete`, `retype`, `enrich-existing`, `attach-pdfs`, `upgrade-pdfs`, `resummarize`, `summarize`.

### Organization and AI-assisted content

- **`cli_clusters.py`** — the `clusters` subtree: `list`, `show`, `set-group`, `prisma`, `new`, `bind`, `rename`, `archive`, `unarchive`, `merge`, `split`, `analyze`, `scaffold-missing`, `audit`, `restore-zotero-coll`, `sync-names`, `resolve-collision`. Three `clusters` branches stay inline in `cli.py`: `coverage` (calls `clusters.compute_coverage`), `delete` (preview/apply cascade delete via `clusters.cascade_delete_cluster` — a `_clusters_delete` helper exists in the module but the dispatch branch does not use it), and `rebind` (via `cluster_rebind`).
- **`cli_summarize.py`** — AI-generated derived content: `crystal emit | apply | list | read | check` (pre-computed canonical crystals), `summarize`, `memory emit | apply | list | read` (structured cluster memory registries), and `vault summarize-status-migrate`.
- **`cli_citations.py`** — writing support: `cite` (formatted citations for one identifier or a cluster), `quote` (add/list/remove saved paper quotes — `cli.py` untangles the positional `quote_target` grammar before calling the handlers), and `compose-draft` (outline + quotes → draft with optional bibliography).

### Maintenance

- **`cli_maintenance.py`** — install/ops surface: `install` (agent-platform integration), `where`, `serve` (REST API), `config encrypt-secrets | set`, `package-dxt`, `index` (rebuild `dedup_index.json`), `dedup invalidate | rebuild | compact`, `status` (per-cluster reading progress), `dashboard`, and the GC half of `cleanup` (`--bundles/--debug-logs/--artifacts`). Also owns the Claude Desktop MCP-config path/install helpers.
- **`cli_vault.py`** — Obsidian-side maintenance: the `vault` subtree (`graph-colors`, `polish-markdown`, `rebuild-overviews`, `tag-migrate`, `prune-footers`, `gc`, `hub-backlink-migrate`, `cleanup-frontmatter`, `install-theme`), `bases emit` (Obsidian Bases generator), `synthesize` (hub index rebuild), and the wikilink-dedup half of `cleanup` (`_cleanup_hub`, also the bare-`cleanup` backwards-compat default).
- **`cli_zotero.py`** — Zotero-side maintenance: `zotero backfill` (tags and notes), `zotero gc` (empty/test/orphan collections), `zotero mark-kept`, `zotero reparent-clusters`.

### Export

- **`cli_notebooklm.py`** — NotebookLM operations: `notebooklm bundle`, `upload`, `shard`, `download`, `read-briefing`, `generate`, `ask`, plus the shared `_preflight_nlm_session` check. Two `notebooklm` branches stay inline in `cli.py`: `login` (interactive / `--import-from` / `--from-browser`, delegating to `notebooklm/auth.py`) and `keepalive` (loop and Windows-task install, delegating to `notebooklm/keepalive.py`).

### Shared plumbing

- **`cli_common.py`** — no subcommands; shared helpers used across modules: deprecated-alias warnings, `_emit_cli_json` / `_json_safe` (structured `--json` output), `_stdout_to_stderr`, `_load_zotero_if_configured`, and argv parsers (`_parse_year_range`, `_parse_csv_terms`, `_parse_negative_terms`, `_parse_seed_dois`).

## What still lives in cli.py itself

Beyond parser construction and routing, `_main_dispatch` retains real logic for commands that were never extracted. These call domain modules directly rather than a `cli_*` handler:

- `run` (→ `pipeline.run_pipeline`, plus post-run fit-check auto-labeling), `init` (→ `init_wizard` / `onboarding` field wizard), `setup` (→ `setup_command`), `tidy` (→ `tidy`), `ask` (→ `workflows.ask_cluster`), `plan` (→ `planner`), `describe` (→ `describe`), `ezproxy login | status` (→ `ezproxy`), `examples list | show | copy` (→ `examples`), `context init | audit | compress` (→ `context_cli.dispatch`), and the entire `topic` subtree (`scaffold | digest | show | propose | assign emit/apply | build | list` → `topic`).
- The inline `clusters delete | rebind | coverage` and `notebooklm login | keepalive` branches noted above, the `search` backend-preset resolution, `quote` argument untangling, and `cleanup` routing between the vault wikilink-dedup and the maintenance GC.

So "where is command X?" has three answers: flags are always in `cli.py`'s `build_parser()`; the handler is usually in the matching `cli_*` module; and for the commands in this section the handler body is in `_main_dispatch` itself, delegating straight to a domain module.

## Adding a new subcommand

1. **Register the parser** in `build_parser()` in `src/research_hub/cli.py` (find the neighboring command's `add_parser` block and follow its `dest` naming convention, e.g. `clusters_command`).
2. **Write the handler** in the `cli_*` module that owns the workflow (tables above) as a private function returning an `int` exit code. Use `cli_common._emit_cli_json` if the command supports `--json`, and raise `ResearchHubError` subclasses for structured failures.
3. **Import and route**: add the handler to the corresponding `from research_hub.cli_<module> import (...)` block in `cli.py`, then add the dispatch branch in `_main_dispatch`.
4. **Config access**: call the module-level `get_config()` / `ClusterRegistry` inside the handler (not at import time) so the `_sync_cli_dependencies()` test-patch propagation works; if you create a *new* `cli_*` module, add its sync lines both at module scope in `cli.py` and inside `_sync_cli_dependencies()`.
5. **Config gating**: if the command must work without a `config.json` (setup/diagnostic class), add it to `exempt_commands` in `_main_dispatch`.
6. **Docs and tests**: add the command to [docs/cli-reference.md](../../docs/cli-reference.md); CLI tests live in `tests/` (`test_cli_smoke_comprehensive.py` for smoke coverage, `test_arch2_cli_split.py` guards the cli-split architecture, plus per-area files like `test_cli_search.py`, `test_cli_notebooklm.py`).

## Source map

- `src/research_hub/cli.py`
- `src/research_hub/cli_citations.py`
- `src/research_hub/cli_clusters.py`
- `src/research_hub/cli_common.py`
- `src/research_hub/cli_maintenance.py`
- `src/research_hub/cli_notebooklm.py`
- `src/research_hub/cli_paper.py`
- `src/research_hub/cli_pipeline.py`
- `src/research_hub/cli_search.py`
- `src/research_hub/cli_summarize.py`
- `src/research_hub/cli_vault.py`
- `src/research_hub/cli_zotero.py`
- `docs/cli-reference.md`
- `README.md`

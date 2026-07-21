# Vault layout and maintenance

What a research-hub vault looks like on disk, and the maintenance commands that keep it healthy — `doctor`, `tidy`, `cleanup`, the dedup index, `vault gc`, and `clusters rebind`. The safety-critical fact of this page: **every maintenance command that mutates the vault defaults to a preview/dry-run and requires an explicit flag (usually `--apply`) to write**, and cluster deletion is a *soft* delete into `raw/_deleted_<slug>/` before anything is ever hard-removed. Command syntax details live in [docs/cli-reference.md](../../docs/cli-reference.md); the interactive cleanup walkthrough is [docs/clean_vault.md](../../docs/clean_vault.md).

All invocations below use the canonical form `python -m research_hub ...` (equivalently the `research-hub` console script). `PYTHONPATH=src` prefixing is only the dev/pytest variant — see [Release and testing](./release-and-testing.md).

## Vault layout

Paths come from `src/research_hub/config.py` (`Config.__init__`). The vault root must live under `$HOME` unless `RESEARCH_HUB_ALLOW_EXTERNAL_ROOT=1` is set — a misconfigured `RESEARCH_HUB_ROOT` fails loudly instead of writing outside home. Defaults (each overridable in config):

- `raw/` (`cfg.raw`) — one subfolder per cluster (`raw/<obsidian_subfolder>/`), holding the per-paper Markdown notes plus an optional `topics/` subfolder of sub-topic notes and cluster index files (`00_*`, `*-index`). Folders named `pdfs/`, `attachments/`, and anything starting with `_deleted_` are excluded from paper walks (`paper.py`, `doctor.py`).
- `raw/_deleted_<slug>/` — **soft-delete residue**. `clusters delete --apply` moves `raw/<slug>/` here instead of removing it (`clusters.py: cascade_delete_cluster`). Everything under a `_deleted_*` dir is skipped by sync, graph coloring, footer pruning, and GC content passes; only `vault gc` ever hard-removes it, and only past an age threshold.
- `hub/` (`cfg.hub`) — per-cluster knowledge pages: `hub/<slug>/` (overview `00_overview.md`, crystals, memory.json, `.base` file, briefs) and `hub/_moc/` Map-of-Content pages. `hub/_moc` and `hub/_archived` are reserved names, never treated as cluster hubs (`vault/gc.py`).
- `.research_hub/` (`cfg.research_hub_dir`) — machine state: `clusters.yaml` (the cluster registry, default location of `cfg.clusters_file`), `dedup_index.json`, `manifest.jsonl`, `dashboard.html`, NotebookLM bundle exports under `bundles/<slug>-<timestamp>/`, ask/brief outputs under `artifacts/<slug>/`, `nlm-debug-*.jsonl` run logs, and timestamped `rebind-*.log` audit logs.
- Also under the root: `projects/`, `logs/`, and `.obsidian/graph.json` (managed graph color groups).

`python -m research_hub where` prints all of these locations plus per-cluster note counts without making any API calls (`cli_maintenance.py: _cmd_where`).

## Destructive vs preview-only: the flag map

Grounded in the argparse wiring in `cli.py` and the handler defaults:

| Command | Default behavior | What makes it write |
|---|---|---|
| `doctor` | read-only checks, **two exceptions below** | `--autofix` backfills frontmatter |
| `tidy` | doctor+autofix, dedup rebuild, bases refresh; cleanup step is preview | `--apply-cleanup` flushes the cleanup preview |
| `cleanup` | dry-run listing (`--dry-run` is the default) | `--apply` deletes; scope flags `--bundles/--debug-logs/--artifacts/--wikilinks/--all` |
| `dedup compact` | preview (`--dry-run` default) | `--apply` writes the compacted index |
| `dedup rebuild` / `index` / `dedup invalidate` | **writes immediately** — but only to `.research_hub/dedup_index.json`, never to notes |
| `vault gc` | dry-run report | `--apply` purges/rewrites |
| `vault polish-markdown`, `tag-migrate`, `hub-backlink-migrate`, `summarize-status-migrate`, `cleanup-frontmatter` | dry-run (`--dry-run` default `True`) | `--apply` writes notes |
| `vault prune-footers` | report only | `--apply` rewrites footers |
| `vault rebuild-overviews` | regenerates hub overview/MOC pages (managed content; debounced, `--force` bypasses) | n/a — always writes hub pages |
| `clusters rebind` | `--emit` prints a proposal; `--apply <report>` is still dry-run | add `--no-dry-run` to actually move files |
| `clusters delete` | preview report, zero Zotero I/O | `--apply` (plus `--force` for non-empty clusters) |
| `clusters delete --purge-zotero-items` | **DESTRUCTIVE** (Zotero items → trash) | only acts with `--apply`; dry-run lists items/PDF counts |
| `zotero gc` | preview of empty/test/orphan Zotero collections | `--apply` (respects `zotero mark-kept` list by default) |

## doctor — health checks

`python -m research_hub doctor` (`doctor.py: run_doctor`) runs ~20 checks: config presence, vault root and `raw/`/`.research_hub/` existence, Zotero API key + reachability (HEAD probe cached 60 s to avoid 429s), frontmatter completeness, cluster drift/collision/name-drift against Zotero, orphan papers, empty clusters, test-pattern cluster names, PDF/crystal coverage, trashed Zotero collections, manifest orphans, defuddle CLI, NotebookLM auth paths, and EZproxy session state. `--strict` surfaces legacy WARNs (missing DOI on old imports, empty sections) that are otherwise collapsed into one INFO line; `--json` emits a machine-readable report.

Two writes hide inside an otherwise read-only command:

- `run_doctor` always calls `_encrypt_plaintext_secrets` first — if it finds a plaintext Zotero API key in `config.json` it encrypts it in place and reports a WARN.
- `--autofix` (`vault_autofix.py: run_autofix`) backfills mechanical frontmatter before checks run: missing `topic_cluster` from the folder→cluster map, missing `ingested_at` from file mtime, and a DOI derived from an arXiv id in the filename. It edits note frontmatter with no dry-run mode of its own.

`clusters audit [--cluster S] [--json]` runs the drift/collision/test-pattern subset of doctor scoped to clusters.

## tidy — one-shot maintenance

`python -m research_hub tidy` (`tidy.py: run_tidy`) chains four non-fatal steps: (1) `doctor --autofix`, (2) dedup index rebuild from Obsidian notes only, (3) `bases emit --force` per cluster (Obsidian `.base` refresh), (4) `cleanup --bundles --debug-logs --artifacts` **in preview mode**. Only `--apply-cleanup` makes step 4 delete; `--cluster <slug>` restricts the bases step.

## cleanup — garbage collection of accumulated files

`python -m research_hub cleanup` (`cleanup.py: collect_garbage`) targets three kinds of regenerable state under `.research_hub/`: bundle dirs (keeps the newest 2 per cluster, `--keep-bundles`), `nlm-debug-*.jsonl` older than 30 days (`--debug-older-than`), and `ask-*.md`/`brief-*.txt` artifacts beyond the newest 10 per cluster (`--keep-artifacts`). You must opt into scopes (`--all` = all three); the default run is a dry-run listing sizes, and only `--apply` deletes. `--wikilinks` is a separate, note-touching pass (`vault/cleanup.py: dedup_hub_pages`) that de-duplicates repeated wikilinks in hub pages. Nothing in `cleanup` touches paper notes or Zotero.

## Dedup index maintenance

The dedup index (`.research_hub/dedup_index.json`, `dedup.py`) maps DOIs and normalized titles to known Obsidian paths and Zotero keys so ingest can skip duplicates. Maintenance surface (`cli_maintenance.py`):

- `index` — full rebuild from Obsidian + Zotero (same as `dedup rebuild`).
- `dedup rebuild [--obsidian-only]` — rebuild; `--obsidian-only` skips Zotero (useful offline), and a failed Zotero pass degrades with a warning rather than corrupting the index.
- `dedup invalidate --doi X | --path Y` — drop stale entries after manual note moves/deletes.
- `dedup compact [--apply] [--json]` — drop stale Obsidian paths and Zotero 404 hits; preview by default.

These commands rewrite only the index file — a bad run costs you duplicate detection, not notes.

## Soft delete and `vault gc`

The soft-delete convention (`clusters.py: cascade_delete_cluster`): `clusters delete <slug> --apply` moves `raw/<slug>/` → `raw/_deleted_<slug>/`, removes `hub/<slug>/`, the cluster's bundles and artifacts, its manifest lines and dedup entries, and the `clusters.yaml` entry. Zotero items are *unbound* from the collection by default; `--delete-zotero-collection` removes the empty container, and `--purge-zotero-items` (flagged DESTRUCTIVE in its own help text) trashes parent items — recoverable in Zotero until trash is emptied, strictly scoped to the cluster's own collection key, with a guard that refuses to operate on the configured parent collection. Dry-run performs zero Zotero I/O.

`vault gc` (`vault/gc.py: run_gc`) is the second stage — the only thing that ever hard-deletes soft-deleted residue. Four passes, all dry-run unless `--apply`:

1. Purge `raw/_deleted_<slug>/` dirs older than `--older-than-days` (default 30, by dir mtime).
2. Remove `hub/<slug>/` dirs whose slug has no registry entry at all (merged-but-present clusters are never orphans; note-linked hubs are protected).
3. Remove `hub/_moc/*.md` pages no live cluster derives *and* no live note links; `PARENT_MOCS` are always protected, and MOC names are derived from both slugs and cluster queries so query-derived sub-MOCs survive.
4. Strip bare parent-MOC lines from paper-note `## Hub` blocks — the only pass that edits note content; skip it with `--no-strip-parents`.

To triage residue interactively before purging, see [docs/clean_vault.md](../../docs/clean_vault.md); cluster-structure invariants are in [docs/cluster-integrity.md](../../docs/cluster-integrity.md).

## clusters rebind — orphan papers back into clusters

`clusters rebind` (`cluster_rebind.py`) is a three-step, report-mediated flow with an extra safety layer beyond dry-run:

1. `clusters rebind --emit > report.md` — walks `raw/` folders not bound to any cluster and proposes moves via a heuristic chain (explicit `cluster:`/`topic_cluster:` frontmatter → Zotero collection key → collection-name/keyword match → tag Jaccard vs seed keywords → folder-name match), each tagged with a confidence level. Folders with ≥5 unmatched papers yield opt-in *new cluster* proposals.
2. Review/edit the JSON blocks in the report — the report is the contract; `--apply` replays exactly what it says.
3. `clusters rebind --apply report.md` — still a dry-run; add `--no-dry-run` to actually move files (`robust_move`, skipping missing sources and existing destinations), and `--auto-create-new` to also create the proposed clusters. Every decision is appended to a timestamped `.research_hub/rebind-*.log`.

## Overview and note-convention rebuilds

- `vault rebuild-overviews [--cluster S] [--force]` re-runs `populate_overview` + `ensure_moc` for every cluster (`vault/hub_overview.py`); a debounce marker prevents redundant rebuilds unless `--force`. This regenerates managed hub pages — distinct from the LLM-driven overview auto-fill (`cluster_overview.py`) that runs inside `auto` and refuses to overwrite hand-curated TL;DRs (it only replaces recognized scaffold/fallback text).
- The migration family — `vault tag-migrate`, `vault hub-backlink-migrate`, `vault summarize-status-migrate`, `vault cleanup-frontmatter`, `vault polish-markdown`, `vault prune-footers` — all share the same UX: scan notes, print per-action counts, and require `--apply` to write. All of them skip `_deleted_*` residue.
- `vault graph-colors --refresh` and `synthesize [--graph-colors]` regenerate managed graph color groups and cluster synthesis pages.

## Agent guidance

- Preview first, always: run the bare command, read the report, then re-run with `--apply` (or `--no-dry-run` for rebind). The tools themselves print the exact re-run hint.
- Treat `raw/_deleted_*` as quarantine, not garbage — restoring is a `git mv`/file move until `vault gc --apply` crosses the age threshold.
- The regenerable/irreplaceable line: dedup index, bundles, artifacts, debug logs, dashboards, hub overviews, `.base` files, and graph colors can all be rebuilt; paper notes under `raw/` and Zotero items cannot. Commands that touch the latter (`--purge-zotero-items`, `zotero gc`, `vault gc` pass 1) are the ones to double-check.

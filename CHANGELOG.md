# Changelog

## v0.9.0 (2026-04-12)

**System integration audit + UX hardening + personal HTML dashboard.**

### Added
- `research-hub dashboard [--open]` — personal HTML dashboard at `<vault>/.research_hub/dashboard.html`. Single self-contained file with stat cards, cluster table, status badges, and NotebookLM links. Hero artifact for the project.
- `research-hub add <doi-or-arxiv-id> [--cluster X]` — one-shot Search → Save replaces hand-writing `papers_input.json`. Fetches metadata via Semantic Scholar with CrossRef enrichment.
- `research-hub init --persona researcher|analyst` — analyst persona skips Zotero entirely (Obsidian + NotebookLM only).
- `research-hub dedup invalidate --doi/--path` and `dedup rebuild [--obsidian-only]` — surgical dedup management without re-scanning Zotero.
- `papers_input.json` validator: pipeline catches missing `creatorType`, malformed authors, missing fields BEFORE hitting Zotero API. Clear error messages instead of cryptic 400 crashes.
- 2 new MCP tools: `add_paper`, `generate_dashboard` (19 total).
- New docs: `docs/cli-reference.md`, `docs/papers_input_schema.md`.

### Changed
- `doctor` now persona-aware: when `no_zotero: true` is set in config or `RESEARCH_HUB_NO_ZOTERO=1` env var, Zotero checks report "Skipped (analyst mode)" instead of FAIL.
- `doctor` correctly counts dedup index entries (was reporting 0 when index had thousands).

### Fixed
- Pipeline silently dropped dict-format authors `[{firstName, lastName}]` → `authors: "Unknown"` in Obsidian YAML.
- Pipeline never wrote `volume`, `issue`, `pages` to Zotero or Obsidian even when input had them.
- `clusters rename` updates display name without orphaning notes.
- 12 new regression tests for pipeline metadata and dedup invalidation.

Suite: 274 → 314 passing.

## v0.8.2 (2026-04-12)

### Added
- New MCP tool `propose_research_setup(topic)` — AI agents propose cluster/collection/notebook names BEFORE creating, ask user to confirm.
- `RESEARCH_HUB_NO_ZOTERO=1` env var enables data analyst persona (Obsidian + NotebookLM only, no Zotero).
- SKILL.md documents both personas + the "always confirm names" protocol.

## v0.8.1 (2026-04-12)

### Fixed
- `_render_obsidian_note` now handles dict-format authors (was producing `authors: "Unknown"`).
- Pipeline + `make_raw_md` now emit `volume`, `issue`, `pages` fields to both Zotero items and Obsidian YAML.
- New `**Citation:** Journal, Vol(Issue), Pages` line in note body.

## v0.8.0 (2026-04-12)

### Added
- Citation graph exploration via Semantic Scholar API.
- `research-hub references <doi>` — list papers cited by this paper.
- `research-hub cited-by <doi>` — list papers that cite this paper.
- 2 new MCP tools: `get_references`, `get_citations` (16 total).

## v0.7.0 (2026-04-12)

### Added
- Daily research operations: `remove`, `mark`, `move`, `find`.
- Cluster CRUD: `clusters rename`, `clusters delete`, `clusters merge`, `clusters split`.
- Vault search: `research-hub find "query" [--full] [--cluster X] [--status Y]`.
- 6 new MCP tools (14 total): `remove_paper`, `mark_paper`, `move_paper`, `search_vault`, `merge_clusters`, `split_cluster`.

## v0.6.0 (2026-04-12)

### Added
- MCP stdio server for AI assistant integration. 8 tools exposed via `research-hub serve`.
- Tools: `search_papers`, `verify_paper`, `suggest_integration`, `list_clusters`, `show_cluster`, `export_citation`, `run_doctor`, `get_config_info`.
- Optional dependency `[mcp]` extra installs `fastmcp>=2.0`.

## v0.5.0 (2026-04-12)

**First public PyPI release.** `pip install research-hub-pipeline[playwright]`

### Added
- `research-hub init` — interactive setup wizard (vault + Zotero + Chrome)
- `research-hub doctor` — 7-check health diagnostic
- `research-hub install --platform X` — skill install for Claude Code / Codex / Cursor / Gemini CLI
- `research-hub verify --doi/--arxiv/--paper` — HTTP-based paper existence verification with 7-day cache
- `research-hub suggest <id> [--json]` — cluster + related-paper suggestions (keyword/tag/author/venue scoring)
- `research-hub cite <id> --format bibtex` — BibTeX / BibLaTeX / RIS / CSL-JSON export via pyzotero
- `research-hub notebooklm login --cdp` — CDP-attach login bypassing Google bot detection
- `research-hub notebooklm upload --cluster X` — auto-upload PDF + URL sources
- `research-hub notebooklm generate --type brief` — trigger NotebookLM artifact generation (fire-and-forget)
- NotebookLM selectors verified against live zh-TW DOM (2026-04-11)
- Bundle builder: author-year PDF filename matching fallback
- platformdirs config resolution (Linux XDG / macOS / Windows APPDATA)
- GitHub Actions: CI (3.10/3.11/3.12) + auto-publish to PyPI on tag push
- SKILL.md bundled in wheel for AI coding assistant discoverability
- Terminal output examples at `docs/examples/`

### Changed
- Package name: `research-hub` → `research-hub-pipeline` (PyPI)
- Config path: repo-local → `platformdirs.user_config_dir("research-hub")`
- `verify` subcommand: extended with `--doi/--arxiv/--paper` flags (repo-integrity check preserved as fallback)
- Pipeline DOI validation: replaced `"48550" in doi` heuristic with real HTTP HEAD checks
- `upload_cluster` + `generate_artifact`: default `headless=False` (visible Chrome)
- README: rewritten for pip-install-first audience (310 lines)

### Fixed
- `Path(__file__).parents[N]` repo-relative paths crash after pip install
- NotebookLM selectors: `source-stretched-button` → `add-source-button`, `source-panel` → `source-picker`
- Bundle builder: 0 PDFs when vault uses Author_Year filenames
- `token_set_ratio` threshold: 87 → 80 (cross-platform rapidfuzz compatibility)
- pytest-cov missing from dev dependencies

## v0.4.0 (2026-04-11)

### Added
- Tri-system cluster binding (Zotero + Obsidian + NotebookLM)
- `clusters bind/show/new/list` CLI
- `sync status/reconcile` for Zotero ↔ Obsidian drift
- `notebooklm bundle --cluster X` drag-drop fallback
- 142 tests

## v0.3.4 (2026-04-10)

### Added
- `research-hub status` dashboard
- `migrate-yaml` for legacy note patching
- Hub index overview page

## v0.3.0 — v0.3.3 (2026-04-10)

### Added
- Dedup index (DOI + title normalization)
- Topic clusters with seed keywords
- Bidirectional wikilink updater
- Cluster synthesis pages
- Semantic Scholar search stub

## v0.2.1 (2026-04-10)

### Added
- First public release (MIT license)
- Bilingual README (EN + zh-TW)
- CI on Python 3.10 / 3.11 / 3.12

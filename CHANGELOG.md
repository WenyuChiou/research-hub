# Changelog

## v0.13.0 (2026-04-12)

**Model-agnostic paper discovery + topic overview notes — the "any AI can drive it" release.**

Two tracks shipped together. Track A replaces single-backend Semantic Scholar search with a three-backend fallback chain (OpenAlex + arXiv + Semantic Scholar) exposed through CLI + MCP, so Claude Code, Claude Desktop, Codex CLI, Gemini CLI, Cursor, Continue, Aider, and plain-shell pipelines all discover papers the same way. Track B adds topic overview notes — every cluster now has a designated `00_overview.md` that any AI can write by reading a cluster digest. Research-hub is pure plumbing; the AI does the writing.

### Added — Track A: Multi-backend paper search + enrich mode

- **`src/research_hub/search/` package** (was single `search.py`) — 7 modules, 759 LOC total. Three backends implementing the `SearchBackend` protocol (`name`, `search`, `get_paper`):
  - **`OpenAlexBackend`** — free, concept search, no API key. Reconstructs abstracts from OpenAlex's inverted index representation. Extracts `arxiv_id` from location metadata. Uses polite-pool `mailto` query param for higher rate limits.
  - **`ArxivBackend`** — Atom XML parsing (stdlib `xml.etree.ElementTree`). 3s throttle per arXiv policy. Client-side year filtering. Strips version suffixes from arxiv IDs.
  - **`SemanticScholarClient`** — existing logic refactored into the backend interface, `year_to` parameter added.
- **`search/fallback.py::search_papers()`** — multi-backend orchestrator. First backend to return a dedup key (normalized DOI → arxiv_id → title) wins the base record; subsequent backends fill empty fields (abstract, pdf_url, citation_count, venue). Backends that raise are logged at WARNING and skipped — never propagates. Results sorted by year descending then citation_count descending.
- **`search/enrich.py::enrich_candidates()`** — resolves a list of heterogeneous candidates (DOI / arxiv ID / title) to full `SearchResult` records. Title matches require rapidfuzz similarity ≥ 60. Purpose-built for Claude Code's WebSearch path: WebSearch discovers candidates, `enrich_candidates` turns them into ingest-ready records using OpenAlex/arXiv/Semantic Scholar.
- **CLI surface:**
  - `research-hub search "..." --year 2024-2025 --min-citations 10 --backend openalex,arxiv --json` — multi-backend query with year window, citation floor, and JSON output for piping.
  - `research-hub search "..." --to-papers-input --cluster <slug>` — emits a ready-to-ingest `papers_input.json` document with empty summary/key_findings/methodology/relevance fields for the AI to fill.
  - `research-hub enrich [candidates...] | -` — new subcommand. Reads DOIs / arxiv IDs / titles from argv or stdin, outputs enriched JSON.
  - `--year` parser accepts `2024`, `2024-`, `-2024`, and `2024-2025`.
- **MCP surface:**
  - `search_papers` extended with `year_from`, `year_to`, `min_citations`, `backends` parameters (backwards compatible — old signature still works).
  - `enrich_candidates(candidates, backends)` — new tool.
  - **26 MCP tools total** (was 25).
- **Backwards compat** — all existing `from research_hub.search import {SearchResult, SemanticScholarClient, iter_new_results}` imports still resolve through `search/__init__.py` re-exports. `iter_new_results` accepts both the legacy single-client signature and new multi-backend signature.

### Added — Track B: Topic overview notes

- **`src/research_hub/topic.py`** (206 LOC) — new module for AI-writable cluster summaries. Research-hub does NOT call any LLM; it provides a digest and a writing target, and the AI does the actual writing.
- **File convention** — overview lives at `<vault>/research_hub/hub/<cluster-slug>/00_overview.md`. The `00_` prefix floats it to the top of Obsidian's default alphabetical folder view.
- **Template sections** — Definition / Why it matters / Applications / Key sub-problems / Seed papers / Further reading. Scaffolded with frontmatter (`type: topic-overview`, `cluster: <slug>`, `status: draft`).
- **CLI surface:**
  - `research-hub topic scaffold --cluster <slug> [--force]` — writes the overview template file. Raises `FileExistsError` without `--force`.
  - `research-hub topic digest --cluster <slug> [--out file.md]` — emits the full-text digest of every paper in the cluster (title + authors + year + DOI + abstract) as markdown. The AI reads this to write the overview.
  - `research-hub topic show --cluster <slug>` — prints the current overview content, or exits 1 with a "no overview" hint.
- **MCP tools (3 new, 29 tools total)**:
  - `get_topic_digest(cluster_slug)` — returns `{cluster_slug, cluster_title, paper_count, papers: [...], markdown}`.
  - `write_topic_overview(cluster_slug, markdown, overwrite=False)` — writes AI-generated markdown. Refuses to overwrite without explicit flag.
  - `read_topic_overview(cluster_slug)` — returns `{ok, markdown}` or `{ok: False, reason: "no overview found"}`.
- **Dashboard integration** — `ClusterCard.has_overview` field, populated from `overview_path().exists()`. Cluster card shows "overview" / "no overview" badge; heading links to Obsidian's `00_overview.md` when present.
- **Vault builder integration** — when rendering the cluster hub/index page, prepends the overview content (frontmatter + first H1 stripped) above the paper list, so the Obsidian hub page opens with the topic summary.

### Added — Docs

- **`docs/ai-integrations.md`** — complete integration guide for Claude Code, Claude Desktop, Cursor, Continue, Codex CLI, Gemini CLI, Aider, and plain-shell workflows. Shows the exact commands for each AI surface. Covers the shared `discover → enrich → ingest → overview → verify via NotebookLM` pattern.

### Fixed

- **CI MCP test failures** — `.github/workflows/ci.yml` now installs `[mcp,dev]` extras. Without fastmcp the `_FallbackMCP` was returning raw functions with no `.fn` attribute, breaking `test_mcp_add_paper`, `test_e2e_smoke::test_e2e_mcp_download_artifacts_tool`, and `test_e2e_smoke::test_e2e_read_briefing_missing_returns_remedy`.

### Tests

- **465 → 520 passing** (+55 tests, 5 skipped unchanged).
- Track A: 40 new tests — `test_openalex_backend` (7), `test_arxiv_backend` (6), `test_search_fallback` (7), `test_search_enrich` (5), `test_cli_search` (6), `test_mcp_server` additions (3), `test_search.py` dedup_key + backcompat (6).
- Track B: 15 new tests — `test_topic` (12), `test_cli_operations` topic tests (3).

### Non-breaking changes only

All existing CLI commands, MCP tool signatures, and import paths continue to work unchanged. The `search.py` module is deleted and replaced by the `search/` package, but the public re-exports make this invisible to callers.

## v0.12.0 (2026-04-13)

**Pipeline hardening + PDF-first NotebookLM bundling + Draft composer — the "vault → draft" transition release.**

Three tracks shipped together, driven by real user-pain caught during a live 22-paper ingest of an LLM harness engineering cluster.

### Added — Track A: Pipeline hardening

- **Full schema validator** — `_validate_paper_input` now checks all 12 required fields upfront (was 4 in v0.11.0). Missing fields are reported with the exact text to paste into `papers_input.json`. Prevents the "KeyError mid-ingest → orphaned Zotero item" failure mode.
- **`slug` + `sub_category` auto-generation** — minimal papers_input.json entries (4 fields) now work out of the box. Slug is derived from `{firstauthor_lastname}{year}-{slugified_title}`; `sub_category` defaults to the cluster slug.
- **Collection-scoped `check_duplicate`** — `zotero/client.py::check_duplicate` gains optional `collection_key` kwarg. Library-wide search was producing false-positive skips when a paper existed in a different cluster's collection. New CLI flag `research-hub ingest --allow-library-duplicates` explicitly bypasses the dedup check.
- **`research-hub pipeline repair --cluster X`** — new subcommand that reconciles Zotero collection ⇄ Obsidian notes ⇄ dedup_index for a given cluster. Finds orphaned Zotero items (no Obsidian note), orphaned notes (no Zotero item), and stale dedup entries. Default dry-run; requires `--execute` to actually write.
- **`docs/papers_input_schema.md`** — rewritten with the full field reference, minimal + complete examples, and common-errors section.

### Added — Track B: PDF-first NotebookLM bundling

- **`research-hub notebooklm bundle --download-pdfs`** — new flag that tries to acquire a local PDF before falling back to URL upload. NotebookLM ingests local PDFs ~6× faster than URLs (it has to fetch + parse URLs server-side at 15-30s each).
- **`notebooklm/pdf_fetcher.py`** — new module with a 4-step fallback chain:
  1. Local cache by DOI (`<pdfs_dir>/<normalized_doi>.pdf`)
  2. Local cache by slug (`<pdfs_dir>/<slug>.pdf`)
  3. arXiv (`https://arxiv.org/pdf/<arxiv_id>.pdf` when the DOI is arxiv)
  4. Unpaywall API (free tier, OA-only papers)
- **Graceful handling of non-downloadable papers** — paywalled without OA, reports, timeouts, and oversized (>50 MB) PDFs all fall through to URL upload without erroring out. `BundleEntry.pdf_source` records provenance for the summary (`local-doi`, `arxiv`, `unpaywall`, etc).
- **Bundle summary** now breaks down by PDF source: `pdf: 22 (arxiv: 19, local-doi: 3, unpaywall: 0)`.

### Added — Track C: Draft composer

- **`research-hub compose-draft --cluster X --outline "Intro;Methods;Results" --style apa`** — new CLI that assembles captured quotes into a markdown draft. Supports APA / Chicago / MLA / LaTeX citation styles. Quotes are assigned to sections by matching `quote.context_note` against outline entries (case-insensitive substring); unmatched quotes land in the first section. Default output path: `<vault>/drafts/<YYYYMMDD>-<cluster>-draft.md`.
- **`src/research_hub/drafting.py`** — new module with `DraftRequest`, `DraftResult`, `compose_draft()`, `compose_draft_from_cli()`, and `DraftingError`. Reuses existing `writing.py` functions (`load_all_quotes`, `build_inline_citation`, `build_markdown_citation`, `resolve_paper_meta`) — no duplication.
- **MCP tool `compose_draft(cluster_slug, outline, quote_slugs, style, include_bibliography)`** — lets AI agents assemble drafts programmatically. Returns `{status, path, cluster_slug, quote_count, cited_paper_count, section_count, markdown_preview}`. **25 MCP tools total** (was 24).
- **Dashboard Writing tab composer panel** — new right column at >=900px: cluster picker, outline textarea, style radios, include-bibliography checkbox, quote multi-select (tied to left-column cards), and a `[Build draft command]` button that emits the exact `research-hub compose-draft ...` invocation and copies it to clipboard (same pattern as Manage tab).

### Changed

- NotebookLM briefing language note: briefings are generated in the language of the Google account's UI locale. To get English briefings for English users, set the Google account language to English before generating. A dedicated `research-hub briefings translate` feature is deferred to v0.13.

### Tests

- **417 → 465 passing** + 5 skipped. 48 new tests across the three tracks:
  - 30+ in `test_pipeline_schema_v012.py`, `test_pipeline_repair.py`, and updated `test_pipeline_metadata.py` / `test_pipeline.py`
  - 21 in `test_pdf_fetcher.py` + updated `test_notebooklm_bundle.py`
  - 22 in `test_drafting.py`, `test_dashboard_sections_v2.py`, `test_mcp_server.py`, `test_consistency.py`

## v0.11.0 (2026-04-12)

**Writing helpers — inline citations, quote capture, and a Writing tab to close the loop from "found it" to "used it in a draft".**

### Added
- **`research-hub cite --inline`** — emits an inline-style citation like `(Lamparth et al., 2024)` instead of full BibTeX. Useful in draft prose.
- **`research-hub cite --markdown`** — emits a markdown link with the DOI: `[Lamparth et al. (2024)](https://doi.org/10.1609/aies.v7i1.31681)`.
- **`research-hub cite --style apa|chicago|mla|latex`** — picks the inline format. APA is default. LaTeX style derives a BibKey from the paper slug (`\citep{lamparth2024human}`).
- **`research-hub quote <slug> --page 12 --text "..."` + `--context "..."`** — captures an excerpt from a paper into `<vault>/.research_hub/quotes/<slug>.md` with a small frontmatter block per quote (page, captured_at, context_note).
- **`research-hub quote list [--cluster SLUG]`** — browse captured quotes.
- **Dashboard Library tab** — every paper row now has a `[Quote]` button next to `[Cite]`. Clicking opens a popup with page + text + context fields and builds the exact `research-hub quote ...` command for you.
- **New Dashboard tab: Writing** (order 35, between Briefings and Diagnostics) — lists captured quotes grouped by cluster and papers marked `status: cited`. Each quote card has `Copy as markdown` and `Copy inline` action buttons.
- 3 new MCP tools (24 total):
  - `build_citation(doi_or_slug, style)` — returns `{inline, markdown}` for a paper so AI agents can build citations for your draft
  - `list_quotes(cluster_slug)` — lists captured quotes
  - `capture_quote(slug, page, text, context)` — saves a quote from the agent side
- **New module `src/research_hub/writing.py`** — holds the citation formatters, `Quote` dataclass persistence, and `resolve_paper_meta` helper that reads an Obsidian note's frontmatter to pull authors/year/title/doi.
- **New section module `src/research_hub/dashboard/writing_section.py`** — the Writing tab renderer.

### Changed
- Dashboard `DashboardData` now carries a `quotes: list[Quote]` field populated from `<vault>/.research_hub/quotes/*.md` on each render.
- `SKILL.md` documents the new `quote`, `cite --inline`, `cite --markdown`, and dashboard Writing tab.

### Tests
- Suite: **386 → 417 passing** + 5 skipped.
- 12 new tests in `tests/test_writing.py` covering the inline/markdown formatters, quote persistence (save + load + multi-block files), and frontmatter resolver.
- 7 new tests in `tests/test_dashboard_sections_v2.py` for the Writing section (empty state, quote cards, grouping by cluster, cited paper listing).
- Updated `test_header_section_renders_tabs` to expect the 6th tab radio.

## v0.10.0 (2026-04-12)

**Dashboard redesign — "personal knowledge garden" for AI-assisted literature review.**

The dashboard now answers a single question: *"AI added a bunch of papers — what did it add, what categories, and where is each one stored across Zotero / Obsidian / NotebookLM?"*

### Added
- **Five-tab audit dashboard** (`Overview` / `Library` / `Briefings` / `Diagnostics` / `Manage`). Pure CSS tabs (radio + `:checked` sibling selectors) — zero JavaScript for the tab mechanic. Default tab is Overview.
- **Overview tab** — three widgets:
  - **Treemap** of papers per cluster, sqrt-scaled flex weights so a 7/8/331 distribution stays readable (cluster names no longer get squeezed). Click any cell to jump to that cluster in the Library tab.
  - **Storage map** — per-cluster table with clickable `↗ Open` deep-links to each of the three systems: `zotero://select/library/collections/{key}`, `obsidian://open?path=raw/{slug}`, and the cluster's NotebookLM notebook URL.
  - **Recent additions** feed — last 15 papers your AI agent ingested, each with a cluster tag, relative time, and inline [Open] menu.
- **Library tab** — cluster cards with paper rows (title, authors, year, 240-char abstract, [Cite] popup, [Open ▼] menu). Per-cluster [Download .bib] button for batch citation export. NO status badges, NO reading-status pills — this is a locator, not a progress tracker.
- **Briefings tab** — inline preview of downloaded NotebookLM briefings with [Open in NotebookLM] and [Copy full text] actions.
- **Diagnostics tab** — health badges (Zotero / Obsidian / NotebookLM) + drift alerts + clickable remedy commands.
- **Manage tab** — per-cluster command-builder forms: rename, merge, split, bind-Zotero, bind-NLM, delete. Each form emits the exact `research-hub clusters …` CLI command on click and copies it to your clipboard.
- **Debug widget** — footer section with a "Copy snapshot" button that emits vault metadata + health state + cluster bindings as a paste-ready blob for AI assistant handoff. Closes the user feedback loop when something breaks.
- **Health banner** — when `doctor` reports any FAIL, the Overview tab shows a red banner at the top with the failing checks and their remedy commands.
- **`--watch` mode** — `research-hub dashboard --watch` polls vault state files every 5s and re-renders on change. Combine with `--refresh N` to control the browser auto-reload interval.
- **`--rich-bibtex` flag** — opt-in Zotero `get_formatted` per paper for full BibTeX entries (abstract, tags, collections). Default uses an instant frontmatter fallback — generation is under a second on a 346-paper vault.
- **Impeccable design tokens** — OKLCH-only color palette, warm-amber brand hue (not default blue), tinted neutrals, 4pt spacing scale, Geist/Literata/Geist Mono typography stack. Light theme.

### Changed
- Dashboard package now split into 6 modules: `types.py` (dataclass contract), `data.py` (vault walker), `citation.py`, `drift.py`, `briefing.py`, `sections.py`, `render.py`, plus inline `template.html` / `style.css` / `script.js`. Extensible via the `DashboardSection` base class.
- Dashboard render time on the 346-paper live vault: **0.9 seconds** (was 10+ minutes when the rich-BibTeX path was the default).
- Zotero credential loader now supports three file layouts: flat keys, nested `zotero.*` block, and the legacy `~/.claude/skills/zotero-skills/config.json` left over from the standalone zotero-skills install. Users who set up Zotero months ago no longer need to re-init.
- `doctor` routes all Zotero credential reads through the shared `_load_credentials()` helper so the health check sees exactly the same keys as the dashboard and the pipeline.
- Dashboard no longer renders per-paper Z/O/N sync badges or reading-status pills — they were fighting Zotero/Obsidian for the same real estate. Cross-system state is shown at the cluster level in the Storage map instead.

### Fixed
- **Chrome file:// security violation.** The Manage tab forms had no `action` attribute, so pressing Enter in an input field submitted to the current URL — which on `file://` triggers Chrome's "unsafe attempt to load URL from frame" block. Forms now carry `action="javascript:void(0)"` and the script.js submit handler routes Enter to the "Copy command" button.
- **Same security violation from treemap cells** — they used `<a href="#tab-library">`, which also trips the file:// check. Replaced with `<button data-jump-tab="library">` + a click handler that selects the target tab radio without navigating the URL.
- **331 missing [Cite] buttons** — `citation.py` caught the Zotero API error and returned `""` instead of falling through to the frontmatter fallback. Now every paper gets a valid BibTeX entry regardless of API availability.
- **Tab panels rendering blank** — CSS `:checked ~ main #tab-*` sibling selector was wrong because the radios are inside `<main>`, not siblings of it. Replaced with `:checked ~ #tab-*` direct sibling.
- **Treemap label overflow** for long cluster names. Added `-webkit-line-clamp: 3`, bumped min-width 140 → 200px and min-height 90 → 140px.
- `_detect_persona` no longer forces `analyst` when `zot=None` — persona is a config-time setting, not derived from runtime client state.
- `generate_dashboard` now instantiates `ZoteroDualClient` (has `get_formatted`) instead of the raw pyzotero `Zotero` object when the api_key is actually loadable.

### Tests
- Suite: **361 → 386 passing** (5 legacy v0.9.0-G1 section tests marked as `@pytest.mark.skip("rewritten in v0.10")`).
- 14 new tests for the dashboard data layer (`tests/test_dashboard_data.py`).
- 23 new tests for the dashboard sections layer (`tests/test_dashboard_sections_v2.py`).

## v0.9.0 (2026-04-12)

**System integration audit + UX hardening + personal HTML dashboard + closes the AI loop with NotebookLM artifact download.**

### Added
- `research-hub notebooklm download --cluster X --type brief` — downloads the latest generated briefing from NotebookLM back to `<vault>/.research_hub/artifacts/<cluster>/brief-<UTC>.txt`. Reads `span.notebook-summary .summary-content` from the DOM directly (no clipboard juggling, locale-independent). **Closes the AI loop**: search → save → upload → generate → **download** → AI analysis.
- `research-hub notebooklm read-briefing --cluster X` — prints the most recently downloaded briefing for inline AI analysis.
- 2 new MCP tools: `download_artifacts(cluster_slug, artifact_type)`, `read_briefing(cluster_slug)` — let AI agents pull briefings into context without re-running NotebookLM.
- `research-hub dashboard [--open]` — personal HTML dashboard at `<vault>/.research_hub/dashboard.html`. Single self-contained file with stat cards, cluster table, status badges, and NotebookLM links. Hero artifact for the project.
- `research-hub add <doi-or-arxiv-id> [--cluster X]` — one-shot Search → Save replaces hand-writing `papers_input.json`. Fetches metadata via Semantic Scholar with CrossRef enrichment.
- `research-hub init --persona researcher|analyst` — analyst persona skips Zotero entirely (Obsidian + NotebookLM only).
- `research-hub dedup invalidate --doi/--path` and `dedup rebuild [--obsidian-only]` — surgical dedup management without re-scanning Zotero.
- `papers_input.json` validator: pipeline catches missing `creatorType`, malformed authors, missing fields BEFORE hitting Zotero API. Clear error messages instead of cryptic 400 crashes.
- 4 new MCP tools total: `add_paper`, `generate_dashboard`, `download_artifacts`, `read_briefing` (21 total).
- New docs: `docs/cli-reference.md`, `docs/papers_input_schema.md`.

### Changed
- `doctor` now persona-aware: when `no_zotero: true` is set in config or `RESEARCH_HUB_NO_ZOTERO=1` env var, Zotero checks report "Skipped (analyst mode)" instead of FAIL.
- `doctor` correctly counts dedup index entries (was reporting 0 when index had thousands).
- `nlm_cache.json` now records `artifacts.brief = {path, downloaded_at, char_count, titles}` per cluster after a successful download.

### Fixed
- Pipeline silently dropped dict-format authors `[{firstName, lastName}]` → `authors: "Unknown"` in Obsidian YAML.
- Pipeline never wrote `volume`, `issue`, `pages` to Zotero or Obsidian even when input had them.
- `clusters rename` updates display name without orphaning notes.
- 12 new regression tests for pipeline metadata and dedup invalidation.
- 4 new tests for the briefing download / read flow (mocked CDP session).

Suite: 274 → 338 passing.

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

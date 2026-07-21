# Ingest pipeline architecture

The ingest pipeline turns a topic string (or an explicit `papers_input.json`) into: Zotero items in a cluster collection, one Obsidian markdown note per paper, refreshed hub navigation pages, and — optionally — a NotebookLM notebook with a generated brief. Two modules own the flow:

1. `src/research_hub/auto.py` — `auto_pipeline()`, the end-to-end orchestrator behind `python -m research_hub auto "<topic>"` ("lazy mode"): cluster create-or-get → search → fit-check → ingest → post-ingest enrichment → NotebookLM.
2. `src/research_hub/pipeline.py` — `run_pipeline()`, the ingest core behind `python -m research_hub ingest`: input validation → authenticity gate → dedup → Zotero writes → Obsidian notes → hub overview sync. `auto_pipeline` calls it as step 5.

The same ingest core is also reachable through the MCP server (`mcp_server.py`), the REST API (`api/v1.py`, `post_auto` / `post_search`), and the dashboard's action executor — all four surfaces converge on `auto_pipeline` / `run_pipeline`, so guards that live there (the append/force guard, the fail-closed relevance gate) protect every caller, not just the CLI.

## Stage 1 — Discovery

Discovery lives in `src/research_hub/search/` behind `search_papers()` in `search/fallback.py`. Backends are pluggable classes (`arxiv_backend.py`, `semantic_scholar.py`, `openalex.py`, `crossref.py`, `pubmed.py`, `dblp.py`, `biorxiv.py`, `chemrxiv.py`, `nasa_ads.py`, `repec.py`, `ssrn_backend.py`, `eric.py`, `cinii.py`, `kci.py`, `google_scholar_backend.py`, `websearch.py`), fanned out per query and merged with ranking in `_rank.py`.

- The default backend set is `DEFAULT_BACKENDS = ("openalex", "arxiv", "semantic-scholar", "crossref", "dblp")` so one rate-limited backend cannot sink a run.
- `--field` selects a preset from `FIELD_PRESETS` (e.g. `bio`/`med` add PubMed and bioRxiv, `econ`/`social` add RePEc and SSRN, `astro` adds NASA ADS); `REGION_PRESETS` covers `jp`/`kr`/`cjk` via CiNii and KCI.
- `--peer-reviewed` excludes gray document types (`GRAY_DOC_TYPES`: preprints, reports, datasets, ...) and applies a minimum-confidence floor.

`auto.py:_run_search()` wraps `search_papers()` and converts results into papers-input dicts via `discover._to_papers_input()`. `discover.py` also implements the separate staged, human-in-the-loop `discover` flow (state machine `new → scored_pending → done` persisted under `.research_hub/discover/<cluster>/`), which stages candidates and an AI scoring prompt instead of ingesting immediately.

Between search and ingest, `auto_pipeline` runs a **fail-closed relevance fit-check**: an LLM CLI detected on PATH (`llm_cli.detect_llm_cli`) judges each candidate against the cluster definition; papers scoring below the threshold (default 3) are quarantined, never written. If no judge CLI is on PATH, the run aborts *before* the search step with explicit alternatives (`--no-fit-check`, or `--no-llm-fit-check` for rule-based term-overlap filtering) rather than silently ingesting unjudged papers.

## Stage 2 — Zotero save: the local-API / Web-API boundary

All Zotero traffic goes through `src/research_hub/zotero/client.py`, which defines the key boundary:

- **Local API** — Zotero desktop's HTTP endpoint at `http://localhost:23119/api` (`LOCAL_API_BASE`, probed by `check_local_api()`). Fast, no network round-trip, **read-only**.
- **Web API** — `api.zotero.org` via pyzotero, authenticated with `ZOTERO_API_KEY` / `ZOTERO_LIBRARY_ID` (resolution order in `_load_credentials()`: env vars → `~/.claude/.env` → research-hub `config.json` → the legacy standalone zotero-skills config). **All writes go here** — the local API does not support writes.

Two client shapes implement the split:

- `get_client()` returns a plain pyzotero **Web API** client. This is what `run_pipeline` uses for ingest, since ingest is write-heavy (item creation, tags, notes, collections).
- `ZoteroDualClient` tries the **local API first for reads** (verifying with a real request at construction) and transparently falls back to the Web API when Zotero desktop is not running or the connection drops mid-run (`_read()` flips `local_available` on connection errors). Writes always route to `self.web`, with `create_items` chunked 50 at a time. The read-heavy surfaces use it: `cli_zotero`, `cli_citations`, `cli_clusters`, and `clusters.py` collection management.

Inside `run_pipeline`, `write_papers_to_zotero()` builds one pyzotero item template per paper (type inferred by `_zotero_item_type`, DOI-prefix venue overrides applied via `zotero/doi_overrides.py`), tags it with hub-namespace tags (`_compose_hub_tags`), routes it to the cluster's collection plus a per-batch subcollection, and flushes in batches of `ZOTERO_BATCH_SIZE = 50`. `_flush_batch` handles partial batch responses carefully: items absent from both the `successful` and `failed` buckets are retried **individually** so each paper gets its own key — never borrowing another paper's key (the STAB-1 rule against silently cross-linking distinct papers onto one item). Each created item also gets an HTML child note (`add_note` / `_build_note_html`).

Setting `RESEARCH_HUB_NO_ZOTERO=1` skips Zotero entirely ("data analyst mode": Obsidian + NotebookLM only), with a loud stderr warning that the cluster's Zotero collection will not receive the papers.

## Stage 3 — Obsidian note generation

After Zotero writes (and DOI/arXiv verification when `--verify` is passed; `auto` runs with `verify=False`), `run_pipeline` writes one markdown note per paper to `raw/<cluster-slug>/<paper-slug>.md` via `_render_obsidian_note()`, then:

- registers the note in the **dedup index** (`DedupHit(source="obsidian", ...)`),
- updates cluster wikilinks (`update_cluster_links`),
- appends a `manifest.jsonl` entry (`action="new"`, with DOI, title, Zotero key, batch label).

The manifest (`manifest.py`, at `.research_hub/manifest.jsonl`) is the append-only audit log of every ingest decision — actions include `new`, `dup-obsidian`, `ingest-reuse-zotero`, `quarantine`, `pdf-attach`, and `error`.

## Stage 4 — Hub index rebuild

Navigation artifacts are refreshed twice, at two granularities:

- Per ingest, `run_pipeline._sync_hub_overview()` derives MOC links for the cluster (`derive_moc_links` / `ensure_moc`) and rewrites the cluster's `00_overview.md` (`populate_overview` in `vault/hub_overview.py`), then `_refresh_cluster_base()` regenerates the cluster's Obsidian `.base` view.
- Per `auto` run (when at least one note was written), `auto_pipeline` calls `vault/hub_overview.populate_all_overviews()` to refresh the vault-wide layer: `_HOME.md`, every `hub/_moc/*.md` body, and every cluster's overview. This is best-effort — a render failure logs a warning without sinking the ingest.

## Stage 5 — NotebookLM upload

The NotebookLM leg (skippable with `--no-nlm`) lives in `src/research_hub/notebooklm/` and runs four sub-steps, mirroring the connector Protocol:

1. **Bundle** (`bundle.py:bundle_cluster`) — walk the cluster's notes, pick per-paper sources (a matched local PDF by DOI or Author_Year filename, else a quality-screened URL, else abstract text) into a bundle report.
2. **Upload** (`upload.py:upload_cluster`) — find-or-create a notebook named after the cluster and upload each source; suspect URLs (error-page titles, dataset DOIs) are screened out unless `--include-suspect-urls`.
3. **Generate** (`upload.py:generate_artifact`) — trigger brief generation.
4. **Download** (`upload.py:download_briefing_for_cluster`) — save the brief under the vault's artifacts.

Transport is **not** ad-hoc browser automation: `notebooklm/client.py` is a thin synchronous adapter over the async `notebooklm-py` upstream client, doing authenticated RPC calls from a stored browser-session state file (`auth.py`, `state.json` under the research-hub dir; obtained via `notebooklm login`). `auto_pipeline` runs a session-health preflight first and, if the session is invalid, defers the whole NLM leg with a `notebooklm login --auto-detect` hint. NotebookLM failures are always **deferred, not fatal** (`report.nlm_deferred = True`, `report.ok` stays `True`): the papers are already in the vault, so the run reports success with a retry path — unlike search or ingest failures, which stop the run.

## Idempotency and dedup

Dedup is layered; each layer catches a different duplicate class (all in `pipeline.py` + `dedup.py`):

- **Persistent dedup index** (`.research_hub/dedup_index.json`, `DedupIndex`) keys hits by normalized DOI *and* normalized title (titles only when >15 normalized chars, to avoid false merges), with sources `obsidian` and `zotero`. It is rebuilt from the vault + Zotero when empty.
- **In-batch dedup** collapses two search backends returning the same paper under different DOIs (journal DOI vs preprint DOI) before Zotero creation, keeping the first occurrence — otherwise both would get Zotero items and their notes would collide on one filename slug.
- **Obsidian hit** → skip, but only when the note file *actually exists* (a stale index entry pointing at a deleted note must not block re-ingest); the existing note gets the new cluster query appended and links updated (`action="dup-obsidian"`).
- **Zotero hit** → the paper is *not* skipped: the existing item is reused (moved into the cluster collection, missing hub tags and child note added, no duplicate item created) and the paper continues to Obsidian-note creation with the reused key (`action="ingest-reuse-zotero"`).
- **Library-wide `check_duplicate`** against Zotero itself, relaxable with `--allow-library-duplicates`.

Other idempotency points: `auto` refuses to ingest into a cluster that already has notes unless `--append` (add) or `--force` (which really overwrites — it clears `raw/<slug>/*.md` first, scoped to Obsidian only, never deleting Zotero items or NotebookLM sources); PDF attach silently skips items that already have a PDF; the cluster-overview autofill skips when a hand-curated TL;DR exists; NotebookLM upload reuses an existing notebook with the same cluster name. Concurrency: each `auto` run writes its candidate list to a per-run path (`.runs/<slug>-<pid>/papers_input.json`) threaded into `run_pipeline`, so concurrent runs cannot clobber each other through the shared default `papers_input.json`.

Before any write, every candidate also passes the **authenticity gate** (`authenticity.py:verify_authenticity`): layered checks (L0 input sanity, L1 DOI registration — with transient resolver failures marked `L1-deferred` and retryable rather than rejected, L3 metadata integrity, L4 relevance fit-check) quarantine failures with a manifest entry instead of writing them. If every candidate is quarantined, `auto` reports the ingest step as a failure with honest counts — it never prints "OK, N papers" for an empty vault.

## Package boundaries

- `search/` — discovery only. Consumes a query, produces ranked `SearchResult`s; knows nothing about Zotero or the vault.
- `zotero/` — the Zotero seam. `client.py` (credentials, local/Web split, dual client), `pdf_attach.py` (open-access PDF lookup via OpenAlex/Unpaywall/arXiv/Crossref and attachment upload), `doi_overrides.py`, `fetch.py`, `enrich.py`, `gc.py`.
- `notebooklm/` — the NotebookLM implementation (`auth.py`, `bundle.py`, `upload.py`, `download.py`, `client.py` over `notebooklm-py`).
- `connectors/` — the *abstraction* over external publish targets: a `Connector` Protocol with `bundle → upload → generate(brief) → download` and typed report dataclasses. `_notebooklm_adapter.py` wraps the existing NotebookLM code without modifying it; `null.py` is the no-op reference implementation for tests and dry runs. New destinations implement the Protocol rather than being wired into `auto.py`.
- `api/` — REST surface (`v1.py` request handlers such as `post_auto` / `post_search` / `get_cluster_quarantine`, `jobs.py` for async job tracking). Thin: validates request bodies and delegates to the same orchestration functions.
- `dashboard/` — local HTML dashboard (`http_server.py`, `render.py`, `sections.py`, `executor.py` for action buttons). Reads vault state and *triggers* pipeline runs; owns no ingest logic.
- `vault/` — Obsidian-side operations: hub overview/MOC/home rendering, cleanup, gc, sync, repair.

Data handoffs are plain dicts and files: search results → papers-input dicts (`discover._to_papers_input`) → per-run `papers_input.json` → `run_pipeline` → notes in `raw/<slug>/` + `manifest.jsonl` + `dedup_index.json` + `logs/pipeline_output.json` → NotebookLM bundle dir → brief artifact.

## End-to-end walkthrough: `python -m research_hub auto "battery degradation modeling"`

Grounded in `auto.py:auto_pipeline()` (dispatched from `cli_pipeline.py:_auto`):

1. **Cluster** — slugify the topic; create the cluster in `ClusterRegistry` if missing, refresh the vault graph config, and auto-create + bind a Zotero collection (probing for an existing collection by name first, and best-effort nesting it under the configured parent collection so ingest has a target without a manual `clusters bind`).
2. **Guard** — if the cluster already has notes in `raw/<slug>/` and neither `append` nor `force` was passed, abort fail-closed. `--dry-run` prints the full step plan here and exits.
3. **Judge preflight** — if the LLM fit-check is on but no judge CLI is on PATH, abort *before* searching (see Stage 1).
4. **Search** — `_run_search` fans out over the resolved backends with `max_papers` (default 8), year and peer-review filters; zero results or a search exception stops the run.
5. **Fit-check** — LLM-judge (or term-overlap) scores each candidate; low scorers are quarantined.
6. **Ingest** — survivors are written to the per-run `papers_input.json` and `run_pipeline` executes Stages 2–4 above (authenticity gate → dedup → Zotero batches → notes → cluster overview). Afterwards `auto` recounts `raw/<slug>/*.md` so the reported ingest count reflects what actually reached the vault, cleans up the per-run dir, and refreshes vault-wide navigation.
7. **Enrichment (best-effort)** — `--with-summary` fills both note-summary layers (`## Summary` one-liner plus Key Findings / Methodology / Relevance) via the detected LLM CLI; the cluster overview is auto-filled; `--with-pdfs` attaches open-access PDFs to the just-created Zotero items.
8. **NotebookLM** — session preflight, then bundle → upload → generate brief → download brief; any failure is deferred with a retry hint.
9. **Report** — an `AutoReport` (per-step results, counts, notebook URL, brief path) is returned; the CLI prints a Next Steps banner and, with `--json`, emits the report as JSON.

For per-flag detail see [docs/cli-reference.md](../../docs/cli-reference.md) and [docs/lazy-mode.md](../../docs/lazy-mode.md); NotebookLM setup lives in [docs/notebooklm.md](../../docs/notebooklm.md). Related pages: [CLI module map](../cli/modules.md), [vault maintenance](../operations/vault-maintenance.md).

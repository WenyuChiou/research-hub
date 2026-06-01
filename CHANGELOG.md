# Changelog

> **Format (v0.95.0+):** entries follow a lightweight
> [Keep a Changelog](https://keepachangelog.com) convention going
> forward — within each version use `### Added / Changed /
> Deprecated / Removed / Fixed / Security` where applicable, and
> flag breaking changes with a **BREAKING:** prefix. Per-release
> migration steps are mirrored in [UPGRADE.md](UPGRADE.md). Entries
> before v0.95.0 predate this convention and are kept verbatim
> (retrofitting 90+ historical entries was judged higher-risk than
> the consistency gain — G4 audit #3).

## [Unreleased]

_Phase B (UI 80/20 — ⌘K command palette + mobile breakpoints +
`_HOME` wayfinding) and Phase D (Zotero metadata correctness —
type-aware `itemType` mapping + `fit/<bucket>` tag + provenance
child-note parity) are staged on `feature/v1.1-ui-80-20` for **v1.1**.
UI scope is capped: the dashboard stays a thin status-mirror +
palette + onboarding demo; no 3-pane / citation-graph rebuild (link
out to the real tools instead)._

### Added

- **Dashboard surfaces fit-check quarantined papers** (FUNC-1 dashboard half).
  The Diagnostics tab gains a "Quarantined (N)" card listing papers the
  authenticity gate rejected (slug / cluster / layer / reason / date) --
  completing FUNC-1 alongside the existing MCP `list_quarantine` and REST
  `GET /clusters/{slug}/quarantine`. Additive: new `QuarantineRecord` +
  `DashboardData.quarantined`, collected best-effort so a missing quarantine
  store never breaks dashboard render.

### Changed

- **User-Agent centralized in `research_hub._useragent` (ARCH-1).** The ~22
  hardcoded `research-hub/<version>` UA literals across the search backends and
  verify / operations / importer / notebooklm now build from
  `research_hub.__version__` via `user_agent()`. This fixes 3 STALE pins
  (`0.4.1`, `0.9.0`, `0.43`) that had drifted off the real version, and a
  version-scan gate test (`test_useragent_version_sync.py`) now fails CI if any
  hardcoded UA literal is reintroduced.

### Fixed

- **REST `_optional_bool` coerces string booleans.** `POST /api/v1/auto` (and
  other bool flags) now accept case-insensitive `"true"`/`"false"` strings (REST
  clients commonly send string bools); other non-bool values still return 400.
- **`auto --force` genuinely overwrites.** `force=true` was previously a no-op
  beyond the FUNC-2 guard (indistinguishable from `--append`); it now clears the
  cluster's `raw/<slug>/*.md` notes before re-ingest (scoped, non-recursive,
  never on dry-run; Zotero / NotebookLM are not pruned). `--force --dry-run`
  advertises the clear step in the plan so the destructive action is previewable.
- **`zotero.fetch.get_notes` no longer swallows all exceptions.** Narrowed a
  bare `except:` to `except Exception` + a warning so KeyboardInterrupt /
  SystemExit propagate and real fetch errors surface (best-effort `[]` fallback
  retained).
- Added functional-test coverage for the `restore_quarantine` MCP tool.


## [1.0.1] - 2026-06-01

### Added

- **`tests/test_skill_structure.py`** — structural + trust invariants for
  the 11 `SKILL.md` files, closing the gap an ai-research-skills quality
  audit (2026-05-28) flagged: frontmatter shape and the installer mirror
  were already tested, but three guarantees were defended only by
  convention. Now asserted on every PR: (1) the ≤500-line
  progressive-disclosure ceiling (max today is research-hub at 244);
  (2) anti-fabrication safety strings survive every reword/sync
  (`research-hub` "Do not invent", `paper-memory-builder` `status: gap`,
  `paper-summarize` "hallucinated", `notebooklm-brief-verifier` "do NOT
  assume coverage"); (3) the sibling disambiguation arrows that keep
  auto-trigger from mis-firing (the paper-summarize / paper-memory-builder
  / literature-triage-matrix trio name each other; `zotero-library-curator`
  names `zotero-skills`; `gap-to-topic` names `literature-triage-matrix`
  + `research-design-helper`). Test-only — no skill content changed; all
  21 parametrized cases pass against the current files.

### Changed

- **`cli.py` god-file split into `cli_*` domain modules (ARCH-2).** The
  8439-line `src/research_hub/cli.py` was broken into focused sibling modules
  (`cli_common`, `cli_citations`, `cli_search`, `cli_notebooklm`, `cli_zotero`,
  `cli_summarize`, `cli_clusters`, `cli_vault`, `cli_pipeline`, `cli_paper`,
  `cli_maintenance`); cli.py is now 3654 lines (−57%) and retains only the
  orchestrator core (`build_parser`, `_main_dispatch`, `main`,
  `_sync_cli_dependencies`). Pure move — byte-faithful handler bodies, no
  behaviour change; the CLI / MCP / REST surface is unchanged and the test
  files were not modified. Each domain module re-exports through cli.py and a
  `_sync_cli_dependencies()` forwarder keeps test monkeypatches on
  `research_hub.cli.*` reaching the relocated handlers. Also deduped the
  triplicated `_load_zotero_if_configured` into a single canonical `cli_common`
  definition and removed a dead, uncalled `_read_doi_from_frontmatter` copy.
- **MCP tool docstrings rewritten for 12 worst-scoring tools (Glama
  TDQS lift)** (`mcp_server.py`). Replaced terse one-line docstrings on
  the 12 tools that Glama's Tool Definition Quality Score flagged as
  weakest (`cluster_rebind`, `ask_cluster`, `discover_continue`,
  `prune_cluster`, `discover_variants`, `examples_show`, `autofill_emit`,
  `autofill_apply`, `fit_check_audit`, `fit_check_drift`,
  `apply_fit_check_to_labels`, `propose_cluster_rebind`). New docstrings
  hit all six TDQS dimensions — Behavior (verb-first opening),
  Conciseness, Completeness (full Returns dict-key list),
  Parameters (per-arg semantics + defaults + valid values),
  Purpose (relationship to neighbouring tools, deprecated-alias
  cross-refs), Usage Guidelines (When to use / When NOT to use
  bullets). The four canonical tools that LLM clients hit most
  (`cluster_rebind`, `ask_cluster`, `discover_continue`,
  `prune_cluster`) get the full multi-line template; the other eight
  get a compact 1-line-per-section variant. Zero behavioural change —
  function bodies / signatures / decorators byte-identical, only
  docstring text differs. Full pytest suite green (3101 passed).
  Expected TDQS impact: individual tool scores 1.8-2.4/5 lift toward
  3-4/5; overall quality grade C should move to B-ish after Glama
  re-introspects on the next release.
- **MCP deprecated aliases hidden from default surface (env-gated)**
  (`mcp_server.py`, `tests/_mcp_helpers.py`). The 10 deprecated MCP tool
  aliases that were already scheduled for v2.0.0 removal are now hidden
  from the default `@mcp.tool()` registration. Glama's Tool Definition
  Quality Score (TDQS) penalises high tool count + poor disambiguation;
  this drops the LLM-facing surface from 86 → 76 tools without breaking
  the v1.x SemVer promise (the functions remain importable as Python
  module attributes; only the FastMCP registration is gated).
  Hidden by default — set `RESEARCH_HUB_MCP_INCLUDE_DEPRECATED=1` to
  re-expose them during your migration window.
  Affected aliases (use the canonical replacement going forward):
  ```
  propose_cluster_rebind  → cluster_rebind(action='propose')
  apply_cluster_rebind    → cluster_rebind(action='apply')
  list_orphan_papers      → cluster_rebind(action='list_orphans')
  summarize_rebind_status → cluster_rebind(action='status')
  list_entities           → read_cluster_memory(kind='entities')
  list_claims             → read_cluster_memory(kind='claims')
  list_methods            → read_cluster_memory(kind='methods')
  read_briefing           → ask_cluster(source='notebooklm', mode='briefing')
  ask_cluster_notebooklm  → ask_cluster(source='notebooklm')
  brief_cluster           → ask_cluster(source='notebooklm', mode='brief')
  ```
  Test helper `_get_mcp_tool` gains an optional `module=` kwarg for
  callers that want to fall back to a Python attribute when an MCP
  registration is gated (back-compat: default `None` preserves the
  existing strict registry lookup).

- **`README.zh-TW.md` full mirror of the new EN structure.**
  Previously the zh-TW README was 152 lines / 6 sections (Real
  Screenshots, Why this exists, Start Here, First-Run Checklist,
  Connect your AI host, License only) — 10 sections behind the EN
  master + in the pre-restructure order. Now 430 lines / 18 sections
  matching the EN's 6-layer importance order: `## 快速開始` (Quick
  start) + `## 目錄` (Contents TOC) + the 16 content sections in the
  new order. 10 new sections translated from EN via `gemini-delegate`;
  existing 6 sections kept where the prose was operator-approved
  quality. All skill names, file paths, CLI commands, env var names,
  brand names, version refs, MCP terms, and code blocks preserved in
  English per locale convention.

- **`README.md` reordered into 6 importance layers**, with a new
  `## Quick start` section and a 17-row `## Contents` TOC inserted
  at the top. Previously install (`## Start Here`) lived at line 121
  behind four selling sections (Real Screenshots / Why this exists /
  What it does / Is this for me?). A first-time visitor arriving
  from awesome-mcp-servers / SkillHub / MCP registry / promo
  posts had to scroll past ~100 lines of pitch before reaching a
  command they could run. New order: Quick start (line 26) → TOC →
  Real Screenshots → Is this for me? → full install (`Start Here`,
  `First-Run Checklist`, `Credential Reference`, `Connect your AI
  host` — moved up from line 243 to sit alongside install) → design
  rationale (`Why this exists`, `What it does`, `Operator Modes` —
  moved down from lines 51-73 into the design layer) → reference
  (Dashboard tour, Inside Zotero, Feature matrix) →
  troubleshooting + meta. No content removed; pure reorder + 2 new
  navigational sections (Quick start ~10 lines, Contents ~20 lines).

### Fixed

- **Pipeline ingest tests no longer make live Crossref / DOI-resolve network
  calls (CI flake fix).** `run_pipeline(dry_run=False)` runs the authenticity
  gate, which corroborates DOIs over HTTP (`_resolve_head_with_retry` +
  `CrossrefBackend`). In the test suite that leaked real network calls which,
  on a CI network blip, hung until the 30s pytest-timeout killed them (the
  2026-06-01 master CI failure on `test_v041_pipeline_ingest_fixes` /
  `test_v062_note_enrich`, while local + PR CI were green). A `conftest.py`
  autouse fixture now runs the gate OFFLINE for pipeline tests — stubbing only
  the two network entry points so the gate's real logic (local rejections such
  as L0 `no_identifier`) is preserved while DOI / Crossref checks take the
  designed fail-open path. Tests that drive the gate's network themselves are
  auto-excluded via source inspection of the gate internals. Suite stays
  3144-green and deterministic.
- **Subprocess reads now degrade gracefully on a stray byte instead of
  crashing the reader thread.** Six diagnostic/system-tool subprocess
  calls used `text=True` with no `errors=` handler: `doctor.py` (the
  `wmic` / `ps` chrome-process lookup), `security/__init__.py` (the
  `icacls` ACL reset / grant / verify calls), `dashboard/executor.py`
  (the command runner's `subprocess.run` + `Popen` paths), and
  `defuddle_extract.py` (had `encoding="utf-8"` but no `errors=`). Under
  Python's UTF-8 mode (`PYTHONUTF8=1`), reading a Windows tool that emits
  cp950/Big5 raised `UnicodeDecodeError: ... byte 0xa4` and killed the
  `subprocess` reader thread (10 tracebacks polluted `doctor` output;
  the affected lookup silently returned nothing). Added
  `errors="replace"` to all six — the codec is **unchanged** (these
  tools legitimately emit locale-encoded output, so forcing utf-8 would
  mangle them), only a bad byte now becomes a replacement char rather
  than a crash. The user-facing LLM-output reads (`llm_cli.py`,
  `paper_summarize.py`) were already protected with
  `encoding="utf-8", errors="replace"`. Verified: `doctor` under
  `PYTHONUTF8=1` goes from 10 `UnicodeDecodeError`s to 0; the
  executor / doctor / security / defuddle suites stay green (141
  passed). Surfaced during a live literature-search dogfood of the
  ai-research-skills audit follow-up.

## [1.0.0] - 2026-05-26

First stable release. 129 commits since v0.91.1 (95 features +
fixes; bumped from 0.91.x trail through 0.95.0 rc cycle to 1.0.0).
Authenticity gate (v0.95+), MCP Server Registry preparation, and
PDF attach reliability hardening are the headline themes.

### Added
- **`mcp-name: io.github.WenyuChiou/research-hub` line in README.md**
  (HTML comment at the top, invisible in rendered Markdown). Required
  for ownership validation when publishing this package to the MCP
  Server Registry at `registry.modelcontextprotocol.io`. Without this
  line in the PyPI-rendered README, `mcp-publisher publish` fails with
  `PyPI package 'research-hub-pipeline' ownership validation failed`.
  The companion `server.json` manifest already declares the namespace
  `io.github.WenyuChiou/research-hub`; this line is the cross-verifier.
  No version bump or release flow is triggered by this change — the
  next PyPI release (currently staged as v1.0.0) will be the first
  PyPI artifact carrying the `mcp-name` line, at which point
  `mcp-publisher publish` can succeed.

### Fixed
- **PDF attach 0% regression from PR #108's requests → httpx port**
  (`zotero/pdf_attach.py`). The `requests` → `httpx` migration in PR #108
  used `httpx.get()` without overriding the default User-Agent
  (`python-httpx/<ver>`). MDPI, Frontiers, Springer-pdfdirect, IEEE, and
  other publishers' bot filters block that UA and return 403. Production
  E2E coverage crashed: a flood cluster got 0/15 OA PDFs attached, the
  Human-Nature cluster got 0/30. New `_PDF_DOWNLOAD_HEADERS` constant
  sends a real Chrome-on-Windows UA + `Accept: application/pdf,...` so
  the publishers' filters let the download through. Live verification:
  `_download_via_httpx_result(<Springer pdfdirect URL>)` now returns
  status 200 + a 1.6 MB PDF (was 403 / 406 bytes of HTML). Regression
  test in `tests/test_v080_pdf_imported_file.py` pins both that headers
  are passed AND that the UA looks like a real browser.

### Added
- **Explicit sub-MOC override via `cluster.moc_links`**
  (`vault/hub_overview.py`, `pipeline.py`,
  `vault/hub_backlink_migrate.py`, `cli.py`). When a cluster's
  `moc_links` field contains a name with a family prefix
  (`LLM-Agents-*` or `Water-Resources-*`), the auto-derived slug-based
  sub-MOC for THAT family is now suppressed — the user-provided name
  wins instead of being appended alongside. Use case: slug
  `generative-ai-large-language-models-coupled` auto-derives
  `LLM-Agents-Coupled`, but the topic is really Human-Nature Systems;
  setting `moc_links: [LLM-Agents-HumanNature]` in `clusters.yaml` now
  yields `[LLM-Agents-HumanNature, LLM-Agents]` instead of also
  tacking on `LLM-Agents-Coupled`. Each family is independent: an
  `LLM-Agents-*` override does NOT suppress the Water-Resources auto
  sub-MOC, and vice-versa. Names that do NOT match a family prefix
  (e.g. `MyCustomMOC`) still pass through additively, as before.
  The override propagates through ALL `derive_moc_links` call sites
  — the cluster `00_overview.md`, MOC pages, `_HOME.md` rendering,
  per-paper `## Hub` section at ingest time (P1 fix: previously
  `pipeline._render_obsidian_note` did NOT pass `cluster.moc_links`,
  so the overview/MOC honoured the override while every paper
  wikilinked to the slug-derived sub-MOC), and `hub-backlink-migrate`
  backfills. Regression test
  `test_explicit_override_propagates_to_paper_note_hub_section`
  pins the pipeline call-site fix.
- **Two-level hub-and-spoke MOC graph (per-cluster sub-MOC)**
  (`vault/hub_overview.py`). Every LLM/water cluster now links to BOTH a
  parent MOC (e.g. `LLM-Agents`) AND a per-cluster sub-MOC derived from
  the slug's distinctive tail (e.g. `LLM-Agents-Flood`,
  `LLM-Agents-ConsumerBehavior`, `Water-Resources-DataPipeline`). Without
  the sub-MOC, every LLM cluster collapsed onto a single `LLM-Agents`
  node in Obsidian graph view; with it, each cluster has a distinct
  sub-hub between the parent and the paper notes — the cross-cluster
  centre stays, but each topic gets its own visible centre too. Two
  parser fixes along the way: hyphenated slug tokens like
  `large-language-models-consumer-behavior` now correctly match
  `"large language model"` substring (haystack normalised
  `-`/`_` → space), and generic possessive prefixes (`my`, `our`,
  `new`, `old`) are stripped so `my-cluster` produces `Cluster` not
  `MyCluster`. Existing clusters need
  `research-hub vault rebuild-overviews` to backfill sub-MOC links into
  legacy paper-note frontmatter; new ingests get them automatically.
- **EZproxy support for paywalled PDF downloads** (`ezproxy.py`, `cli.py`,
  `zotero/pdf_attach.py`, `pyproject.toml`). Opt-in via
  `cfg.ezproxy_url_template`. New
  `research-hub ezproxy login` captures institutional SSO cookies via
  Playwright; `paper attach-pdfs` then wraps publisher URLs through the
  proxy and falls back to the direct URL on any proxy failure. Generic
  per-institution template — any university with an EZproxy gateway can
  configure it. Closes the IEEE/Wiley/Elsevier-via-paywall gap noted in
  the README's Known limitations.
- **`auto --year RANGE` flag** (`cli.py`, `auto.py`). The standalone
  `search --year` filter is now also exposed on the `auto` subcommand so
  users who want recent literature can write
  `auto "LLM × X" --year 2024-` directly instead of running a separate
  search step. Same syntax as `search --year`: `2024-2025` (closed range),
  `2024-` (from 2024), `-2024` (up to 2024). Wired end-to-end through
  `_auto()` → `auto_pipeline(..., year_from, year_to)` → `_run_search()` →
  `search_papers(year_from, year_to)`. Unset = no year filter, behaviour
  unchanged.

### Changed
- **LLM-judge fit-check uses a stricter rubric when the cluster topic is
  LLM-narrowed** (`fit_check.py`). For a cluster topic that explicitly
  mentions LLMs (any of `LLM` / `large language model` / `ChatGPT` /
  `GPT-N` / `generative AI` / `LLM agent` / `AI agent` / `agentic AI`),
  the LLM-judge prompt switches from the default 0-5 rubric ("squarely
  about / on-topic adjacent angle / tangentially related…") to a stricter
  one anchored on **how central the LLM is to the paper's contribution**.
  Under the new rubric an ML/DL-without-LLM paper in the same parent
  domain scores **2** (instead of 4 under the old rubric), so the
  default `--fit-check-threshold 4` (PR #104) now actually filters those
  out. This addresses the empirical finding that running
  `auto "LLM × flood"` was still letting through ~12/15 pure ML-flood
  papers — they were getting "on-topic adjacent angle (4)" from the
  generic rubric. Detection scans BOTH the cluster definition and the
  slug, so freshly-created clusters (where the definition is the
  slugified topic fallback) trigger the strict rubric correctly. Five
  new tests pin every LLM-narrowing token variant.
- **NLM keepalive: real refresh via SDK public API + minute-cadence default**
  (`notebooklm/keepalive.py`, `cli.py`). The old `rotate_and_persist_session`
  used the SDK's *private* `_rotate_cookies` poke which returned success
  without verifying the session was still alive — every "ok" in the logs
  could have been a silent no-op against a revoked session, which is why
  the documented "持久一年" never actually held. New
  `refresh_and_persist_session` calls the SDK's *public*
  `fetch_tokens_with_domains` which GETs the NotebookLM homepage and
  extracts (csrf_token, session_id) as a side-effect of cookie rotation:
  if tokens come back, the cookies are observably good. The function
  returns a structured `RefreshResult` with `before_metadata` /
  `after_metadata` / `changed` (freshness-cookie expiry diff) so an
  operator can see PSIDTS actually moved forward. The old function name
  is retained as a thin bool shim for back-compat callers.
  `keepalive_once` was restructured to call refresh *first* (no pre-health
  gate — the Codex review of the old design flagged that as the source
  of permanently-stale sessions: a transient health-check error skipped
  the only refresh attempt). Default cadence flipped from hourly to
  **15 minutes** (`--interval` 21600 → 900 s, floor 3600 → 600 s;
  `--interval-minutes` 6 → 15 with /SC MINUTE schtasks) — PSIDTS expires
  every ~3-4 hours, so hourly left only ~3 retries per expiry window
  and routinely lost races on flaky networks. `--interval-hours` is
  kept as a deprecated alias multiplied to minutes at dispatch.
  Existing tests in `tests/test_v0950_nlm_keepalive_and_browser_login.py`
  rewrote classes A (refresh) and B (keepalive_once) for the new
  contract; classes C/D/E (CLI / from-browser) unchanged. Note: "持久一年"
  is achievable *only* when (a) the scheduled task runs every 15 min without
  interruption, (b) Google does not revoke the account on a security event,
  and (c) the long-lived `SID`/`PSID` cookies (~1 year nominal) have not
  naturally expired — keepalive does not defeat any of those.
- **`auto --fit-check-threshold` default raised 3 → 4** (`cli.py`). The
  LLM-judge fit-check now defaults to "clearly related" instead of
  "tangentially related and above". Rationale: at threshold 3 a "Large
  language models for X" cluster was consistently letting through pure
  ML/DL papers about X (no LLM at all) — the judge correctly scored
  them as 3 ("flood + AI, sort of related") and they passed. At
  threshold 4 the same papers are filtered out (still scored 3, now
  below the bar), cleaning the cluster to the actually-LLM-specific
  subset. Empirically on an "LLM × flood forecasting" run: kept dropped
  from 22/30 → 15/30, and the truly-LLM proportion rose from ~18% →
  ~20% (the LLM-judge is still generous on ML-flood papers; a sharper
  prompt is a follow-up). Use `--fit-check-threshold 3` to get the old
  lax behaviour. Python API `auto_pipeline(..., fit_check_threshold=3)`
  deliberately stays at 3 for back-compat with programmatic callers
  and tests — the strict default is a CLI-UX choice, not an API
  contract change.
- **`auto --with-summary` is now ON by default** (`cli.py`). After ingest, the
  per-paper Key Findings / Methodology / Relevance sections are filled via the
  detected LLM CLI (claude / codex / gemini) on every run; previously the
  `--with-summary` flag had to be opted in explicitly. The flag uses
  `argparse.BooleanOptionalAction`, so `--no-with-summary` is the new opt-out.
  `--full-auto` no longer needs to re-set `--with-summary` and was simplified
  accordingly, which incidentally lets `--full-auto --no-with-summary` respect
  the opt-out (silently overridden before). Python API
  `auto_pipeline(..., with_summary=False)` deliberately stays opt-in (mirrors
  the `--with-pdfs` PR #90 split) so programmatic callers don't fire 20+ LLM
  CLI invocations per run silently.

- **`auto --with-pdfs` is now ON by default** (`cli.py`, `auto.py`). The `auto`
  subcommand attaches open-access PDFs from arXiv/OpenAlex/Unpaywall/Crossref
  to the ingested Zotero items as part of every run; previously `--with-pdfs`
  had to be opted in explicitly. The flag uses `argparse.BooleanOptionalAction`,
  so `--no-with-pdfs` is the new opt-out for runs where you only want the
  NotebookLM bundle. Rationale: the bundle ladder already downloaded the PDFs
  for NLM but they never made it into Zotero, leaving the
  `cluster/pdf_coverage` doctor check stuck at 0%. The Python API
  `auto_pipeline(..., with_pdfs=False)` deliberately stays opt-in so
  programmatic callers (tests, library users) don't fire the PDF-attach
  network round-trips silently — the CLI hands in an explicit `True` from
  argparse instead. `--full-auto` no longer needs to re-set
  `--with-pdfs` and was simplified accordingly, which incidentally lets
  `--full-auto --no-with-pdfs` respect the explicit opt-out (it was silently
  overridden before). The `ingest` and `run` subcommands stay opt-in
  (`--with-pdfs` only) — they are lower-level entry points where an explicit
  flag still makes sense.

### Fixed
- **Cluster overview LLM auto-fill now fires after `populate_overview` runs
  too** (`cluster_overview.py`). PR #91 fixed `_CHINESE_TEMPLATE_MARKER` to
  match the Chinese scaffold (`一到兩句話...`) but in the real `auto` flow,
  `populate_overview` (`vault/hub_overview.py`) runs BEFORE `apply_overview`
  and overwrites the TL;DR with the cluster's topic-string fallback (`"LLM
  for flood forecasting..."`). The Chinese marker then no longer matches and
  `apply_overview` silently classified the topic string as "hand-curated",
  skipping LLM enrichment. Net effect: every `auto`-fresh cluster still
  ended with an empty TL;DR / Core Question / Scope. The scaffold check is
  now `_is_scaffold_tldr(text, cluster_query, cluster_slug)` which also
  recognises:
    * the English fallback `"No cluster summary available yet."` (from
      `_render_tldr`)
    * exact match against the cluster's `first_query` (the topic-string
      fallback `_overview_tldr` writes when there's no NLM brief yet)
    * exact match (case-insensitive) against the slug humanised (the
      last-resort fallback in `_overview_tldr`)
  Two regression tests pin the new branches.


### Added
- **`brief_to_docx.js` ships inside `skills/research-design-helper/scripts/`**
  (plugin `0.3.13 → 0.3.14`). Sister script to
  `skills/gap-to-topic/scripts/dossier_to_docx.js` — same Markdown → Word
  converter (heading styles, bullet lists via numbering reference,
  tables with dual-width DXA, en / zh-TW font auto-select, Markdown
  separator-row skip), but default stem is `design_brief` instead of
  `topic_dossier`. Makes the Stage 3a artifact shareable with advisors
  / committee members who prefer Word over Markdown.
  - **Not part of the contracted Stage 3a output.** `design_brief.md`
    remains the canonical artifact; the `.docx` is an optional
    convenience for human consumption only. Downstream skills (Stage
    3b `research-context-compressor`) read the `.md` frontmatter +
    section 1 directly, not the `.docx`.
  - **Verdict-colour regex inherited verbatim but does NOT fire on
    design brief content** — no "Do not pursue" / "Not assessed" /
    "不予推進" / "未評估" strings appear in a design brief. Keeping
    the regex unchanged means a single fix to the dossier generator
    lands in both scripts via parallel PRs.
  - SKILL.md adds `## Generate .docx (optional, plugin v0.3.14+)`
    section between `## Output` and `## Token-saving behavior`,
    mirroring the gap-to-topic `§4.5 Generate .docx` pattern.
  - `scripts/README.md` ships alongside, documenting prereq
    (`npm install -g docx`), invocation examples (en + zh-TW), and
    the design-brief-specific deviation (the regex no-op).
  - New test
    `test_design_helper_has_brief_to_docx_script_and_skill_md_section`
    asserts `scripts/brief_to_docx.js` exists, the SKILL.md has the
    new `## Generate .docx (optional` heading, and the script's
    default stem is `design_brief` not `topic_dossier`.
  - Mirrored to `src/research_hub/skills_data/`.

- **Stage 2 → 3a → 3b handoff wiring**
  (`skills/research-design-helper/`, `skills/research-context-compressor/`,
  `tests/fixtures/topic_dossier_sample.gaps.yml`,
  `tests/test_handoff_gap_to_topic_design_helper.py`, plugin
  `0.3.11 → 0.3.12`). Two broken wires fixed as one coherent
  user-facing capability:
  - **`research-design-helper` reads `.research/topic_dossier.gaps.yml`**
    as new Input #2. New Workflow §0 preamble auto-pre-fills segment 1
    (RQ) from the chosen `gaps[].statement` and segment 5 (risks) from
    `open_questions[]` + the specific concern hinted by
    `gaps[].feasibility`. Segments 2–4 (mechanism / identifiability /
    validation) are never pre-filled — the dossier doesn't carry that
    material and pre-filling with non-content corrupts the Socratic
    dialog. When the upstream `.gaps.yml` is absent, the skill behaves
    exactly as before (no regression for standalone users). Candidate
    selection is verdict-aware: filter `gaps[]` to
    `verdict in {conditional-go, go}`, then auto-pick if one,
    ask-the-user if 2+, halt with "nothing to frame" if zero.
  - **`design_brief.md` frontmatter carries Stage 2 provenance.**
    Two new optional fields: `source: topic_dossier.gaps.yml#<gap-id>`
    (URI-fragment pointer to the chosen gap) and `gap_verdict:` (frozen
    snapshot of `verdict` + first 60 chars of `verdict_reason`). The
    brief becomes self-contained — a future reader sees which dossier
    candidate this design was framed for. Provenance-protection: a
    refresh that would change the `source` gap-id triggers a confirm
    prompt instead of silent overwrite.
  - **`research-context-compressor` reads `.research/design_brief.md`**
    as new Input #2 under "For any project". Reads the frontmatter
    (`project`, `source`, `gap_verdict`) + section 1 (Research
    question) only. This implements the long-claimed `pipeline.md`
    contract; the brief is the authority on the sharpened RQ and the
    manifest mirrors it. If frontmatter `source` is set, copies that
    gap-id into the manifest's `provenance.from_gap` field
    (forward-compat with downstream tools).
  - **First cross-skill handoff integration test** ships at
    `tests/test_handoff_gap_to_topic_design_helper.py` with a frozen
    fixture at `tests/fixtures/topic_dossier_sample.gaps.yml` (copied
    from the v0.3.10 dogfood example). Asserts: fixture parses + has
    v0.3.10+ top-level keys + `recall.screen` sub-block + per-gap
    downstream-consumer fields + `open_questions[].text`; downstream
    SKILL.md prose lists the handoff input + has the §0 preamble +
    preserves the absent-`.gaps.yml` fallback; design_brief_template
    frontmatter has `source` + `gap_verdict`;
    research-context-compressor mentions `design_brief.md`; the
    schema reference covers every key the fixture contains (drift
    detector). Subsequent stage-to-stage wires (3a → 3b proper,
    6 → 7, …) should follow this test shape.
  - Mirrored to `src/research_hub/skills_data/`. Pure additive change
    — no removed inputs, no breaking behaviour, no required new
    fields. Users without a `.gaps.yml` see identical UX to v0.3.11.

- **`dossier_to_docx.js` ships inside `skills/gap-to-topic/scripts/`**
  (plugin `0.3.9 → 0.3.10`). `topic_dossier.docx` is now a first-class
  contracted deliverable of the `gap-to-topic` skill. The generator converts
  `topic_dossier.md` to a styled Word document using `docx` 9.x: heading
  styles (H1/H2 navy, H3 dark grey), bullet lists via numbering reference,
  tables with dual-width DXA column sizing, bilingual verdict colour coding
  (light red "Do not pursue" / "不予推進", light yellow conditional
  "Worth pursuing … only if" / "值得推進…條件", light green unconditional,
  light grey "Not assessed" / "未評估"), Markdown separator-row skip, and an
  optional TOC + page break after the first table (`--no-toc` to suppress).
  Font auto-selects: filename matching `.zh|zh-|zh_|-tw|-cn` → Microsoft
  JhengHei; else Arial. Prerequisite: `npm install -g docx`. SKILL.md updated
  with §4.5 "Generate .docx" workflow step; front-matter description and "What
  it produces" updated to list `.docx` as a first-class artifact. Mirrored to
  `src/research_hub/skills_data/gap-to-topic/scripts/`.

### Fixed
- **`paper-memory-builder` doc enhancements — F-cross2 figures.yml
  sentinel + F-cross3 evidence-artifact scanning** (`skills/paper-memory-builder/SKILL.md`,
  `skills/paper-memory-builder/references/yaml-schemas.md`,
  `tests/test_handoff_gap_to_topic_design_helper.py`, plugin
  `0.3.15 → 0.3.16`). Two small doc improvements surfaced by the
  Stage 7-8 dogfood (`~/.claude/audits/dogfood_runs/2026-05-23-paper-memory-academic-writing-stage-7-8/VERIFICATION.md`):
  - **F-cross2 — figures.yml `file:` sentinel values.** The schema
    requires `figures[].file` (required field), but real-world
    Word-based research workflows often have figures embedded
    directly inside the `.docx` manuscript with no separable source
    file. Adds a `### file: sentinel values (v0.3.16+)` section to
    `references/yaml-schemas.md` documenting three sentinels:
    `embedded-in-manuscript`, `embedded-in-supporting-information`,
    `embedded-in-presentation`. Downstream consumers
    (academic-writing-skills figure-text checks, future
    figure-archive tooling) treat these as "present in manuscript,
    no separable artifact to verify independently." Documented
    limitation, not a permanent solution — future versions may add
    a pre-processing step that extracts embedded figures.
  - **F-cross3 — SKILL.md "Scanning the paper repo for evidence
    artifacts" sub-section.** The previous Inputs section only
    described figures + manifest files but real research repos
    contain many non-figure evidence artifacts (simulation CSVs,
    analysis scripts, drawio sources, reviewer-response artifacts).
    The new sub-section documents typical artifact types and shows
    an example of populating `claims[].evidence_artifacts` with
    artifact PATHs for non-figure evidence (e.g. a chi-squared test
    claim might cite an `outputs/llm-abm_decision_log.csv` + the
    analysis script that ran it, in addition to the manuscript
    anchor). Makes the audit trail end-to-end traceable.
  - **Tests:** added 2 new test cases to
    `test_handoff_gap_to_topic_design_helper.py`:
    (1) `test_paper_memory_yaml_schemas_documents_file_sentinel_values`
    asserts all 3 sentinels appear in `yaml-schemas.md`;
    (2) `test_paper_memory_skill_md_documents_evidence_artifact_scanning`
    asserts the SKILL.md Inputs section has the new sub-section AND
    mentions at least 3 non-figure artifact types (Simulation,
    Analysis scripts, Drawio).
  - Pure additive prose change. Mirrored to
    `src/research_hub/skills_data/paper-memory-builder/`.

- **Codex review tightenings — multi-eligible fixture + design_brief
  placeholder marker** (`tests/fixtures/topic_dossier_multi_eligible_sample.gaps.yml`,
  `skills/research-design-helper/references/design_brief_template.md`,
  `skills/research-design-helper/SKILL.md`,
  `tests/test_handoff_gap_to_topic_design_helper.py`, plugin
  `0.3.14 → 0.3.15`). Two follow-ups from the independent Codex
  evaluation of the v0.3.12 + v0.3.13 + v0.3.14 deliverables
  (`.ai/codex_eval_report.md`, verdict ship-with-fixes):
  - **C2 — multi-eligible fixture.** The §0 "2+ candidates, ask the
    user" branch was documented in SKILL.md and verified by the
    branch-coverage prose test, but never exercised against a real
    fixture with multiple `verdict ∈ {conditional-go, go}` entries.
    New synthetic fixture
    `tests/fixtures/topic_dossier_multi_eligible_sample.gaps.yml`
    ships 3 gaps (G1 conditional-go, G2 conditional-go, G3 no-go) so
    the filter produces 2 eligibles. Two new tests:
    (a) `test_multi_eligible_fixture_parses_and_has_2plus_go_eligible`
    asserts the fixture's filter result keeps the 2+ branch
    exercised (guards against fixture decay), and (b) a
    parametrized `test_fixture_parses_and_drives_correct_section_0_branch`
    runs across both fixtures asserting each drives its expected §0
    branch (auto-pre-fill vs ask-the-user). A future third fixture
    for the zero-eligible halt branch can be added with one tuple.
  - **C4 — design_brief placeholder marker.** The v0.3.12 dogfood
    filled segments 2–4 with test-fit placeholder content (not from
    real Socratic dialog) and used an ad-hoc `_TEST-FIT-PLACEHOLDER_`
    inline tag. Codified as a structured frontmatter field:
    `placeholder_segments: []` (list of segment numbers). Example:
    `placeholder_segments: [2, 3, 4]` means segments 2–4 are
    placeholders, downstream tools should refuse to gate real
    research on a brief with non-empty list. SKILL.md adds a
    "Placeholder marker (v0.3.15+)" paragraph in the Output section
    explaining when to use it. New test
    `test_design_brief_template_has_placeholder_segments_field`
    asserts the frontmatter accepts the field.
  - Pure additive: no removed fields, no changed enum tokens, no
    behaviour change on absent/empty placeholder list. Mirrored to
    `src/research_hub/skills_data/`.

- **`research-context-compressor` Output spec shows
  `provenance.from_gap`; `research-design-helper` §0 forbids
  in-file pre-fill annotations** (`skills/research-context-compressor/SKILL.md`,
  `skills/research-design-helper/SKILL.md`,
  `tests/test_handoff_gap_to_topic_design_helper.py`, plugin
  `0.3.12 → 0.3.13`). Two minor SKILL.md prose tightenings surfaced
  by the v0.3.12 Stage 3a + 3b dogfood (`~/.claude/audits/dogfood_runs/2026-05-22-research-design-helper-llm-abm-socio-hydrology/`):
  - **F1 — compressor Output example now shows `provenance.from_gap`.**
    The field was registered in `docs/research-workspace-manifest.md`
    (PR #95) and mentioned in the compressor `## Inputs` section
    (PR #96), but the `## Outputs you must produce` section had no
    example — a prose-driven skill is at risk of agents missing the
    wire. v0.3.13 adds an explicit example block under Outputs
    showing the `provenance: { from_gap: ... }` shape and codifies
    the absent-state rule (omit the block when there's no upstream;
    do NOT write `provenance: {}` or `null`). Provenance-protection
    on refresh now also explicitly applies to
    `manifest.provenance.from_gap` (mirrors the v0.3.12 rule in
    `research-design-helper`).
  - **F2 — §0 forbids `_PRE-FILL_`-style annotations in
    `design_brief.md` content.** The v0.3.12 §0 wrote
    `gaps[].statement` into segment 1 but didn't say HOW to format
    it. The dogfood agent added a `_PRE-FILL (review/sharpen): ..._`
    annotation that wouldn't get cleaned up after segment 1 dialog
    sharpened the RQ. v0.3.13 clarifies: write the statement
    verbatim, no annotation in the file; the chat-level message
    flags it as pre-fill. Means segment 1 dialog can simply
    overwrite the statement with the sharpened RQ — no cleanup
    step needed.
  - **Test coverage:** added 2 new test cases to
    `test_handoff_gap_to_topic_design_helper.py` (14 → 16 total)
    asserting (1) the compressor Outputs section mentions
    `provenance` AND `from_gap`, (2) the §0 segment-1 pre-fill rule
    explicitly forbids `_PRE-FILL_` annotations in file content
    (negation regex, not just word-presence — guards against
    rewrites that drop the prohibition).
  - Pure additive prose change (no removed inputs, no schema
    changes, no behaviour change on absent upstream). Mirrored to
    `src/research_hub/skills_data/`.

- **`gap-to-topic` schema reference + research-hub discoverability**
  (`skills/gap-to-topic/references/dossier-template.md`,
  `docs/ai-research-skills.md`, plugin `0.3.10 → 0.3.11`). Two
  contract-vs-reality fixes ahead of the Stage 2 → 3a handoff wiring:
  - **Schema reference refresh.** The `topic_dossier.gaps.yml` schema
    in `references/dossier-template.md` was stale relative to what
    `gap-to-topic` actually emits since v0.3.6 (the `--screen`
    fit-check integration) and v0.3.9 (the 7-section reflow): missing
    top-level `run_type` / `recall` (with full `screen` sub-block) /
    `pipeline`; missing per-gap `open_confidence` /
    `dead_end_evidence` / `borderline_reason` / `verdict` /
    `verdict_reason`. The schema is now byte-aligned with the real
    output and adds a top-level `downstream_consumer:
    research-design-helper` key as a forward-compat hook recording
    the contract reader.
  - **Discoverability.** `docs/ai-research-skills.md` had zero mentions
    of `gap-to-topic` despite the skill being shipped at v0.3.10.
    Added a new Stage 2.5 row to the Stages table, a "Deciding whether
    a research gap is worth pursuing" entry to the When-to-use table,
    and a full `### gap-to-topic (v0.3.11)` section in All packaged
    skills documenting Reads / Writes / handoff to Stage 3a /
    trigger phrases.
  - Pure additive changes (no removed fields, no enum tokens changed).
    Mirror at `src/research_hub/skills_data/gap-to-topic/` updated in
    parity.
- **`gap-to-topic` dossier reflowed as a 7-section research-grade decision
  memo** (`skills/gap-to-topic/`, plugin `0.3.8 → 0.3.9`). The v0.3.8
  dossier rendered as "Markdown converted to Word" — wide scorecard with
  one-letter-wide columns, no decision-level visual cue, too many tables
  in the body. `references/dossier-template.md` is reorganised: §1
  Executive Decision Summary (metadata + verdict cards + key uncertainty)
  → §2 Candidate Definitions (prose, no roster table) → §3 Decision
  Scorecards (per-candidate small tables, replacing the wide combined
  one) → §4 Evidence Base → §5 Gate-by-Gate Assessment (each gate uses a
  fixed Score / Evidence / Interpretation / Risk / Action-needed
  skeleton) → §6 Risks and Upgrade/Kill Tests (named risks; operational
  kill-test artifacts; salvage path) → §7 Recommended Next Steps (formal
  research-memo prose) → Appendix A Search and Screening Protocol
  (reproducibility log) → Appendix B Deliverable File List. SKILL.md
  "What it produces" updated to match. Mirrored to
  `src/research_hub/skills_data/gap-to-topic/`.
- **Cluster overview LLM auto-fill now actually fires on fresh clusters**
  (`cluster_overview.py`, `vault/hub_overview.py`,
  `tests/test_v071_cluster_overview.py`, `tests/test_hub_overview.py`).
  The `_CHINESE_TEMPLATE_MARKER` constant in `cluster_overview.py` and
  the `_SCAFFOLD_MARKERS` tuple in `vault/hub_overview.py` both stored
  **mojibake** from a historical cp950 ↔ UTF-8 round-trip, so they never
  matched the actual Chinese placeholder phrases `topic.py` writes for a
  new cluster (`一到兩句話說清楚...` for TL;DR, `用一句話寫下...` for
  核心問題). Net effect: every brand-new cluster was immediately
  classified as "hand-curated", `apply_overview` silently refused to
  call the LLM, and the sibling `populate_overview` path likewise
  refused to refresh those sections — leaving the `00_overview.md`
  stuck at the empty scaffolding (TL;DR / 核心問題 / 範圍定義 / 領域地圖
  / 必讀論文 / 時間線 / 開放問題 all blank). The markers are now the
  real opening phrases (`一到兩句話`, `用一句話寫下`); the legacy
  mojibake markers stay so vaults whose existing `00_overview.md` still
  contains the corrupted bytes are still recognised and refreshed
  cleanly. The test fixture `_template_text` was likewise mojibaked and
  now mirrors `topic.py` verbatim, plus two dedicated regression tests
  (one per code path) pin the marker ↔ template round-trip so this
  can't drift silently again.
- **`gap-to-topic` dossier — section-by-section rework for researcher value**
  (`skills/gap-to-topic/`, plugin `0.3.7 → 0.3.8`).  A section-by-section
  review with the maintainer, plus a Codex evaluation, reworked
  `references/dossier-template.md`:
  - **Decision scorecard** is now a 5-point Likert per gate — each gate is
    a claim rated 1–5 (strongly agree … strongly disagree); the cell is
    `N/5 label — description`; a topic is worth pursuing only if every gate
    rates 3 or higher.
  - **Gate 2** gains "What it would contribute" (one explicit claim) and a
    "Minimum validation sketch"; a caution paper is summarised by the kind
    of risk it raises, not offloaded to the reader.
  - **Gate 3** gains "Design feasibility", a "Scale outline", and an
    explicit proposal-vs-dissertation feasibility split — it is no longer
    only a data-availability test.
  - **The decision is yours** is framed consistently as a conditional
    recommendation; the upgrade/kill test is written as concrete artifacts;
    a failed candidate gets a salvage-path line.
  - **Appendix A** is recast from a tool log into a method note (search
    scope, inclusion criteria, automated-vs-judgement).
  - **What's in this deliverable** gains a file tree.
  SKILL.md "What it produces" updated.  Mirrored to
  `src/research_hub/skills_data/gap-to-topic/`.
- **`gap-to-topic` dossier reworked to read as a plain summary report**
  (`skills/gap-to-topic/`, plugin `0.3.6 → 0.3.7`).  A review found the
  dossier still did not read cleanly in Word: the candidate roster showed
  an `id` column of `G1`/`G2` codes; the Decision scorecard used
  `✓ ✗ ~` glyphs and the jargon verdicts "No-go / Conditional go / Go";
  there was no index of the bundle's files.  `references/dossier-template.md`
  now: drops the `id` column (the `G1`/`G2` ids stay only in `.gaps.yml`)
  and states "why it could be a gap" in plain words; drops the scorecard
  glyphs for plain words; replaces the verdict jargon with plain phrasing
  ("Do not pursue — as stated" / "Worth pursuing — only if its open
  conditions hold" / "Worth pursuing"); adds a "What's in this deliverable"
  index section; gives the Bottom line one plain paragraph per candidate.
  The `.gaps.yml` schema moved to a trailing "not emitted" reference block.
  SKILL.md "What it produces" updated.  Mirrored to
  `src/research_hub/skills_data/gap-to-topic/`.
- **ingest collapses in-batch duplicate papers** (`pipeline.py`). Two search
  backends can return the SAME paper under different DOIs (a journal DOI vs a
  repository/preprint DOI). DOI-keyed search-merge dedup keeps both, and
  `dedup.check()` cannot catch them either — `dedup.add()` runs only in the
  note-writing loop, so in-batch siblings stay invisible during Zotero-item
  creation. Result: two Zotero items for one paper and two notes colliding on
  an identical filename slug (one silently overwriting the other). A new
  pre-ingest in-batch dedup pass now collapses candidates sharing a
  normalized DOI or normalized title (mirrors `DedupIndex.add()`'s >15-char
  title guard), keeping the first occurrence and logging a `dup-in-batch`
  manifest entry for each collapsed sibling.
- **`gap-to-topic` §1 now applies the fit-check relevance gate**
  (`skills/gap-to-topic/`, plugin `0.3.5 → 0.3.6`).  `search --screen`
  (PR #84) wired the BM25 relevance gate into the `search` command; §1 now
  uses it.  SKILL.md §1: step 1 runs `search --adversarial --screen --json`
  and reads the new `{screening_summary, results}` shape (each paper
  carries a `relevance` field); steps 2-3 build the matrix and `.bib` from
  the **on-topic** results only (`kept: true`), excluding screened-out
  off-topic noise; step 4 reports the retrieved-vs-on-topic counts in the
  recall headline.  `references/dossier-template.md` Appendix A pipeline +
  recall-mechanics rows updated.  Mirrored to
  `src/research_hub/skills_data/gap-to-topic/`.
- **ingest dedup re-scoped to research-hub's own literature** (`pipeline.py`).
  `auto` for a new topic produced a near-empty cluster — a search returned
  25 papers, fit-check kept all 25, yet only ~1 Obsidian note was created.
  Cause: the dedup index was dominated by `source:"zotero"` entries
  mirroring the user's ENTIRE Zotero library (mostly never managed by
  research-hub) plus stale `source:"obsidian"` entries pointing at deleted
  note files. The dedup block treated **any** paper merely present in the
  Zotero library as a duplicate and `continue`-d past Obsidian-note
  creation, dropping it from the new cluster. Dedup now skips a paper only
  when it duplicates research-hub's OWN literature: (1) the `obsidian_hit`
  branch requires the note file to actually exist on disk — a stale index
  entry no longer blocks ingest; (2) the `zotero_hit` branch no longer
  skips — it still reuses the existing Zotero item (moves it into the
  cluster collection, adds hub tags + note, creates **no** duplicate item)
  but the paper is now ingested into research-hub with its Obsidian note
  created and bound to the cluster. New manifest action
  `ingest-reuse-zotero` records the reuse decision.
- **fit-check no-LLM relevance gate rewritten** (`fit_check.py`, `auto.py`).
  The old `no_llm_fit_check` gate split the topic into independent unigrams
  and kept any paper matching `>= 0.1` of them — i.e. **1 of 5** words. A
  generic hydrology paper trivially matched `water`/`model`/`resources`
  and passed while the discriminating phrase "large language model" was
  destroyed; the `llm-water-resources` cluster ended up **38/43
  off-topic**. The gate is rebuilt as a pure-Python **BM25** scorer over
  **1–3-gram** topic terms — phrases like "large language model" survive
  intact, matching is plural-tolerant, and IDF is self-calibrated on the
  candidate batch. A paper is rejected only when the batch's sorted BM25
  scores show a **blatant bimodal split** — a gap whose upper cluster
  out-scores the lower by ≥ 5× (the cross-field contamination signature:
  pure-hydrology papers score ~1 vs ~8 for genuine LLM papers). A focused,
  all-relevant search spreads only ~2× and is kept whole; cold-start
  (batch < 5, no topic terms, or no clear gap) defers — keeps all, flags
  `relevance_unverified`. Recall-biased: the no-LLM tier only catches
  blatant contamination; fine-grained relevance screening is the
  LLM-judge tier's job. New public API: `extract_topic_terms`,
  `bm25_scores`, `screen_relevance`. Grounded in a research sweep of
  ASReview (TF-IDF + Naive Bayes) and BM25 screening practice.

- **`gap-to-topic` dossier — evidence-strength tags + an upgrade/kill test**
  (`skills/gap-to-topic/`, plugin `0.3.4 → 0.3.5`).  A Codex evaluation of a
  real dossier found two gaps: (1) Gate 1 said a gap was "densely populated"
  but the reader had to open `literature_matrix.md` to see the occupancy
  signal was partly conference abstracts / artifacts, not primary studies;
  (2) a "conditional go" listed open conditions but no threshold — the
  advisor still had to supply the kill/upgrade logic.  `references/dossier-template.md`
  now: Gate 1 tags each cited work by evidence type (primary study / review
  / close analogue / caution paper / conference abstract / preprint / data
  artifact) and ends with a one-sentence evidence-mix summary; "The decision
  is yours" carries an explicit **upgrade / kill test** per conditional-go
  candidate.  Mirrored to `src/research_hub/skills_data/gap-to-topic/`.
- **`gap-to-topic` dossier — added tables for scannability**
  (`skills/gap-to-topic/`, plugin `0.3.3 → 0.3.4`).  Follow-up to the
  reader-first redesign: the verdicts were still spread across prose bullets
  in each gate section.  `references/dossier-template.md` now puts a
  **Decision scorecard** table in the Bottom line (candidates × the 3 gates
  + verdict, with a `✓`/`✗`/`~`/`—` cell convention), a **roster table** in
  The candidates, and turns Appendix A (how it was produced) and Appendix B
  (companion files) into tables.  Gate 1–3 bodies keep prose — the verdicts
  now live once, in the scorecard, so the gate sections carry only the
  evidence (no duplication).  SKILL.md "What it produces" updated.  Mirrored
  to `src/research_hub/skills_data/gap-to-topic/`.
- **`gap-to-topic` dossier was organised tool-first and code-first, not
  reader-first** (`skills/gap-to-topic/`, plugin `0.3.2 → 0.3.3`).  A review
  of a real dossier found it opened with a metadata table of pipeline / API
  rows, wove `search --adversarial` / `literature-triage-matrix` / plugin
  versions through the body, and labelled candidates with bare `[G1]` /
  `[G2]` codes a researcher cannot decode.  `references/dossier-template.md`
  is redesigned reader-first: a plain-language **Bottom line** leads; each
  candidate gets a readable **name** (the `G1` id demoted to a `.gaps.yml`
  tag); each gate states its verdict in plain words before the evidence; all
  tool / pipeline / recall mechanics move to **Appendix A**, companion-file
  notes to **Appendix B**.  SKILL.md "What it produces" + the §0 step updated
  to match; `.gaps.yml` schema gains a `name:` field.  Mirrored to
  `src/research_hub/skills_data/gap-to-topic/`.
- **`gap-to-topic` §1 named `literature-triage-matrix` as the default
  prior-art tool but no step produced its matrix** (`skills/gap-to-topic/`,
  plugin `0.3.1 → 0.3.2`).  The SKILL.md "orchestrates" paragraph + `Inputs`
  + the §2 component input-contracts all referenced
  `.research/literature_matrix.md` as an available input, yet the §1
  numbered procedure only ran `search` — so an agent following §1 literally
  never built the matrix (a "phantom input"; surfaced by a 2026-05-21
  workflow audit).  §1 now has an explicit step 2 that feeds the
  `search --adversarial --json` results to `literature-triage-matrix` to
  produce the matrix; `.bib` and recall are renumbered to steps 3-4.
  `references/dossier-template.md` Pipeline line updated.  Mirrored to
  `src/research_hub/skills_data/gap-to-topic/`.
- **`gap-to-topic` §1 `.bib` instruction was unworkable** (`skills/gap-to-topic/`,
  plugin `0.3.0 → 0.3.1`).  SKILL.md §1 step 2 and `references/dossier-template.md`
  told the skill to emit the §1 reference list via `cite --format bibtex`, but
  `cite` resolves identifiers only against an already-ingested Zotero library —
  at topic-selection time the candidate papers are not ingested, so `cite`
  returns "Could not resolve identifier" for every §1 DOI.  Surfaced by the
  2026-05-21 dogfood run.  The `.bib` is now built from the
  `search --adversarial --json` metadata, which the skill already has in hand
  at §1.  Mirrored to `src/research_hub/skills_data/gap-to-topic/`; plugin
  version bumped so the marketplace cache invalidates.
- **`notebooklm login --auto-detect` now works** (`notebooklm/auth.py`).
  The pre-fix implementation shelled out to the upstream `notebooklm login`
  subprocess and polled the patchright Chromium profile's *on-disk* Cookies
  SQLite for a `notebooklm.google.com` row. Chromium buffers cookies in
  memory and flushes them to that store only on a lazy timer, so a
  freshly-signed-in session stayed invisible on disk for minutes — the poll
  loop always timed out without ever firing the save. `--auto-detect` now
  drives the Chromium browser directly via Playwright (same stealth flags
  the SDK uses) and polls the **live `page.url`**: the moment the page
  settles on the NotebookLM host — and holds there for 3 consecutive polls,
  so a mid-redirect flash never triggers a premature save — the session is
  captured straight from the live browser context via `storage_state`. No
  terminal ENTER, no subprocess, no disk-cookie race. Fail-closed: a
  timeout, a browser-launch error, or a driver-start failure all return
  non-zero without saving and never raise into the CLI. Removed the dead
  disk-polling helpers (`_patchright_cookies_db`, `_has_notebooklm_cookie`,
  `_cookies_db_modified_since`).

- **`probe_cleared_failed_no_abstract` URL quality signal now triggers text
  fallback in the NLM bundle builder** (`notebooklm/bundle.py`).  Springer /
  Wiley paywall skeleton pages return HTTP 200 with no body; the URL quality
  probe previously rated this `ok`, so the URL was uploaded to NotebookLM
  which also received an empty shell.  The fix treats this reason code the
  same as `likely_error_page` — falling back to the abstract as a copied-text
  source, or skipping if no abstract is available.

- **Zotero reparent on cluster reuse** (`auto.py`).  Clusters created before
  the parent-collection feature was added lived at the Zotero library root.
  On subsequent `auto` runs the pipeline found them by name and returned early,
  never calling `ensure_parent_collection`.  New helper
  `_maybe_reparent_collection` PATCHes the collection's `parentCollection` to
  the configured parent (default `"research-hub"`) when it is currently
  top-level (`parentCollection=False`).  Idempotent and best-effort.

- **PDF auto-attach step in `auto_pipeline`** (`auto.py`).  When `--with-pdfs`
  is passed, the pipeline now also calls the OA-PDF attachment chain
  (OpenAlex / Unpaywall / arXiv) for every Zotero item in the cluster after
  ingest, attaching the PDF as an `imported_file` child item.  Previously
  `--with-pdfs` only fed PDFs to the NLM bundle, not Zotero.

- **Summarize pending hint** in `auto_pipeline` next-steps output.  After a
  run, if any papers in the cluster have `summarize_status: pending`, the
  terminal output now prints a `[HINT]` line with the exact command to run
  (`paper summarize --pending --cluster <slug>`).

### Added
- **`search --screen` — fit-check BM25 relevance gate on the search
  command** (`cli.py`).  The BM25 relevance gate (`screen_relevance` /
  `bm25_scores`, from PRs #79/#81/#83) was only applied by the `auto`
  ingest pipeline; the standalone `search` command returned unscreened,
  potentially off-topic results.  `search --screen` now runs that same
  gate over the retrieved papers: each result is tagged with a relevance
  score + a keep / screened-out verdict, and a screening summary
  (`N retrieved → M kept, K screened out`) is printed to stderr.  It is
  **recall-preserving** — no paper is dropped from the output, so a caller
  can still audit the full retrieved count.  `--json` switches to a
  `{"screening_summary": {...}, "results": [...]}` object (each result
  carrying a `relevance` block) when `--screen` is set; without `--screen`
  the output is byte-identical to before (bare array).  Composable with
  `--adversarial` / `--max-variants` / `--rank-by` (orthogonal to ranking
  — `--screen` only annotates).  Reuses the existing gate; no new scorer.

- **`gap-to-topic` skill — a topic-decision dossier.** New 11th packaged
  skill. Choosing a thesis/proposal topic is a go/no-go decision, not a
  literature review; `gap-to-topic` produces a `.research/topic_dossier.md`
  that runs a candidate breakthrough point through a 3-gate AND test —
  ① is the gap open (adversarial-recall search + a verifiable `.bib`),
  ② is it a contribution (dead-end history + problem-solving/incremental
  typing), ③ is it feasible (data/resource accessibility) — and hands the
  final "is it worth doing" verdict back to the researcher. `skills/gap-to-topic/`
  (SKILL.md + 3 references + evals) mirrored to `skills_data/`;
  `.claude-plugin/plugin.json` 10→11 skills, version `0.2.0 → 0.3.0`. The
  `research-design-helper` and `literature-triage-matrix` descriptions gain
  a one-line boundary clause routing topic-selection prompts to `gap-to-topic`.
- **NLM session pre-flight in `auto_pipeline`.**  Before attempting any
  NotebookLM browser work, `auto_pipeline` now calls `check_session_health`
  on the stored `state.json`.  When the session is missing or expired the
  pipeline skips NLM gracefully, sets `nlm_deferred=True`, and prints a
  `[HINT]` pointing at `research-hub notebooklm login` — instead of running
  a full headless browser session that would crash with an opaque Playwright
  error.  The `_print_next_steps` footer now distinguishes
  *"session expired → login first"* from *"transient error → retry"*.
  Health-check errors are caught so existing behaviour is preserved when
  the auth module is unavailable.
- **Adversarial-recall search — `research-hub search --adversarial`.**
  A single query phrasing systematically misses papers that use other
  vocabulary; in topic-scoping search a missed paper makes a research gap
  look open when it is not. `--adversarial` expands the query into several
  phrasings (LLM-generated when an LLM CLI is on PATH, deterministic
  fallback otherwise), searches each, unions the results by `dedup_key`,
  and prints a recall-confidence verdict (`high`/`medium`/`low`, derived
  from query saturation) to stderr. New `search/query_expansion.py`;
  `adversarial_search()` + `RecallReport` added to `search/fallback.py`;
  `tests/test_search_adversarial.py` (18 cases).
- **Summary quality improvements** (4 changes):
  - `link_updater.find_related_in_cluster` capped at **10 results** (was
    unbounded) — prevents mega-hub nodes in the Obsidian graph for large
    clusters.
  - `remove_paper_links(slug, raw_dir, cluster)` — new function scrubs a
    deleted paper's slug from every sibling note's Related Papers section;
    removes the entire section header when the deleted slug was the last
    entry.
  - `remove_paper()` now cascades the cleanup automatically and returns
    `links_cleaned` in its result dict.  `dry_run=True` is respected.
  - `paper_summarize` RELEVANCE prompt updated to require a **specific
    dimension** (method / empirical context / finding) rather than
    accepting a generic "this paper is relevant to [cluster]" sentence.
  - `crystal emit` prompt now exposes a `first_finding` field per paper
    (first Key Findings bullet, callout-format aware) to give the LLM
    more signal per paper.
- **`docs/literature-review-deliverable.md` — format specification.**
  Defines the consolidated document the skill pipeline (`search` →
  `literature-triage-matrix` → `research-design-helper`) produces end
  to end: the fixed 9-section
  contract, the `.bib` + `.gaps.yml` companion-file schemas, the
  per-paper summarization contract (and how it relates to the
  `paper-summarize` skill), honesty rules, and the bilingual /
  Markdown+Word bundle convention. A fully synthetic worked example
  ships in the `ai-research-skills` catalog repo.
- **CI `skill-version-guard` job** (`.github/workflows/ci.yml`). Blocks
  a PR that changes skill content (`skills/` or
  `src/research_hub/skills_data/`) without also bumping
  `.claude-plugin/plugin.json` `version`. The marketplace plugin cache
  directory is keyed on the version string, so an un-bumped
  skill-content change ships to `master` but never reaches user
  installs. A 2026-05-21 dogfood verification (finding V1b) caught
  exactly this — a SKILL.md change merged without a version bump and
  silently failed to propagate. This guard makes that class of bug a
  hard CI failure at PR time.
- **`--peer-reviewed` flag on `search` and `auto`.** Drops preprint
  backends (arXiv/bioRxiv/chemRxiv/medRxiv), excludes gray doc types
  (preprint/posted-content/report/book-chapter/paratext/dataset), and
  floors corroboration. Closes the gap where `auto` ran search with
  **zero** filtering and the one-shot pipeline could not express
  "peer-reviewed only" (gray literature silently entered the vault).
- **`doctor` check `nlm_auth_paths`.** Reports which NotebookLM
  re-authentication paths actually work on this machine (interactive
  vs `--from-browser`/rookiepy) and the exact command to run.
- **`paper-memory-builder` anti-leakage rule + E4 triad.** New JSON
  Schema at `skills/paper-memory-builder/references/claims.schema.json`
  enforces: a claim with empty / absent `evidence_artifacts` MUST have
  `status: gap` and a non-empty `gap_reason`. Two new files alongside:
  `scripts/check_claims_schema.py` (validator with JSON-pointer-style
  error paths) and `tests/test_check_claims_schema.py` (14 cases — 1
  meta, 4 positive, 5 negative, 4 schema-shape guardrails). The
  binding contract is restated in `skills/paper-memory-builder/SKILL.md`
  §"Anti-leakage rule" so it survives the SKILL.md-only marketplace
  install sync. Status enum extended: `draft | supported | rejected |
  gap`. Closes the long-standing Phase 2 Task B1 + E4 backlog item
  from the `WenyuChiou/ai-research-skills` plan.
- **`tests/test_skills_data_parity.py`** (21 cases) — guards the
  `skills/` ↔ `src/research_hub/skills_data/` byte-parity invariant.
  ``research_hub.skill_installer`` copies skills from
  ``skills_data/``, so editing a SKILL.md in ``skills/`` only ships
  the change to public-repo readers, not to ``research-hub install``
  users. This test catches the divergence at PR time. Exception list
  (``SHADOW_ONLY_IN_SKILLS_TREE``) documents intentional shadows; one
  entry today (``zotero-skills`` vendored copy, scheduled for removal
  in Phase 2 Wave C).
- **Backup-first callout in `zotero-library-curator`.** SKILL.md
  §"Output discipline" + `references/report-template.md` now lead the
  "Suggested follow-ups" section with a Zotero-RDF backup reminder
  before any apply/CRUD handoff to `zotero-skills` or
  `research-hub zotero ... --apply`. Closes the gap surfaced by the
  `ai-research-skills` Task #27 dogfood walk: read-only audit + apply
  step are different skills, and the callout was only on the
  marketplace README — never echoed to the user at handoff time.

### Changed
- **`research-workspace` plugin version bumped `0.1.0` → `0.2.0`**
  (`.claude-plugin/plugin.json`). The marketplace plugin cache is keyed
  on this version; a dogfood test on 2026-05-20 confirmed fresh
  `claude plugin install` users were still receiving the pre-Phase-7
  cached `0.1.0` skill bundle — i.e. the `paper-memory-builder`
  anti-leakage rule (Phase 7 Wave A) and the `zotero-skills` shadow
  removal (Wave C) had shipped to `master` but not to user installs.
  Bumping the plugin version forces a fresh cache directory so those
  changes actually propagate. No skill behavior changed by the bump
  itself.
- **`paper-summarize` and `literature-triage-matrix` descriptions gain
  an "extract claims" disambiguation clause.** The same dogfood test
  surfaced a fragile auto-trigger boundary: a user saying "extract
  claims from these papers" could land at `paper-memory-builder`
  (own draft), `paper-summarize` (per-cited-paper), or
  `literature-triage-matrix` (cross-paper matrix). Both descriptions
  now state the disambiguation explicitly so the router picks
  correctly.

### Removed
- **Vendored `skills/zotero-skills/` shadow (Phase 7 Wave C).** The
  308-line vendored copy of the standalone `zotero-skills` plugin has
  been deleted; the canonical 60-line skill at
  `WenyuChiou/zotero-skills` is now the single source of truth.
  Coupled site updates landing in the same commit: `skill_installer.py`
  drops its `zotero-skills` exclusion (the dir no longer exists to
  filter), `tests/test_skills_data_parity.py` empties
  `SHADOW_ONLY_IN_SKILLS_TREE`, `tests/test_v068_3_version_sync.py`
  and `tests/test_v066_skill_schema.py` drop the now-stale exclusion
  comments / dead constants, and `docs/interop-test-v068-2.md` notes
  the historical snapshot vs the post-Wave-C state. Callers that
  resolve `Skill(skill="zotero-skills")` by bare name will now route
  to the canonical standalone plugin once that marketplace install
  exists in their environment. Users who relied on the vendored copy
  without separately installing `WenyuChiou/zotero-skills` will get a
  skill-not-found error until they run
  `git clone https://github.com/WenyuChiou/zotero-skills ~/.claude/skills/zotero-skills`
  (or `claude plugin install zotero-skills@ai-research-skills --scope user`).
  Closes Phase 2 backlog Item #3 from the
  `WenyuChiou/ai-research-skills` plan.
- **`.claude-plugin/plugin.json` description count corrected**
  9 → 10 skills (paper-summarize was added in v0.69 but never
  reflected in the auto-discovery plugin manifest). Picked up the
  Wave B reviewer P9 follow-up.

### Fixed
- **`probe_cleared_failed_no_abstract` now routes to abstract-text fallback.**
  When a URL's `summarize_status` is `failed_no_abstract` and the HTTP probe
  returns 200, the bundle was classifying the entry as `url_quality=ok` and
  uploading the URL to NotebookLM. This silently failed because publisher
  paywall pages (e.g. Springer) return HTTP 200 with a skeleton page that
  NLM also cannot read — the same paywall the summarizer hit at ingest time.
  `probe_cleared_failed_no_abstract` now resolves to `quality=likely_error_page`
  so the bundle falls back to abstract text when available, matching the same
  path already taken for `cloudflare_block`, `tf_cookie_wall`, and other
  confirmed paywall signals.
- **Ubuntu CI OOM (issue #61).** ubuntu-latest runners have ~7 GB RAM;
  2800+ tests with lazy-loaded modules OOM the runner. `test` job split
  into `test` (windows/macOS — 14 GB, full suite) and `test-ubuntu`
  (4 `pytest-split` shards, ~700 tests each). Coverage moved to
  `windows-latest` (per-shard coverage would undercount). `pytest-split>=0.8`
  added to dev deps.
- **User-agent strings updated to `research-hub/1.0.0`** across all
  14 search backends (biorxiv, chemrxiv, cinii, crossref, dblp, eric,
  kci, nasa_ads, openalex, pubmed, repec, websearch + the 3 already-fixed
  in the prior OSS-readiness commit). Mailto format preserved for APIs
  that recommend it (openalex, crossref, pubmed).
- **`cli.py build_parser()`** catches `PackageNotFoundError` (not bare
  `Exception`) when looking up the installed package version.
- **`pipeline_repair.py` provenance tag** bumped from
  `pipeline-repair-v0.12.0` to `pipeline-repair-v1.0.0`.

### Changed
- **`notebooklm login --help` rewritten to the three real paths.**
  Previously advertised `--cdp / --from-chrome-profile /
  --use-system-chrome / --timeout / --keep-open` as working modes;
  they were silently no-ops (the underlying aliases `del`'d their
  arguments). Help now states only: interactive default,
  `--import-from`, `--from-browser`.
- **`--from-browser` failure on Python ≥3.14 is now actionable.**
  Detects the missing-rookiepy + no-prebuilt-wheel case and points to
  the two paths that work (interactive in a terminal / `--import-from`)
  instead of a generic `pip install` hint that cannot succeed there.
- **5 SKILL.md descriptions tightened for keyword overlap with
  natural-language trigger prompts** (Phase 7 Wave A polish):
  `research-hub` adds "organize them" (matches the verified trigger
  prompt "find papers and organize them"); `paper-memory-builder`
  adds "extract claims, supporting evidence, and figure key numbers"
  (matches the catalog phrase); `research-design-helper` adds "is my
  research question sharp enough to be falsifiable?"
  (matches the verified Phase 5.3.b trigger example);
  `zotero-library-curator` adds "bloated or under-used" (matches the
  SKILL body's own audit dimension) plus an explicit RDF-backup
  reminder line. `research-hub-multi-ai` reframes itself as the
  **research-domain router** vs `agent-collab-workspace:agent-task-splitter`
  (generic multi-agent decomposition), documenting the artifact
  asymmetry (`.coord/multi_ai_plan.md` vs `.coord/plan.yml`) so the
  two skills no longer silently shadow each other on the same prompt
  — the routing overlap the `ai-research-skills` Task #27 trigger
  verification surfaced.

### Fixed
- **`auto` / `ingest` now refresh `_HOME.md`, MOC bodies, and cluster
  overviews on success.** The `populate_all_overviews` cascade
  (which writes `_HOME.md`, populates `(populated by sync)` MOC bodies
  with their cluster lists, and refreshes every `hub/<slug>/00_overview.md`)
  existed but was wired into `vault rebuild-overviews` only — `auto`
  never called it. Result: every research-session ingest left the
  vault-level navigation silently stale (empirically reproduced
  post-PR-D 4-leg E2E: no `_HOME.md` on disk, MOCs frozen at
  "(populated by sync)"). Now the cascade fires automatically when
  ingest wrote >0 papers; failures are logged to stderr and swallowed
  (the ingest itself already succeeded, navigation drift is non-fatal).
- **`--auto-detect` cookies path hotfix.** PR-D's `_patchright_cookies_db`
  hardcoded the LEGACY `Default/Cookies` path; modern Chromium (80+,
  including patchright's bundled chromium-1208) stores cookies under
  `Default/Network/Cookies`. Result: auto-detect polled the wrong file,
  never fired, user logged in successfully in the browser but the save
  never triggered. The path resolver now prefers
  `Default/Network/Cookies`, falls back to legacy `Default/Cookies`
  only if modern is missing AND legacy exists; if neither has been
  written yet (browser starting), returns the modern path so the next
  poll finds it the moment chromium writes it.

### Added
- **`notebooklm login --auto-detect` — fully automatic zero-touch login.**
  Replaces the half-automatic `--wait-file` flow (which still required a
  manual file-touch after browser sign-in). With `--auto-detect`,
  research-hub polls the patchright Chromium profile's Cookies SQLite
  read-only for a `notebooklm.google.com` host_key. When you sign in
  and land on the NotebookLM homepage, the cookie appears, the script
  feeds both `\n` (any pending `input()` ENTER) and `y\n` (any pending
  `click.confirm` "Save anyway?" fallback) to the SDK subprocess, and
  the session is saved automatically. No terminal, no wait-file touch,
  no click.confirm response. Fail-closed on `--wait-timeout`
  (default 300 s): nothing is saved on timeout. Mutually exclusive with
  `--wait-file`, `--import-from`, `--from-browser`.

### Fixed
- **Ingest skips a paper missing one or more required core fields
  instead of aborting the whole batch.** A real-world `auto` run (LLM
  reservoir management search) hit a CrossRef return with empty
  `authors: []` and the pipeline fail-fast-aborted the entire ingest
  with "INPUT VALIDATION FAILED" even though 2 other valid papers
  were ready to write. The previous `missing_doi_only` skip branch
  was inert (`doi` is not in any required-fields list, so
  `_validate_paper_input` never emitted "missing required field
  'doi'") and is replaced by a working
  `_only_missing_required_field_errors` predicate covering every
  field in `REQUIRED_FIELDS_CORE` (title / authors / year). When
  every error for a paper is a "missing required field 'X'" error,
  that paper is skipped from the batch with a logged "SKIPPED invalid
  input" entry, and the remaining valid papers still write to Zotero /
  Obsidian. Strict dry-run behaviour is preserved (every validation
  issue surfaces) so the operator sees the full picture before a real
  run.
- **L1-deferred-but-L2-corroborated papers no longer fail-close at
  `L1-deferred`.** When the DOI resolver HEAD is transient-blocked
  (anti-bot 401/403/406/418/451/etc. -- classified as
  `*_check_unavailable` by F7 / PR #51), the gate used to quarantine
  immediately at `L1-deferred` even when L2 corroboration (now augmented
  by PR #53's CrossRef-by-DOI metadata verify) would confirm it. The
  gate now lets such papers fall through to L2 / L3 / fit-check; if all
  pass, the paper is accepted with
  `provenance.doi_recheck_pending = True` and
  `provenance.doi_recheck_details = {reason, status_code, url,
  resolved_via}` so a future tool can re-verify the DOI when the
  publisher's anti-bot wall lifts. Definitive L1 failure (HTTP 404/410)
  still fail-closes as `doi_unresolved` / `L1` -- the fabrication
  guarantee is unchanged; L2 corroboration + L3 metadata integrity
  remain the fabrication gate. The `L1-deferred` quarantine bucket is
  structurally empty post-fix; `DEFERRED_LAYER` survives as a public
  constant used by docs / reporting.
- **L2 corroboration augments single-source DOIs with direct CrossRef
  metadata verify.** A paper found by only one search backend (e.g.
  `source: 'openalex'`) was quarantined `L2 / uncorroborated` even when
  its DOI was independently confirmable via CrossRef. The gate now
  does a direct `https://api.crossref.org/works/{doi}` metadata fetch
  for such papers; if CrossRef returns a record whose title/year/
  authors match per the existing `_records_agree` predicate
  (`fuzz.token_set_ratio >= 85`, `|year_delta| <= 1`, surname
  intersection >= 1), CrossRef is recorded as a verified backend and
  the paper passes L2. Strictly augmentative: CrossRef is an
  authoritative metadata source, this only adds an existing-paper
  evidence check; the L2 corroboration bar itself is unchanged. Result
  cached in `crossref_verify_cache.json` (schema 1.0); failures are
  fail-quiet and not cached.
- `zotero gc` / `zotero mark-kept --all-orphans`: a real cluster
  collection whose Zotero key drifted from its `cluster.zotero_collection_key`
  binding (e.g. a Zotero-truncated date-prefixed name like
  `20260518-machine-learning-flood-forecas`) is no longer mis-flagged as an
  orphan candidate. New conservative, suppression-only name-normalization
  match (`_normalize_collection_name` + bidirectional prefix match, min
  12-char guard). No rebind/merge/delete-logic change; strictly fewer GC
  candidates. PR-A's non-empty hard-skip remains as an independent safety
  net.
- **arXiv hits no longer leak past `--exclude-type preprint`.** The
  arXiv backend left `doc_type` empty, so the type filter silently
  missed every raw arXiv result (bioRxiv/chemRxiv already set it).
  Now `doc_type="preprint"`.
- **Self-heal commands are environment-correct.** New
  `recommended_cli_invocation()` picks the `research-hub` console
  script when on PATH, else the `python -m research_hub` module form.
  Wired into the NLM preflight, `RequiresAuthRefresh`, keepalive task
  resolution, and the auto-pipeline NLM-skip hint — these previously
  hardcoded a console-script command that fails on source checkouts.
- **`notebooklm keepalive` no longer reports false-green.** It now
  re-probes session health *after* rotating cookies; a rotation that
  does not preserve a usable session (server-side re-auth) returns
  non-zero instead of exit 0.
- **F7: doi.org anti-bot 418 no longer quarantines every valid paper.**
  The authenticity gate's DOI resolver sent the default
  `python-requests` User-Agent, which doi.org/Cloudflare answer with
  HTTP 418 — read as `doi_unresolved` → **every** peer-reviewed paper
  fail-closed-quarantined (reproduced: `accepted: 0; quarantined: 2`,
  `DOIs accessible: 0`; the same DOI returns 200 with a real UA). Fix:
  send a real `User-Agent`; classify 408/418/425/429/5xx + network
  errors as *transient* (bounded retry + backoff, **not** cached as a
  permanent miss, surfaced as `*_check_unavailable`); genuine 404/410
  stay fail-closed `doi_unresolved` so the anti-fabrication guarantee
  is unchanged. A 0/malformed status also fails closed.
- **F7 completion: access-blocked resolver statuses defer.** DOI HEAD
  statuses other than resolved 2xx/3xx or definitive 404/410
  non-registration (for example 401/403/406/451 anti-bot walls) now
  route to `doi_check_unavailable` / `L1-deferred` instead of permanent
  `doi_unresolved` / `L1` quarantine.
- **Semantic Scholar API keys are validated before use.** A
  non-latin-1 `SEMANTIC_SCHOLAR_API_KEY` now emits a clear warning and
  is ignored so the backend queries anonymously instead of crashing while
  requests encodes the `x-api-key` header.
- **DOI resolve cache auto-migrates pre-PR-#51 poisoning.** The F7
  completion (anti-bot HEAD defers, PR #51) was silently neutralised on
  any DOI cached under the old non-transient classification -- the
  cache-hit short-circuit returned the stale `doi_unresolved` outcome
  before the new logic ran. `DoiResolveCache.load` now performs a
  one-shot schema 1.0 -> 1.1 migration that prunes
  `reason="doi_unresolved"` entries whose `status_code` is not in
  `{404, 410}` (genuine non-existence) and rewrites the cache at the
  new schema version. Entries with status 404/410, success entries, and
  any other reason are preserved. Idempotent; logged at WARNING when
  any entry is pruned.

### Removed
- **Dead `notebooklm login` flags:** `--cdp`, `--chrome-binary`,
  `--use-system-chrome`, `--from-chrome-profile`,
  `--chrome-profile-path`, `--chrome-profile-name`, `--keep-open`,
  `--timeout`, and the unused `login_interactive` /
  `login_interactive_cdp` aliases they delegated to.

### Fixed (PR-A)
- **`zotero gc` no longer presents non-empty real collections as
  deletion candidates.** Any Zotero collection whose key was not a
  *current* cluster binding was flagged `orphan-from-vault` — including
  stale non-empty date-prefixed duplicate collections holding real
  items. `delete_candidates` already hard-skipped non-empty collections
  (so no data could actually be lost), but the **output falsely implied
  a data-loss risk**, eroding trust in the tool. Now: non-empty orphans
  get a distinct `orphan-with-items(N)` reason, are listed under a
  separate "NON-EMPTY ORPHANS — review only; gc cannot delete these"
  section, are never offered in the interactive prompt, and are
  excluded from `--yes`. Empty/test junk GC is unchanged.

### Fixed (PR-B)
- **F6: `auto` no longer prints `[OK] ingest N papers` when 0 were
  written.** When every candidate was quarantined by the fail-closed
  authenticity gate the raw dir was never created, the `exists()` guard
  was skipped, and the tentative `len(papers)` count survived — the
  pipeline reported a clean ingest of N papers while the vault got
  nothing. The count is now authoritative (`0` when nothing written);
  an all-quarantined ingest is reported as a failed step with an
  actionable `quarantine list` hint, not `[OK]`. A 0-written /
  0-quarantined result (e.g. empty search) keeps the lenient path with
  an honest `N written, M quarantined (of K candidates)` message.
- **F8: `notebooklm upload` no longer exits 0 when 0 sources were
  transferred.** _(Root cause later revised — the common cause is the
  URL-quality skip, not the upstream API; see the "Fixed (F8 real fix)"
  entry above.)_ When NotebookLM's source API drifts under the pinned
  `notebooklm-py` (e.g. `Sources data ... is not a list (NoneType)`)
  the notebook is created but no sources land; the old code returned 0
  because `fail_count == 0`. A non-dry-run upload that transfers,
  caches, and prunes nothing is now a non-zero error naming the likely
  cause. (`notebooklm-py` was already pinned `<0.5.0`; this drift is
  server-side, so honest reporting is the only available remedy.)

### Fixed (PR-C — deep F7)
- **Transient DOI-resolution failures defer instead of being
  fail-closed-quarantined as fraud.** PR-B's minimal F7 fix stopped the
  *cache* poisoning but the authenticity gate still quarantined ANY
  `not ok` at L1 — including `*_check_unavailable` (doi.org / Crossref
  rate-limit or network blip after the bounded retry). A sustained
  rate-limit window therefore still rejected valid papers, requiring
  manual `quarantine restore`. Now the L1 branch splits by reason
  family: transient → distinct `L1-deferred` layer (reported as
  "deferred, retryable"; recovers on a later run / `quarantine
  restore`); permanent (`*_unresolved`, 404/410, no-identifier,
  predatory/metadata/fit/uncorroborated) → unchanged `L1` quarantine.
  The paper is still held out of ingest in both cases (fail-closed —
  the anti-fabrication L0–L5 guarantee is unchanged; a fabricated DOI
  returns 404 → permanent → quarantined). `auto` now reports
  `N quarantined, D deferred` distinctly, and an all-deferred run says
  the papers were *not* rejected and how to retry, instead of
  "quarantined". (An optional `quarantine retry-deferred` convenience
  CLI is deferred to a later follow-up — existing `quarantine restore`
  already recovers deferred entries.)

### Added (PR-D)
- **`notebooklm login --wait-file PATH` — non-interactive login (no
  terminal/ENTER).** The upstream login blocks on `input("press
  ENTER")`, which can't be driven headless/scripted. With `--wait-file`
  you sign in in the browser then create PATH (`touch PATH`, or an
  automation wrapper does it); research-hub polls for it and feeds the
  newline that triggers the upstream session save. `--wait-timeout`
  (default 300s) fails closed — on timeout the subprocess is terminated
  and nothing is saved. Stale signal files are cleared first so a
  leftover from a previous run can't auto-trigger before sign-in. This
  formalizes (in Python, testable) the signal-pipe technique used to
  recover the maintainer's expired session.

### Fixed (F8 real fix)
- **`auto` can now actually upload publisher-URL clusters to
  NotebookLM.** Diagnosed 2026-05-19: an all-URL cluster (DOIs →
  ScienceDirect/Elsevier) uploaded 0 sources because every entry was
  `likely_error_page` (our local probe can't read the anti-bot wall)
  and the conservative URL-quality gate skipped them all — and `auto`
  called `upload_cluster` positionally with no way to override, so
  there was no path to rescue it through the pipeline. The earlier F8
  message also mis-blamed a NotebookLM API change (the
  `SourcesAPI.list ... NoneType` warning was a red herring — listing an
  empty new notebook). The conservative skip is intentional design and
  is **unchanged**; instead `--include-suspect-urls` is now exposed on
  `auto` and threaded `auto → auto_pipeline → upload_cluster`, and the
  0-sources error message now lists the real likely cause first (URL
  sources skipped → re-run with `--include-suspect-urls`) instead of
  pointing at the upstream API.

### Added (F8 first-principles fix — content-priority ladder)
- **NotebookLM bundles now upload the abstract as a text source when no
  PDF is obtainable, instead of a paywalled URL.** First-principles
  diagnosis: NLM needs *content*, not a URL — a paywalled publisher DOI
  carries none. Local PDF (rung 1) and Unpaywall/OA PDF (rung 2, via
  `fetch_paper_pdf`) already worked; the gap was rung 3. `bundle.py`
  now: no PDF + (no URL or a `likely_error_page` paywall URL) + a real
  `## Abstract` in the note → emits `action="text"` carrying the
  abstract (title/DOI-prefixed); a *good* (non-suspect) URL is still
  preferred (full text). `NotebookLMClient.upload_text` →
  `sources.add_text`; `upload.py` dispatches `action="text"`;
  `BundleReport.text_count`. Net: an all-paywall-URL cluster that
  previously uploaded 0 sources now uploads the abstracts — real
  content NotebookLM can synthesise. The conservative URL-quality gate
  and `--include-suspect-urls` override (band-aid) are unchanged.
- **`socket.getfqdn` CI flake — autouse stub in `tests/conftest.py`**
  (master had been red on this for ≥3 consecutive runs:
  `26185448887`, `26191738564`, `26192402510`). Multiple test files
  construct `ThreadingHTTPServer(("127.0.0.1", 0), ...)` whose
  `server_bind()` calls `socket.getfqdn("127.0.0.1")`. On macOS
  GitHub Actions runners (and Bonjour/mDNS-equipped environments
  generally) the reverse-DNS lookup hangs 30+ seconds before
  `pytest-timeout` fires — Python stdlib
  [issue14914](https://bugs.python.org/issue14914), 14-year-old bug.
  The first attempt of this fix patched only the
  `artifact_server` fixture in `test_artifact_delete_endpoint.py`,
  but the next CI re-run surfaced the same flake at
  `test_dashboard_executor_e2e.py::test_e2e_sse_event_after_action`.
  `grep -rln 'ThreadingHTTPServer'` found **7 test files** with the
  same construction pattern, so the fix promoted to a
  `conftest.py`-level autouse fixture (`_stub_socket_getfqdn`) that
  stubs `socket.getfqdn` for every test in `tests/`. Production
  code path is unchanged — `monkeypatch` scope is per-test,
  reverting at teardown.

### Removed

- **Legacy root `plugin.json` deleted** (Phase 7 Wave B from the
  `WenyuChiou/ai-research-skills` marketplace-maturity tracker — see
  research-hub issue
  [#60](https://github.com/WenyuChiou/research-hub/issues/60)). The
  file was an early Cowork-plugin placeholder with a self-described
  TODO ("Convert to full Cowork plugin manifest when plugin schema is
  finalized") that never got migrated. It declared 3 skill paths,
  one of which (`skills/knowledge-base/SKILL.md`) was the long-removed
  `knowledge-base` alias, while 11 actual skill dirs ship under
  `skills/`. The active manifest is `.claude-plugin/plugin.json`,
  which uses Claude Code marketplace auto-discovery and is unaffected.
  `grep -rn 'plugin\.json'` against `tests/` + `src/` + non-meta docs
  returns zero references to the root file — it is a pure orphan.
  Removing it removes a misleading source of truth without touching
  any install / marketplace / test path.

---

_Older releases (the v1.0.0 pre-release planning notes, v0.95.x and earlier)
are archived in [CHANGELOG-archive/CHANGELOG-pre-1.0.md](CHANGELOG-archive/CHANGELOG-pre-1.0.md)._

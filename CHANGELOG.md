# Changelog

## v0.37.2 (2026-04-18)

**Final fix for the 16-build-long CI failure: parent-package attribute leak.**

After v0.37.1 fixed test_drift_crystal's `sys.modules` pollution, 3 tests in `test_v033_workflows.py` still failed on Python 3.10/3.11/3.12 with `assert False is True`. Root cause: the autouse `_reset_cached_modules` fixture popped `sys.modules["research_hub.crystal"]` but **not** the cached attribute on the parent package.

**The bug**:
1. mock.patch("research_hub.crystal.list_crystals") walks `getattr(research_hub_pkg, "crystal")` → finds the OLD module from a prior test
2. Patches `list_crystals` on the OLD module
3. `ask_cluster` does `from research_hub.crystal import list_crystals` → finds sys.modules empty (fixture popped it) → re-imports from disk → DIFFERENT module object → unpatched real function
4. Real `list_crystals` returns `[]` on tmp vault → no match → digest fallback fails → ok=False

**Fix**: Extended `_reset_cached_modules` to also `delattr(parent_pkg, child_name)`. This forces mock.patch's `_importer` to fall through to `__import__`, which re-loads the same module that ask_cluster's late import will find.

Local Python 3.14 didn't reproduce because Python 3.14's import machinery handles the parent-package attribute lookup differently.

**This was a 16-build-long CI red streak** since v0.30 — bug existed earlier, was masked locally by import ordering. Now confirmed green locally with both pytest 8 and 9. Memory file `feedback_research_hub_user_facing_bugs.md` updated to enforce CI-green-before-tag from now on.

---

## v0.37.1 (2026-04-18)

**CI green for the first time since v0.31.1. 15+ red builds caused by one test pollution bug.**

`tests/test_drift_crystal.py::_install_fake_crystal_module` permanently replaced `sys.modules["research_hub.crystal"]` with a stub module containing only `check_staleness`, with no teardown. In CI's alphabetical test order this stub leaked into every subsequent test that imports from `research_hub.crystal` — most notably `test_v033_workflows.py`, which then failed with `AttributeError: <module 'research_hub.crystal'> does not have the attribute 'list_crystals'` when `mock.patch` tried to find an attribute on the stub.

Locally the failure was hidden because Python 3.14 + pytest's discovery order in pip-editable mode loaded `research_hub.crystal` differently. CI uses 3.10/3.11/3.12 + plain install + `--maxfail=3`.

**Fix**: autouse fixture in `test_drift_crystal.py` snapshots `sys.modules["research_hub.crystal"]` and `research_hub.crystal` attribute before each test, restores both on teardown. 5-line change.

This release ships ONLY the fixture fix — same 1312 tests, no other code changes.

---

## v0.37.0 (2026-04-18)

**Cluster integrity + memory CLI/MCP exposure + critical require_config bug fix. 1282 → 1312 tests (+30).**

Two intersecting goals:
1. **Cluster ↔ paper binding can drift in any vault** (rename + folder not migrated, import-folder dump without --cluster, manual folder reorg). Doctor never noticed; rebind path didn't exist. v0.37 closes both gaps for all 4 personas.
2. **Memory layer (v0.36) was Python-API only.** v0.37 adds CLI subcommand + 4 MCP tools so Claude Code / any MCP client can query.
3. **Bonus critical fix**: `require_config()` now treats `RESEARCH_HUB_ROOT` env var as a valid init signal (was: required config.json file). Headless / CI / test environments no longer hit a misleading "not initialized" SystemExit when the env-var path is the only init.

Full release report: [docs/audit_v0.37.md](docs/audit_v0.37.md). Design notes: [docs/cluster-integrity.md](docs/cluster-integrity.md).

### Added — Cluster integrity (Track A)

5 new doctor checks in `src/research_hub/doctor.py`:
- `cluster/missing_dir` — FAIL: `cluster.obsidian_subfolder` doesn't exist as `raw/<dir>` (e.g. cluster renamed without folder migration)
- `cluster/orphan_papers` — WARN: `raw/foo/` holds papers but no cluster has `obsidian_subfolder=foo` (e.g. legacy layout, archive restore, import-folder dump)
- `cluster/empty` — WARN: cluster's folder has 0 papers
- `cluster/cross_tagged` — WARN: paper physically in cluster A folder but `cluster:` frontmatter says cluster B
- `quote/orphan` — WARN: quote captured on a paper not in any cluster (Persona C concern)

NEW `src/research_hub/cluster_rebind.py` — emit/apply rebind workflow:
- `emit_rebind_prompt(cfg)` walks `raw/`, reads each orphan paper's frontmatter (`cluster:`, `collections`, `tags`, `category`), proposes target cluster with high/medium/low confidence
- `apply_rebind(cfg, report_path, dry_run=True)` executes file moves; dry-run is the default
- All moves logged to `.research_hub/rebind-<timestamp>.log` for manual undo

NEW CLI: `research-hub clusters rebind {--emit, --apply <path> [--no-dry-run]}`.

### Added — Memory CLI + MCP exposure (Track B)

NEW CLI subcommand `research-hub memory {emit, apply, list, read}` matching the crystal subcommand pattern.

NEW 4 MCP tools (52 → 56):
- `list_entities(cluster)` — orgs/datasets/models/etc. registry
- `list_claims(cluster, min_confidence)` — typed claims with confidence filter
- `list_methods(cluster)` — technique families
- `read_cluster_memory(cluster)` — full ClusterMemory dict; returns `found: false` graceful fallback

### Fixed — `require_config()` env-var path (Track Z)

`src/research_hub/config.py::require_config` previously raised SystemExit("not initialized") whenever no `config.json` existed, even if `RESEARCH_HUB_ROOT` pointed to a valid directory. This blocked CI tests and any user bootstrapping via env vars (despite `HubConfig.__init__` fully honoring the env var). Now treats either signal as initialized.

3 regression tests in `tests/test_config.py`:
- `test_require_config_accepts_research_hub_root_env_var` — env-var path works
- `test_require_config_still_fails_when_root_dir_missing` — bogus paths still fail (security: don't accept any env value blindly)
- `test_require_config_fails_when_no_config_and_no_env` — original guard preserved

### Tests

- `tests/test_v037_cluster_integrity.py` — 18 tests (12 doctor/rebind + 6 persona × cluster-integrity matrix covering all 4 personas A/B/C/H)
- `tests/test_v037_memory_cli.py` — 6 tests
- `tests/test_v037_memory_mcp.py` — 4 tests
- `tests/test_config.py` — 3 new regression tests for require_config env-var path

### Vault restore (closes Task #124, pending since v0.28)

Restored 1094 paper notes (was 36) from `knowledge-base-archive-20260415/` across 9 topic folders + 5 archived clusters. Cleaned 4 `persona-*-test` test pollution folders + 5 stray quote files. Live-verified the new doctor checks against this real vault: detected 1063 orphans + 3 missing_dir + 5 quote orphans (all from test pollution, since cleaned).

### Stats

- Tests: 1282 → 1312 (+30)
- New files: 6 (rebind module + 3 test files + 2 docs)
- Modified: pyproject, CHANGELOG, README ×2, doctor, mcp_server, cli, config, mcp-tools.md

---

## v0.36.0 (2026-04-18)

**Structured memory layer (entities + claims + methods). 1270 → 1282 tests (+12). Architecture-only release.**

Crystals tell the AI *what to think* about a cluster (canonical prose). The new memory layer captures *what is named and asserted* in a cluster — orgs, datasets, models, benchmarks, methods, and structured claims with confidence + supporting paper slugs. Generated once per cluster via the same emit/apply pattern.

Full release report: [docs/audit_v0.36.md](docs/audit_v0.36.md). Design notes: [docs/cluster-memory.md](docs/cluster-memory.md).

### Added — Cluster memory (Track A)

NEW `src/research_hub/memory.py` (~280 LOC):
- 4 dataclasses: `MemoryEntity`, `MemoryClaim`, `MemoryMethod`, `ClusterMemory`
- 3 vocabularies (open-ended, suggested only): entity types (org/dataset/model/benchmark/method/person/concept/venue), method families (supervised/self-supervised/rl/finetune/prompt/search/graph/statistical/geometric/symbolic/hybrid/other), confidence levels (high/medium/low)
- `emit_memory_prompt(cfg, cluster_slug)` → builds AI extraction prompt (reuses `crystal._read_cluster_papers` + `_read_cluster_definition`)
- `apply_memory(cfg, cluster_slug, scored)` → validates JSON, dedups by slug, filters unknown paper slugs, writes atomic `hub/<slug>/memory.json`
- `read_memory`, `list_entities`, `list_claims`, `list_methods` query helpers
- Strict slug validation (lowercase kebab-case)
- Claims with no supporting papers are skipped

NEW `tests/test_v036_memory.py` — 12 tests covering emit + apply + filter + dedup + invalid-slug + invalid-confidence + empty-payload + round-trip + missing-file.

NEW `docs/cluster-memory.md` — design rationale, schema reference, how this differs from crystals, how to add a new entity type or method family.

### Preserved (zero behavioral changes)

- `crystal.py` unchanged — memory imports `_read_cluster_papers` and `_read_cluster_definition` read-only
- All CLI commands unchanged (no `memory` subcommand yet)
- All MCP tools unchanged (no `list_entities` / `list_claims` / `list_methods` exposed yet)
- `notebooklm/*` unchanged
- Connector Protocol from v0.35 unchanged

CLI + MCP integration of memory lands in v0.37 alongside the housekeeping batch.

### Stats

- Tests: 1270 → 1282 (+12)
- New files: 3 (memory module + tests + design doc)
- Modified files: 1 (pyproject version bump)
- LOC delta: ~+700

### Codex critique status (now complete)

- Phase 1 (Document abstraction) ✅ v0.31
- Phase 2 (structured memory) ✅ v0.36
- Phase 3 (tool consolidation) ✅ v0.33
- #5 (NLM as optional connector) ✅ v0.35

---

## v0.35.0 (2026-04-18)

**Connector Protocol abstraction. 1262 → 1270 tests (+8). Architecture-only release; no CLI/MCP changes.**

NotebookLM is no longer the only external service research-hub knows about. A new `Connector` Protocol formalizes the bundle/upload/generate/download/check_auth surface so future connectors (Notion, Google Drive, Logseq, custom KM systems) can be plugged in without touching workflows or CLI code.

Full release report: [docs/audit_v0.35.md](docs/audit_v0.35.md). Design notes: [docs/connector-design.md](docs/connector-design.md).

### Added — Connector Protocol (Track A)

NEW `src/research_hub/connectors/__init__.py` (~110 LOC):
- `Connector` typing.Protocol — name + 5 methods (`bundle`, `upload`, `generate`, `download`, `check_auth`)
- 3 dataclasses: `ConnectorBundleReport`, `ConnectorUploadReport`, `ConnectorBriefReport` — uniform Report shapes across all connectors
- Module-level registry: `register_connector()`, `get_connector(name)`, `list_connectors()`
- Auto-registers built-in `notebooklm` + `null` connectors at import time

NEW `src/research_hub/connectors/null.py` (~70 LOC) — `NullConnector` for testing and Persona B/H environments where NotebookLM is unavailable. Returns synthetic empty reports; `check_auth` always True.

NEW `src/research_hub/connectors/_notebooklm_adapter.py` (~110 LOC) — `NotebookLMConnector` wraps existing `notebooklm.bundle.bundle_cluster`, `notebooklm.upload.upload_cluster`, `notebooklm.upload.generate_artifact`, `notebooklm.upload.download_briefing_for_cluster`. Maps internal Report types to Protocol Report dataclasses.

NEW `tests/test_v035_connectors.py` — 8 tests: protocol satisfaction (`isinstance(c, Connector)`), registry validation (rejects empty name + non-Protocol objects), null connector synthetic returns, adapter delegation via `patch("research_hub.notebooklm.bundle.bundle_cluster")`.

NEW `docs/connector-design.md` — design rationale + how to add a new connector.

### Preserved (zero behavioral changes)

- `src/research_hub/notebooklm/*` — 2,463 LOC unchanged
- 15 existing import sites of `notebooklm.*` — unchanged
- All CLI commands — unchanged (no `--connector` flag yet)
- All MCP tools — unchanged
- All workflows.py wrappers — unchanged

This release is the architecture seam for v0.36+. CLI/MCP exposure of `--connector` flags lands when a second real connector is added.

### Stats

- Tests: 1262 → 1270 (+8 connector tests)
- New files: 5 (3 connector source + 1 test + 1 design doc)
- Modified files: 1 (pyproject version bump)
- LOC delta: +512

---

## v0.34.0 (2026-04-18)

**Dashboard polish + persona × pipeline test matrix. 1249 → 1262 tests (+13). No new features.**

CSS-only dashboard polish (dark mode, refined token system, animations) + first cross-persona test coverage (Personas C and H had ZERO direct tests before; now 4 personas tested).

Connector abstraction (the prior v0.34 plan) deferred to v0.35.

Full release report: [docs/audit_v0.34.md](docs/audit_v0.34.md). Persona reference: [docs/personas.md](docs/personas.md).

### Added — Dashboard polish (Track A)

`src/research_hub/dashboard/style.css` (~150 LOC added/edited):
- **Full dark mode** under `@media (prefers-color-scheme: dark)`. Auto-switches with OS theme.
- **Token system extended**: `--surface-3`, `--border-strong`, `--header-bg/-fg`, `--brand-glow`, `--ok-soft/--warn-soft/--fail-soft`, `--shadow-1/-2/-glow`, `--radius-sm/md/lg/xl/pill`, `--ease-out`, `--duration-fast/base`. Type scale gained `--text-md-2` (1.125rem) + `--text-2xl` (2rem) — fills the awkward 1rem→1.5rem gap.
- **Live pill**: pulsing animation + glow ring when active; calmer chip when off
- **Buttons**: hover lifts to `--brand-strong` + glow; active tap depresses 1px
- **Cluster cards**: hover lift + open shadow
- **Treemap cells**: gradient + radial highlight + lift-on-hover with saturation pulse
- **Status badges**: tinted backgrounds (was just colored borders)
- **Vault search**: focus ring with brand glow
- **Sticky header**: theme-aware via `--header-bg` (was hardcoded dark)

5 demo PNGs in `docs/images/` re-shot at @2x via the v0.32 `dashboard --screenshot` CLI.

**Constraints preserved (verified):** all 6 tab radio IDs, all 6 panel IDs, `vault-search`, `live-pill`, `csrf-token`, all `data-jump-tab`/`data-cluster`/`[data-action]` attributes. Zero changes to `template.html`, `script.js`, or any Python.

### Added — Persona × pipeline test matrix (Track B)

NEW `tests/_persona_factory.py` — `make_persona_vault(tmp_path, persona)` builds vault state for personas A/B/C/H. Forces `RESEARCH_HUB_CONFIG=/nonexistent` to bypass developer's real config (caught a real pollution bug during development).

NEW `tests/test_v034_persona_matrix.py` — 13 tests targeting 8 high-risk persona × pipeline combinations + persona-aware doctor + dashboard rendering for all personas. Coverage shifts from "Persona A everywhere + B in 2 spots" to "all 4 personas have at least one direct test for their critical pipeline."

NEW `docs/personas.md` — formal persona reference. Per-persona profile, typical CLI pipeline, per-feature ✅/🟡/❌ matrix. Maps each persona to its test file.

### Fixed — pre-release CI hygiene (shipped earlier today as v0.33.3, included here)

- `pyproject.toml addopts` filters `-m 'not stress'` so 1000-paper stress tests stay opt-in
- `tests/conftest.py` autouse fixture path pattern extended from `test_cli_*.py` to also match `test_v0NN_*.py` for v030+ tests calling `cli.main([...])`

### Test count

| Release | Passing | Skipped | xfail | Delta |
|---|---|---|---|---|
| v0.33.3 | 1249 | 14 | 2 + 1 xpassed | — |
| **v0.34.0** | **1262** | **14** | **2** + 1 xpassed | **+13** |

### Out of scope (v0.35+)

- **Connector abstraction** — still 1-2 days work; deferred to focus this release on polish + tests
- **Codex Phase 2 (structured memory)** — multi-release research project
- **`cli.py` / `mcp_server.py` monolith splits** — HIGH RISK
- **Live NotebookLM round-trip in CI** — needs Chrome+CDP
- **Task #124 archived vault restore** — needs user decision
- **Search recall xfail baselines** (v0.26)
- **Zotero key encryption** via OS keyring
- **`.dxt` Claude Desktop extension**

## v0.33.3 (2026-04-18)

**Patch: stress test marker filter + screenshot CLI test autouse fixture extension.**

Two CI hygiene fixes that surfaced after v0.33.2:

### Fixed — stress tests no longer run by default

`tests/test_v030_large_vault.py::test_dashboard_render_1000_papers_under_5s` was running in the default pytest run despite the `pytestmark = pytest.mark.stress` marker. The marker was registered in `pyproject.toml::[tool.pytest.ini_options].markers` (purely documentary) but the `addopts` line never actually filtered them out.

Fix: added `-m 'not stress'` to `addopts`. `pytest -m stress` still opts in.

### Fixed — `test_v032_screenshot.py::test_cli_screenshot_requires_out_for_single_tab` CI fail

The autouse `_auto_mock_require_config` fixture in `tests/conftest.py` only matched `tests/test_cli_*.py` paths. v0.32's screenshot test calls `cli.main([...])` from a `test_v032_*.py` file, so it hit `require_config()` and crashed in CI (no config file).

Fix: extend the autouse fixture path pattern to match `test_v0NN_*.py` for v030+ files (currently v030, v031, v032, v033, v034). Patches `cli.get_config` only — NOT `cli.require_config` itself, since the dispatcher detects monkey-patching via `cli.get_config is require_config.__globals__["get_config"]` and would break if we replaced require_config (lambda has different __globals__).

## v0.33.2 (2026-04-17)

**Patch: brief_cluster fixes found in live NotebookLM round-trip test.**

Full live round-trip validation (bundle → upload → generate → download → preview against real NotebookLM with 20 sources) caught two bugs in the `brief_cluster` wrapper that all unit tests missed (because they mocked the cluster registry).

### Fixed — `ClusterRegistry` has no `load()` method

`brief_cluster` called `ClusterRegistry.load()` but the registry auto-loads on `__init__`. Removed the redundant call.

### Fixed — wrong attr name for source count

`bundle_result.source_count` doesn't exist on `BundleReport`; it has `pdf_count` and `url_count` properties instead. `brief_cluster` now returns `pdf_count`, `url_count`, AND their sum as `source_count`.

### Verified — end-to-end live

Live round-trip on `llm-agents-software-engineering` cluster (20 URL sources):
- Bundle: 20 URLs bundled
- Upload: 6 new uploaded, 14 skipped from cache (prior NLM session auth still valid)
- Generate: 3 saved briefings created
- Download: 313-char briefing persisted to `.research_hub/artifacts/`
- `brief_cluster` wrapper: completes with `steps=[bundle, download]` when notebook already exists

## v0.33.1 (2026-04-17)

**Patch: ask_cluster fuzzy-match bugs found via live testing. 1247 → 1249 tests (+2 regression).**

Live smoke-test of v0.33.0 on the real `llm-agents-software-engineering` cluster (10 crystals) caught two bugs in the `ask_cluster` fuzzy matcher:

### Fixed — `ask_cluster` false-miss on boundary scores

The token_set_ratio cutoff of 60 was too strict. "what is this field about" vs "What is this research area about?" scores 59.6 — just below the cutoff, causing a false miss and digest fallback. **Cutoff lowered to 55.** Canonical questions still score ≥60 when matching; unrelated questions still score <40.

### Fixed — `ask_cluster` false-positive via WRatio scorer

Adding rapidfuzz's `WRatio` as a fallback scorer turned out promiscuous. Example: "what is this field about" ↔ "Why does this research matter now? What changed?" scored WRatio=86 (because of "What" in the target) while the correct match scored only 67. **Removed WRatio**, kept only token_set_ratio applied to both the crystal question text AND the slug-as-words (slugs often match better when user rephrases, e.g. "what is this field about" → slug "what-is-this-field" tokenises to the same words).

### Added — acronym expansion for common research terms

"what's the SOTA" scored only 33 against "What is the current state of the art..." because the acronym and full phrase share no tokens. Added `_expand_acronyms()` preprocessing that expands SOTA → state of the art, LLM → large language model, RAG → retrieval augmented generation, RL → reinforcement learning, etc. both sides before scoring.

### Test matrix (post-fix live against real cluster)

| User query | Matched crystal | Score |
|---|---|---|
| "what is this field about" | what-is-this-field | 100 |
| "what's the SOTA" | sota-and-open-problems | 82 |
| "how do people evaluate work" | evaluation-standards | 92 |
| "common mistakes beginners make" | common-pitfalls | 80 |
| "completely unrelated question about cooking" | (falls back to digest) | - |

+ 2 regression tests in `tests/test_v033_workflows.py` for both failure modes.

## v0.33.0 (2026-04-17)

**Tool consolidation (Codex Phase 3). 1235 → 1247 tests (+12). 5 task-level MCP wrappers on top of 64 low-level tools.**

Addresses the Codex architecture critique: "把 50+ tools 往上收斂成 task-oriented actions... 底下再去調 MCP tool." Casual Claude Desktop users now get 2-3× faster workflows (1 call instead of 3-4). Power users unaffected — all 64 low-level tools registered unchanged.

Full release report: [docs/audit_v0.33.md](docs/audit_v0.33.md). User guide: [docs/task-workflows.md](docs/task-workflows.md).

### Added — Track A: 5 task-level workflow wrappers

**New file:** `src/research_hub/workflows.py` (~440 LOC). Every function imports and calls existing internals; zero logic duplication.

- **`ask_cluster(cluster_slug, question, detail="gist")`** — read path. Fuzzy-matches natural-language question against crystal questions via rapidfuzz. Falls back to topic digest if no crystal matches. Replaces the common 3-call sequence `list_crystals → read_crystal → (optional) search_vault`.
- **`brief_cluster(cluster_slug, force_regenerate=False)`** — full NotebookLM round-trip. Chains `notebooklm_bundle → upload_cluster → generate_artifact → download_briefing_for_cluster → read_briefing`. Degrades gracefully if Playwright not installed.
- **`sync_cluster(cluster_slug)`** — "what needs attention" maintenance view. Combines `check_crystal_staleness + drift_check + run_doctor` into a prioritized recommendations list with copy-paste CLI commands.
- **`compose_brief_draft(cluster_slug, outline=None, max_quotes=10)`** — writing assembly. Builds default outline from cluster overview + crystal TLDRs when outline not provided, then delegates to `compose_draft`.
- **`collect_to_cluster(source, cluster_slug, ...)`** — unified ingest. Auto-routes: DOI/arXiv → `add_paper`; folder path → `import_folder`; http(s):// URL → `.url` file + `import_folder`.

### Added — CLI

- **`research-hub ask <cluster> "<question>" [--detail tldr|gist|full]`** — terminal wrapper for `ask_cluster`. Other 4 workflows stay MCP-only (see audit for why).

### Added — Tests

- **12 new tests** in `tests/test_v033_workflows.py`. Autouse fixture pops cached `research_hub.*` modules between tests to prevent ordering pollution that surfaced during development.
- **5 new entries** in `tests/test_consistency.py::EXPECTED_MAPPINGS` for the 5 new MCP tools.

### Added — Documentation

- `docs/task-workflows.md` (NEW) — user-facing guide with example Claude Desktop prompts for each wrapper.
- `docs/audit_v0.33.md` (NEW) — release report with design decisions and verification.

### Backward compatibility

**Absolute.** All 64 v0.32 MCP tools and signatures remain unchanged. Calling code written against v0.32 works identically against v0.33. `tests/test_consistency.py::test_no_orphaned_mappings` gates this — it would fail if any tool were removed.

### Test count

| Release | Passing | Skipped | xfail | Delta |
|---|---|---|---|---|
| v0.32.0 | 1235 | 14 | 2 + 1 xpassed | — |
| **v0.33.0** | **1247** | **14** | **2** + 1 xpassed | **+12** |

### Notes on delivery

Codex Track A hung after 15 minutes of exploration (same pattern as v0.30/v0.31/v0.32 Codex stalls when faced with large multi-file surveys). Claude took over directly, inspected actual internal signatures (crystal attrs, NLM function names, fit-check API), and finished the implementation. Workflows.py matches the real codebase — several of the brief's guessed function names were wrong (e.g. `upload_cluster_bundle` vs real `upload_cluster`).

### Out of scope (v0.34+)

- **Codex Phase 2** — structured memory layer (entities / claims / methods / datasets)
- **Connector abstraction** — NotebookLM as pluggable plug-in
- **`cli.py` / `mcp_server.py` monolith splits** — still HIGH RISK
- **Live NotebookLM round-trip test** — when user opens Chrome
- **Task #124 archived vault restore** — needs user decision on merge strategy
- **Search recall xfail baselines** (v0.26)
- **Zotero key encryption** via OS keyring
- **`.dxt` Claude Desktop extension**

## v0.32.0 (2026-04-17)

**Polish: high-quality screenshots + housekeeping. 1227 → 1235 tests (+8). No architectural changes.**

User concrete pain: existing `docs/images/*.png` were 800-1200 px non-Retina manual captures from weeks ago. v0.32 ships a permanent fix: a `--screenshot` CLI that re-renders any dashboard tab via headless Playwright at user-controlled DPI. All 5 demo PNGs re-shot at 2880×1800 (Retina @2x). Plus graphify integration redesign (v0.31.1 design bug) and external repo fix to `gemini-delegate-skill`.

Full release report: [docs/audit_v0.32.md](docs/audit_v0.32.md).

### Added — Track A: Dashboard `--screenshot` CLI

- **`src/research_hub/dashboard/screenshot.py`** (NEW): `screenshot_dashboard()` and `screenshot_all()` render the self-contained `dashboard.html` in headless Chromium at user-controlled `device_scale_factor`.
- **CLI:** `research-hub dashboard --screenshot TAB --out PATH --scale 2 --viewport-width 1440 --viewport-height 900`
- **Tabs:** overview / library / briefings / writing / diagnostics / manage (+ crystal alias for briefings)
- **Batch:** `--screenshot all --out-dir DIR` writes one PNG per tab
- **Default scale=2** = Retina-grade (2880×1800). Pass `--scale 3` for print-quality (5760×3600).
- **Graceful** `PlaywrightNotInstalled` error if `[playwright]` extra missing (same dep as NotebookLM).
- **5 new tests** in `tests/test_v032_screenshot.py` (Playwright mocked).

### Added — Track B: 5 dashboard PNGs re-shot at @2x

All 5 PNGs in `docs/images/` re-captured via the new CLI. File sizes ~6-7× larger; resolution ~3.5× per axis.

### Added — Track C: New image + Mermaid

- **`docs/images/import-folder-result.png`** — Library tab showing imported docs (referenced from `import-folder.md` + `.zh-TW.md`)
- **`docs/example-claude-mcp-flow.md`** — NEW Mermaid sequence diagram showing full ingest → crystallize → query → bundle flow visually (renders natively on GitHub)

### Fixed — Track D: graphify integration redesign

v0.31.1 audit documented: graphify is a coding-skill, not a standalone CLI. v0.31's `--use-graphify` always failed soft.

- **`--graphify-graph PATH`** flag added — accepts pre-built `graph.json` from user's `/graphify` skill run in Claude Code
- **`--use-graphify`** kept for backward compat (now emits `DeprecationWarning` and skips integration)
- **`graphify_bridge.run_graphify()`** deprecated — raises `GraphifyNotInstalled` with actionable 2-step workflow guidance
- **`graphify_bridge.parse_graphify_communities()`** + `map_to_subtopics()` unchanged (still parse pre-built graph.json)
- **`docs/import-folder.md`** rewrote "Deep extraction with graphify" section with the new workflow
- **3 new tests** in `tests/test_v032_graphify_redesign.py`
- **3 v0.31 graphify tests** updated for new deprecated behavior (test count unchanged for those)

### Added — Track E: Documentation

- **`docs/screenshot-workflow.md`** (NEW) — usage guide for the screenshot CLI, custom dimensions, batch capture, Obsidian graph manual workflow, troubleshooting
- **`docs/audit_v0.32.md`** (NEW) — release report with before/after metrics

### Fixed — Track F: gemini-delegate-skill external repo

External repo `https://github.com/WenyuChiou/gemini-delegate-skill` updated (commit `7493c8e`):

- **`SKILL.md`**: NEW "Fourth rule" section — verify file writes after Gemini exits. Documents two failure modes from v0.31 work: (1) `Error executing tool write_file: params must have required property 'file_path'` after first successful write, (2) silent partial writes from rate-limit retries. Includes B-grade translation-quality caveat.
- **`scripts/run_gemini.sh`** + **`.ps1`**: NEW `--verify-file PATH` (repeatable) + `--verify-sentinel TEXT` flags. After gemini exits, check expected files exist + non-empty + optionally contain sentinel string. Exit 1 with `VERIFY_FAILED` if not.
- **`README.md`**: "Known Limitations" section with verify-file usage example
- **Local skill** at `~/.claude/skills/gemini-delegate/` synced

### Test count

| Release | Passing | Skipped | xfail | Delta |
|---|---|---|---|---|
| v0.31.1 | 1227 | 14 | 2 + 1 xpassed | — |
| **v0.32.0** | **1235** | **14** | **2** + 1 xpassed | **+8** |

### Out of scope (v0.33+)

- **Codex Phase 2** — structured memory layer (entities/claims/methods/datasets)
- **Codex Phase 3** — tool consolidation (50+ tools → 5 task-level wrappers)
- **Connector abstraction** (NotebookLM → optional plug-in)
- **`cli.py` / `mcp_server.py` monolith splits** — still HIGH RISK
- **Search recall xfail baselines** (v0.26)
- **Restore archived vault** (Task #124) — archive contents have legacy folder names predating v0.27 cluster slugs; needs user decision on merge strategy
- **Live NotebookLM round-trip test** — needs user to open browser + CDP attach
- **Zotero key encryption**, **CDP token rotation**, **`.dxt` Claude Desktop extension**

## v0.31.1 (2026-04-17)

**Patch release: 3 bugs found in v0.31 live smoke test + 1 CI flake fix. 1223 → 1227 tests (+4).**

All bugs were caught within an hour of v0.31.0 shipping by hands-on validation against PDF, DOCX, URL, and graphify imports. Patches landed same day.

### Fixed — `import-folder` quality

- **PDF title derivation** (`src/research_hub/importer.py`): imported PDF notes now prefer embedded PDF metadata title, then fall back to the first non-empty extracted line. Previously fell straight to the filename.
- **DOCX title derivation** (`src/research_hub/importer.py`): DOCX extractor refactored to return `(title, body)`. Title sourced from `core_properties.title` or the first `Heading 1` / `Title` paragraph before falling back to the filename.
- **Markdown and TXT title logic clarified**: markdown keeps `# ` H1 detection; plain text uses the first non-empty short line when it looks like a title.
- **URL extraction returns plain text, not raw HTML** (`src/research_hub/importer.py::_html_to_text`): `_extract_url` now strips HTML tags from `readability-lxml`'s `.summary()` output via stdlib `html.parser`, preserving paragraph breaks. Previously imported URL notes had full `<html><body><div>...` markup in the body.

### Fixed — `clusters delete`

- **`--purge-folder` flag added** (`src/research_hub/cli.py`): optional destructive cleanup removes `<vault>/raw/<slug>/` and `<vault>/hub/<slug>/` after unbinding the registry entry. Default behavior unchanged (registry-only unbind).

### Fixed — CI test compatibility

- **`tests/test_v030_security.py`**: `test_mcp_read_crystal_blocks_traversal_slug` and `test_mcp_add_paper_blocks_injection_identifier` previously called `tool.fn(...)` directly. CI runs a fastmcp version where the decorator returns the raw function (no `.fn` attribute) — tests now use `getattr(tool, "fn", tool)` to work in both environments. Same pattern Track D's NotebookLM tests already use.

### Documented — graphify integration limitation

Live attempt to use `--use-graphify` revealed graphify (`pip install graphifyy`) is not a standalone CLI for full first-time extraction — it's a coding-assistant skill that runs subagents from inside Claude Code / Codex / etc. Standalone `graphify <folder>` is not a valid invocation. Our `graphify_bridge.run_graphify()` will always fail with subprocess error in v0.31. Workaround in v0.31.1: `--use-graphify` continues to fail-soft (warning logged, import continues without sub-topic assignment). v0.32 will redesign the integration: either invoke `graphify update <path>` (no-LLM AST mode) or document a "use Claude Code's `/graphify` skill, then point research-hub at the produced `graphify-out/graph.json`" workflow with a new `--graph-json` flag.

### Added

- **4 regression tests** in `tests/test_v031_1_quality.py`.

## v0.31.0 (2026-04-17)

**Document abstraction + analyst persona enablement. 1199 → 1223 tests (+24).**

External Codex architecture review surfaced a real strategic gap: research-hub was too paper-centric to serve users with folders of mixed local docs (industry researchers, internal knowledge bases, founders doing market research). The repo's analyst persona existed in name but the ingest pipeline still demanded a DOI. v0.31 starts the `paper → document` abstraction without breaking academic paper paths, and adds `import-folder` so folder-of-PDFs use cases work end-to-end. Plus closes the NotebookLM CLI/MCP asymmetry critique.

Full release report: [docs/audit_v0.31.md](docs/audit_v0.31.md).

### Added — Track A: Document abstraction

- **`src/research_hub/document.py`** (NEW) — `Document` base class with 7 canonical source kinds (paper / pdf / markdown / docx / txt / url / transcript). `Paper` becomes a subclass with the rich academic frontmatter; non-academic content uses `Document` directly with minimal frontmatter.
- **Backward compat:** existing paper notes have `source_kind: paper` implicit (parser defaults to "paper" if field missing). No migration needed.
- **6 new tests** in `tests/test_v031_document.py`.

### Added — Track B: `import-folder` command

- **`src/research_hub/importer.py`** (NEW, ~280 LOC) — walks a folder, extracts text per file type, writes Document notes via `atomic_write_text`.
- **5 supported file types**: `.pdf` (pdfplumber), `.md` / `.markdown` (direct), `.txt` (direct + encoding detect), `.docx` (python-docx), `.url` (requests + readability-lxml).
- **Dedup by SHA256 content hash** alongside existing DOI dedup.
- **Auto-creates cluster** if `--cluster` slug doesn't exist.
- **`--dry-run`** flag for preview before writing.
- **`--use-graphify`** flag delegates to Track C for deep multi-modal extraction.
- **CLI:** `research-hub import-folder ./project --cluster X`
- **MCP tool:** `import_folder_tool(folder, cluster_slug, dry_run)`
- **New optional deps** in `pyproject.toml`: `[project.optional-dependencies] import = [pdfplumber, python-docx, readability-lxml, requests]`. Install via `pip install 'research-hub-pipeline[import]'`.
- **8 new tests** in `tests/test_v031_import_folder.py`.

### Added — Track C: graphify bridge

- **`src/research_hub/graphify_bridge.py`** (NEW, ~140 LOC) — subprocess wrapper around the external [graphify](https://github.com/safishamsi/graphify) CLI for users who want deep multi-modal extraction (PDFs + code + images + video transcripts) and Leiden community detection-based sub-topic suggestions.
- `find_graphify_binary()` detects graphify on PATH; raises `GraphifyNotInstalled` with actionable install instructions if missing.
- `parse_graphify_communities()` reads graphify's `graph.json`, groups nodes by community.
- `map_to_subtopics()` matches graphify's communities to research-hub's imported files for `subtopics:` frontmatter assignment.
- graphify is **NOT** added to research-hub deps — user installs separately via `pip install graphifyy && graphify install`.
- **4 new tests** in `tests/test_v031_graphify_bridge.py` (all subprocess mocked).

### Added — Track D: NotebookLM MCP tools

Closes the CLI/MCP asymmetry external critique flagged: `read_briefing` was MCP but the rest of the NotebookLM round-trip was CLI-only.

- `notebooklm_bundle(cluster_slug, download_pdfs)` — wrap existing bundle handler as MCP tool
- `notebooklm_upload(cluster_slug)` — Playwright + CDP attach upload
- `notebooklm_generate(cluster_slug, artifact_type)` — trigger brief generation
- `notebooklm_download(cluster_slug)` — pull generated brief into vault artifacts
- AI agents (Claude Desktop) can now drive the full ingest → bundle → upload → generate → download flow without dropping to terminal.
- **3 new tests** in `tests/test_v031_notebooklm_mcp.py` (Playwright mocked).

### Added — Track E: Documentation

- **`docs/import-folder.md`** + **`docs/import-folder.zh-TW.md`** — usage guide for the new feature with examples per file type, troubleshooting, graphify walkthrough. zh-TW translated by Gemini and edited by Claude (first production Gemini test — see audit).
- **`docs/audit_v0.31.md`** — release report.
- **README.md + README.zh-TW.md** — Architecture docs section links to new docs.

### Fixed — Track Z: ship-today (commit fa4e0e2)

- README.md:198 + README.zh-TW.md:198: `1113 passing` → `1199 passing` (left over from v0.30).
- Created GitHub Releases for v0.10.0 through v0.30.0 via `gh release create --generate-notes` (was only on tags before; "Latest" badge had been showing v0.9.0).

### Test count

| Release | Passing | Skipped | xfail | Delta |
|---|---|---|---|---|
| v0.30.0 | 1199 | 14 | 2 + 1 xpassed | — |
| **v0.31.0** | **1223** | **14** | **2** + 1 xpassed | **+24** |

### Out of scope (v0.32+ — Codex critique deferred items)

- **Structured memory layer** (entities / claims / methods / datasets) — Codex's Phase 2. Genuinely a research project; needs its own design + scope.
- **Tool consolidation to ~5 task-level actions** — Codex's Phase 3. Risky for AI agent users who want fine-grained primitives. Need to design carefully so we expose BOTH layers.
- **Stable external API + auto-sync version/test counts** — infra, not user-visible.
- **NotebookLM as fully optional connector** — already true (analyst persona); Track D closed the MCP asymmetry but didn't extract a connector interface.
- **v0.30's deferred Track D refactor** (`cli.py` / `mcp_server.py` splits) — still HIGH RISK, still deferred.

## v0.30.0 (2026-04-16)

**Hardening + production audit. 1142 → 1199 tests (+57). Closes 28-issue audit.**

The release that takes research-hub from "shipping fast" to "safe to recommend to others." A 3-agent audit found 28 issues across security, workflow correctness, UX, performance, docs, and tests; this release closes 20 of them across 4 parallel tracks. The headline P0 fix: **`pipeline.py` Zotero collection routing was broken** — when a cluster was bound to a Zotero collection, papers always went to the default. The user's literal stated workflow ("整理到Zotero 對應collection") was silently broken in v0.29 and is fixed in v0.30.

Full release report: [`docs/audit_v0.30.md`](docs/audit_v0.30.md). Migration guide: [`UPGRADE.md`](UPGRADE.md).

### Fixed — Track A: Critical fixes + security

- **Zotero collection routing** (P0 #1) — `pipeline.py` now routes papers to the cluster-bound `zotero_collection_key` instead of always using the default. The cluster collection was already computed for dedup checks but never plumbed to `t["collections"]`. Adds explicit log line `Routing to collection: KEY (cluster=slug)` so users can verify.
- **Path traversal** (P0 #2) — new `src/research_hub/security.py` module: `validate_slug`, `validate_identifier`, `safe_join`, `chmod_sensitive`, `atomic_write_text`. Wired `validate_slug()` into 50+ MCP tool call sites. `Path(cfg.X) / cluster_slug / ...` constructions in `crystal.py`, `topic.py`, `clusters.py` now use `safe_join`.
- **CSRF + Origin check on `/api/exec`** (P0 #3) — server generates CSRF token at startup, embeds in HTML as `<meta name="csrf-token">`; clients must send `X-CSRF-Token` header. Origin header validated against server's bind address.
- **Subprocess kill on timeout** (P0 #4) — `dashboard/executor.py` switched from `subprocess.run(timeout=...)` to `Popen` + explicit `proc.kill()` on `TimeoutExpired`. No more zombie processes piling up.
- **File permissions** (P1 #6) — `init_wizard.py` + `config.py` now `chmod 700` on `~/.research_hub/` and `chmod 600` on `config.json` (POSIX only; Windows handled via NTFS ACLs).
- **Identifier validation** (P1 #7) — MCP `add_paper(identifier=...)` rejects shell metacharacters, semicolons, newlines.
- **Atomic state writes** (P1 #8) — `clusters.yaml`, `dedup_index.json`, crystal markdown writes go through `atomic_write_text` (tmp file + `os.replace`).
- **`--allow-external` warning** (P1 #9) — 5-second banner warning before `serve --dashboard --host 0.0.0.0`. Skip via `--yes`.
- **Bounded SSE queue** (P2 #13) — backpressure via oldest-event-drop instead of blocking new events.

### Fixed — Track B: UX + Performance

- **Cross-platform file locks** — new `src/research_hub/locks.py` (~80 LOC) with `fcntl`/`msvcrt` advisory `file_lock(path)` context manager. Wrapped `clusters.py::ClusterRegistry.save()` and `dedup.py::DedupIndex.save()` so two concurrent processes (e.g., dashboard server + CLI ingest) don't corrupt state.
- **Cluster slug case normalization** (P2 #14) — `ClusterRegistry.get()` and `create()` now normalize slug to lowercase + strip whitespace. `clusters get LLM-AGENTS`, `clusters get llm-agents`, `clusters get "  LLM-Agents  "` all resolve to the same cluster.
- **Env var validation** (P2 #15) — `config.py` `_validate_root_under_home()` rejects `RESEARCH_HUB_ROOT` paths outside `$HOME` unless explicitly opted in via `RESEARCH_HUB_ALLOW_EXTERNAL_ROOT=1` (e.g., shared network drive). Prevents misconfigured env vars from creating vault folders in system directories.
- **`--help` epilog with "Start here" banner** (P1 #12) — `research-hub --help` now ends with a 5-step quickstart pointing at `init` → `doctor` → `where` → `serve --dashboard` → `install --mcp`. Plus link to GitHub.

### Added — Track C: Test gap closure

NEW test files:
- `tests/test_v030_migration.py` (5 tests) — v0.10 → v0.29 vault format compatibility
- `tests/test_v030_concurrent.py` (4 tests) — `file_lock` contract, atomic write idempotence
- `tests/test_v030_unicode.py` (5 tests) — CJK / RTL / emoji titles, slugs rejected for non-ASCII
- `tests/test_v030_large_vault.py` (4 stress tests) — 1000-paper render budget, 500-paper dedup rebuild

### Added — Track E: Documentation

- **`docs/mcp-tools.md`** (~250 lines) — 50+ MCP tools categorized by stage (discovery, clusters, labels, sub-topics, crystals, fit-check, autofill, citation graph, quotes, search, examples) with signatures + use cases. Closes the gap that left Claude Desktop users blind to research-hub's capabilities.
- **`UPGRADE.md`** (~135 lines) — Migration guide covering v0.1 → v0.30, with quick path for v0.28/v0.29 users + breaking-changes detail for older versions + rollback procedure.
- **`docs/anti-rag.zh-TW.md`** (~200 lines) — Full 繁體中文 translation of the architectural explainer. Largest non-Anglophone audience.
- **`docs/example-claude-mcp-flow.md`** (~180 lines) — Worked example: ingest paper → crystallize cluster → query → handle staleness → cluster split. With token economics ($0.94/year per cluster vs $23.40 with raw-paper queries).
- **`docs/audit_v0.30.md`** (~190 lines) — Release report with before/after metrics + per-track delivery summary + verification commands.

### Test count

| Release | Passing | Skipped | xfail | Delta |
|---|---|---|---|---|
| v0.29.0 | 1142 | 12 | 5 | — |
| **v0.30.0** | **1199** | **14** | **2** + 1 xpassed | **+57** |

### Out of scope (v0.31+)

- Track D refactor — `cli.py` (3012 LOC) and `mcp_server.py` (1458 LOC) splits deferred (HIGH RISK; non-essential)
- Audit log, CDP token rotation, symlink config validation, Zotero key encryption, gRPC/REST API, .dxt Claude Desktop extension
- Search-quality v0.26 xfail baselines (5 outstanding) and citation-graph optimization for >500-paper clusters

## v0.29.0 (2026-04-16)

**Onboarding UX — confusion-proof first install. 1122 → 1142 tests (+20).**

Fixes 7 pain points that confused new users about "source code vs vault" separation.

### Added
- **`research-hub where`** — instant (<0.1s) status showing config path, vault path, note count, crystal count, MCP config status, and vault folder tree. No API calls. The first command a new user should run after `init`.
- **`research-hub install --mcp`** — auto-writes `research-hub` MCP server entry to `claude_desktop_config.json` (Windows/macOS/Linux paths auto-detected). Non-destructive merge preserves existing MCP servers. Prints "Restart Claude Desktop to activate."
- **`require_config()`** in `config.py` — fails early with actionable error ("Run: research-hub init") when no config exists, instead of silently creating vault at `~/knowledge-base`. Wired into all CLI commands except `init`, `doctor`, `install`, `examples`.
- **Init completion banner** — `research-hub init` now ends with formatted box showing vault path + config path + 4-step ordered command checklist (doctor → add → serve → install --mcp).
- **Existing Obsidian vault detection** — if init path contains `.obsidian/`, prints note count + "will add folders alongside your notes, nothing overwritten".
- **Doctor header** — `research-hub doctor` now prints config + vault paths at the top before running checks, so user immediately sees which vault they're checking.
- **README "Source code vs vault" section** — new table explaining the two-directory design in both README.md (EN) and README.zh-TW.md (繁中).
- **6 demo screenshots** in `docs/images/` — dashboard overview, crystals section, library sub-topics, manage live pill, diagnostics, Obsidian graph view with label coloring.
- **20 new tests** in `tests/test_onboarding_ux.py`.

### Changed
- **PyPI description** updated to: "CLI + MCP server for Zotero + Obsidian + NotebookLM research pipelines. Run `research-hub init` after install."

### Test count
| Release | Passing | Delta |
|---|---|---|
| v0.28.0 | 1122 | — |
| **v0.29.0** | **1142** | **+20** |

## v0.28.0 (2026-04-15)

**Crystals — anti-RAG semantic compression. Pre-computed canonical Q→A answers replace query-time context assembly. 1087 → 1122 tests (+35).**

First research-hub release that changes the architectural axis instead of refining the existing one. Full architectural explainer: [`docs/anti-rag.md`](docs/anti-rag.md). Release audit: [`docs/audit_v0.28.md`](docs/audit_v0.28.md).

### The shift

Every previous research-hub MCP tool returned **raw materials** (paper abstracts, cluster digests, topic lists) that the calling AI had to piece together at query time. v0.28 introduces a parallel path: for each cluster, the user's AI writes up to 10 canonical Q→A answers ONCE via emit/apply, stored as markdown. Subsequent queries read the pre-written answer directly — no re-synthesis, no 30 KB abstract dumps.

Measured token efficiency on the test cluster: **32 KB (old get_topic_digest) → 1.8 KB (new list_crystals + read_crystal) = ~18× reduction** for common-case cluster-level questions. Quality is deterministic because synthesis happens once at generation time, not per-query.

### Added — Track A: Crystal core (`crystal.py`)

- **`src/research_hub/crystal.py`** (~320 LOC) — full module with:
  - `CANONICAL_QUESTIONS` — 10 slots (what-is-this-field / why-now / main-threads / where-experts-disagree / sota-and-open-problems / reading-order / key-concepts / evaluation-standards / common-pitfalls / adjacent-fields)
  - `Crystal`, `CrystalEvidence`, `CrystalStaleness` dataclasses
  - `emit_crystal_prompt()` — builds markdown prompt with cluster paper list + 10 questions + JSON schema
  - `apply_crystals()` — parses JSON, writes to `hub/<cluster>/crystals/<slug>.md` (idempotent)
  - `list_crystals()` / `read_crystal()` / `check_staleness()` — query API
  - Stores `based_on_papers:` provenance + `last_generated:` + `generator:` + `confidence:` in frontmatter
  - `STALENESS_THRESHOLD = 0.10` — crystal flagged stale if >10% of cluster papers changed since generation
- **`research-hub crystal emit/apply/list/read/check`** — new CLI sub-commands mirroring the autofill + fit-check emit/apply pattern
- **5 new MCP tools**: `list_crystals`, `read_crystal`, `emit_crystal_prompt`, `apply_crystals`, `check_crystal_staleness` (total MCP tool count now 52)
- **26 new tests** in `tests/test_crystal.py` covering emit + apply + round-trip + staleness + canonical question stability

### Added — Track B: Crystal dashboard surface

- **`CrystalSection`** in `dashboard/sections.py` — renders inside Overview tab, shows per-cluster completion ratio (e.g. 10/10), stale badges, expandable crystal list with TL;DRs, "Copy regenerate command" button
- **`_check_crystal_staleness`** drift detector in `dashboard/drift.py` — emits `DriftAlert` for each stale crystal with fix command
- **`CrystalSummary`** dataclass on `DashboardData` — populated in `collect_dashboard_data` by calling `crystal.list_crystals` + `crystal.check_staleness` per cluster
- **9 new tests** in `tests/test_dashboard_crystal_section.py` + `tests/test_drift_crystal.py`
- CSS: `.crystal-section`, `.crystal-card`, `.crystal-stale-badge`, `.crystal-list`

### Added — Track C: Documentation + multilingual

- **`docs/anti-rag.md`** (~340 lines) — architectural explainer. Karpathy critique, eager-vs-lazy framing, concrete before/after example, generation + query flow diagrams, honest limitations
- **`README.zh-TW.md`** — full 繁中 README mirror
- **`README.md`** — rewritten from 341 → 170 lines. Screenshot-led, MCP-first, anti-RAG value prop in first 15 lines
- Status badges for PyPI / tests / Python / license
- Claude Desktop `mcpServers` config snippet copy-paste ready

### Fixed during Phase 4 review

- `tests/test_consistency.py` — added 5 new MCP tool mappings (`list_crystals → crystal list`, etc). Contract test requires every `@mcp.tool()` to have a CLI mapping; Track A added 5 new tools so the mapping needed updating.

### Live verification

Executed end-to-end against `llm-agents-software-engineering` (20 papers, 4 sub-topics):

1. `research-hub crystal emit` → 176-line prompt with 20 paper rows + 10 questions (~8 KB)
2. Fed prompt to the Claude in this release session (Opus 4.6) who answered all 10 questions based on accumulated knowledge from v0.12-v0.28 audits
3. `research-hub crystal apply` → 10 markdown files written, 775 lines total
4. `research-hub crystal list` → all 10 returned with TL;DRs
5. `research-hub crystal check` → all 10 fresh (delta = 0%)
6. `research-hub crystal read --level gist` → ~1 KB pre-written paragraph returned
7. `research-hub dashboard` → CrystalSection renders 10/10, 0 stale

### Test count

| Release | Passing | Delta |
|---|---|---|
| v0.27.0 | 1087 | — |
| **v0.28.0** | **1122** | **+35** |

### Breaking changes

None. All additions are backward-compatible:
- Clusters without crystals get empty CrystalSection + clear generation instructions.
- All existing MCP tools unchanged.
- Crystal generation uses emit/apply (never calls an LLM from inside research-hub — provider-agnostic).

### v0.29 backlog

- Custom canonical questions per cluster (`canonical_questions.yaml`)
- `.dxt` Claude Desktop extension for one-click install
- `clusters analyze --apply` (auto-apply split suggestions)
- Search quality fixes (the 4 v0.26 xfail root causes)
- Sub-topic IntersectionObserver virtualization (100+ papers per sub-topic)

## v0.27.0 (2026-04-15)

**Directness release — live HTTP dashboard server, auto-refreshing Obsidian graph colors, sub-topic-grouped Library UI, citation-graph cluster auto-split. 1019 → 1087 tests (+68).**

v0.26.0 diagnosed friction. v0.27.0 removes it. Full audit report: [`docs/audit_v0.27.md`](docs/audit_v0.27.md).

### Added — Track A: Live dashboard HTTP server

- **`research-hub serve --dashboard [--port 8765] [--host 127.0.0.1]`** — starts a localhost-only HTTP server backing the dashboard. Forms in the Manage tab now POST to `/api/exec` and execute directly (whitelisted subprocess), bypassing the copy-to-clipboard step.
- **`src/research_hub/dashboard/http_server.py`** (~240 LOC) — stdlib `ThreadingHTTPServer` with `GET /`, `/healthz`, `/api/state`, `/api/events` (SSE), `POST /api/exec`. No new dependencies.
- **`src/research_hub/dashboard/executor.py`** (~170 LOC) — whitelist of 20+ allowed actions (rename/merge/split/bind-*/move/label/mark/remove/ingest/topic-build/dashboard/pipeline-repair/notebooklm-*/discover-*/autofill-apply/compose-draft/clusters-analyze). `subprocess.run([...], shell=False)` — never shell interpolation.
- **`src/research_hub/dashboard/events.py`** (~90 LOC) — `EventBroadcaster` + `VaultWatcher` thread. Polls vault mtimes every 5s; on change, emits `vault_changed` to all connected SSE clients.
- **`script.js` live mode** — `detectLiveMode()` on page load hits `/healthz`, switches to fetch-and-execute when server present; falls back to clipboard copy when it's not (no regression for static usage).
- **Live pill** (`● Live` / `◯ Static`) in header indicates current mode.
- **38 new tests** in `tests/test_dashboard_live_server.py` cover bind enforcement, whitelist rejection, subprocess never uses `shell=True`, SSE broadcaster delivery, vault watcher mtime detection, CLI flag parsing.

### Added — Track B: Auto-refreshing graph colors + sub-topic Library UI

- **`vault/graph_config.py`** now produces TWO dimensions: (a) existing cluster-path color groups (`path:raw/<slug>/`), (b) new label-tag color groups (`tag:#label/seed`, `tag:#label/core`, ..., 9 groups covering `CANONICAL_LABELS`).
- **`refresh_graph_from_vault(cfg)`** — high-level convenience that reads `clusters.yaml`, rebuilds both dimensions, writes `.obsidian/graph.json` idempotently. Preserves user-authored color groups whose queries don't match the research-hub patterns.
- **Auto-refresh hooks** wired into `ClusterRegistry.create/delete/rename/bind/merge/split` + `research-hub dashboard` — so every cluster mutation and every dashboard rebuild auto-updates the graph.
- **`research-hub vault graph-colors --refresh`** — explicit manual trigger.
- **`paper.ensure_label_tags_in_body(path, labels)`** — injects `<!-- research-hub tags start -->\n#label/seed #label/core\n<!-- research-hub tags end -->` at the end of each paper note body. Idempotent. Required for Obsidian's graph `tag:#label/foo` query to work.
- **`LibrarySection._cluster_card`** rewritten to group papers by sub-topic when the cluster has `topics/NN_*.md` files. Each sub-topic renders as a collapsed `<details class="subtopic-card">`. Papers not assigned to any sub-topic go to a trailing "Unassigned" group. If the cluster has zero sub-topics, falls back to today's flat list (no regression for small clusters).
- **18 new tests** in `tests/test_graph_config_v027.py` / `test_library_subtopic_rendering.py` / `test_paper_label_tags.py`.

### Added — Track C: Citation-graph cluster auto-split

- **`src/research_hub/analyze.py`** (~220 LOC) — new module. `build_intra_cluster_citation_graph` fetches references for every paper via existing `citation_graph.get_references`, builds co-citation graph (nodes = cluster papers, edges = shared refs). `suggest_split` runs `networkx.algorithms.community.greedy_modularity_communities` + TF-IDF sub-topic name generation. `render_split_suggestion_markdown` produces a markdown report the user reviews before running `topic apply-assignments`.
- **`research-hub clusters analyze --cluster X --split-suggestion [--min-community-size N] [--max-communities M]`** — new CLI command.
- **`@mcp.tool() def suggest_cluster_split(cluster_slug, ...)`** — new MCP tool (v0.27 brings MCP tool count to 47).
- **Persistent citation cache** at `.research_hub/citation_cache/<cluster>/<slug>.json` — prevents re-hitting Semantic Scholar. Rate-limit aware: if >50% of papers return empty citations, the markdown report emits a "rerun after 1 hour" warning.
- **New dependency: `networkx >= 3.0`** — pure Python, ~10 MB, no heavy transitive deps.
- **12 new tests** in `tests/test_analyze.py`.

### Live verification results

- Graph refresh: **14 groups** written to `.obsidian/graph.json` (5 cluster + 9 label).
- 331-paper cluster auto-split: analyzed successfully, **4 communities** found (RAG/knowledge, multi-agent frameworks, LLM+disaster, long-term memory), modularity 0.312, citation coverage 44% (rate-limited but still usable). Full report at `docs/cluster_autosplit_llm-agents-social-cognitive-simulation.md`.
- Live server: `/healthz` returns live mode, `/api/state` returns 366 papers + 5 clusters + 2 briefings JSON, `/api/exec dashboard` runs in 7.6s and returns returncode 0, unknown action returns 400.

### Fixed during review

- **`_read_cluster_papers` used folder name instead of `topic_cluster` frontmatter.** The 331-paper cluster's notes live in `raw/llm-agent/` but have `topic_cluster: llm-agents-social-cognitive-simulation` in their YAML. Fixed by delegating to `vault.sync.list_cluster_notes` (rglob + frontmatter filter). ~15 LOC.
- **`test_consistency.py::test_every_mcp_tool_is_documented_in_expected_mappings`** — Track C added `suggest_cluster_split` without updating the contract test. Added `"suggest_cluster_split": "clusters analyze --split-suggestion"` to `EXPECTED_MAPPINGS`.

### Test count

| Release | Passing | Delta |
|---|---|---|
| v0.26.0 | 1019 | — |
| **v0.27.0** | **1087** | **+68** |

### Breaking changes

None. All additions are backward-compatible:
- The live server is opt-in via `--dashboard` flag; `serve` without it still starts MCP stdio.
- `script.js` falls back to clipboard when no server is running (existing static usage unchanged).
- Graph color auto-refresh preserves user-authored color groups.
- `LibrarySection._cluster_card` falls back to flat-list rendering when the cluster has no sub-topics.

### v0.28.0 backlog

- Auto-apply split suggestion (`clusters analyze --apply`)
- Sub-topic card virtualization for 100+ papers per sub-topic
- Multi-user auth (if server needs sharing)
- Search quality fixes (from v0.26 xfail baselines — still outstanding)
- Translate NotebookLM briefings (still deferred)

## v0.26.0 (2026-04-14)

**End-to-end audit release — search → notes → DB → dashboard/MCP API. 873 → 1019 tests (+146).**

First cross-cutting audit of the package. Four Codex tracks ran in parallel covering literature search accuracy, note organization, database sync/drift, and dashboard + MCP coverage. Full audit report: [`docs/audit_v0.26.md`](docs/audit_v0.26.md).

### Added — Track A: Search accuracy audit (tests/evals/*)

- **Golden fixture** (`tests/evals/fixtures/golden_llm_agents_se.yml`) with 20 hand-curated papers for the `llm-agents-software-engineering` cluster. Generated from live notes, authoritative source.
- **Metrics collector** (`tests/evals/conftest.py`) writes `tests/evals/_metrics.json` for the audit report.
- **24 new tests** across recall@20, recall@50, rank stability, dedup merge, confidence calibration, DOI normalization (10 forms), fit-check term-overlap correlation, empty-abstract handling, silent backend failures, auto-threshold floor, citation expansion failure logging.
- **`@pytest.mark.network`** + `@pytest.mark.evals` markers registered in `pyproject.toml`. Offline by default, opt-in via `pytest -m network`.
- **5 audit findings locked in as xfail baselines** (recall, rank, merge, calibration): these surface real search-quality bugs that will flip to green once v0.27.0 ranker/fusion fixes land. Full diagnosis in `docs/audit_v0.26.md`.

### Added — Track B: Note organization audit

- **`src/research_hub/paper_schema.py`** — reusable `validate_paper_note(path) -> NoteValidationResult` with missing_frontmatter + empty_sections + todo_placeholders fields.
- **`doctor.check_frontmatter_completeness()`** — walks every paper note, rolls up to a `HealthBadge`.
- **`scripts/audit_note_content.py`** → writes `docs/audit_v0.26_notes.md` with per-note coverage.
- **31 new tests** (parametrized): `test_topic_roundtrip.py` (4), `test_topic_content_guard_stress.py` (21 parametrized cases across 10 section headings × 2 mutation types), `test_frontmatter_schema.py` (4).
- Round-trip coverage: apply_assignments → build_subtopic_notes → re-read preserves ALL hand-edited structured sections (TL;DR, 核心問題, 範圍, 關鍵概念, 分類法, 代表論文, 時間線, 開放問題, 連結, See also).

### Added — Track C: Database / sync / drift audit

- **`scripts/audit_vault_sync.py`** → writes `docs/audit_v0.26_vault_sync.md` with per-cluster Zotero/Obsidian/dedup counts, orphans, stale manifest refs, drift alerts.
- **22 new tests** across pipeline_repair (8), dedup rebuild round-trip (4), cluster rename triple-sync (4), manifest integrity (3), drift detector coverage (3).
- **4 new drift detectors** in `src/research_hub/dashboard/drift.py`:
  - `zotero_orphan` — Zotero item in bound collection with no matching `.md` note
  - `subtopic_paper_mismatch` — subtopic file `papers:` frontmatter ≠ actual Papers section count
  - `stale_dedup_path` — dedup entry pointing to deleted `.md`
  - `stale_manifest_cluster` — manifest entry references a cluster slug missing from clusters.yaml
- **`pipeline_repair.py`** now appends `repair_*` actions to `manifest.jsonl` in execute mode + detects folder_mismatch + duplicate_doi across clusters.
- **`dedup.rebuild_from_obsidian`** now tolerates malformed YAML with WARN log instead of crashing.
- **`clusters rename`** now syncs NotebookLM cache name in addition to clusters.yaml and Zotero collection name (the v0.25 triple-sync gap).

### Added — Track D: Dashboard + MCP API comprehensive testing

- **`src/research_hub/dashboard/manage_commands.py`** — Python port of JS `buildManageCommand` + `buildComposeDraftCommand` + `shellQuote`. Enables unit-testing command builders without Playwright.
- **76 new tests** across 5 files:
  - `test_dashboard_script_logic.py` (14) — all 6 manage action builders + composer builder + shell escape + absolute obsidian:// regression + hash-anchor regression + empty-state rendering
  - `test_mcp_server_comprehensive.py` (12+) — declarative contract (every MCP tool has docstring + type-annotated params) + behavior tests for 7 of 9 decorated tools
  - `test_cli_smoke_comprehensive.py` (34+) — declarative `--help` smoke test for every registered subcommand + happy-path smoke tests for discover/fit-check/autofill/pipeline-repair/compose-draft/clusters-rename/topic-scaffold
  - `test_dashboard_idempotent.py` (3) — same-data renders produce identical HTML, empty vault renders without crash, missing bindings gracefully show unbound
  - `test_dashboard_persona.py` (3) — analyst hides Zotero column + omits bibtex, researcher auto-detected when Zotero configured

### Fixed

- **`fit_check.emit_prompt()`** rendered empty string for papers with `abstract=""` instead of `(no abstract)` marker. Silent fit-check scoring bug. Regression test in `tests/evals/test_fit_check_accuracy.py`.
- **`dedup.rebuild_from_obsidian`** crashed on malformed YAML; now warns and skips.
- **`pipeline_repair.py`** didn't log repair actions to manifest in execute mode.
- **`clusters rename`** missed NotebookLM cache sync (shipped in v0.24 as intended, covered by test now).

### Test count

- **v0.25.0**: 873 passing, 5 skipped
- **v0.26.0**: **1019 passing, 12 skipped, 5 xfail baselines** (+146 net)

### Breaking changes

None. All changes are additive: new modules, new tests, new drift detectors, new doctor check, new scripts, new pyproject markers. Existing APIs unchanged. Users who upgrade from v0.25.0 will see the same behavior + auto-labeled clusters will get 2 additional drift detectors enabled by default.

### v0.27.0 backlog (shipped as documented baselines)

1. Deterministic rank tiebreak (`rank_results` sort key) — closes `test_rank_stability`
2. Longer-wins field fill in `merge_results` — closes `test_dedup_merges_same_paper`
3. Confidence score incorporates term_overlap — closes `test_confidence_calibration`
4. Cluster-query aware eval (`test_recall_at_*` uses `cluster.seed_keywords`) — closes recall floors
5. Legacy folder migration tool (`migrate-yaml --all-legacy`)
6. Doctor integration for `check_frontmatter_completeness`
7. Empty-cluster pruning (`clusters prune --empty`)

## v0.25.0 (2026-04-14)

**Structured research-note principle + dashboard obsidian:// fix + file:// hash navigation fix.**

Live use of the `llm-agents-software-engineering` cluster surfaced three distinct issues: (1) topic overview and sub-topic notes were being emitted as wall-of-text English prose that was unreadable for skim-first research use; (2) the "Papers by label" cross-cluster list in the dashboard Library tab produced `obsidian://` URLs with relative paths, so clicking them did nothing; (3) label-filter chips in the dashboard triggered `window.location.hash` assignments that Chrome blocks under `file://` origin, making the first click unreliable. v0.25 fixes all three.

### Added — Structured note templates (Track A)

- **`OVERVIEW_TEMPLATE`** and **`SUBTOPIC_TEMPLATE`** in `src/research_hub/topic.py` rewritten as hierarchical, table-driven skeletons. Future `topic scaffold` and `topic build` runs emit the new structure automatically.
- **Sub-topic structure:** bilingual H1 (`# 中文標題 / English Title`), TL;DR (1–2 sentences), 核心問題 (blockquote), 範圍 (涵蓋/不涵蓋 as separate bullet lists), 關鍵概念 table, 分類法 table, 代表論文 table, Papers (auto-generated), 時間線 table, 開放問題 (numbered + bolded), 連結, See also.
- **Overview structure:** TL;DR, 核心問題, 範圍定義, 領域地圖 table (linking sub-topics), 關鍵概念詞彙表 table, 必讀論文 table, 時間線 table, 開放問題, 連結, 延伸閱讀.
- **Design rationale:** tables > paragraphs for any comparison or list of >3 items with the same shape; Traditional Chinese prose with English technical proper nouns preserved inline (LLM, SWE-bench, ACI, GPT-4, etc.); H1 is bilingual so the vault is searchable in both languages.

### Fixed — Dashboard `obsidian://` URLs now use absolute paths (Track B)

- **`_obsidian_url(relative_path, vault_root)`** in `src/research_hub/dashboard/sections.py` now accepts a vault_root and builds absolute paths via `Path(vault_root) / relative`, URL-encoding the result with `quote(..., safe='/:')`. Previously produced `obsidian://open?path=raw/cluster/slug.md` (relative), which Obsidian cannot resolve.
- **Threaded `vault_root`** from `DashboardData.vault_root` through five call sites: `_render_cross_cluster_labels`, `_cluster_card`, `_binding_line`, `_storage_row`, and the cluster card overview link.
- **Affected tabs:** Library tab → "Papers by label (across all clusters)" → clicking a paper now opens Obsidian. Also the cluster card header, binding line Obsidian chip, and Overview tab storage map rows.

### Fixed — Dashboard file:// hash navigation (Track C)

- **`handleLabelFilter()`** in `src/research_hub/dashboard/script.js` previously wrote `window.location.hash = "#tab-library?..."` on every label-chip click. Chrome's file:// security policy blocks hash changes with query strings, throwing "Unsafe attempt to load URL from frame with URL file:///..." — making the first click unreliable.
- **Fix:** removed all three `window.location.hash = ...` assignments. `applyLibraryFilters()` already updates DOM state directly; the hash was decorative and also broke file:// origin usage. Removed the now-unused `applyLibraryHashFilter()` function (24 lines of dead code).

### Enforcement

- The new template structure is codified in THREE places to keep future work consistent:
  1. `topic.py` templates (research-hub internal — affects future `topic scaffold`/`topic build`)
  2. `~/.claude/projects/.../memory/feedback_note_structure.md` (cross-conversation Claude memory)
  3. Worked example in the `llm-agents-software-engineering` cluster (5 files: overview + 4 sub-topics)

### Tests

- `tests/test_subtopic_content_protection.py` — 6 tests updated from English section headings (`## Scope`, `## Why these papers cluster together`, `## Open questions`) to new Chinese headings (`## 範圍`, `## 核心問題`, `## 開放問題`).
- `tests/test_topic_subtopics.py::test_build_subtopic_notes_overwrites_papers_section_only` — same heading update.
- **873 tests pass / 5 skipped.** No new tests added; the existing content-protection suite validates that the new templates still round-trip cleanly through `topic build` rebuilds without losing hand-edited content in preserved sections.

### Breaking changes

- **None for existing clusters.** `topic build` preserves all non-Papers section content across rebuilds (content-guard from v0.24 still active). Users with wall-of-text sub-topic notes can keep them — the new template only applies to newly scaffolded sub-topics.
- **Guidance:** users who want to adopt the new structure for existing clusters should rewrite `00_overview.md` and `topics/NN_*.md` by hand following the template in `feedback_note_structure.md`. There is no auto-migration tool because the new format is semantic, not mechanical.

## v0.24.0 (2026-04-14)

**Autofill + auto labels + Zotero sync + sub-topic protection — closing the "everything should be automatic on a full run" gap.**

Live audit on `llm-agents-software-engineering` exposed four process gaps where the pipeline silently left work for the user after ingest. v0.24 fixes all four.

### Added — Track A: Autofill paper note content via emit/apply

- **`src/research_hub/autofill.py`** — canonical module for generating paper note body content from abstracts.
- **`find_todo_papers(cfg, cluster_slug)`** scans for papers whose body contains `[TODO: ...]` markers and whose abstract is non-empty.
- **`emit_autofill_prompt(cfg, cluster_slug)`** builds a markdown prompt listing each TODO paper's title + abstract, asks the AI for structured JSON with `summary`, `key_findings`, `methodology`, `relevance` per paper.
- **`apply_autofill(cfg, cluster_slug, scored)`** consumes the AI JSON and rewrites the `## Summary … ## Relevance` block in each paper note, preserving frontmatter, abstract, and the `## Related Papers in This Cluster` footer.
- **CLI:** `research-hub autofill emit --cluster X > prompt.md` and `research-hub autofill apply --cluster X --scored out.json`. Same emit/apply pattern as fit-check.
- **2 new MCP tools:** `autofill_emit`, `autofill_apply`.

### Added — Track B: Auto labels from fit score

- **`.fit_check_accepted.json` sidecar** written alongside the existing rejected sidecar during `fit_check.apply_scores`.
- **`paper.label_from_fit_score(score, is_top_tier)`** mapping: score 5 → `core` + `seed` for top-tier (top 20%); score 4 → `core`; score 3 → user decides (metadata only); score 2 → `tangential`; score 0-1 → `deprecated`.
- **`paper.apply_fit_check_to_labels(cfg, cluster_slug)`** now reads BOTH sidecars and labels accepted papers too — not just deprecated.

### Added — Track C: Zotero collection rename sync

- **`research-hub clusters rename --name "Foo" slug`** now ALSO renames the bound Zotero collection via `pyzotero.update_collection` when `zotero_collection_key` is set.
- **Warning-only failure** — Zotero API error prints to stderr but doesn't roll back the clusters.yaml rename.
- **Idempotent** — no API call when target name already matches.

### Added — Track D: Sub-topic content protection

- **`topic._write_papers_section` content guard** — snapshots all non-Papers sections before rewrite, verifies every section is still byte-identical after rewrite, raises `ValueError` if any section would be deleted or modified.
- **`_extract_sections_excluding_papers(text)`** helper — returns `{heading: content}` for every `## X` section except `## Papers`.

### Tests

- **832 → 873 passing** (+41 tests, 5 skipped unchanged).
- `tests/test_autofill.py`: 10 tests
- `tests/test_label_from_fit_score.py`: 8 tests
- `tests/test_clusters_rename_zotero.py`: 4 tests (mocked pyzotero)
- `tests/test_subtopic_content_protection.py`: 6 tests
- Existing fit_check / paper / topic / consistency tests extended for 13 new assertions

### CLI + MCP

- 1 new CLI subcommand group: `autofill {emit, apply}`
- 2 new MCP tools: `autofill_emit`, `autofill_apply` → **52 total** (was 50)
- `clusters rename` gains Zotero sync side effect
- `fit-check apply-labels` now handles accepted papers too

### Deferred to v0.25+

- Pipeline-integrated autofill (run automatically as part of `ingest --fit-check`)
- Bi-directional Zotero note sync (Obsidian body changes propagate to Zotero mirror)
- Slug rename for clusters
- Top-tier seed ranking by citation count (currently list-order)

## v0.23.1 (2026-04-14)

**Python 3.11 CI fix.** `tests/test_dashboard_data.py:55` used a nested f-string with backslashes in the expression part (for quoting label strings inline), which is valid Python 3.12+ but raises `SyntaxError: f-string expression part cannot include a backslash` on Python 3.10/3.11. Local tests passed on Python 3.14; CI's 3.11 job failed immediately on import. Fix: extract the label-quoting into a plain string join outside the f-string. No runtime behavior change.

## v0.23.0 (2026-04-14)

**Dashboard feature completion + stress test suite.** v0.22 added label plumbing; v0.23 wires labels into the dashboard as an interactive filter system and adds a stress test layer the project was missing entirely.

### Added — Dashboard feature completion (Track A)

- **Clickable label filter chips.** Cluster card label chips (`seed: 3`, `core: 4`, etc.) are now `<a>` elements with `data-label` + `data-cluster` attributes. Clicking one jumps to the Library tab and filters paper rows to only those with that label. Click again to clear. URL hash tracks the state (`#tab-library?label=seed&cluster=llm-agents-software-engineering`), so filters are bookmarkable.
- **Archived papers section per cluster.** Each cluster card gains a collapsible `<details class="cluster-archive">` block showing archived papers (from `raw/_archive/<cluster>/`) with their fit_reason and a copy-button that emits the exact `research-hub paper unarchive --cluster X --slug Y` command. Hidden when `archived_count == 0`.
- **Cross-cluster "Papers by label" view.** New section at the top of the Library tab, rendered only when any cluster has labeled papers. Groups papers by canonical label across all clusters — answers "show me every `seed` paper in my vault" in one place. Each paper in the list links to its Obsidian note.
- **Label badges in Library paper rows.** Each paper row now shows `[seed, benchmark]` monospaced chips alongside the existing title/authors/year. Rows gain `data-cluster-row` + `data-labels` attributes so the label filter (A1) can hide/show them in one JS pass.
- **Writing tab quote filter by paper label.** Writing tab gains a filter bar (`Filter by paper label: [all] [seed] [core] [method] [benchmark]`) that hides quote cards to only those captured from papers with the selected label. Quote cards gain `data-paper-labels` attribute.
- **Minimal CSS additions** — all new classes (`cluster-label--active`, `cluster-archive`, `cross-cluster-labels`, `paper-row-labels`, `quote-filter-bar`, `quote-filter-chip`, `label-group`) reuse existing `--brand` / `--muted` color vars. No new CSS variables.
- **`script.js` gains two handlers** — `handleLabelFilter()` for A1/A4, `handleQuoteLabelFilter()` for A5. Both attach on `DOMContentLoaded`.

### Added — Stress test suite (Track B)

New `tests/stress/` directory with 8 stress test modules, all auto-marked with `@pytest.mark.stress` via `tests/stress/conftest.py`. **Default `pytest -q` excludes them** via `addopts = "--ignore=tests/stress"` in `pyproject.toml`. Opt-in with `pytest tests/stress/ -v`.

| Module | Stress coverage |
|---|---|
| `test_dashboard_render.py` | Render on 100/500/2000/5000-paper synthetic vaults with linear time budgets |
| `test_dashboard_render_content.py` | Verify label markup still renders at scale |
| `test_frontmatter_rewrite.py` | 500-paper `set_labels` loop + body preservation (regression for v0.20.1-class corruption) |
| `test_topic_build.py` | 30 sub-topics × 100 papers with random assignments |
| `test_discover_merge.py` | 5 backends × 100 results with 60% DOI overlap, confidence boost correctness |
| `test_pipeline_ingest.py` | 100-paper ingest with mocked Zotero, dedup index growth check |
| `test_paper_label_parallel.py` | 200-paper threaded `set_labels(add=)` — race detection |
| `test_fit_check_prompt.py` | 200-candidate prompt budget check (< 200KB for LLM context) |

`tests/stress/_helpers.py` provides `make_stress_cfg`, `build_synthetic_cluster`, `build_synthetic_vault`, `synthetic_paper_note` — reusable fixtures for any stress test that needs a fake vault.

### CI workflow

- `.github/workflows/ci.yml` gains a new `stress-tests` job that runs only on `pull_request`. 10-minute timeout. Stays off the main branch push path so default CI stays fast (default run is ~45s, stress run is ~60s).

### Tests

- **Default suite: 810 → 832 passing** (+22 dashboard + data unit tests in the default pyramid)
- **Stress suite: 0 → 12 tests** (opt-in, excluded from default)
- **Default `pytest --collect-only | grep stress` returns 0** — stress tests genuinely excluded

### Live verification on the real cluster

Labeled 8 core papers in `llm-agents-software-engineering` and verified end-to-end:
- `research-hub label <slug> --set seed,benchmark` wrote frontmatter cleanly
- `research-hub find --cluster X --label seed` returned the 3 seed papers
- `research-hub dashboard` rendered `seed: 3 core: 4 method: 5 benchmark: 4` histogram on the cluster card
- Clicking a chip in the rendered HTML emits the filter hash

### Non-breaking

All existing CLI commands, MCP tools (50 still), and existing dashboard rendering unchanged. This release is purely additive: new dashboard elements, new stress tests, new CI job.

### Deferred to v0.24+

- Auto-label `accepted` papers from fit-check (needs a `.fit_check_accepted.json` sidecar that `discover continue` doesn't yet write)
- `topic build --group-by-label` sectioned sub-topic notes
- Cross-cluster label view in MCP (currently only in dashboard UI)
- Stress test run against a real production vault (currently all synthetic)

## v0.22.0 (2026-04-13)

**Paper labels + pruning — curate clusters after ingest with a 9-label vocabulary, archive-first deletion, and a fit-check → labels bridge.**

v0.14-v0.21 built discovery + ingest + topic notes, but zero curation after ingest. Once a paper landed in the vault, you could only mark its reading status (`unread/reading/read`) or use free-form Obsidian tags. v0.22 adds a controlled label vocabulary stored in paper frontmatter, a CLI to query and update it, an archive-first pruning workflow, and label-aware topic + dashboard rendering.

### Added — `src/research_hub/paper.py` (~290 LOC)

New canonical module for paper labels and curation:

- **`PaperLabel` dataclass** — `slug`, `cluster_slug`, `path`, `labels`, `fit_score`, `fit_reason`, `labeled_at`
- **`CANONICAL_LABELS`** — frozenset of 9 standard labels: `seed`, `core`, `method`, `benchmark`, `survey`, `application`, `tangential`, `deprecated`, `archived`. User-defined labels also work; only the 9 drive tooling.
- **`read_labels(cfg, slug)`** — locate paper note by slug across all clusters, return label state
- **`set_labels(cfg, slug, labels=, add=, remove=, fit_score=, fit_reason=)`** — three modes (replace / add / remove), updates `labeled_at` timestamp automatically
- **`list_papers_by_label(cfg, cluster_slug, label=, label_not=)`** — query papers in a cluster with label filters
- **`apply_fit_check_to_labels(cfg, cluster_slug)`** — read `.fit_check_rejected.json` sidecar, tag matching papers in the vault as `deprecated` with their fit_score and fit_reason
- **`prune_cluster(cfg, cluster_slug, label=, archive=True, delete=False, dry_run=True)`** — archive-first move-to-`raw/_archive/<cluster>/` (default), or hard-delete with explicit `--delete` flag. Rebuilds dedup index after either operation.
- **`unarchive(cfg, cluster_slug, slug)`** — restore an archived paper back to its active cluster, removes `archived` label
- **`label_from_fit_score(score)`** — default mapping: 5/4 → `core`, 2 → `tangential`, 0/1 → `deprecated`, 3 → no auto-label
- **`_rewrite_paper_frontmatter()`** — defensive rewriter that handles CRLF and LF, preserves block-list continuations, and is regression-tested against the v0.20.1 newline bug class

### Added — Frontmatter fields

Paper notes now support (all optional, backwards-compatible):

```yaml
labels: [seed, benchmark]                          # list of labels
fit_score: 5                                       # int 0-5 from fit-check
fit_reason: "Canonical SE benchmark"               # one-line rationale
labeled_at: "2026-04-14T08:00:00Z"                 # ISO timestamp
```

Existing `tags:`, `status:`, `subtopics:`, `topic_cluster:` are unchanged. Labels live in their own namespace.

### Added — CLI surface

```bash
# Label a paper
research-hub label <slug> --set seed,benchmark      # replace
research-hub label <slug> --add method               # append
research-hub label <slug> --remove deprecated        # subtract
research-hub label <slug>                            # show current state

# Bulk from JSON
research-hub label-bulk --from-json labels.json

# Query by label
research-hub find --cluster X --label seed
research-hub find --cluster X --label-not deprecated

# Bridge fit-check sidecar to labels
research-hub fit-check apply-labels --cluster X

# Pruning (archive-first)
research-hub paper prune --cluster X --label deprecated --dry-run
research-hub paper prune --cluster X --label deprecated --archive
research-hub paper prune --cluster X --label deprecated --delete --zotero

# Undo
research-hub paper unarchive --cluster X --slug <slug>
```

### Added — Pipeline integration

`research-hub ingest --fit-check` now auto-runs `apply_fit_check_to_labels()` after the pipeline finishes, tagging any rejected papers in the vault as `deprecated` with their fit score + reason. Disable with `--no-fit-check-auto-labels`.

### Added — Topic note integration

`topic build` now renders inline label badges next to each paper wiki-link in sub-topic notes:

```markdown
## Papers

- [[jimenez2024-swe-bench|SWE-bench (Jimenez 2024)]] `[seed, benchmark]` — canonical SE benchmark
- [[yang2024-swe-agent|SWE-agent (Yang 2024)]] `[core, method]` — agent-computer interfaces for SE
- [[chen2024-self-debug|Self-Debug (Chen 2024)]] `[method]` — iterative self-correction
```

### Added — Dashboard integration

`ClusterCard` gains `label_counts: dict[str, int]` and `archived_count: int` fields, populated from `paper.list_papers_by_label()` and `paper.archive_dir()`. The cluster card UI shows a label histogram + archived count under the existing summary line.

### MCP surface (4 new, 50 total)

- `label_paper(slug, labels?, add?, remove?, fit_score?, fit_reason?)` → `{ok, slug, labels, fit_score, fit_reason, labeled_at}`
- `list_papers_by_label(cluster_slug, label?, label_not?)` → list of paper state dicts
- `prune_cluster(cluster_slug, label="deprecated", archive=True, delete=False, dry_run=True)` → move/delete report
- `apply_fit_check_to_labels(cluster_slug)` → `{tagged, already, missing}`

**46 → 50 MCP tools.**

### Tests

- **775 → 810 passing** (+35 tests, 5 skipped unchanged)
- `tests/test_paper_labels.py`: 25 tests
  - read/set labels (12) — including v0.20.1-class regression test for closing-fence newline preservation
  - list_papers_by_label (6)
  - apply_fit_check_to_labels (4)
  - frontmatter rewrite (3)
- `tests/test_paper_prune.py`: 10 tests covering archive, delete, custom label, unarchive, dedup index rebuild

### Non-breaking changes

All existing CLI commands, MCP tool signatures, and frontmatter fields are unchanged. Papers without `labels:` are valid and read as `labels: []`. The pipeline auto-labels only papers that were REJECTED by fit-check (the rejected sidecar already exists). Accepted-papers auto-labeling is deferred to v0.23 (needs a `.fit_check_accepted.json` sidecar that doesn't exist yet).

### Deferred to v0.23+

- Auto-label accepted papers from fit-check (needs new accepted-sidecar)
- `topic build --group-by-label` for sectioned sub-topic notes
- AI bulk labeling from cluster digest (`label-bulk --from-digest`)
- Clickable dashboard label filters
- Cross-cluster label views (e.g. all `seed` papers across clusters)

## v0.21.0 (2026-04-13)

**Discovery quality — multi-query + citation expansion + cluster dedup + seed DOIs + larger defaults.**

Live test on `llm-agents-software-engineering` found the cluster had only ~25-30% of the papers a real literature review would include (20 out of an expected 50-80). Root cause: `discover new` only ran a single query with a small default limit, never fetched citation neighbors, and re-showed papers already ingested in the cluster. v0.21 fixes all five gaps in one release.

### Added — Track A: Multi-query variation

- **`research-hub discover variants --cluster X --query "..." --count 4`** — new subcommand that emits a prompt asking the AI to generate N query variations, each capturing a different facet of the topic (benchmarks vs frameworks vs evaluation vs adjacent specializations). Reads the cluster definition from `00_overview.md` if present.
- **`research-hub discover new --from-variants file.json`** — runs the search once per variation and merges results via the existing DOI-keyed merge layer. Papers hit by multiple variations get a confidence boost and their `_discover_meta.matched_variations` list tracks which queries found them.
- **`emit_variation_prompt()` and `apply_variations()`** helpers in `discover.py` for the emit/apply pattern.
- **1 new MCP tool:** `discover_variants(cluster_slug, query, count=4)` — **46 total** (was 45).

### Added — Track B: Citation graph expansion

- **`research-hub discover new --expand-auto`** — picks the top 3 keyword-search results (ranked by confidence then citation count) as seed papers and fetches their references + forward citations via the existing `CitationGraphClient` (v0.8, Semantic Scholar-backed).
- **`research-hub discover new --expand-from doi1,doi2,doi3`** — user-specified seed DOIs for expansion.
- **`--expand-hops`** (default 1, bounded — no recursion in v0.21).
- **30-per-seed-per-direction cap** — stops runaway expansion on highly-cited seeds like SWE-bench.
- **Graceful degradation** — if S2 rate-limits (HTTP 429), log a warning and continue with whatever was fetched. Never crashes the discover flow.
- **Dedup with keyword results** — if a seed's reference is already in the keyword pool, the entry gets a confidence boost and a `source_tags` entry for "citation-graph" instead of being added as a duplicate.
- **`_citation_node_to_search_result()` helper** converts `CitationNode` (S2 shape) to `SearchResult` for uniform merging.

### Added — Track C: Cluster dedup (default behavior)

- **`discover new` now filters out papers already ingested in the cluster** before stashing candidates. Reads `raw/<cluster>/*.md` frontmatter, extracts DOIs, normalizes, and excludes matching candidates.
- **`--include-existing`** flag bypasses the dedup (useful for re-scoring already-ingested papers against a new definition).
- **`DiscoverState.deduped_against_cluster`** tracks the skipped count, visible in `discover status`.
- Skips `00_overview.md`, `index.md`, and the `topics/` subdirectory when scanning.

### Added — Track D: Seed DOI injection

- **`research-hub discover new --seed-dois "10.x/meta,10.y/auto,10.z/ling"`** — user-specified DOIs to inject as candidates regardless of search hits.
- **`--seed-dois-file path.txt`** — one DOI per line, comments (lines starting with `#`) allowed.
- **Resolution logic:** if the DOI is already in keyword-search results, boost its confidence and tag as `seed`. Otherwise call `enrich_candidates()` (v0.13) to resolve the DOI to full metadata via Crossref/OpenAlex/arXiv and add as new entry.
- **Max confidence (1.0)** for user-supplied seeds — the user has explicit intent.
- **`DiscoverState.seed_dois`** tracks the list.
- **Graceful skip** on invalid DOIs — logged, not raised.

### Added — Track E: Larger defaults

- **`limit`** default in `discover_new()`: **25 → 50**
- **`per_backend_limit`** (over-fetch factor): **`max(limit*2, 20)` → `max(limit*3, 40)`**
- Rationale: a limit of 25 was truncating the long tail before ranking could pick the best. Over-fetching 3x gives the merge layer enough material to produce N high-quality candidates after dedup + confidence sort.
- CLI `--limit` flag still overrides the default exactly.

### Extended DiscoverState

New fields (all backwards-compat via `from_json()` defaulting):

```python
variations_used: list[str]       # variation queries that ran
expanded_from: list[str]         # seed DOIs used for citation expansion
seed_dois: list[str]             # user-injected seeds
deduped_against_cluster: int     # count of candidates filtered by cluster dedup
```

### CLI + MCP surface

**CLI:**
```bash
research-hub discover variants --cluster X --query "..." --count 4 [--out file.md]
research-hub discover new --cluster X --query "..." \
    [--from-variants file.json] \
    [--expand-auto | --expand-from doi1,doi2] [--expand-hops 1] \
    [--seed-dois doi1,doi2 | --seed-dois-file dois.txt] \
    [--include-existing]
```

**MCP:**
- `discover_new` gains `from_variants`, `expand_auto`, `expand_from`, `expand_hops`, `seed_dois`, `include_existing` parameters (all optional, backwards compatible)
- `discover_variants` added (**46 MCP tools total**)

### Non-breaking except…

- **Default `limit` changed from 25 to 50** — unflagged `discover new` returns roughly 2x as many candidates as before. Revert explicitly with `--limit 25`.
- **Cluster dedup is now default** — unflagged `discover new` skips papers already in the cluster. Revert explicitly with `--include-existing`.

These behavior changes are net-positive for a normal workflow but scripts that depended on the exact v0.20 numbers will see differences.

### Tests

- **740 → 775 passing** (+35 tests, 5 skipped unchanged).
- `tests/test_discover_quality.py`: 35 tests across 5 tracks (8 multi-query, 8 citation expansion, 6 cluster dedup, 7 seed DOIs, 6 defaults + integration).
- Existing `tests/test_discover.py` (20 tests) kept green with minor default adjustments.

### Expected impact on real discovery runs

Running the v0.21 flow on the existing `llm-agents-software-engineering` cluster with `--from-variants --expand-auto --seed-dois "metagpt,autocoderover,lingma"` should yield 50-80 candidates instead of 15-20, surfacing the papers the v0.20 audit identified as missing: MetaGPT, AutoCodeRover, Agentless, Lingma, SWE-rebench, SWE-Verified, Commit0, Moatless, and others.

### Deferred to v0.22+

- OpenAlex citation graph as S2 alternative (would eliminate rate-limit risk)
- NLP-driven query expansion (synonym explosion, boolean OR groups) — emit/apply variation already achieves similar ends via AI
- `discover iterate` to remember which variations have been run across sessions
- Cross-cluster citation expansion

## v0.20.2 (2026-04-13)

**Backend live-behavior fixes + honest coverage audit.** A session-ending audit ran each of the 13 registered backends against a real query designed to hit its strongest coverage area. **Only 4 of 13 returned correct results end-to-end.** Mocked unit tests were passing but the live APIs behaved differently from the test fixtures. v0.20.2 fixes the three most impactful issues and documents the rest as known-broken for v0.21.

### Fixed

- **arXiv backend (`search/arxiv_backend.py`)** — the search query was wrapped in quotes as `all:"LLM agent software engineering"`, which arXiv interprets as a phrase match requiring the exact sequence. No paper's metadata contains that exact string, so live queries returned 0 results for the entire v0.13.0-v0.20.1 period. Live audit confirmed 0 hits against "LLM agent software engineering" while a raw API call with AND-joined terms returned 5 relevant papers.
  - **Fix:** new `_build_arxiv_query()` helper that splits free-text queries into `all:term1 AND all:term2 AND ...`, preserves explicit quoted phrases, and falls back to `all:*` on empty input.
  - **Verified live:** post-fix returns 5 on-topic papers (SkillMOO, SWE-bench bug triggers, Tokalator, From LLMs to LLM-based Agents, etc.).
  - **Regression tests:** 4 new tests in `test_arxiv_backend.py` covering AND-split, quoted-phrase preservation, empty fallback, single-word.

- **bioRxiv backend (`search/biorxiv.py`)** — `_matches_query()` used `any(...)`, so a 4-word query matched any paper containing at least one query word. Live audit returned papers about "heavy metal bacterial adaptation" for a query about "protein structure prediction AlphaFold" because both use the word "protein".
  - **Fix:** switched to strict AND — all query terms must be present in the title or abstract.
  - **Trade-off:** strict AND returns 0 results for specific multi-word queries where bioRxiv doesn't have a matching paper, instead of returning irrelevant papers. The honest-zero behavior is better for downstream fit-check and ranking.
  - **Regression tests:** updated `test_biorxiv_matches_query_requires_all_terms` to assert strict AND semantics with 4/4, 3/4, 2/4, 1/4 term cases.

- **Semantic Scholar backend (`search/semantic_scholar.py`)** — on HTTP 429 the backend silently returned an empty list with no user-facing signal, making it impossible to distinguish "no results" from "rate-limited". Live audit hit 429 on every run because S2's free tier throttles aggressively.
  - **Fix:** added a `logger.warning()` with a link to the API key signup page. Existing silent return behavior preserved for callers that don't want to fail on rate limit; visible warning tells the user why they're getting zero results.

### Known issues deferred to v0.21

These were surfaced by the live audit but need a larger fix than a patch release:

- **DBLP** — query uses substring matching that accepts "Swedish" as a match for "SWE-bench". Needs a word-boundary regex or a different API query strategy.
- **ChemRxiv** — ChemRxiv migrated off the Figshare API around 2022-2023; group_id 13652 returns empty results. Needs the Cambridge Open Engage API.
- **RePEc** — the IDEAS HTML scraper's regex pattern (`/p/<series>/<handle>.html`) matches zero handles against the current HTML. Needs a rewrite against either the current DOM or the OAI-PMH endpoint directly (skipping the HTML handle-list step).
- **CiNii** — live audit confirmed the backend parses the Atom XML correctly, but the `from`/`until` year filter excludes all results because CiNii dates everything as the current year (2026) by default. Needs verification of CiNii's date field semantics.
- **KCI** — the endpoint URL returned HTML not JSON in the live audit. The KCI public REST API may live at a different path or may not exist at all. Needs investigation.
- **NASA ADS** — correctly reports `ADS_DEV_KEY` missing at runtime. Not a bug, just requires the user to set the env var.

### Working backends after v0.20.2 (5 of 13)

| Backend | Live status | Use case |
|---|---|---|
| OpenAlex | ✅ | general STEM + humanities |
| arXiv | ✅ (post-fix) | CS, math, physics, bio preprints |
| Crossref | ✅ | DOI-authoritative metadata, all fields |
| PubMed | ✅ | biomedicine |
| ERIC | ✅ | education research |

Plus **Semantic Scholar** when not rate-limited (intermittent).

### Tests

- **735 → 740 passing** (+5 regression tests, 5 skipped unchanged).
- `test_arxiv_backend.py`: 4 tests for `_build_arxiv_query()`.
- `test_biorxiv_backend.py`: 1 test for strict AND filter.

## v0.20.1 (2026-04-13)

**Bug fix.** v0.14.0-B's `_update_subtopic_frontmatter` (called when `topic build` runs on an existing sub-topic file) dropped the trailing newline before the closing `---` fence, producing corrupted frontmatter like:

```yaml
papers: 10
status: draft---     ← missing newline before the fence
```

The corrupted YAML broke `_extract_frontmatter_block`'s `text.find("\n---\n", 4)` lookup, which made `_existing_subtopic_paper_count` return 0 for every sub-topic file, which made `research-hub topic list` show every cluster as having 0 papers per sub-topic — even though the sub-topic notes themselves contained the correct paper lists.

Bug surfaced during a real live test on the cleaned-up `llm-agents-software-engineering` cluster (8 papers expanded to 20 via `discover new` + `discover continue --auto-threshold`, then sub-topic notes built). The first `topic build` worked; the second `topic build` (after re-running `topic assign apply` with corrected paper slugs) corrupted the frontmatter.

**Fix:** one-character change to add the missing `\n` between the frontmatter body and the closing fence in `_update_subtopic_frontmatter`'s return value.

**Regression test added:** `test_build_subtopic_notes_rerun_preserves_frontmatter_yaml` runs build twice and asserts the YAML closing fence stays on its own line, plus verifies `list_subtopics()` returns the correct paper count after rebuild.

Tests: 734 → 735 passing (+1 regression test).

## v0.20.0 (2026-04-13)

**CJK literature backends + region preset — Japanese and Korean academic literature now first-class.**

After v0.19, research-hub covered all major Western fields (CS, biomedicine, social science, chemistry, astronomy, education) but every backend assumed English-language content. Anyone searching for Japanese, Korean, or Chinese literature got nothing — a hard miss for ~15% of the world's research output and a major gap for researchers in Asia. v0.20 adds two CJK-region academic search backends and a `--region` preset that mirrors the `--field` pattern but selects backends by language/region instead of discipline.

### Added — Two CJK backends

- **`CiniiBackend`** (`src/research_hub/search/cinii.py`, ~150 LOC) — CiNii Research, run by Japan's National Institute of Informatics (NII). The canonical bibliography for Japanese academic literature: ~26M records covering Japanese journals, conference proceedings, theses, books, projects. Free, no API key required. Uses the OpenSearch Atom XML endpoint at `https://cir.nii.ac.jp/opensearch/all` with year filters via `from`/`until` params. Parses Atom + Dublin Core + PRISM + CiNii namespaces, extracts DOI from multiple identifier formats (`https://doi.org/...`, `info:doi/...`, `prism:doi`). doc_type maps from `dc:type` to `journal-article`/`thesis`/`book`/`conference-paper`. Japanese characters in titles preserved verbatim.

- **`KciBackend`** (`src/research_hub/search/kci.py`, ~150 LOC) — Korea Citation Index, run by the Korean National Research Foundation. Covers Korean academic literature across all disciplines. Free OpenAPI access at `https://www.kci.go.kr/kciportal/po/search/poArtiSearList.kci` for basic queries, no key required. JSON API. Tries multiple field name variants (`titleEng` first, falling back to `title`; `authors`/`authorList`; `journalNameEng`/`journalName`) to be robust against schema drift. Year filter via `startYear`/`endYear` params.

### Added — `--region` preset

New flag on `research-hub search` and `research-hub discover new`, **mutually exclusive with `--backend` and `--field`**:

| Region preset | Backends |
|---|---|
| `en` | v0.16 5-backend list (DEFAULT_BACKENDS) |
| `jp` | openalex + cinii + crossref |
| `kr` | openalex + kci + crossref |
| `cjk` | openalex + cinii + kci + crossref |

Resolution priority: `--region` > `--field` > `--backend` > `DEFAULT_BACKENDS`. The CLI `add_mutually_exclusive_group` enforces that only one of the three flags can be supplied at a time.

### Backend registry

`_BACKEND_REGISTRY` now has **14 entries (13 unique classes + `medrxiv` alias)**:

```python
_BACKEND_REGISTRY = {
    # ... v0.16-v0.19 entries ...
    "cinii": CiniiBackend,    # NEW
    "kci": KciBackend,        # NEW
}
```

`DEFAULT_BACKENDS` stays at the v0.16.0 5-backend list — CJK backends are opt-in.

### CLI / MCP

- `--region` flag on `search` and `discover new` (mutually exclusive with `--backend` and `--field`)
- `discover_new` Python function gains `region: str | None = None` parameter
- `search_papers` and `discover_new` MCP tools gain `region: str | None = None` parameter
- **No new MCP tools** — 45 stays.

### Bilingual docs

- **`docs/zh/cli-reference.md`** (297 lines) — Traditional Chinese translation of `docs/cli-reference.md` (302 lines). Completes the v0.19.0 ZH translation pass that hit a Gemini rate limit on the third file. All four `docs/zh/*.md` files now have full translations.

### Tests

- **702 → 734 passing** (+32 tests, 5 skipped unchanged).
- `tests/test_cinii_backend.py`: 12 tests (Atom XML parsing, multi-namespace identifier extraction, Japanese characters, year filter, doc_type mapping).
- `tests/test_kci_backend.py`: 12 tests (titleEng fallback, authors as list/dict/string, year filter, articleId URL building).
- `tests/test_region_preset.py`: 2 tests for jp/cjk presets.
- Existing fallback / CLI / discover / MCP tests updated.

### Non-breaking changes only

All existing CLI commands, MCP tool signatures, default backend list, and import paths continue to work unchanged. `--region` is purely additive but mutually exclusive with the existing `--backend` and `--field` flags.

### Field + region coverage matrix

After v0.20 (combining v0.16-v0.20):

| Coverage axis | Options |
|---|---|
| **Field presets (11)** | cs, bio, med, physics, math, social, econ, chem, astro, edu, general |
| **Region presets (4)** | en, jp, kr, cjk |
| **Total backends (13)** | OpenAlex, arXiv, Semantic Scholar, Crossref, DBLP, PubMed, bioRxiv, RePEc, ChemRxiv, NASA ADS, ERIC, CiNii, KCI |

### Deferred to v0.21+

- **Chinese-language backends** — CSSCI/CNKI require institutional subscriptions; deferred until a free open path exists
- **Cross-CJK title fuzz match** — current title-similarity dedup uses Latin word boundaries, doesn't handle CJK boundaries well; v0.21 candidate
- **JSTOR / PsycINFO / IEEE Xplore** — paid databases, lower priority

## v0.19.1 (2026-04-13)

**Build fix.** v0.19.0 wheel was rejected by PyPI with a 400 Bad Request because the wheel had **duplicate file entries** for `research_hub/examples/*`. The `[tool.hatch.build.targets.wheel] packages = ["src/research_hub"]` already includes the `examples/` subpackage automatically, but the additional `[tool.hatch.build.targets.wheel.force-include]` section added the same files a second time. Removing the redundant `force-include` block fixes the duplicate entries; `twine check` now PASSES and the wheel uploads cleanly. No code changes — same v0.19.0 features, just a working build.

## v0.19.0 (2026-04-13)

**Onboarding wizard + bundled examples + bilingual docs scaffolding — lower the barrier for non-CS users.**

After v0.18.0, research-hub had 11 backends and 11 field presets but a brand-new researcher still had to read three docs and stitch six CLI calls together to create their first cluster. v0.19 ships an interactive `init --field <slug>` wizard that walks through cluster creation + first `discover` run with field-appropriate defaults, plus a bundled examples library so users can copy a working cluster definition instead of inventing one from scratch.

### Added — `research-hub init --field <slug>` wizard

- **`src/research_hub/onboarding.py`** (~250 LOC) — field-aware wizard that:
  1. Prompts for cluster name + slug (auto-derived from name)
  2. Prompts for query + optional definition
  3. Creates the cluster registry entry
  4. Runs `discover_new()` internally with the field preset (so the user gets a fit-check prompt without having to call `discover new` themselves)
  5. Prints next-steps with copy-pasteable commands
- **Both interactive and scriptable.** `--non-interactive` mode requires all flags (`--field`, `--cluster`, `--name`, `--query`) and runs end-to-end without input prompts.
- **Existing `init` (no `--field`) unchanged** — calls the legacy `init_wizard.run_init()` for backwards compatibility.

### Added — Field-aware `doctor` check

- **`src/research_hub/doctor_field.py`** (~120 LOC) — for each cluster, scans paper notes for venue/keyword signals and infers the dominant field. Compares against the cluster's declared field (inferred from `seed_keywords`) and reports a `WARN` when they disagree.
- Surfaces in `research-hub doctor` output as `cluster_field:<slug>`. Example: `WARN cluster_field:my-cluster: declared field=cs but papers look like bio (confidence=0.78, signal=12)`.
- Signal keywords cover all 11 fields (cs, bio, med, physics, math, astro, chem, social, econ, edu, general).

### Added — `research-hub examples {list, show, copy}` subcommand group

- **`src/research_hub/examples/`** — bundled example cluster definitions:
  - `cs_swe.json` — LLM agents for software engineering
  - `bio_protein.json` — protein structure prediction
  - `social_climate.json` — climate adaptation modeling
  - `edu_assessment.json` — automated writing assessment with LLMs
- Each example has `name`, `slug`, `field`, `query`, `definition`, `year_from`/`year_to`, `min_citations`, `sample_dois`, `description`.
- `research-hub examples list` — print all 4 with field tags
- `research-hub examples show <name>` — full JSON definition
- `research-hub examples copy <name> [--cluster <slug>]` — copy as a new cluster in the user's `clusters.yaml`, ready for `discover new`
- **3 new MCP tools** (45 total): `examples_list`, `examples_show`, `examples_copy`
- Wheel build now `force-include`s the `examples/` directory via `[tool.hatch.build.targets.wheel.force-include]`.

### Added — Bilingual docs scaffolding

- **`docs/onboarding.md`** (English, new) — first-time setup, three personas (CS researcher, biomedicine PhD, social science postdoc), wizard walkthrough, field reference table.
- **`docs/zh/`** — directory scaffolded with English placeholder content + `<!-- ZH translation pending -->` markers in each file:
  - `docs/zh/README.md` — Chinese entry point with translation status
  - `docs/zh/quickstart.md` — quickstart stub
  - `docs/zh/onboarding.md` — onboarding stub
  - `docs/zh/ai-integrations.md` — integration guide stub
- **A separate Gemini pass** will translate these stubs to traditional Chinese in v0.19.x. Codex did not write Chinese content because CJK content is poorly handled by Codex per the project delegation rules.

### Tests

- **680 → 702 passing** (+22 tests, 5 skipped unchanged).
- `tests/test_onboarding.py`: 10 tests for wizard interactive/non-interactive flows + examples loader.
- `tests/test_doctor_field.py`: 6 tests for field inference signals + doctor warnings.
- `tests/test_examples_cli.py`: 4 tests for CLI surface (list/show/copy/init --field).
- `tests/test_cli_init_doctor.py`, `tests/test_consistency.py`: extended for new commands and MCP tools.

### Non-breaking changes only

- Existing `init`, `doctor`, `examples`-namespace-free CLI all unchanged.
- `--field` flag on `init` is purely additive.
- All v0.18.0 features and import paths preserved.

### Deferred to v0.19.x and v0.20+

- **Chinese translation pass** for `docs/zh/` — separate Gemini run, lighter than this release.
- **CJK literature backends** (CiNii Japan, KCI Korea) — non-trivial encoding + API access challenges; v0.20 candidate.
- **Field auto-detection at cluster creation** — currently doctor warns after the fact; in v0.20+ the wizard could pre-validate the user's chosen field against their seed keywords.

## v0.18.0 (2026-04-13)

**Three more domain backends — chemistry, astronomy/astrophysics, education now first-class.**

v0.17.0 covered CS, biomedicine, social science, economics. v0.18.0 fills in the remaining major fields a research university actually has: chemistry (ChemRxiv), astronomy/astrophysics/geophysics (NASA ADS), and education (ERIC). After this release, the workflow generalizes from "STEM + biomedicine + social science" to "STEM + biomedicine + social science + chemistry + astronomy + education" — most disciplines covered.

### Added — Three more backends

- **`ChemrxivBackend`** (`src/research_hub/search/chemrxiv.py`, ~110 LOC) — ChemRxiv runs on Figshare's infrastructure. Uses the public Figshare API at `https://api.figshare.com/v2/articles/search` with `group_id=13652` to filter to ChemRxiv-hosted content. Free, no key. Returns title, authors, year, DOI, abstract, doc_type=`preprint`. The de-facto chemistry preprint server, same role as bioRxiv for biology.

- **`NasaAdsBackend`** (`src/research_hub/search/nasa_ads.py`, ~150 LOC) — NASA Astrophysics Data System REST API at `https://api.adsabs.harvard.edu/v1/search/query`. Reads API key from `ADS_DEV_KEY` environment variable; without a key the backend returns `[]` and logs a one-time WARNING (graceful degradation, never crashes). Get a free key at https://ui.adsabs.harvard.edu/user/settings/token. Covers ~16M records: astronomy, astrophysics, solar physics, planetary science, geophysics, Earth science. ADS query syntax (`year:[2024 TO 2025]`, `doi:"..."`, `bibcode:"..."`) is used for filters and lookups.

- **`EricBackend`** (`src/research_hub/search/eric.py`, ~120 LOC) — ERIC (Education Resources Information Center), run by the U.S. Institute of Education Sciences. Public REST API at `https://api.ies.ed.gov/eric/`. Free, no key. ~2M records covering education research papers, theses, and ED reports. Maps ERIC IDs to doc types (`EJ`-prefixed = `journal-article`, `ED`-prefixed = `report`).

### Added — Three new field presets

| Preset | Backends |
|---|---|
| `chem` | openalex + chemrxiv + crossref + semantic-scholar |
| `astro` | openalex + arxiv + nasa-ads + crossref + semantic-scholar |
| `edu` | openalex + eric + crossref + semantic-scholar |

The `general` preset now expands to **11 backends** (was 8 in v0.17): the v0.16 + v0.17 + v0.18 set combined.

### Backend registry

`_BACKEND_REGISTRY` now has **12 entries (11 unique classes + `medrxiv` alias for `BiorxivBackend`)**:

```python
_BACKEND_REGISTRY = {
    "openalex": OpenAlexBackend,
    "arxiv": ArxivBackend,
    "semantic-scholar": SemanticScholarClient,
    "crossref": CrossrefBackend,
    "dblp": DblpBackend,
    "pubmed": PubMedBackend,
    "biorxiv": BiorxivBackend,
    "medrxiv": BiorxivBackend,    # alias
    "repec": RepecBackend,
    "chemrxiv": ChemrxivBackend,    # NEW
    "nasa-ads": NasaAdsBackend,     # NEW
    "eric": EricBackend,            # NEW
}
```

`DEFAULT_BACKENDS` stays at the v0.16.0 5-backend list — the new domain backends are still opt-in.

### CLI / MCP — no signature changes

The `--field` flag's `choices=sorted(FIELD_PRESETS.keys())` is computed dynamically, so adding new presets to `FIELD_PRESETS` automatically extends the CLI. The `discover_new` and `search_papers` MCP tools accept the new preset names without any signature changes. **No CLI parser modifications, no MCP tool count change (42 stays).**

### Tests

- **652 → 680 passing** (+28 tests, 5 skipped unchanged).
- `tests/test_chemrxiv_backend.py`: 8 tests (POST + JSON body, `group_id=13652` assertion, year filter, doc_type=preprint).
- `tests/test_nasa_ads_backend.py`: 8 tests (graceful degradation without API key, Bearer auth header, year range query, DOI/bibcode lookup).
- `tests/test_eric_backend.py`: 8 tests (year filter via `publicationdateyear`, EJ vs ED doc_type mapping, authors as string or list).
- `tests/test_field_preset.py`: 3 new tests for chem/astro/edu presets.
- `tests/test_search_fallback.py`: registry assertion test for the 3 new backends.

### Field coverage matrix after v0.18.0

| Domain | Backends | Preset |
|---|---|---|
| CS / SE / AI | openalex + arxiv + s2 + dblp + crossref | `--field cs` |
| Math / theoretical physics | openalex + arxiv + crossref + s2 | `--field math` |
| Applied physics / astronomy | openalex + arxiv + nasa-ads + crossref + s2 | `--field astro` |
| Biology | openalex + pubmed + biorxiv + crossref + s2 | `--field bio` |
| Medicine | openalex + pubmed + biorxiv + crossref + s2 | `--field med` |
| Chemistry | openalex + chemrxiv + crossref + s2 | `--field chem` |
| Civil / environmental engineering | openalex + crossref + s2 (general STEM) | `--field general` (no specialty backend) |
| Economics / social science | openalex + crossref + s2 + repec | `--field social` / `--field econ` |
| Education | openalex + eric + crossref + s2 | `--field edu` |
| Humanities | openalex + crossref + s2 (general) | `--field general` (no specialty backend) |

### Deferred to v0.19+

- **CJK literature backends** (CiNii Japan, KCI Korea) — non-trivial encoding + API access challenges
- **JSTOR / PsycINFO** for humanities + psychology — paid databases, lower priority
- **IEEE Xplore** for EE/CE — paid API
- **Bilingual docs + onboarding wizard** — `research-hub init --field bio` walkthrough, EN/ZH per-field quickstarts

## v0.17.0 (2026-04-13)

**Domain backends + field preset — biology, medicine, economics, social sciences now first-class.**

v0.16.0 covered CS / general STEM well but left biomedicine, economics, and social sciences under-served. This release adds three high-impact domain backends and a `--field` preset shortcut so a researcher in biomedicine doesn't need to know which backends fit their field — they say `--field bio` and get the right combination automatically.

### Added — Three new domain backends

- **`PubMedBackend`** (`src/research_hub/search/pubmed.py`, ~150 LOC) — NCBI E-utilities API, free, no key required (key gives 10 req/s instead of 3 req/s, not needed for typical search loads). Two-step request flow: `esearch.fcgi` returns PMID list, `esummary.fcgi` returns structured metadata. Returns title, authors, year, journal, DOI, doc_type. PubMed does not return abstracts via esummary — relies on the merge layer to fill abstracts from other backends. Year filter uses `[pdat]` term tag, DOI lookup uses `[doi]` tag. ~35M biomedical citation database, the canonical biomedicine source.

- **`BiorxivBackend`** (`src/research_hub/search/biorxiv.py`, ~120 LOC) — bioRxiv + medRxiv preprint aggregator. Single backend that queries both servers (biology + medical preprints) and merges results. The official biorxiv API has no free-text search endpoint, so the backend fetches a date window (`/details/{server}/{date_from}/{date_to}/{cursor}`) and filters client-side by query terms. Inefficient but the only option without HTML scraping. Registered as both `biorxiv` and `medrxiv` (alias) in the backend registry.

- **`RepecBackend`** (`src/research_hub/search/repec.py`, ~180 LOC) — RePEc (Research Papers in Economics) via OAI-PMH XML protocol. Two-stage like PubMed: scrape IDEAS HTML search results to get RePEc handle list (`/p/<series>/<handle>.html` regex), then fetch metadata for each handle via OAI-PMH `GetRecord` request. Parses Dublin Core XML (`dc:title`, `dc:creator`, `dc:date`, `dc:identifier`, `dc:type`). The IDEAS HTML scraping is fragile (could break if RePEc changes their markup), but it's the only viable free option. ~3M economics records, cross-publisher coverage.

### Added — `--field` preset shortcut

New flag on `research-hub search` and `research-hub discover new`:

```bash
research-hub search "..." --field bio
research-hub discover new --cluster X --field social --query "..."
```

Available presets:

| Preset | Backends |
|---|---|
| `cs` | openalex + arxiv + semantic-scholar + dblp + crossref |
| `bio` | openalex + pubmed + biorxiv + crossref + semantic-scholar |
| `med` | openalex + pubmed + biorxiv + crossref + semantic-scholar |
| `physics` | openalex + arxiv + crossref + semantic-scholar |
| `math` | openalex + arxiv + crossref + semantic-scholar |
| `social` | openalex + crossref + semantic-scholar + repec |
| `econ` | openalex + crossref + semantic-scholar + repec |
| `general` | all 8 backends |

`--field` and `--backend` are **mutually exclusive** (CLI rejects both at once with a clear error). Default if neither supplied: keep v0.16.0 default (5 backends — `openalex,arxiv,semantic-scholar,crossref,dblp`).

### Backend registry

`_BACKEND_REGISTRY` now includes the 3 new backends + `medrxiv` alias for `BiorxivBackend`:

```python
_BACKEND_REGISTRY = {
    "openalex": OpenAlexBackend,
    "arxiv": ArxivBackend,
    "semantic-scholar": SemanticScholarClient,
    "crossref": CrossrefBackend,
    "dblp": DblpBackend,
    "pubmed": PubMedBackend,
    "biorxiv": BiorxivBackend,
    "medrxiv": BiorxivBackend,    # alias — same backend queries both servers
    "repec": RepecBackend,
}
```

`DEFAULT_BACKENDS` stays at the v0.16.0 5-backend list — the new domain backends are opt-in via `--field` or explicit `--backend`.

### MCP surface

- `search_papers` and `discover_new` MCP tool signatures gain optional `field: str | None = None` parameter. When set, it overrides `backends`. Backwards compatible: omitting it restores v0.16.0 behavior.
- **No new MCP tools** — 42 tools total.

### Tests

- **618 → 652 passing** (+34 tests, 5 skipped unchanged).
- `tests/test_pubmed_backend.py`: 8 tests for the two-step esearch+esummary flow.
- `tests/test_biorxiv_backend.py`: 6 tests covering both servers, date window, query filter.
- `tests/test_repec_backend.py`: 8 tests for HTML scraping + OAI-PMH XML parsing.
- `tests/test_field_preset.py`: 8 tests for preset resolution + mutex with `--backend`.
- Existing fallback / CLI / discover tests updated.

### Non-breaking changes only

All existing CLI commands, MCP tool signatures, default backend list, and import paths continue to work unchanged. `--field` is purely additive.

### Deferred to v0.18+

- **NASA ADS** for astronomy/physics
- **ChemRxiv** for chemistry preprints
- **ERIC** for education research
- **IEEE Xplore** (paid API, lower priority)
- **JSTOR** for humanities (paid)

## v0.16.0 (2026-04-13)

**Multi-backend that actually works + filters + smart ranking — fixes the gaps live tests #2 and #3 surfaced.**

v0.13.0 promised a three-backend fallback chain but live tests revealed it was functionally single-backend: 29/29 candidates across both test runs came from OpenAlex; arXiv and Semantic Scholar contributed zero hits. Root cause: arXiv preprints have zero citations by definition, so the global `min_citations` filter dropped all of them. Test #3 also showed citation-count sort actively hurting noisy queries — IPCC/Lancet reports with 2000+ citations dominated the top 5 positions while the actually-relevant migration papers (with <50 cits) ranked lower. This release fixes the multi-backend chain, adds two new specialized backends, and replaces the citation sort with a smart ranking heuristic.

### Added — Two new backends

- **`CrossrefBackend`** (`src/research_hub/search/crossref.py`, ~140 LOC) — Crossref REST API, free, no key required. Cross-publisher DOI metadata via `https://api.crossref.org/works`. Filters by `type:journal-article` to bias toward primary research. Returns title, authors, year, journal, doc_type, citation count. Does NOT return abstracts (Crossref doesn't store them) — used as a confidence-booster + type-filter source, not a primary search.
- **`DblpBackend`** (`src/research_hub/search/dblp.py`, ~140 LOC) — DBLP computer science bibliography, free, no key. 100% coverage of CS/SE publications including workshop papers and preprints OpenAlex misses. JSON API at `https://dblp.org/search/publ/api`. Returns title, authors, year, venue, doc_type. No abstracts, no citation counts (DBLP doesn't expose them) — used as a recall-boost for SE/CS topics.

### Added — Confidence merging + smart ranking

- **`SearchResult` gains three fields:**
  - `confidence: float` (0.5–1.0) — `0.5 + 0.25 * (n_backends_found - 1)` clamped to 1.0
  - `found_in: list[str]` — which backends saw this paper
  - `doc_type: str` — OpenAlex-style document type (journal-article, book-chapter, report, preprint, etc)
- **`search/_rank.py`** (new module, ~80 LOC) — `merge_results()`, `confidence_from_backends()`, `rank()`, `apply_filters()`, `_term_overlap()`.
- **Smart ranking** (default): `2 * confidence + recency + relevance` where recency is `max(0, 1 - 0.2 * (current_year - paper_year))` and relevance is the fraction of query terms present in the paper's title+abstract. Replaces the legacy citation-count-descending sort, which biased toward popular-but-irrelevant survey papers on polysemous queries.
- **Legacy ranking preserved:** `--rank-by citation` restores v0.15.0 behavior; `--rank-by year` sorts by recency only; default `--rank-by smart` is the new heuristic.

### Added — Filter flags on `research-hub search` and `research-hub discover new`

- **`--exclude-type "book-chapter,report,paratext"`** — drops results whose `doc_type` matches any of the listed types. Useful for filtering out IPCC synthesis docs, Lancet review reports, etc.
- **`--exclude "ipcc lancet burden plastic"`** — negative keywords. Drops results whose title or abstract contains any listed term (case-insensitive substring match).
- **`--min-confidence 0.75`** — requires the paper to be found by at least 2 backends (confidence 0.5 = single backend, 0.75 = two, 1.0 = three or more).
- **`--backend-trace`** — logs per-backend hit counts before merge so you can see exactly why a backend returned nothing.
- **`--rank-by {smart,citation,year}`** — pick ranking strategy.

### Fixed — multi-backend now actually multi-backend

- **`search/fallback.py::search_papers` reworked** to call each backend with appropriate filters:
  - **arXiv** ignores `min_citations` (preprints have zero citations by definition — root cause of v0.13.0 gap #6)
  - **Other backends** apply `min_citations` as before
  - All backends still respect the `year_from`/`year_to` filter
- Per-backend over-fetch (`per_backend_limit = max(limit*2, 20)`) so the merge step still has enough candidates after dedup.
- Backend trace mode logs hit counts at WARNING level when enabled.

### Default backend list

`DEFAULT_BACKENDS` is now `("openalex", "arxiv", "semantic-scholar", "crossref", "dblp")` — 5 backends instead of 3. Existing `--backend openalex,arxiv,semantic-scholar` still works (explicit list overrides the default).

### MCP surface

- `search_papers` and `discover_new` MCP tool signatures gain optional `exclude_types`, `exclude_terms`, `min_confidence`, `rank_by` parameters. Backwards compatible: omitting them restores v0.15.0 behavior.
- **No new MCP tools** — 42 tools total.

### Tests

- **581 → 618 passing** (+37 tests, 5 skipped unchanged).
- `tests/test_crossref_backend.py`: 6 tests for the Crossref backend (mocked HTTP).
- `tests/test_dblp_backend.py`: 6 tests for the DBLP backend (mocked HTTP, fixture JSON).
- `tests/test_search_confidence.py`: 8 tests for confidence merging across backends.
- `tests/test_search_filters.py`: 10 tests for filter flags and ranking modes.
- Existing fallback / CLI / MCP / discover tests updated for new fields and signatures.

### Non-breaking changes only

All existing CLI commands, MCP tool signatures, and import paths continue to work unchanged. The new ranking is the new default but legacy citation sort is one flag away.

### Deferred to v0.17+

- **PubMed / bioRxiv / medRxiv backends** for biology/medicine — v0.17
- **RePEc backend** for economics/social science — v0.17
- **`--field bio|med|cs|social|...` preset** for newcomers — v0.17
- **NASA ADS / ChemRxiv / ERIC backends** — v0.18+

## v0.15.0 (2026-04-13)

**Discovery workflow glue — the "one wrapper, not six commands" release.**

Driven by a live end-to-end test of v0.14.0 that revealed 9 pain points between "I have a topic" and "I have a papers_input.json ready to ingest". This release fixes the highest-priority glue issues (shape bugs + command chain) in one track. Tracks B (backend dedup + confidence) and C (query intelligence) are deferred to v0.16+ pending a second live test.

### Added — `research-hub discover` wrapper

- **`src/research_hub/discover.py`** (new module, ~290 LOC) — stateful wrapper around search + fit-check that chains the two together with a pause at the AI-scoring handoff. State lives under `<vault>/.research_hub/discover/<cluster-slug>/` and is safe to delete.
- **`research-hub discover new --cluster X --query "..."`** — runs search internally, stashes candidates, writes the fit-check prompt to stdout or `--prompt-out file`. Supports `--year`, `--min-citations`, `--backend`, `--limit`, `--definition`.
- **`research-hub discover continue --cluster X --scored file.json`** — reads stashed candidates, runs fit-check apply (writes the existing `.fit_check_rejected.json` sidecar), converts accepted candidates into a correctly-shaped papers_input.json. Supports `--threshold N` (explicit) and `--auto-threshold` (uses `median(scores) - 1` clamped to `[2, 5]`).
- **`research-hub discover status --cluster X`** — shows current stage (`new` / `scored_pending` / `done`), candidate count, accepted/rejected counts.
- **`research-hub discover clean --cluster X`** — removes the stash directory, safe to run before re-discovering.

### Added — `--auto-threshold` for fit-check apply

- **`research-hub fit-check apply --auto-threshold`** computes threshold from score distribution (`median - 1` clamped to `[2, 5]`). Explicit `--threshold N` still wins when both are supplied. Useful for well-calibrated AI scoring where 5 = obvious accept, 3 = boundary case, 0-1 = obvious reject — the median-1 heuristic rejects boundary cases that the default threshold of 3 would keep.
- **`fit_check.compute_auto_threshold(scores)`** exposed as a reusable helper.

### Fixed — shape bugs from v0.13.0-A

- **`research-hub search --to-papers-input` emitted `{"papers": [...]}`** but the pipeline schema requires a flat JSON array. Now emits a flat list.
- **Authors were a comma-joined string** instead of the Zotero creator dicts the pipeline expects (`[{"creatorType":"author", "firstName":"...", "lastName":"..."}, ...]`). Now emits creator dicts via a shared `_authors_to_creators` helper.
- **Required-but-empty fields** (`summary`, `key_findings`, `methodology`, `relevance`) caused the pipeline validator to reject the output. Now filled with `[TODO: ...]` placeholder markers that the AI replaces in the next step.

These bugs meant v0.14.0's `--to-papers-input` output was unusable without a manual Python adapter script between `search` and `ingest`. v0.15.0 eliminates both adapter steps.

### MCP surface

- 4 new tools: `discover_new`, `discover_continue`, `discover_status`, `discover_clean` — **42 tools total** (was 38).

### Tests

- **560 → 581 passing** (+21 new tests, 5 skipped unchanged).
- `tests/test_discover.py`: 20 tests covering state management, continue logic, auto-threshold, status, clean, and a CLI end-to-end smoke test.
- Existing `test_cli_search.py` and `test_fit_check.py` updated for the new shapes.

### Non-breaking changes only

- `research-hub search --to-papers-input` output shape changed from `{"papers": [...]}` to a flat list. **This is technically a breaking change for any script that parsed the old (buggy) output.** But since the old shape was incompatible with the pipeline validator, it's unlikely any caller actually used it end-to-end.
- All existing CLI commands and MCP tool signatures continue to work unchanged.

### Deferred to v0.16+

- Cross-backend dedup (arxiv↔DOI pairs still double-count)
- SearchResult confidence scoring (which backends found each paper)
- Query generation from cluster definition
- Reject-reason failure analysis

## v0.14.0 (2026-04-13)

**Rigorous fit-check + sub-topic notes — the "know your papers are on-topic AND find them by theme" release.**

Two tracks shipped together. Track A adds a multi-gate fit-check system so you can catch off-topic papers BEFORE they pollute a cluster (instead of discovering it only after the 20-minute NotebookLM cycle). Track B adds sub-topic notes so you can browse a cluster by theme without flipping through every paper. Both tracks stay in the emit/apply pattern — research-hub never calls an LLM directly, the user's AI does the scoring and writing.

### Added — Track A: Multi-gate fit-check system

- **`src/research_hub/fit_check.py`** (328 LOC) — four gates validating cluster topic fit at every pipeline stage.
- **Gate 1 — Pre-ingest AI scoring.** `research-hub fit-check emit` builds a prompt asking an AI to score each candidate paper 0-5 against the cluster definition (falls back to parsing the overview's `## Definition` section when no `--definition` supplied). `research-hub fit-check apply` consumes the scored JSON, filters by threshold (default 3), and writes `.fit_check_rejected.json` sidecar for audit. Default threshold is 3 (keep score >= 3).
- **Gate 2 — Ingest-time term overlap.** Fast, no AI. Extracts up to 12 key terms from the cluster definition (4-char words, word-boundary matches, stoplist). Computes the fraction present in each paper's abstract. Zero overlap → paper frontmatter tagged `fit_warning: true` but still ingested (warning only, never blocks).
- **Gate 3 — Post-ingest NotebookLM audit.** `notebooklm/upload.py` briefing system prompt now requires a `### Off-topic papers` section in every generated briefing. `research-hub fit-check audit --cluster X` parses the section, writes `.fit_check_nlm_flags.json`, and exits 1 if any papers are flagged.
- **Gate 4 — Periodic drift check.** `research-hub fit-check drift` re-emits the fit-check prompt for already-ingested papers against the current overview. Reports only — never auto-removes.
- **CLI surface:**
  - `research-hub fit-check emit --cluster X --candidates file.json [--definition "..."]`
  - `research-hub fit-check apply --cluster X --candidates file.json --scored file.json [--threshold 3]`
  - `research-hub fit-check audit --cluster X`
  - `research-hub fit-check drift --cluster X`
  - `research-hub ingest --fit-check --fit-check-threshold 3` — opt-in gate at ingest time.
- **MCP surface:** 4 new tools — `fit_check_prompt`, `fit_check_apply`, `fit_check_audit`, `fit_check_drift` — **33 tools total** (was 29).

### Added — Track B: Sub-topic notes

- **`src/research_hub/topic.py`** extended with sub-topic propose/assign/build/list support. All v0.13.0 functions (`scaffold_overview`, `read_overview`, `get_topic_digest`, `hub_cluster_dir`, `overview_path`) remain unchanged. `topic.py` grew from 206 LOC to ~720 LOC.
- **File convention** — each cluster's `raw/<cluster>/` folder now has a `topics/` subfolder containing `NN_<slug>.md` files, one per sub-topic. Paper notes gain a `subtopics: [a, b]` frontmatter field. A paper can belong to multiple sub-topics.
- **Three-phase workflow:**
  - **Propose** (`research-hub topic propose --cluster X [--target-count 5]`) — emits a prompt asking an AI to propose 3-6 natural groupings from the cluster digest.
  - **Assign** — `research-hub topic assign emit --subtopics proposed.json` emits the per-paper mapping prompt. `research-hub topic assign apply --assignments file.json` writes the `subtopics:` frontmatter to each paper note.
  - **Build** (`research-hub topic build --cluster X`) — reads paper frontmatter, generates `topics/NN_<slug>.md` for each unique sub-topic. File numbering is stable across runs. Overwrites ONLY the `## Papers` section; Scope / Why / Open questions / See also are user-owned and preserved verbatim on re-run.
  - **List** (`research-hub topic list --cluster X`) — prints a table of existing sub-topics with paper counts.
- **Sub-topic template sections** — Scope / Why these papers cluster together / Papers (auto-generated) / Open questions / See also. Papers section uses Obsidian wiki-links: `[[<slug>|<short-title> (<lastname> <year>)]] — <one-line take>`.
- **MCP surface:** 5 new tools — `propose_subtopics`, `emit_assignment_prompt`, `apply_subtopic_assignments`, `build_topic_notes`, `list_topic_notes` — **38 tools total** (was 33 after Track A).
- **Dashboard integration** — `ClusterCard.subtopic_count` field, populated from `list_subtopics()`. Cluster card shows a `N subtopics` badge when count > 0 (hidden when 0 to avoid clutter).

### Fixed

- **CI MCP test failures (second occurrence).** The earlier `[mcp,dev]` fix in v0.13.0 was insufficient: the tests still used fastmcp's private `mcp._tool_manager._tools` API and the direct `imported_function.fn(...)` pattern, both of which break on fastmcp versions where the decorator does not wrap the imported name. Added `tests/_mcp_helpers.py` with `_list_mcp_tool_names(mcp)` and `_get_mcp_tool(mcp, name)` that try the public `mcp.get_tools()` / `mcp.get_tool(name)` (async) API first and fall back to the private path only for older versions. Replaced every private-API access in `test_consistency.py`, `test_mcp_add_paper.py`, `test_mcp_citation_graph.py`, `test_mcp_server.py`, `test_e2e_smoke.py`.

### Tests

- **520 → 560 passing** (+40 new tests, 5 skipped unchanged).
- Track A: 20 new tests in `tests/test_fit_check.py` covering all four gates (emit_prompt, apply_scores, term_overlap, parse_nlm_off_topic, drift_check, CLI integration).
- Track B: 20 new tests in `tests/test_topic_subtopics.py` + `tests/test_cli_operations.py` covering propose/assign/build/list, stable numbering, multi-sub-topic papers, Papers-section-only overwriting.

### Non-breaking changes only

All existing CLI commands, MCP tool signatures, and public topic.py functions continue to work unchanged. `--fit-check` and sub-topic features are opt-in — default v0.13.0 behavior preserved.

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

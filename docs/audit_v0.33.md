# research-hub v0.33.0 — Tool consolidation (Codex Phase 3)

**Released:** 2026-04-17
**Theme:** 5 task-level MCP wrappers on top of 64 low-level tools. Casual Claude Desktop users get 2-3× faster workflows (1 call instead of 3-4). Power users unaffected — all 64 tools still registered.

---

## TL;DR

| Metric | v0.32.0 | v0.33.0 | Δ |
|---|---|---|---|
| Tests | 1235 | 1247 | +12 |
| MCP tools registered | 64 | 69 | +5 task-level wrappers |
| Low-level tools unchanged | 64 | 64 | 0 (absolute backward compat) |
| New CLI commands | 0 | 1 (`research-hub ask`) | +1 |
| Codex critique addressed | Phase 1 + 3 partial | Phase 3 concrete | Phase 2 still v0.34+ |

**Headline:** `ask_cluster(cluster_slug, question)` — the casual Claude Desktop path. "What's SOTA in X?" used to take 3 MCP calls; now it's 1. Under the hood it still uses the existing crystal primitives with a rapidfuzz match.

---

## The 5 task-level wrappers

All in `src/research_hub/workflows.py`. Each function imports and calls existing internals; zero logic duplication.

| Wrapper | Covers | Chains | Saves |
|---|---|---|---|
| `ask_cluster` | Read path | `list_crystals` → fuzzy match → `read_crystal` or fallback to `get_topic_digest` | 2-3 calls → 1 |
| `brief_cluster` | NotebookLM round-trip | `notebooklm_bundle` → `upload_cluster` → `generate_artifact` → `download_briefing_for_cluster` → `read_briefing` | 4-5 calls → 1 |
| `sync_cluster` | Maintenance | `list_crystals` + `check_staleness` + `drift_check` + `run_doctor` → prioritized recommendations | 4 calls → 1 |
| `compose_brief_draft` | Writing | `read_overview` + `list_crystals` (for default outline) + `compose_draft` | 3 calls → 1 |
| `collect_to_cluster` | Unified ingest | Auto-routes DOI/arXiv/folder/URL to `add_paper` or `import_folder` | Eliminates routing overhead |

See `docs/task-workflows.md` for each wrapper's full signature + examples.

---

## Tracks delivered

### Track A — `workflows.py` + 5 MCP tools (Codex brief → Claude direct, commit `1a822a6`)

Codex (per CLAUDE.md delegation protocol) was dispatched for Track A but hung after 15 minutes of exploration. Claude took over directly — inspected the actual internal signatures:

- `crystal.Crystal` has `tldr` / `gist` / `full` as separate attributes (not `.body(detail)` method)
- `notebooklm.upload` exports `upload_cluster`, `generate_artifact`, `download_briefing_for_cluster` (brief guessed different names)
- `fit_check.drift_check(cfg, cluster_slug)` is the real drift API
- `doctor.run_doctor()` returns a list of `CheckResult` dataclasses with `.status` / `.message` / `.name`
- `operations.add_paper(identifier, cluster=...)` returns `int` (0 = success)
- `importer.import_folder(cfg, folder, cluster_slug=..., ...)` returns `ImportReport` with `.imported_count` / `.entries`

Workflows.py code matches real signatures; all 12 new tests pass. 

Test ordering pollution discovered: other tests (e.g. discover / pipeline) were leaving `research_hub.crystal` module state patched. Fixed with an `autouse=True` fixture in `test_v033_workflows.py` that pops cached modules before each test.

### Track B — Documentation (Claude direct)

- `docs/task-workflows.md` (NEW, ~230 lines) — user-facing guide explaining:
  - Why the 2-layer design exists
  - Each of the 5 wrappers with example Claude Desktop prompts
  - When to drop down to low-level tools
  - Migration: no migration needed; all 64 v0.32 tools unchanged
- `docs/audit_v0.33.md` (this file)

### Track C — Release (Claude direct)

- pytest full suite: 1247 passed (v0.32 was 1235, +12 from Track A)
- `pyproject.toml`: 0.32.0 → 0.33.0
- `CHANGELOG.md`: v0.33.0 entry
- `README.md` + zh-TW: badges + version + link to `task-workflows.md`
- tag v0.33.0 + push + gh release

---

## Design decisions

### 5 wrappers, not 7

The Explore agent's original analysis suggested 7 wrappers. Cut 2:

- **`discover_and_score`** — the existing emit/apply pattern (2 calls) doesn't significantly benefit from wrapping (1 call saved). Advanced users review AI-generated scores anyway.
- **`fit_and_ingest`** — same rationale. fit-check is an advanced feature; wrappers are most valuable for the read path.

**5 wrappers chosen** cover major workflows:
- Read (ask_cluster) — highest-traffic
- Maintain (sync_cluster) — "what needs attention"
- Ingest (collect_to_cluster) — unified entry
- External (brief_cluster) — NotebookLM full round-trip
- Write (compose_brief_draft) — draft assembly

### CLI vs MCP-only

Only `ask_cluster` got a CLI surface (`research-hub ask <cluster> "<question>"`) because:

- `sync` as CLI conflicts with existing `sync status` / `sync reconcile` subcommands
- `brief_cluster` requires Playwright + CDP setup — better documented than exposed as a CLI one-liner
- `compose_brief_draft` takes a structured outline — awkward for CLI
- `collect_to_cluster` is redundant with existing `add` / `import-folder` for CLI users

AI agents call all 5 via MCP. CLI users who want the 5-tool chain can copy-paste the CLI commands from docs.

### Backward compatibility is absolute

All 64 v0.32 MCP tools and their signatures remain unchanged. v0.33 is additive only. `tests/test_consistency.py::test_no_orphaned_mappings` gates this.

---

## Live verification

### Offline

```bash
PYTHONPATH=src python -m pytest -q
# 1235 → 1247 passed (+12)
PYTHONPATH=src python -m pytest tests/test_v033_workflows.py -v
# 12 new tests all pass
```

### CLI

```bash
research-hub ask llm-agents-software-engineering "what is this field about"
# Returns JSON with source=crystal + answer body (or digest fallback)

research-hub ask some-cluster  # no question → returns topic digest summary
```

### Via Claude Desktop MCP

```
User: Claude, ask my llm-agents cluster what's the SOTA
Claude: [calls ask_cluster(cluster_slug="llm-agents-software-engineering",
                            question="what's the SOTA", detail="gist")]
        Based on crystal "sota-and-open-problems" (matched, confidence=high):
        [the ~100 word pre-written answer]
        
        Source: crystal • Not stale
```

vs. v0.32 which required Claude to:
1. Call `list_crystals` → get 10 tuples
2. Pick the matching slug manually
3. Call `read_crystal` → get answer

### Backward compat check

```bash
PYTHONPATH=src python -m pytest tests/test_consistency.py -v
# 3 tests pass: every_mcp_tool_is_documented, no_orphaned_mappings, etc.
# Confirms 69 tools registered (64 old + 5 new).
```

---

## v0.34+ backlog

- **Codex Phase 2** — structured memory layer (entities/claims/methods/datasets). Needs its own design conversation.
- **Connector abstraction** — NotebookLM as pluggable plug-in instead of core Playwright dependency.
- **`cli.py` / `mcp_server.py` monolith splits** — HIGH RISK, deferred 4 releases now.
- **Search recall xfail baselines** (v0.26).
- **Task #124 vault restore** — needs user decision.
- **Live NotebookLM round-trip test** — when user opens Chrome.
- **Zotero key encryption** via OS keyring.
- **`.dxt` Claude Desktop extension.**

---

## Release commits

```
1a822a6 feat(v0.33-A): 5 task-level workflow wrappers on top of 64 low-level MCP tools
+ docs commit (Track B)
+ release commit (Track C)
```

PyPI: `pip install -U research-hub-pipeline` after GHA auto-publishes.

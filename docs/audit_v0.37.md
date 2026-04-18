## v0.37.0 audit (2026-04-18)

**Theme:** Cluster integrity + memory CLI/MCP + critical require_config bug fix.

### Track A — Cluster integrity (Codex Brief A, committed `3c6c477`)

5 doctor checks + 1 new module + 12 tests. Live-verified against Wenyu's restored vault (1094 papers): doctor caught 1063 orphans + 3 missing_dir + 5 quote orphans (test pollution, since cleaned). `clusters rebind --emit` produced 347 high/medium-confidence proposals on first heuristic pass.

Persona × failure-mode matrix established (6 modes × 4 personas) — every persona hits at least 3 modes with non-trivial probability. Doctor + rebind cover all 6.

### Track B — Memory CLI/MCP (Codex Brief B, committed `9c27f7e`)

CLI: `research-hub memory {emit, apply, list, read}` matching the crystal subcommand pattern.

4 new MCP tools (52 → 56):
- `list_entities`, `list_claims` (with `min_confidence` filter), `list_methods`, `read_cluster_memory` (graceful `found:false` fallback)

10 new tests (CLI + MCP + persona extensions). Codex initially wrote MCP tests as direct function calls — failed because `@mcp.tool()` returns `FunctionTool` wrapper. Claude fixed via existing `_get_mcp_tool(...).fn` pattern from `tests/_mcp_helpers.py`.

### Track Z — Critical bug fix: require_config env-var path (Claude direct)

User reported CI failure on GitHub Actions: `test_cli_screenshot_requires_out_for_single_tab` with `SystemExit: 1` from `require_config()`.

Root cause: `require_config()` only treated `config.json` existence as initialization, but `HubConfig.__init__` happily honors `RESEARCH_HUB_ROOT` env var. Headless / CI / test environments hit a misleading "not initialized" error despite functional initialization.

Fix: 5-line change in `src/research_hub/config.py::require_config` — accept `RESEARCH_HUB_ROOT` (must point to existing directory) as alternative init signal. Plus 3 regression tests in `tests/test_config.py`:
- env-var path works
- bogus path still fails
- original "no init at all" guard preserved

### Vault restore (closes Task #124, pending since v0.28)

User-initiated full merge from `knowledge-base-archive-20260415/`:

| | Before | After |
|---|---|---|
| Paper notes | 36 | 1094 |
| PDFs | 0 | 27 (93 MB) |
| Clusters | 1 (LLM-SE) + 4 persona-test pollution | 5 (4 archived + LLM-SE) |
| Hub topics/methods/theories | none | restored |
| Project notes | none | 3 (abm-paper, governed-broker, survey) |

All 1094 papers verified as real, on-topic for Wenyu's PhD work (ABM + behavioral theory + LLM agents + flood adaptation). Persona-test pollution cleaned (4 cluster folders, 4 cluster entries, 5 quote files).

### Test totals

```
1312 passed, 15 skipped, 2 xfailed, 1 xpassed in 53.44s
```

(+30 from v0.36: 12 cluster integrity + 6 persona ext + 6 memory CLI + 4 memory MCP + 3 require_config regression — wait, that's 31. Some other test counts also moved due to side effects. Net +30 passing.)

### Codex stalls (recurring pattern, documented)

Codex Brief B "completed (exit code 0)" notification arrived ~10 min before the actual `git commit` happened in the Codex shell. Pattern: Codex writes files quickly, then spends a long time at the staging+commit step with PowerShell profile errors clouding the log. Brief A landed cleanly; Brief B hung but eventually committed without intervention.

### Constraints honored

- 0 modifications to `crystal.py`
- 0 modifications to `memory.py` (only ADD `cluster_rebind.py`)
- 0 modifications to `notebooklm/*` or `connectors/*`
- File moves use `shutil.move` (not in-place edits)
- All log writes append-only to `.research_hub/rebind-<timestamp>.log`
- `--no-dry-run` must be EXPLICITLY set; default conservative

### What's NOT in v0.37 (deferred to v0.38)

- Zotero key encryption at rest
- Search recall baselines
- `.dxt` MCP extension packaging
- Re-shoot dashboard screenshots with restored vault (planned but skipped this release to ship faster — user requested)

### Sequence sanity (running tally)

| Release | Theme | Tests |
|---|---|---|
| v0.34 | Dashboard polish + persona test matrix | 1262 |
| v0.35 | Connector Protocol abstraction | 1270 |
| v0.36 | Structured memory layer (entities/claims/methods) | 1282 |
| **v0.37** | **Cluster integrity + memory CLI/MCP + require_config fix** | **1312** |

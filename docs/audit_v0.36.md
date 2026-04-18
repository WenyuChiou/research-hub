## v0.36.0 audit (2026-04-18)

**Theme:** Phase 2 = structured memory layer. Architecture-only release.

### Track A — Cluster memory (Codex, committed `204f01a`)

3 files, 12 tests, ~700 LOC. Design decision (locked by user):

- **Cluster-level batch extraction** — one emit/apply per cluster, not per-paper. Cheaper, captures cross-paper patterns. Re-extracts from scratch when papers change (acceptable for v0.36 first cut).

Codex-Claude split:
- Brief: Claude (`.ai/codex_task_v036_memory.md`, ~480 lines, full code embedded incl. test stub bodies)
- Execution: Codex (`exec --full-auto`, ~5 min, no stalls)
- Verification + commit-message review + release: Claude

### Track B — Live verification

```python
# Real cluster from Wenyu's vault: llm-agents-software-engineering (20 papers)
>>> from research_hub.config import get_config
>>> from research_hub.memory import emit_memory_prompt
>>> cfg = get_config()
>>> prompt = emit_memory_prompt(cfg, "llm-agents-software-engineering")
>>> len(prompt), prompt.count("\n")
(9319, 182)
```

Prompt structure verified end-to-end:
- ✅ Cluster name + definition pulled from 00_overview.md
- ✅ All 20 papers listed with slug/title/year/doi/one_liner
- ✅ JSON schema with worked examples for entities/claims/methods
- ✅ Vocabulary suggestions (8 entity types, 12 method families) included as guidance, not enforced

Adapter delegation chain unchanged (imports `_read_cluster_papers`, `_read_cluster_definition` from crystal.py — zero crystal modifications).

### Test totals

```
1282 passed, 14 skipped, 3 xfailed in 63.86s
```

(+12 memory tests; +1 xfailed because previous v0.35 xpassed reverted to xfail — flaky baseline test, not a regression)

### Constraints honored

- 0 modifications to `crystal.py` (read-only imports)
- 0 modifications to `cli.py` / `mcp_server.py` / `workflows.py`
- 0 modifications to `notebooklm/*` or `connectors/*`
- All file I/O via `safe_join` + `atomic_write_text`

### What's NOT in v0.36 (deferred to v0.37)

- `research-hub memory emit/apply/list` CLI subcommand
- 4 MCP tools: `list_entities` / `list_claims` / `list_methods` / `read_memory`
- Per-paper incremental extraction (alternative granularity)
- Memory staleness detection (parallel to crystal staleness)
- `extract` workflow wrapper that bundles emit + AI call + apply

### Sequence sanity (full Codex critique now closed)

| Critique | Phase | Shipped |
|---|---|---|
| #1 Phase 1: Document abstraction | Paper as one of 7 source kinds | v0.31 |
| #2 Phase 2: Structured memory | entities/claims/methods registry | **v0.36** |
| #3 Phase 3: Tool consolidation | 5 task-level wrappers on top of 50+ primitives | v0.33 |
| #4 Connector abstraction | Protocol + 2 builtins | v0.35 |
| #5 NLM as optional | Adapter + null fallback | v0.35 |

Next release (v0.37) shifts from architecture to housekeeping: vault restore (Task #124), Zotero key encryption, search recall baselines, MCP `.dxt` extension.

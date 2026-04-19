## v0.39.0 audit (2026-04-18)

**Theme:** Cluster rebind v2 — close the 67% coverage gap from v0.37.

### Why this release

User flagged after v0.38.1: "what about the 716 orphan papers still stuck?" Live re-check on Wenyu's restored 1094-paper vault confirmed v0.37's `clusters rebind --emit` produced proposals for only 347/1063 orphans (33%). The other 716 had no heuristic match — these were the ABM/behavioral/survey/traditional-abm topic-folder papers from his old layout.

This was the SINGLE BIGGEST blocker for using research-hub on a non-trivial vault. Other v0.39 candidates (UI design audit, persona MCP filter, zh-TW localization) were polish; this was broken core flow.

### Phase 1 exploration (2 parallel Explore agents)

**Agent #1** mapped the existing 5 heuristics in `cluster_rebind.py::_propose_cluster` and identified the failure modes:
- `topic_cluster:` field had non-empty values in many legacy papers but was silently dropped (heuristic only checked `cluster:`)
- Zotero `collections:` were human-readable NAMES like "LLM AI agent" but heuristic only matched 8-char Zotero keys (`WNV9SWVA`)
- No semantic-overlap matching between tags and `seed_keywords`

**Agent #2** sampled 24 orphan papers (3 per topic folder) and confirmed the patterns:
- ABM-Theories: `category: abm-theory`, tags BDI / decision-making
- Behavioral-Theory: `research/social-behavior` tags, "Social capital" Zotero collection
- llm-agent (339 papers): `topic_cluster: llm-agents-social-cognitive-simulation` set
- survey (411 papers): `category: flood-abm`, `research/flood-abm` tag
- traditional-abm (227 papers): `category: flood-abm`, "傳統ABM" Zotero collection

### Track A — Codex Brief A (committed `6853827`)

3 new heuristics + auto-create + 4 MCP tools delivered as one Codex brief. 18 tests across 3 files. Codex landed cleanly on first try (no stalls).

**New heuristic chain (8 total)**:
1. H1: explicit `cluster:` field → HIGH (existing)
2. H2: `topic_cluster:` non-empty → HIGH (NEW)
3. H3: Zotero collection KEY match → HIGH (existing)
4. H4: Zotero collection NAME match → HIGH/MEDIUM (NEW)
5. H5: tag↔seed_keywords Jaccard overlap → MEDIUM/LOW (NEW)
6. H6: tag exactly equals slug → MEDIUM (existing)
7. H7: category substring → LOW (existing)
8. H8: folder name → LOW (existing)

**Auto-create**: folders with ≥ 5 unmatched orphans propose new clusters. Opt-in via `--auto-create-new` flag (conservative default).

**4 new MCP tools**: `propose_cluster_rebind`, `apply_cluster_rebind`, `list_orphan_papers`, `summarize_rebind_status`. Pattern follows v0.37-B memory MCP tools (uses `_get_mcp_tool(...).fn(...)` for tests to avoid the FunctionTool wrapper bug).

### Track D — Live verification

```python
>>> from research_hub.config import get_config
>>> from research_hub.cluster_rebind import emit_rebind_prompt
>>> import re, json
>>> cfg = get_config()
>>> report = emit_rebind_prompt(cfg)
>>> # Existing-cluster proposals
>>> match = re.search(r"```json\s*\n(.*?)\n```", report, re.DOTALL)
>>> moves = json.loads(match.group(1))
>>> len(moves)
646
>>> # Auto-create proposals
>>> ac_match = re.search(r"## Proposed new clusters.*?```json\s*\n(.*?)\n```", report, re.DOTALL)
>>> new_clusters = json.loads(ac_match.group(1))
>>> [(p["source_folder"], p["paper_count"]) for p in new_clusters]
[("ABM-Theories", 7), ("Behavioral-Theory", 20), ("Benchmarking", 8),
 ("general-reference", 17), ("survey", 289), ("traditional-abm", 76)]
>>> sum(p["paper_count"] for p in new_clusters)
417
>>> # Total coverage
>>> 646 + 417
1063
```

Coverage: 1063 / 1063 = **100%**. Up from 33% in v0.37.

### Test totals

```
1387 passed, 15 skipped, 3 xfailed in 60.91s
```

(+18 from v0.38.1: heuristics=8, autocreate=5, mcp=5)

### Constraints honored

- 0 changes to existing heuristic semantics — only ADDED new heuristics in priority order
- `--auto-create-new` is OPT-IN (conservative)
- Default still dry-run for `apply`
- All MCP tests use `_get_mcp_tool(...).fn(...)` (v0.37 lesson)
- 0 changes to `crystal.py` / `memory.py` / `connectors/` / `notebooklm/`

### What's NOT in v0.39

- AI-assisted classification (emit/apply with AI deciding) — v0.40 candidate, would push coverage even on edge cases the heuristics can't reach
- Interactive CLI walkthrough — friction in tests, prefer MCP-driven flow where Claude iterates
- Confidence threshold filtering on apply
- Rollback log replay (`rebind --undo`)

### Sequence sanity

| Release | Theme | Tests | CI |
|---|---|---|---|
| v0.37 | Cluster integrity (rebind v1) | 1312 | ✅ |
| v0.38 | Persona-aware UI + UX polish | 1369 | ✅ |
| **v0.39** | **Rebind v2 — 100% orphan coverage** | **1387** | (pending CI verify) |

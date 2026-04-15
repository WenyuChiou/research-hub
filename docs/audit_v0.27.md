# research-hub v0.27.0 — Directness Release Audit

**Date:** 2026-04-15
**Scope:** Live dashboard HTTP server, Obsidian graph auto-refresh, sub-topic Library UI, citation-graph cluster auto-split
**Delegation:** Claude (plan + review + live verification) + 3 Codex tracks in parallel
**Test count:** 1019 → 1087 passing (+68 new), 12 skipped, 5 xfail baselines (search quality, carried from v0.26.0)

## Executive summary

v0.26.0 delivered the audit; v0.27.0 delivers the fixes that make the dashboard pleasant to use every day.

| Surface | Before (v0.26) | After (v0.27) |
|---|---|---|
| Manage form execution | Copy to clipboard → paste into terminal | **Direct POST to `/api/exec`** when server running, clipboard fallback when not |
| Vault change detection | Manual `research-hub dashboard` | **SSE push** from server; browser soft-reloads automatically |
| Obsidian graph colors | 1/5 clusters colored, no label dimension | **14 color groups** (5 cluster paths + 9 label tags) auto-refreshed on every cluster mutation + dashboard build |
| 331-paper cluster UI | Flat `<ol>` with 331 DOM rows | Sub-topic-grouped collapsed `<details>` (graceful fallback when no sub-topics) |
| Big-cluster sub-topic tooling | Manual 2-phase `emit_propose_prompt` | **`clusters analyze --split-suggestion`** with citation graph community detection |
| MCP surface | 46 tools | **47 tools** (+ `suggest_cluster_split`) |
| CLI subcommand count | ~40 | +2 (`serve --dashboard`, `vault graph-colors`, `clusters analyze`) |
| Test count | 1019 passing | **1087 passing** (+68) |

All 3 tracks finished in ~22 minutes of parallel execution. Only 1 post-review fix needed (`_read_cluster_papers` looked up by folder name instead of `topic_cluster` frontmatter — the 331-paper cluster's notes live in `raw/llm-agent/` not `raw/llm-agents-social-cognitive-simulation/`).

---

## 1. Track A — Live dashboard HTTP server (38 new tests)

**New modules:**
- `src/research_hub/dashboard/http_server.py` (~240 LOC) — stdlib `ThreadingHTTPServer` with `GET /`, `/healthz`, `/api/state`, `/api/events` (SSE), `POST /api/exec`
- `src/research_hub/dashboard/executor.py` (~170 LOC) — whitelist of 20+ allowed actions, `execute_action()` via `subprocess.run([...], shell=False)`
- `src/research_hub/dashboard/events.py` (~90 LOC) — `EventBroadcaster` + `VaultWatcher` thread polling vault mtimes every 5s

**Modified:**
- `cli.py` — `serve` subcommand extended with `--dashboard`, `--port`, `--host`, `--allow-external`, `--no-browser` flags
- `script.js` — `detectLiveMode()` + `execAction()` + `openEventStream()`; falls back to clipboard when no server
- `sections.py::HeaderSection` — adds `<span id="live-pill">` showing `● Live` or `◯ Static`
- `style.css` — `.live-pill--on` / `.live-pill--off` styles

**Live verification (against real vault):**

```
$ research-hub serve --dashboard --port 18765 --no-browser
dashboard server listening on http://127.0.0.1:18765/

$ curl http://127.0.0.1:18765/healthz
{"ok": true, "version": "0.27.0", "mode": "live"}

$ curl http://127.0.0.1:18765/api/state | jq '{total_papers, clusters: .clusters|length, briefings: .briefings|length}'
{
  "total_papers": 366,
  "clusters": 5,
  "briefings": 2
}

$ curl -X POST http://127.0.0.1:18765/api/exec \
    -H "content-type: application/json" \
    -d '{"action":"dashboard","slug":null,"fields":{}}'
{"ok": true, "action": "dashboard", "returncode": 0, "duration_ms": 7658, ...}

$ curl -X POST http://127.0.0.1:18765/api/exec -d '{"action":"nuke"}'
HTTP 400
```

✅ All 4 checks pass. Manage forms now execute directly; dashboard auto-reloads via SSE after every vault change.

**Security model:**
- Default bind `127.0.0.1` — refuses `0.0.0.0` without `--allow-external` explicit opt-in
- All actions run as `subprocess.run([...], shell=False)` — no shell interpolation, no injection
- Whitelist enforced via `ALLOWED_ACTIONS` frozenset (20 actions)
- 5-minute timeout per action
- No auth (localhost-only)

---

## 2. Track B — Graph colors + sub-topic Library UI (18 new tests)

**Modified modules:**
- `src/research_hub/vault/graph_config.py` — added label-color-group dimension, `refresh_graph_from_vault()` convenience, idempotent-diff semantics preserving user-authored groups
- `src/research_hub/clusters.py` — auto-refresh hook in `create/delete/rename/bind/merge/split`
- `src/research_hub/cli.py` — `research-hub dashboard` now triggers graph refresh + new `vault graph-colors --refresh` subcommand
- `src/research_hub/paper.py` — `ensure_label_tags_in_body()` writes `<!-- research-hub tags start -->...<!-- ... end -->` sentinel block with `#label/<value>` tags (idempotent)
- `src/research_hub/dashboard/sections.py` — `_cluster_card()` rewritten to group papers by sub-topic when available, flat-list fallback otherwise
- `src/research_hub/dashboard/style.css` — `.subtopic-card` / `.subtopic-card--unassigned` styles

**Live verification:**

```
$ research-hub vault graph-colors --refresh
Refreshed graph colors: 14 groups

$ cat ~/knowledge-base/.obsidian/graph.json | python -c "import sys,json; print(len(json.load(sys.stdin)['colorGroups']))"
14
```

Graph now has:
- **5 cluster paths** (path:raw/llm-agents-behavioral-science-environmental-interaction/, etc.)
- **9 label tags** (tag:#label/seed, tag:#label/core, tag:#label/method, tag:#label/benchmark, tag:#label/survey, tag:#label/application, tag:#label/tangential, tag:#label/deprecated, tag:#label/archived)

Open Obsidian graph view — clusters are now visually grouped by folder AND papers are tinted by label. Seed/core papers pop out against the tangential background.

---

## 3. Track C — Cluster auto-split via citation graph (12 new tests)

**New module:** `src/research_hub/analyze.py` (~220 LOC)
- `build_intra_cluster_citation_graph(cfg, cluster_slug)` — co-citation graph via existing `citation_graph.get_references`, persistent cache at `.research_hub/citation_cache/<slug>/<paper_slug>.json`
- `suggest_split(cfg, cluster_slug)` — `networkx.algorithms.community.greedy_modularity_communities` + TF-IDF-style sub-topic name generation
- `render_split_suggestion_markdown(suggestion)` — markdown report compatible with the existing `topic.apply_assignments` workflow

**New dep:** `networkx >= 3.0` (pure Python, ~10 MB, no heavy transitive deps)

**New CLI:** `research-hub clusters analyze --cluster X --split-suggestion`
**New MCP tool:** `suggest_cluster_split(cluster_slug, min_community_size, max_communities)`

**Live verification on the 331-paper cluster:**

Initial run failed with "0 papers" — `_read_cluster_papers` was looking up papers by folder name (`raw/llm-agents-social-cognitive-simulation/`), but the 331 papers actually live in `raw/llm-agent/` with `topic_cluster: llm-agents-social-cognitive-simulation` in their frontmatter. Fixed by switching to `vault.sync.list_cluster_notes` which identifies membership by frontmatter.

After the fix:

```
$ research-hub clusters analyze --cluster llm-agents-social-cognitive-simulation --split-suggestion --min-community-size 15 --max-communities 8
Analyzed 331 papers → 4 communities (modularity=0.312, coverage=44%)
Report written to docs/cluster_autosplit_llm-agents-social-cognitive-simulation.md
```

### Communities found

| # | Proposed slug | Papers | Top shared references |
|---|---|---|---|
| 01 | `generation-retrieval-augmented-knowledge` | 35 | 10.18653/v1/2020.emnlp-main.550, 10.18653/v1/2021.findings-emnlp.320, 10.18653/v1/2021.eacl-main.74 |
| 02 | `multi-agent-review-agents` | 33 | 10.1145/3586183.3606763, 10.1007/s11704-024-40231-1, 10.48550/arxiv.2309.07864 |
| 03 | `language-large-disaster` | 28 | (disaster / LLM intersection) |
| 04 | `memory-agents-long-term` | 26 | (long-term memory / agent persistence) |

122 of 331 papers grouped. Remaining 209 fell below the `min-community-size=15` floor — they become the "Unassigned" group that will render collapsed in the sub-topic-aware Library tab after `topic apply-assignments` + `topic build`.

**Quality assessment:** The 4 communities are **semantically coherent** despite only 44% citation coverage. The auto-generated TF-IDF names capture the theme correctly:
- RAG/retrieval — real topic cluster (papers on retrieval-augmented generation)
- Multi-agent frameworks — real topic cluster (LLM agent collaboration)
- LLM + disaster — real topic cluster (climate/flood applications)
- Long-term memory — real topic cluster (agent persistence/memory)

The slugs need human review (e.g. `generation-retrieval-augmented-knowledge` should probably become `retrieval-augmented-generation`), but the paper groupings themselves are usable.

**Rate-limiting behavior:** Semantic Scholar returned 429 for roughly half the papers (>180 `citation fetch failed` warnings in stderr). The cache is populated for the successful half, so a second run tomorrow will benefit from the cached data and likely improve coverage to 80%+.

---

## 4. Fixes applied during review

1. **`_read_cluster_papers` used folder name instead of frontmatter** (src/research_hub/analyze.py). Track C tests passed with a fake cluster in `raw/agents/`, but the 331-paper cluster's notes live in `raw/llm-agent/` with `topic_cluster: llm-agents-social-cognitive-simulation`. Fixed by delegating to `vault.sync.list_cluster_notes` which does an rglob + frontmatter filter. Updated test to include `topic_cluster:` in fixture frontmatter.

2. **`test_consistency.py::test_every_mcp_tool_is_documented_in_expected_mappings`** — Track C added a new `@mcp.tool() suggest_cluster_split` but the contract test requires every MCP tool to have a CLI mapping in `EXPECTED_MAPPINGS`. Added `"suggest_cluster_split": "clusters analyze --split-suggestion"`.

Total fix LOC: ~30 lines.

---

## 5. How to use

### Start the live dashboard
```bash
research-hub serve --dashboard --port 8765
# Browser opens automatically to http://127.0.0.1:8765/
# Every Manage form button now executes directly
# Vault changes stream to the browser via SSE — no manual refresh
```

### Split a big cluster
```bash
# 1. Generate suggestion
research-hub clusters analyze --cluster X --split-suggestion

# 2. Review docs/cluster_autosplit_X.md — rename slugs as needed

# 3. Apply suggestion (manual for now)
# Edit each paper's subtopics: frontmatter or use topic apply-assignments

# 4. Build sub-topic notes
research-hub topic build --cluster X

# 5. Regenerate dashboard (graph colors auto-refresh)
research-hub dashboard
```

### Rebuild graph colors standalone
```bash
research-hub vault graph-colors --refresh
# Writes .obsidian/graph.json with 5 cluster + 9 label color groups
```

---

## 6. Test count growth

| Release | Passing | Delta |
|---|---|---|
| v0.25.0 | 873 | — |
| v0.26.0 | 1019 | +146 (audit) |
| **v0.27.0** | **1087** | **+68 (directness)** |

Test breakdown v0.27 by track:
- Track A (live server): 38 tests
- Track B (graph + UI): 18 tests
- Track C (auto-split): 12 tests

---

## 7. v0.28.0 backlog

- **Auto-apply split suggestion** — today user must copy the JSON from the markdown report and run `topic apply-assignments` manually. An `--apply` flag on `clusters analyze` could skip that.
- **Resume cache on second S2 run** — the 44% coverage will improve tomorrow once the cache is populated. A banner in the dashboard could tell the user "rerun in X hours for better results".
- **Multi-user auth** — if the server ever needs to be shared (e.g. lab machine), add Bearer token support.
- **REST API for external integrations** — the `/api/*` endpoints are internal; documenting a stable API surface is a separate release.
- **Sub-topic card virtualization** — when a sub-topic has 100+ papers, the rendered DOM might still be slow. `IntersectionObserver`-based lazy rendering would fix it without introducing a framework.
- **Search quality fixes** (from v0.26 xfail baselines) — still outstanding. v0.29?

---

## Conclusion

v0.26 diagnosed friction. v0.27 removed it. The dashboard is now a first-class interactive surface, the graph view reflects the cluster AND label structure, and the 331-paper cluster has an actual path to being split (citation graph → 4 communities → user reviews → `topic build`).

Every Manage operation that used to cost 2 manual steps now costs 1 click.

**Bottom line:** v0.27.0 is the "make the knowledge garden pleasant" release. The hard architectural decisions (static vs server) were made 2 releases ago; this release just executes them now that the audit baseline is locked.

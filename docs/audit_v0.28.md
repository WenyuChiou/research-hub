# research-hub v0.28.0 — Crystals Release Audit

**Date:** 2026-04-15
**Scope:** Anti-RAG semantic compression layer (pre-computed canonical Q→A "crystals")
**Delegation:** Claude (plan + Track C + live verification + review) + 2 Codex tracks in parallel
**Test count:** 1087 → 1122 passing (+35 new), 12 skipped, 5 xfail baselines (carried from v0.26)

## Executive summary

v0.26 diagnosed friction. v0.27 removed it. **v0.28 changes the architectural axis.**

The user's framing (summarizing Karpathy's "LLM wiki" post and critiquing it):

> "wiki 派只是換一個做法去做同樣的事情 … 還是沒有解決『如果要讓 AI 理解我的資訊，仍然要先拼湊一堆相關資訊餵給模型』的問題，只是把拼湊的碎片給放大 … 我實在想不到 RAG 怎麼死 然後我們的系統也一樣會遇到這個post提到的問題"

The user was right. Every MCP tool research-hub previously exposed to Claude returned **raw materials** (paper abstracts, cluster digests, paper lists). The calling AI had to piece them together at query time. It didn't matter if the chunks were abstracts or wiki pages — still query-time assembly.

**v0.28's answer: store the AI's reasoning, not the inputs.** Crystals are pre-computed canonical Q→A markdown files. Per cluster, up to 10 crystals. Each crystal is the calling AI's one-time answer to one canonical question. Subsequent queries read the pre-written answer directly — no re-synthesis.

[→ Architectural explainer: `docs/anti-rag.md`](anti-rag.md)

---

## What shipped

### Track A — Crystal core module (Codex, 26 tests)

**New files:**
- `src/research_hub/crystal.py` — full module: `CANONICAL_QUESTIONS`, `Crystal`/`CrystalEvidence`/`CrystalStaleness` dataclasses, `emit_crystal_prompt()`, `apply_crystals()`, `list_crystals()`, `read_crystal()`, `check_staleness()`, `get_canonical_questions()`
- `tests/test_crystal.py` — 26 tests

**Modified:**
- `src/research_hub/cli.py` — new `crystal` subparser with `emit/apply/list/read/check` sub-commands
- `src/research_hub/mcp_server.py` — 5 new `@mcp.tool()` functions (`list_crystals`, `read_crystal`, `emit_crystal_prompt`, `apply_crystals`, `check_crystal_staleness`)
- `tests/test_consistency.py` — added 5 new MCP tool mappings

### Track B — Dashboard + drift surface (Codex, 9 tests)

**Modified:**
- `src/research_hub/dashboard/sections.py` — `CrystalSection` (~130 LOC) renders inside Overview tab with per-cluster completion ratio, stale badges, expandable crystal lists
- `src/research_hub/dashboard/drift.py` — `_check_crystal_staleness` detector + dispatcher wiring
- `src/research_hub/dashboard/types.py` — `CrystalSummary` dataclass on `DashboardData`
- `src/research_hub/dashboard/data.py` — populates `crystal_summary_by_cluster` in `collect_dashboard_data`
- `src/research_hub/dashboard/__init__.py` — registers `CrystalSection` in `DEFAULT_SECTIONS`
- `src/research_hub/dashboard/style.css` — `.crystal-section`, `.crystal-card`, `.crystal-stale-badge` styles

**New files:**
- `tests/test_dashboard_crystal_section.py`
- `tests/test_drift_crystal.py`

### Track C — Documentation + multilingual (Claude direct)

**New files:**
- `docs/anti-rag.md` — full architectural explainer (~340 lines). Karpathy critique, eager-vs-lazy framing, before/after concrete example, generation + query flow diagrams, honest limitations.
- `README.zh-TW.md` — full繁中 README mirror

**Modified:**
- `README.md` — rewritten from 341 → 170 lines. Screenshot-led, MCP-first, explicit anti-RAG pitch.

---

## Live verification

Executed end-to-end against the `llm-agents-software-engineering` cluster (20 papers, 4 sub-topics, the cluster that's been the test bed since v0.25).

### Step 1: Emit

```bash
research-hub crystal emit --cluster llm-agents-software-engineering --out /tmp/crystal_prompt.md
```

Result: wrote a 176-line markdown prompt containing the cluster definition + 20 paper rows + 10 canonical questions + JSON schema. ~8 KB total.

### Step 2: Answer (this Claude session, acting as "calling AI")

I answered the prompt directly in this conversation. Wrote 10 crystal objects in JSON matching the schema. Used actual knowledge of the 20 papers accumulated across the v0.12-v0.28 audits. Saved to `/tmp/crystals.json` (~50 KB of Q→A content).

`generator: claude-opus-4-6`

### Step 3: Apply

```bash
research-hub crystal apply --cluster llm-agents-software-engineering --scored /tmp/crystals.json
```

Result:
```
written: 10, replaced: 0, skipped: 0
```

10 `.md` files written to `hub/llm-agents-software-engineering/crystals/`:

| File | Lines | Question |
|---|---|---|
| `what-is-this-field.md` | 69 | What is this research area about? |
| `why-now.md` | 65 | Why does this research matter now? |
| `main-threads.md` | 91 | What are the 3-5 main research threads? |
| `where-experts-disagree.md` | 67 | Where do experts disagree? |
| `sota-and-open-problems.md` | 74 | SOTA + open problems |
| `reading-order.md` | 79 | 5 papers to read first |
| `key-concepts.md` | 90 | 10-20 key concepts |
| `evaluation-standards.md` | 89 | Benchmarks + metrics + datasets |
| `common-pitfalls.md` | 72 | Common newcomer mistakes |
| `adjacent-fields.md` | 79 | Connected research areas |

**Total: 775 lines.** 10 markdown files with TL;DR + Gist + Full + Evidence + See Also + frontmatter provenance (`based_on_papers`, `last_generated`, `generator`, `confidence`).

### Step 4: Round-trip

```bash
research-hub crystal list --cluster llm-agents-software-engineering
```

Result: 10 crystals listed with TL;DRs (all ~30 words each).

```bash
research-hub crystal check --cluster llm-agents-software-engineering
```

Result: all 10 crystals reported `fresh` with `delta=0%` (0 papers added or removed since generation).

```bash
research-hub crystal read --cluster llm-agents-software-engineering --slug what-is-this-field --level tldr
```

Returned the 1-sentence TL;DR. ~180 bytes.

```bash
research-hub crystal read --cluster llm-agents-software-engineering --slug sota-and-open-problems --level gist
```

Returned the 100-word paragraph with inline wiki-links to 3 papers. ~1 KB.

### Step 5: Dashboard surface

```bash
research-hub dashboard
```

Generated `dashboard.html` contains:
- `<section class="crystal-section">`
- `10/10` completion badge for the cluster
- 10 `<details class="crystal-card">` expandable cards
- Graph color refresh: 10 groups (1 cluster path + 9 label tags)

### Step 6: Vault demo-state cleanup

Deleted the 4 empty clusters from the registry (backed up `clusters.yaml.demo-bak` first). The vault is now at minimal demo state:

- **1 cluster** in `clusters.yaml`: llm-agents-software-engineering
- **20 papers** in `raw/`
- **4 sub-topic notes** in `raw/llm-agents-software-engineering/topics/`
- **10 crystal files** in `hub/llm-agents-software-engineering/crystals/`
- **10 Obsidian color groups** in `.obsidian/graph.json` (1 cluster + 9 labels)

---

## Token efficiency measurement

The anti-RAG claim needs a number. Measurement:

**Before v0.28 — "what is this cluster about?" query via `get_topic_digest()`:**

- Dump: 20 paper entries × ~1.5 KB each = **~30 KB**
- Plus cluster overview: **~2 KB**
- Total context passed to calling AI: **~32 KB**
- Calling AI must then read + synthesize 20 abstracts into an answer

**After v0.28 — same query via `list_crystals()` + `read_crystal(level="gist")`:**

- `list_crystals()` response: 10 tuples × ~100 bytes = **~1 KB**
- `read_crystal(slug="what-is-this-field", level="gist")` response: **~800 bytes** (the pre-written gist)
- Total context passed to calling AI: **~1.8 KB**

**Compression ratio: 32 KB → 1.8 KB = 17.8× reduction** for the common-case cluster-level question.

More importantly, the calling AI does **zero synthesis work**. The answer was pre-computed at generation time and is read verbatim. Quality is deterministic across invocations, not a new synthesis attempt each time.

For the "full" level (drill-down), the crystal returns ~3-4 KB instead of the 100-word gist — still 8× smaller than the 32 KB raw dump, and still no synthesis.

---

## Test count

| Release | Passing | Delta |
|---|---|---|
| v0.27.0 | 1087 | — |
| **v0.28.0** | **1122** | **+35** |

Breakdown:
- Track A (crystal core): 26 tests in `tests/test_crystal.py`
- Track B (crystal UI): 9 tests in `tests/test_dashboard_crystal_section.py` + `tests/test_drift_crystal.py`
- Track C (docs): 0 tests (Claude direct)

0 regressions from v0.27. All 5 xfail baselines from v0.26 (search quality) still present, still flagged.

---

## What's NOT in v0.28

- **Auto-regeneration on staleness** — `check_crystal_staleness()` only flags; user decides when to regenerate.
- **Custom canonical questions per cluster** — v0.28 hardcodes 10. Custom questions land in v0.29.
- **Cross-cluster crystals** — "what does my whole vault know about X" spanning clusters: out of scope.
- **Embedding-based routing** — calling AI picks which crystal via semantic understanding (reads 10 TL;DRs, picks one). No vector index in research-hub.
- **Internal LLM calls** — research-hub never calls an API. Provider-agnostic via emit/apply.
- **.dxt Claude Desktop extension** — deferred to v0.29.
- **Search quality fixes** — v0.26 xfail baselines still outstanding.

---

## v0.29 backlog

1. **Custom canonical questions** — user can add `hub/<cluster>/canonical_questions.yaml` with extra questions beyond the 10 defaults.
2. **.dxt packaging** — `research-hub-v0.29.dxt` for Claude Desktop one-click install.
3. **Auto-apply split suggestions** — `clusters analyze --apply` directly runs `topic apply-assignments` from the citation-graph clustering output.
4. **Search quality fixes** — rank tiebreak, dedup merge longer-wins, confidence-with-term-overlap, cluster-query-aware eval (the 4 v0.26 xfail root causes).
5. **Sub-topic virtualization** — `IntersectionObserver`-based lazy rendering when a sub-topic has 100+ papers.
6. **Crystal MCP prompt cache** — if the calling AI asks the same question twice, cache the routing decision.

---

## Conclusion

v0.28 is the first research-hub release that genuinely changes the architecture axis rather than iterating on the existing axes. v0.25 fixed UI bugs, v0.26 audited, v0.27 made the dashboard direct — all refinements to a RAG-shaped system. v0.28 introduces a parallel path: for the ~10 questions that dominate cluster-level AI queries, the answer is pre-computed and stored as markdown. The calling AI reads the answer, not the inputs.

This is not a replacement for paper notes, sub-topic grouping, or the live dashboard. Those handle the tail of specific drill-down questions. Crystals handle the head — the ~10 questions per cluster that get asked over and over. Both paths coexist; the calling AI chooses based on what's available.

**Token efficiency measurement: ~18× reduction for common-case cluster queries. Quality is deterministic because synthesis happened once, not per-query.**

The user's critique of Karpathy's wiki — that bigger chunks are still just RAG — was the right framing. The answer wasn't a better wiki. The answer was to stop storing inputs and start storing answers.

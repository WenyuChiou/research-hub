# Task-level workflows (v0.33+)

research-hub exposes **two layers** of MCP tools:

1. **Task-level wrappers (5 tools)** — for the 80% case. One call does what used to take 3-4.
2. **Low-level primitives (64 tools)** — for custom workflows, debugging, and scripting.

Both layers are registered and both work. Casual Claude Desktop users should prefer task-level; power users and scripts can mix freely.

---

## The 5 task-level wrappers

### 1. `ask_cluster(cluster_slug, question=None, detail="gist")`

**The read path.** Answers a natural-language question about a cluster.

```
User: Claude, what's the state of the art in llm-agents-software-engineering?
Claude: [calls ask_cluster(cluster_slug="llm-agents-software-engineering",
                            question="what's the state of the art")]
        Based on crystal "sota-and-open-problems" (gist, 95 words):

        SWE-bench accuracy moved from ~1% (Jimenez 2024 baseline) to ~33%
        (mid-2025). The frontier shifted from "can it work" to "what does
        correctness beyond pass@k look like?"...

        Source: crystal • Confidence: high • Not stale
```

**Under the hood:**
1. `list_crystals(cluster_slug)` — get all 10 pre-computed Q→A titles
2. Fuzzy-match your `question` against crystal questions via rapidfuzz
3. If match found (score > 60): `read_crystal(slug, level=detail)` → return
4. If no match: fall back to `get_topic_digest(cluster_slug)` at reduced size

**Parameters:**
- `cluster_slug` — required. Validated against path traversal.
- `question` — optional natural-language question. If omitted, returns the topic digest directly.
- `detail` — one of `tldr` (1 sentence), `gist` (~100 words, default), `full` (~1000 words + evidence).

**Returns:**
```python
{
    "ok": True,
    "source": "crystal" | "digest",
    "crystal_slug": "sota-and-open-problems",  # only if source=crystal
    "question_matched": "What is the current state of the art?",  # crystal Q
    "answer": "<the answer text>",
    "evidence": ["jimenez2024-swe-bench", "yang2024-swe-agent", ...],
    "confidence": "high" | "medium" | "low",
    "stale": False,
    "suggest_regenerate": False,
    "hint": "..."  # only when cluster has no crystals yet
}
```

### 2. `brief_cluster(cluster_slug, force_regenerate=False)`

**The NotebookLM round-trip.** Bundle → upload → generate → download → preview in one call.

```
User: Claude, generate a brief for the llm-agents cluster
Claude: [calls brief_cluster(cluster_slug="llm-agents-software-engineering")]
        Bundled 20 papers to .research_hub/bundles/.../
        Uploaded to NotebookLM notebook ID abc123
        Generated briefing
        Downloaded to .research_hub/artifacts/.../brief-20260417T...txt

        Preview: "Large language models are being applied to software
        engineering tasks with growing sophistication..."
```

**Under the hood:** chains `notebooklm_bundle` → `notebooklm_upload` → `notebooklm_generate` → `notebooklm_download` → `read_briefing`.

**Pre-req:** `pip install 'research-hub-pipeline[playwright]'` + an already-authenticated Chrome instance attachable via CDP. See [docs/notebooklm.md](notebooklm.md).

**Graceful degradation:** if Playwright isn't installed, returns `{ok: False, bundle_dir: ..., error: "playwright not installed"}` — at least you have the bundle to upload manually.

### 3. `sync_cluster(cluster_slug)`

**"What needs my attention?"** — aggregate maintenance view.

```
User: Claude, what needs attention in llm-agents-software-engineering?
Claude: [calls sync_cluster(cluster_slug="llm-agents-software-engineering")]
        Sync summary:
        - Stale crystals (3): sota-and-open-problems, reading-order, key-concepts
          → Run: research-hub crystal emit --cluster llm-agents-software-engineering > prompt.md
        - Drift score: 2 (below 3-threshold, no action needed)
        - Vault issues: none
```

**Under the hood:** chains `check_crystal_staleness` + `fit_check_drift` + `fit_check_audit` + `run_doctor`, then builds a prioritized `recommendations` list with copy-paste commands.

### 4. `compose_brief(cluster_slug, outline=None, max_quotes=10)`

**Writing assembly.** Builds a markdown draft pulling from cluster crystals, overview, captured quotes, and paper notes.

```
User: Compose a draft for the llm-agents cluster using this outline:
- Introduction
- Main research threads
- Evaluation standards
- Open problems

Claude: [calls compose_brief(cluster_slug="llm-agents-software-engineering",
                              outline="- Introduction\n- Main research threads\n...")]
        Draft written: drafts/llm-agents-software-engineering-20260417.md
        Word count: 1,247
        Paper citations: 15
        Quotes inlined: 8
        Missing citations: [] (all referenced papers have DOIs)
```

**Under the hood:** `list_quotes` + `read_topic_overview` + `list_crystals` (for TLDRs as outline scaffold if `outline` is None) + `compose_draft` + `build_citation` pass.

### 5. `collect_to_cluster(source, cluster_slug, ...)`

**Unified ingest.** Auto-routes by source shape.

```
# By DOI:
collect_to_cluster("10.48550/arxiv.2310.06770", cluster_slug="llm-agents")
# → add_paper (resolves via OpenAlex, creates Zotero + Obsidian notes)

# By arXiv ID:
collect_to_cluster("2310.06770", cluster_slug="llm-agents")

# By folder:
collect_to_cluster("/path/to/pdfs", cluster_slug="market-research")
# → import_folder_tool (extracts text, writes Document notes)

# By URL:
collect_to_cluster("https://en.wikipedia.org/wiki/Knowledge_graph",
                    cluster_slug="kg-notes")
# → writes .url file, then import_folder_tool
```

**Under the hood:** detects source kind via regex + `os.path.isdir`, dispatches to the right underlying tool.

---

## When to drop down to low-level tools

Task-level wrappers are fine for the common 80% case. Go low-level when:

- **You want partial control.** `brief_cluster` chains 4 tools; if you only want to regenerate the brief from existing bundle, call `notebooklm_generate` directly.
- **You're scripting.** `ask_cluster`'s fuzzy match is nice for interactive use but unpredictable for automation. Call `list_crystals` → pick by exact slug → `read_crystal` in scripts.
- **Error recovery.** When a wrapper fails at step 3 of 5, you might want to retry just that step. Task-level returns enough info (`steps: [...]`) to know where, but calling the failed low-level tool directly is simpler.
- **Custom workflows.** E.g., "ingest a DOI but skip the Obsidian note" — task-level `collect_to_cluster` doesn't expose that; use `add_paper` with custom flags.

---

## Migration guide (v0.32 → v0.33)

**You don't need to migrate anything.** All 64 v0.32 MCP tools still work identically.

**If you're a Claude Desktop user:** no changes. Claude will automatically prefer the new task-level tools when they match your prompt (because they're more direct).

**If you're writing custom MCP code:** consider whether your code would be shorter with the new wrappers. Replace where clear, keep where the low-level gives you control you need.

**If you're maintaining scripts:** low-level tools are stable long-term. Wrappers may evolve based on usage patterns — treat them as higher-level UX, not API contracts.

---

## See also

- [docs/mcp-tools.md](mcp-tools.md) — complete catalogue of task-level + low-level tools
- [docs/example-claude-mcp-flow.md](example-claude-mcp-flow.md) — worked example showing both layers
- [docs/anti-rag.md](anti-rag.md) — crystal architecture (what `ask_cluster` reads under the hood)
- [docs/audit_v0.33.md](audit_v0.33.md) — release report for this change

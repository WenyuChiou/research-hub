# Why crystals are not RAG

_A short architectural explainer for v0.28.0. For 中文 → [anti-rag.zh-TW.md](anti-rag.zh-TW.md)._

## The critique

Every knowledge-base-for-AI system — vector databases, Notion AI, Obsidian Copilot, Mem, Reflect, even Karpathy's recent "LLM wiki" proposal — shares the same architectural disease:

**When an AI needs to understand your knowledge, it still has to piece together relevant pieces at query time and feed them to a model.**

The surface pattern varies:
- **Dumb RAG:** embed everything → distance search → grab top-K → stuff context.
- **Smart RAG:** add keywords, classifiers, hierarchical chunks, re-ranking — better retrieval, same assembly.
- **Wiki-for-AI:** pre-generate organized prose pages → the AI reads those pages at query time.

None of these change the core shape: **the unit of storage is the input**, and the LLM does synthesis **every time**. Wiki-for-AI is a nicer chunk, not a different architecture. Bigger chunks, better retrieval, but still:
- Pay the full context cost on every query.
- Get variance across runs because synthesis happens live.
- Can't answer the same question twice without re-doing the work.

As a research user friend put it:

> "他做的只是拉大查詢單位的資訊量以及加強檢索能力，就如同以往我們在做 RAG 一樣… 還是沒有解決『如果要讓 AI 理解我的資訊，仍然要先拼湊一堆相關資訊餵給模型』的問題，只是把拼湊的碎片給放大"

Roughly: *"They just made the retrieval unit bigger and the fetching smarter, same as RAG. The core problem — that the AI still has to assemble a bunch of related chunks before it can understand your data — is untouched. They just scaled up the fragments."*

This is correct. We needed a different architectural axis.

## The shift: eager, not lazy

What if **the unit of storage is the answer**, not the input?

Specifically: for any given research cluster, the useful questions are surprisingly finite. A PhD student browsing their field asks maybe ten kinds of questions:

1. What's this field about?
2. Why does it matter now?
3. What are the main research threads?
4. Where do experts disagree?
5. What's the state of the art and what's unsolved?
6. If I'm new, which 5 papers should I read first?
7. What are the 10-20 key concepts?
8. How do people evaluate their work here?
9. What are common pitfalls?
10. What adjacent fields does this connect to?

Everything else is a drill-down into one of those. And **those 10 answers can be written once, stored as markdown, and retrieved directly next time.** No re-reading 20 abstracts. No query-time fusion. The answer IS the artifact.

We call each answer a **crystal**. Each cluster has up to 10 crystals in `hub/<cluster>/crystals/<question-slug>.md`, with three levels of detail:

- **TL;DR** (1 sentence)
- **Gist** (~100 words)
- **Full** (~500-1000 words with inline wiki-links + evidence table)

## Concrete before/after

**User asks Claude: "What's LLM-for-software-engineering about right now?"**

### Before v0.28 (lazy)

```
Claude → research-hub.get_topic_digest("llm-agents-software-engineering")
       ← 30 KB: all 20 paper abstracts concatenated + frontmatter + overview

Claude: [reads 30 KB, synthesizes answer, replies]
```

Every time someone asks this, Claude re-reads 30 KB and re-does the synthesis. Quality drifts across runs. Token spend scales with cluster size.

### After v0.28 (eager)

```
Claude → research-hub.list_crystals("llm-agents-software-engineering")
       ← 1 KB: 10 crystal (slug, question, tldr, confidence) tuples

Claude: [picks "what-is-this-field"]
Claude → research-hub.read_crystal(..., level="gist")
       ← 200 bytes: pre-written 100-word answer + evidence

Claude: [relays to user]
```

Claude reads 1.2 KB total. The answer was written once, at generation time, by the same quality of model. Deterministic output. No re-synthesis.

When Claude needs details: `level="full"` returns the ~1000-word answer with inline wiki-links and an evidence mapping. Claude reads that, then optionally drills into specific papers by wiki-link.

## What this is NOT

- **Not embeddings.** research-hub doesn't run sentence-transformers or maintain a vector index. The calling AI picks which crystal via semantic understanding (it's an LLM — it can read 10 TL;DRs and pick).
- **Not a wiki.** Wikis pre-compute **organization**. Crystals pre-compute **answers**. A wiki page still needs to be read + synthesized. A crystal answer is ready to emit verbatim.
- **Not an essay / understanding.md.** One long document per cluster is closer than a wiki, but it's still one chunk the calling AI has to pick through. Crystals are bounded, slotted, named — you know exactly what's there.
- **Not auto-generated via API calls.** research-hub never calls an LLM itself. Crystal generation uses the emit/apply pattern (same as [autofill](../src/research_hub/autofill.py) and [fit-check](../src/research_hub/fit_check.py)): you get a prompt, feed it to whatever LLM you prefer, save the JSON answer, apply it to disk. Provider-agnostic.
- **Not a replacement for paper notes.** Crystals handle the common cluster-level questions. Specific drill-down ("how does SWE-agent differ from OpenDevin?") still falls through to direct paper reads. Both paths exist.

## The three observations that make this work

1. **Canonical questions are finite.** If you've watched researchers ask questions about their own field, it's surprising how few question SHAPES exist. ~10 covers 90% of queries. This means a small, bounded artifact archive can carry most of the load.

2. **The calling AI can route without help.** LLMs are perfectly capable of reading 10 question titles + one-sentence TL;DRs and picking the most relevant. research-hub doesn't need to build an embedding layer or TF-IDF index. It just returns the list; the AI picks.

3. **Answer quality is deterministic at generation time.** When you generate a crystal with a strong LLM reading the whole cluster once, you lock in that quality. Subsequent reads return the exact same text. No variance. No "Claude forgot the SOTA number this time."

## Staleness

Crystals have a `based_on_papers: [...]` frontmatter field. When you add/remove papers from the cluster, `research-hub crystal check --cluster X` computes the delta ratio. If >10% of the cluster has changed, the crystal is flagged stale. The dashboard shows a badge; the drift detector emits an alert. **You** decide when to regenerate (not automatic — this avoids unnecessary LLM spending).

## What crystals don't solve

- **Cross-cluster questions.** Crystals are per-cluster. "What does my whole vault know about agents?" spanning multiple clusters is a v0.29+ problem.
- **Unexpected drill-downs.** If a user asks a specific question none of the 10 canonical slots cover, the calling AI falls back to direct paper reads. Same as today.
- **User-specific custom questions.** v0.28 hardcodes the 10. Custom questions land in v0.29.
- **Search quality.** The 5 xfail baselines from v0.26 (recall, rank stability, dedup merge, confidence calibration) are orthogonal. Crystals reduce the frequency of search calls but don't fix the underlying ranker.

## Generation flow

```
┌────────────────┐
│  User: "crys-  │
│  tallize the   │
│  llm-agents    │
│  cluster"      │
└────────┬───────┘
         │
         ▼
┌──────────────────┐      ┌────────────────────┐
│ Claude (or any   │      │ research-hub       │
│ LLM) calls MCP ──┼─────►│ emit_crystal_prompt│
│ emit_crystal_    │      │ (reads 20 papers)  │
│ prompt()         │      └────────┬───────────┘
└──────────────────┘               │
                                   ▼
                          ┌────────────────────┐
                          │ Returns markdown   │
                          │ prompt (~30 KB):   │
                          │ - cluster defn     │
                          │ - paper list       │
                          │ - 10 questions     │
                          │ - JSON schema      │
                          └────────┬───────────┘
                                   │
                     ┌─────────────┴─────────────┐
                     │ Claude answers the prompt │
                     │ itself (it's an LLM).     │
                     │ Produces JSON with 10     │
                     │ crystal objects.          │
                     └─────────────┬─────────────┘
                                   │
                                   ▼
┌──────────────────┐      ┌────────────────────┐
│ Claude calls MCP │      │ research-hub       │
│ apply_crystals() │─────►│ apply_crystals     │
│ with the JSON    │      │ (writes 10 .md     │
└──────────────────┘      │  files to hub/...) │
                          └─────────┬──────────┘
                                    │
                                    ▼
                          ┌─────────────────────┐
                          │ crystals persisted  │
                          │ Dashboard shows     │
                          │ 10/10 crystals, 0   │
                          │ stale               │
                          └─────────────────────┘
```

Zero LLM API calls from inside research-hub. Claude does all the synthesis work; research-hub just provides the prompt template and persists the answer.

## Query flow

```
┌───────────────────────┐
│ User: "what's the     │
│ SOTA in LLM-SE?"      │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐      ┌──────────────────┐
│ Claude                │      │ research-hub     │
│ list_clusters()       │─────►│ returns 5        │
│                       │◄─────│ clusters         │
└──────────┬────────────┘      └──────────────────┘
           │
           ▼
┌───────────────────────┐      ┌──────────────────┐
│ Claude picks          │      │ research-hub     │
│ "llm-agents-software- │      │ returns 10       │
│  engineering"         │─────►│ crystal tuples   │
│ list_crystals(slug)   │◄─────│ (slug, q, tldr)  │
└──────────┬────────────┘      └──────────────────┘
           │
           ▼
┌───────────────────────┐      ┌──────────────────┐
│ Claude picks          │      │ research-hub     │
│ "sota-and-open-       │      │ returns pre-     │
│  problems"            │─────►│ written ~100-    │
│ read_crystal(...,     │◄─────│ word answer      │
│  level="gist")        │      └──────────────────┘
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│ Claude replies to     │
│ user with the ~100    │
│ word pre-written      │
│ answer (+ optional    │
│ commentary)           │
└───────────────────────┘
```

**Total research-hub work per query:** 2 small function calls, ~1 KB of data returned. No paper reads, no abstract concatenation, no re-synthesis.

## Honest limitations

- **Crystal quality depends on the LLM that generated them.** Use a weak model and your crystals will be shallow. Use a strong one once, and every future query benefits.
- **Some questions genuinely need fresh synthesis.** "How does SWE-agent's ACI idea relate to the tool-use patterns from the new Gemini paper I just added?" is not a canonical question. Falls through to raw paper reads. That's fine.
- **Cluster boundaries matter.** If your "cluster" is actually 3 unrelated research areas lumped together, crystals will be incoherent. Use [`research-hub clusters analyze --split-suggestion`](../src/research_hub/analyze.py) first.
- **No automatic refresh.** Adding 1 paper to a 20-paper cluster won't mark crystals stale. Adding 3 will. You decide when to regenerate.

## See also

- [Karpathy's LLM Wiki post](https://karpathy.ai/) (the thing we're arguing against)
- [Audit v0.28](audit_v0.28.md) — release report with live test of crystals on the llm-agents-software-engineering cluster
- [`src/research_hub/crystal.py`](../src/research_hub/crystal.py) — the implementation
- [`src/research_hub/autofill.py`](../src/research_hub/autofill.py) — the emit/apply pattern we mirror

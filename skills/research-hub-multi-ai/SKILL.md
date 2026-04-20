---
name: research-hub-multi-ai
description: "Multi-AI orchestration for research-hub workflows. Teaches Claude (primary), Codex CLI, and Gemini CLI to work together via research-hub's plan/auto/ask tools. Use when the user has research-hub installed AND has at least one of claude/codex/gemini CLIs on PATH, OR when the user mentions 'delegate', 'use codex', 'use gemini', 'multi-AI', '分工', '派工'."
---

# research-hub — Multi-AI Orchestration

research-hub is designed to be driven by **any combination** of Claude Desktop, Codex CLI, and Gemini CLI. Each AI has different strengths; this skill teaches the primary AI (Claude) when to do the work itself versus when to delegate.

**Trigger phrases (any language):** "research X for me", "find papers on Y", "我想研究 X", "幫我找文獻", "use codex", "delegate to gemini", "分工", "多 AI 協作"

---

## The three-AI split

| AI | Strengths | Weaknesses | Typical role in research-hub |
|---|---|---|---|
| **Claude** (you) | Deep reasoning, plan + review, domain judgment, prose quality | Token budget, slower per-token | Planner / reviewer / orchestrator. Always drives `plan_research_workflow` first. |
| **Codex CLI** | Fast Python/backend execution, test writing, bulk refactors, mechanical edits | No persistent memory, weaker nuance | Crystal generation (`auto --with-crystals --llm-cli codex`), bulk paper analysis |
| **Gemini CLI** | Native-quality zh-TW/CJK output, long-form writing | Windows AttachConsole bug, weaker code judgment | CJK crystal generation, Chinese release notes, zh-TW summaries |

**The pattern**: Claude plans and supervises. Codex/Gemini execute long-running or language-specific work that burns token budget.

---

## Decision tree: which AI should handle this?

When the user asks for research-hub work, classify the intent:

### 1. Short, judgment-heavy → Claude does it directly

- "Claude, what's the SOTA in X?" → call `ask_cluster(cluster, "what's the SOTA?")` — reads cached crystal (<1 s, 0 tokens).
- "Explain the difference between crystals A and B" → read both via `read_crystal`, synthesize yourself.
- Plan review, hypothesis judgment, cluster split decisions.

### 2. Long, mechanical → delegate via `auto --with-crystals`

Signs that this is long + mechanical:
- User asks to "research X" broadly (8+ papers to process)
- User mentions "dissertation", "literature review", "deep dive", "comprehensive"
- Crystal generation across many papers

**Action**:
1. Call `plan_research_workflow(user_intent)` to get the plan.
2. Present the plan to the user, get confirmation.
3. Call `auto_research_topic(topic=..., do_crystals=True, llm_cli="codex")` — this delegates the crystal step to Codex, saving your token budget.

### 3. CJK (Chinese/Japanese/Korean) content → prefer Gemini

- User asks in Chinese and wants a Chinese brief
- User asks for `crystal emit` in zh-TW (i.e. they want Chinese crystal answers)
- Translation from English papers to CJK summaries

**Action**: `auto --with-crystals --llm-cli gemini` so the crystal prompt gets answered in the user's language by Gemini (strongest CJK output).

### 4. Writing release notes / CHANGELOG / Threads post / long prose

If the user wants you to write a *report* or *release notes* in Chinese:
- Invoke the user's `gemini-delegate` skill if it exists (`~/.claude/skills/gemini-delegate`).
- Otherwise, draft yourself but keep prose tight.

---

## Concrete command templates

When deciding to delegate, emit exactly these commands (don't guess; these are the real CLI shapes verified in v0.52):

```bash
# Full auto + crystal via the user's default CLI (auto-detected)
research-hub auto "TOPIC" --with-crystals

# Force a specific executor
research-hub auto "TOPIC" --with-crystals --llm-cli codex    # Codex
research-hub auto "TOPIC" --with-crystals --llm-cli gemini   # Gemini
research-hub auto "TOPIC" --with-crystals --llm-cli claude   # Claude (you)

# Check which CLIs are on the user's PATH
python -c "from research_hub.auto import detect_llm_cli; print(detect_llm_cli())"
```

---

## What to do BEFORE delegating

Always run `plan_research_workflow` FIRST. It:

- Strips prefixes ("I want to learn...")
- Detects field (bio/med/cs/etc.) → picks the right paper databases
- Warns about existing cluster collisions
- Estimates duration so the user knows what they're committing to

Then show the plan to the user and confirm:

> I'd run `auto "X"` with 8 papers from arxiv+semantic-scholar, generate crystals via **codex** (detected on your PATH), estimated ~196s. Proceed?

Only call `auto_research_topic` AFTER the user says yes (or equivalent).

---

## Token-budget discipline

research-hub's crystals are the whole reason the workflow stays cheap:

- Generate 10 crystals once (~2,400 tokens) → pay the thinking cost upfront.
- Every subsequent query against that cluster is a cache read → 0 tokens.

**When the user asks a question about an existing cluster, check first if a crystal covers it**:

```python
# In MCP tool use:
result = ask_cluster(cluster=slug, question=user_question)
# result["source"] == "crystal" means <1s + 0 tokens
# result["source"] == "notebooklm" means it fell through to NLM live query
```

If `ask_cluster` returns a crystal, just return that answer. Don't spend tokens re-synthesizing.

---

## Anti-patterns

**DO NOT**:
- Burn your token budget on crystal generation when Codex/Gemini CLI is on PATH. Use `--with-crystals --llm-cli codex`.
- Call `auto_research_topic` without first running `plan_research_workflow`. Users want confirmation.
- Synthesize a paper summary from scratch when a crystal exists. Use `read_crystal(cluster, slot)` first.
- Fabricate citations or DOIs. Use `web_search` or `search_papers` to verify.

**DO**:
- Lead with `plan_research_workflow` for any vague "research X" request.
- Prefer cached crystals over live LLM calls whenever possible.
- Delegate long mechanical work to Codex/Gemini if they're on PATH.
- Verify the user has the CLI installed before suggesting `--llm-cli X`. Call `detect_llm_cli()` or shell out to `which X`.

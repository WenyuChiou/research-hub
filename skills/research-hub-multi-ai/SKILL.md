---
name: research-hub-multi-ai
description: Multi-AI orchestration for research-hub workflows. Use when the user wants Claude, Codex CLI, Gemini CLI, or another shell-capable assistant to share research-hub work such as planning, ingesting, crystal generation, Chinese/English summaries, or long-running literature workflows.
---

# research-hub Multi-AI Orchestration

research-hub can be driven by any AI that can run shell commands, call MCP tools, or call REST endpoints. Use this skill to decide when the primary assistant should work directly and when to delegate long or language-specific work to Codex CLI or Gemini CLI. The underlying workspace may connect Zotero, Obsidian, and NotebookLM, or any useful two-tool subset.

**Stage-agnostic, character-driven routing.** This skill is NOT bound to a specific research stage (discover / ingest / design / write / submit). The decision to delegate is driven by **task character** — token-heavy code, long-context reading, CJK prose, mechanical bulk edits — not by which stage of the research pipeline you happen to be in. A 200-page systematic-review summary in Stage 1 routes to Gemini for the same reason a zh-TW cover letter in Stage 8 does: long CJK prose that pays off Gemini's strength.

## Roles

| AI | Best role | Use when |
|---|---|---|
| Primary assistant | planning, review, domain judgment, user-facing explanation | ambiguous tasks, quality control, final synthesis |
| Codex CLI | Python/backend execution, tests, mechanical bulk work, crystal generation | long local processing or code-heavy workflows |
| Gemini CLI | long-context drafting and CJK output | Traditional Chinese summaries, bilingual briefs, long prose drafts |

## Decision Rules

- Start with `research-hub plan "intent"` for broad research requests.
- Use `research-hub auto "topic" --with-crystals --llm-cli codex` for long mechanical crystal generation when Codex is available.
- Use `research-hub auto "topic" --with-crystals --llm-cli gemini` when the user explicitly wants Chinese/Japanese/Korean output.
- Use `research-hub auto "topic" --no-nlm` for first-run validation before NotebookLM automation is trusted.
- Use cached crystals or `research-hub ask <cluster> "question"` before spending tokens on a fresh synthesis.

## Commands

```bash
research-hub plan "TOPIC"
research-hub auto "TOPIC" --with-crystals
research-hub auto "TOPIC" --with-crystals --llm-cli codex
research-hub auto "TOPIC" --with-crystals --llm-cli gemini
research-hub ask <cluster> "question"
```

Check available CLIs:

```bash
python -c "from research_hub.auto import detect_llm_cli; print(detect_llm_cli())"
```

## Guardrails

- Do not delegate before the workflow is clear.
- Do not fabricate citations or metadata.
- Do not assume Gemini is Chinese-only; it can be used in English, but its strongest reason to choose it over Codex is language-heavy or long-context prose.
- Do not overwrite vault notes or delete clusters without explicit user approval.

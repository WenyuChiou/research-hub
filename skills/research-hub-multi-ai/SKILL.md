---
name: research-hub-multi-ai
description: Research-domain router that writes `.coord/multi_ai_plan.md` when a single round of work will need two or more delegates AND the work touches research-hub artifacts (`.research/`, `.paper/`, Zotero/Obsidian/NotebookLM pipelines). For a single delegate, use `codex-delegate` or `gemini-delegate` directly — do not invoke this skill. For generic non-research multi-agent decomposition (pure code refactor, generic translation, no research-hub artifact), use `agent-collab-workspace:agent-task-splitter` instead (different artifact `.coord/plan.yml`, different scope). The router decides task splitting, dependency ordering, and reconciliation; the leaves execute.
---

# research-hub Multi-AI Router

This skill is the **router** in a router/leaves architecture. The leaves are `codex-delegate` and `gemini-delegate`. The router's only job is to write a coordination plan; the leaves read their assigned task brief from that plan and execute.

## When to Invoke

Invoke this skill **only** when a single round of work will need two or more delegates. Examples:

- Codex writes the test scaffolding **and** Gemini drafts the zh-TW companion doc — same round, both delegates.
- Three parallel Codex runs against independent subtrees of the same repo, with a final Claude reconciliation step.
- A sequence of mixed handoffs: Codex generates data, Gemini summarises in zh-TW, Codex writes a plot script.

If only one delegate is needed this round, **use the leaf skill directly**. Do not produce a router plan for a one-task delegation — it adds ceremony with no benefit.

## When Not to Invoke

- Single delegate this round (just Codex, just Gemini): use the leaf skill.
- Single-LLM `research-hub auto` runs that pass `--llm-cli codex` or `--llm-cli gemini`: the flag is a research-hub feature, not a router decision. See "Single-LLM research-hub routing" below for reference.
- Pure-Claude planning, review, or judgment work: keep it in Claude.

## Prerequisite check

The router emits commands that go through the `research-hub` CLI in many cases. Before producing a plan, verify the CLI exists:

```bash
research-hub doctor
```

If that command is **not found** (vs. emitting a health report), the user installed only the Claude Code marketplace plugin. Stop and tell them:

> This skill orchestrates `research-hub` CLI commands across multiple AIs, but the CLI itself isn't installed. Please run:
>
> ```bash
> pip install research-hub-pipeline
> research-hub setup --persona researcher   # or analyst | humanities | internal
> ```
>
> Then re-run your request.

Do **not** produce a plan that calls `research-hub ...` if the CLI is missing — the user can't execute it. Plans that only call `codex-delegate` / `gemini-delegate` (no research-hub CLI) are fine without it.

## Output artifact: `.coord/multi_ai_plan.md`

The router's only output is `.coord/multi_ai_plan.md` at the workspace root. Every plan has YAML frontmatter and a per-task brief block.

Schema:

```yaml
---
plan_id: <short-slug>             # e.g. paper-corpus-2026-05
created_utc: 2026-05-09T12:34:56Z
goal: <one paragraph>
success_criteria:
  - <observable check 1>
  - <observable check 2>
tasks:
  - id: t1
    agent: codex                  # codex | gemini | claude
    brief_path: .ai/codex_task_t1.md
    depends_on: []
    success_criteria:
      - <verification command or assertion>
  - id: t2
    agent: gemini
    brief_path: .ai/gemini_task_t2.md
    depends_on: [t1]
    success_criteria:
      - <verification>
risks:
  - <known risk>
---
```

A ready-to-paste template lives in `references/multi_ai_plan_template.md`.

The router writes the plan **and** writes each per-task brief at the path declared in `brief_path`. Leaves read the brief and execute.

## Hand-off contract

The plan is the source of truth. After the router writes it:

1. Each leaf is invoked with the brief path as input. Leaves do not read the plan — they read their own brief.
2. Claude (or another reconciler) reads `result.json` from each leaf, compares against `success_criteria` in the plan, and decides accept / re-run / fall back.
3. Plans are append-mostly: if a re-run is needed, append a new task with a fresh id rather than mutating an existing one.

## Single-LLM research-hub routing (reference only)

The `research-hub auto` command takes a `--llm-cli` flag to pick which CLI handles long mechanical work like crystal generation. This is a research-hub feature, not router logic. Use it directly without invoking this skill:

```bash
research-hub auto "TOPIC" --with-crystals --llm-cli codex
research-hub auto "TOPIC" --with-crystals --llm-cli gemini
```

Pick `codex` for token-heavy mechanical generation; pick `gemini` for long-context reading or CJK output. If you also need a second delegate in the same round (e.g. translate the resulting brief to zh-TW with Gemini), then this becomes a multi-AI plan and the router applies.

Check available CLIs:

```bash
python -c "from research_hub.auto import detect_llm_cli; print(detect_llm_cli())"
```

## Guardrails

- Do not produce a plan with a single task — that is a misuse; use the leaf skill directly.
- Do not fabricate citations or metadata in either the plan or the per-task briefs.
- Do not assume Gemini is Chinese-only; route by task character (long context, CJK prose, second-opinion review), not by language alone.
- Do not overwrite `.coord/multi_ai_plan.md` of a different plan_id — append a new file `.coord/multi_ai_plan_<plan_id>.md` if the workspace already has an active plan.
- Do not overwrite vault notes or delete clusters without explicit user approval.

# `.coord/multi_ai_plan.md` template

Create `.coord/multi_ai_plan.md`, or a plan-id suffixed sibling if another plan
is active. Do not invent additional contract fields without updating consumers.

```yaml
---
plan_id: <short-slug-date>
created_utc: <RFC3339 UTC>
goal: <one paragraph>
success_criteria:
  - <observable round-level check>

tasks:
  - id: t1
    agent: codex
    brief_path: .ai/codex_task_t1.md
    result_artifact: .ai/codex_task_t1.txt.result.json
    result_contract: codex_result_json_v1
    in_scope: [tests/example/]
    depends_on: []
    stop_condition: <observable completion or blocker>
    success_criteria:
      - <test or assertion>

  - id: t2
    agent: antigravity
    brief_path: .ai/agy_task_t2.md
    result_artifact: .ai/agy_result_t2.md
    result_contract: agy_markdown_v1
    in_scope: [fixtures/example/]
    depends_on: []
    stop_condition: <observable completion or escalation>
    success_criteria:
      - <file + sentinel verification>

  - id: t3
    agent: primary
    brief_path: inline
    result_artifact: inline
    result_contract: inline
    in_scope: []
    depends_on: [t1, t2]
    stop_condition: <accept, request fix, or report blocker>
    success_criteria:
      - <review and reconciliation check>

risks:
  - <known risk>

reconciliation:
  agent: primary
  steps:
    - Read every declared result_artifact and inspect actual diffs.
    - Run the acceptance checks independently.
    - Append a new fix-up task on mismatch; never rewrite completed history.
---

# Brief: t3 (primary, inline)

## Context
- <required context>

## Goal
- <reconciliation outcome>

## Constraints
- Do not silently widen scope.
- Never accept a leaf's completion claim without checking its evidence.

## Acceptance
- <commands and observable assertions>
```

## Field reference

| Field | Required | Notes |
|---|---|---|
| `plan_id` | yes | Unique for an active round |
| `created_utc` | yes | RFC3339 UTC |
| `goal` | yes | Round outcome |
| `success_criteria` | yes | Round-level evidence |
| `tasks[].id` | yes | Unique within plan |
| `tasks[].agent` | yes | `codex`, `antigravity`, or `primary` |
| `tasks[].brief_path` | yes | Real path; `inline` only for primary |
| `tasks[].result_artifact` | yes | Codex `result.json`, Antigravity `agy_result_*.md`, or primary `inline` |
| `tasks[].result_contract` | yes | `codex_result_json_v1`, `agy_markdown_v1`, or `inline` |
| `tasks[].in_scope` | yes | Non-overlapping write ownership |
| `tasks[].depends_on` | yes | Task ids; may be empty |
| `tasks[].stop_condition` | yes | Completion/escalation boundary |
| `tasks[].success_criteria` | yes | Verifiable task checks |

## Conventions

- Codex briefs follow `codex-delegate`; Antigravity briefs follow
  `antigravity-delegate`, including its <=250-word result and verify flags.
- Long-context/CJK/judgment work is `primary`, not Antigravity.
- Every leaf is preflighted before launch.
- The primary model owns reconciliation, review, commit, and push.

## Anti-patterns

- One-task plan: use the leaf directly.
- Parallel tasks with overlapping write paths.
- Assuming every leaf emits `result.json`.
- Mutating success criteria after a task finished.
- Using an archived or unavailable delegate because an old brief names it.

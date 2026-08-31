# Workflow contract

This contract defines the resumable stage machine and its human decision gates.
The orchestrator may automate low-risk transitions, but it may not weaken a gate
because a tool makes an action easy.

## Stage machine

| Stage | Entry condition | Exit criteria | Typical next stage |
|---|---|---|---|
| `orient` | project root is known | manifests identify question/status, data, entrypoints, evidence, and unknowns | `scope` |
| `scope` | orientation evidence exists | researcher accepts the question, boundaries, inclusion/exclusion criteria, and constraints | `discover` |
| `discover` | scope decision is accepted | queries and sources are logged; candidates are deduplicated and triaged | `synthesize` |
| `synthesize` | an auditable corpus exists | claims link to sources; contradictions, confidence, and gaps are explicit | `design` |
| `design` | evidence gaps and question are known | method, variables, assumptions, validation, and stopping rules are approved | `execute` |
| `execute` | design and resource authorization exist | reproducible runs and validated outputs exist; failures are retained | `write` |
| `write` | evidence artifacts are stable enough to cite | draft claims are source-linked and semantic review findings are resolved | `release` |
| `release` | verification checklist is complete | human authorizes the exact submission/release/merge and post-action checks pass | complete |

Skipping a stage requires a recorded reason and evidence that its exit criteria
were already satisfied. Never infer that evidence from a previous session alone.

## Gate registry

| Gate | Required before | Minimum decision packet |
|---|---|---|
| `scope_commitment` | freezing the research question, corpus criteria, or evaluation target | alternatives, trade-offs, uncertainty, accepted scope |
| `external_write` | Zotero/NotebookLM/Drive/issue/email/account mutation outside approved local scope | exact target, fields/files, preview, rollback limits |
| `experiment_authorization` | costly, long, quota-consuming, or non-reversible experiment | command, resource/time estimate, stopping rule, expected artifacts |
| `semantic_revision` | changing scientific meaning in manuscript, rebuttal, claims, or conclusions | before/after meaning, supporting evidence, unresolved uncertainty |
| `release_authorization` | submission, publication, PR merge, tag/release, or destructive cleanup | final diff/artifacts, checks, destination, rollback/irreversibility |

The accepted decision outcomes are `accept`, `decline`, and `cancel`.

- `accept` authorizes only the described action, target, and bounds.
- `decline` forbids that action; a materially different alternative needs a new
  packet rather than a relabeled retry.
- `cancel` ends the workflow without interpreting cancellation as failure.

## Automatic actions

The orchestrator may proceed without a new gate for read-only inspection,
deterministic validation, local previews, and reversible writes already covered
by an accepted scope decision. Every automatic action still needs a logged tool,
input reference, result, and validation.

## Retry and resume

- Each action declares a bounded retry count; default maximum: two attempts.
- A retry must address a concrete failure and must not broaden scope.
- Store the next unexecuted action in `pending_action` before pausing.
- Match approval by `action_id`, exact scope, parameter/preview hashes, and
  resource bounds. A mismatch invalidates the approval and requires a new gate.
- Resume from verified artifacts when their bytes and relevant dependencies are
  unchanged. Rerun only affected validation when they changed.
- Never mark a stage complete from a tool's exit code alone; inspect the required
  artifact or result contract.
- `completed` and `cancelled` are terminal and require `pending_action: null`;
  `cancelled` must contain the scoped decision whose outcome is `cancel`.

## Privacy and secret handling

Never collect secrets through in-band elicitation or store them in
`.research/workflow_state.yml`. Credentials belong in the user's host secret
store or environment. State may record only that a capability was available or
unavailable, never the credential value.

## Degraded operation

If structured MCP elicitation is unavailable, ask the same decision in chat or
CLI and record the outcome. If a source/tool is unavailable, use a predeclared
adapter fallback only when it preserves the research scope and validation; else
set `blocked` with the missing capability and recovery condition.

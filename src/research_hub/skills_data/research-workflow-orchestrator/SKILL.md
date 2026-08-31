---
name: research-workflow-orchestrator
description: Run a resumable end-to-end research workflow that automates low-risk work, pauses at explicit human decision gates, records provenance, and routes each stage to the appropriate research-hub skill or MCP tool.
---

# research-workflow-orchestrator

Coordinate an entire research project without turning consequential scientific
decisions into silent automation. The orchestrator resumes from
`.research/workflow_state.yml`, performs safe work automatically, and asks for
one structured decision only when the next action crosses a declared gate.

This is a coordination skill, not a new research engine. It routes to the
existing research-hub skills and available CLI/MCP integrations. Read
`references/workflow-contract.md` before the first run. Read
`references/tool-adapters.md` only for the current stage or when selecting a
tool adapter. The machine-readable state contract is
`references/workflow-state.schema.json`.

## Use when

- The user asks to run, resume, automate, or supervise a multi-stage research
  project.
- Work spans at least three of topic scoping, discovery, synthesis, design,
  experiments, writing, and release.
- A persistent human-in-the-loop audit trail is required.

Do not use for one isolated operation. Route a single literature table to
`literature-triage-matrix`, one design conversation to
`research-design-helper`, one paper summary to `paper-summarize`, or project
orientation alone to `research-project-orienter`.

## Required inputs

1. Project root.
2. User objective and constraints.
3. Existing `.research/` manifests, if present.
4. Available tool capabilities. Discover them; never assume an MCP server,
   connector, credential, or browser session exists.

If the state file does not exist, propose a workflow ID and start at `orient`.
Creating the local state file is reversible, but present the initial plan before
executing later stages.

## Automation policy

Classify every proposed action before invoking a tool:

| Action class | Default behavior |
|---|---|
| Read-only discovery, validation, comparison | Run automatically |
| Local deterministic generation with a preview or rollback | Run automatically, preserve provenance |
| Local reversible metadata update | Run automatically when inside approved scope |
| External write, public communication, account change | Stop at `external_write` |
| Costly or long experiment/simulation | Stop at `experiment_authorization` |
| Semantic manuscript/rebuttal change | Stop at `semantic_revision` |
| Submission, publication, release, merge, destructive cleanup | Stop at `release_authorization` |

Unknown risk is gated. Tool availability never lowers the gate class.

## Run loop

1. **Load** `.research/workflow_state.yml` and validate the fields used by the
   current run. If absent, initialize from the schema; do not invent completed
   decisions or artifacts.
2. **Orient** with `research-project-orienter`, or create a previewed local
   manifest using `research-context-compressor` after presenting the initial
   plan. This reversible project-local initialization needs no separate gate;
   freezing its research question or scope still needs `scope_commitment`.
3. **Plan** the smallest next stage. Name inputs, expected artifacts, tool
   adapter, validation, risk class, and any gate.
4. **Decide**:
   - no gate: execute and validate;
   - gate: show the decision packet and wait;
   - missing capability: use the documented fallback or report a blocker.
5. **Record** stage, action, hashes/provenance, validation result, and decision.
   Write state atomically; never record success before validation passes.
6. **Advance** only when exit criteria in the workflow contract pass. Otherwise
   retry within the declared bound or stop with a concrete blocker.
7. **Resume** from the recorded pending action. Never rerun a costly or external
   action merely because a new chat/session started.

## Human decision packet

At a gate, present only what the researcher needs to decide:

```text
Gate: <gate id>
Decision: <one sentence>
Why now: <evidence and uncertainty>
Proposed action: <tool + exact mutation/cost/scope>
Preview: <diff, plan, candidates, or artifact link>
Reversible: <yes/no and rollback>
Options: accept / decline / revise / cancel
```

- `accept`: record approval for the exact action and scope, then continue.
- `decline`: record the decision, choose a safe alternative if one exists, and
  do not repeatedly ask for the same rejected action.
- `revise`: block execution until a replacement action with a new hash is
  presented and accepted.
- `cancel`: record cancellation and stop the workflow cleanly.

An `accept` is valid only through a signed policy checkpoint or exact local-TTY
hash confirmation. A bare actor label from an agent or MCP caller is not human
authorization.

Approval is scoped to the described action. A later public, destructive, more
expensive, or semantically different action needs a new decision.

## Stage routing

| Stage | Primary routes | Required evidence before advancing |
|---|---|---|
| `orient` | `research-project-orienter`, `research-context-compressor` | project manifest and open questions |
| `scope` | `gap-to-topic`, `research-design-helper` | accepted question, criteria, constraints |
| `discover` | `literature-triage-matrix`, research-hub search, Zotero | query log, deduplicated candidate set |
| `synthesize` | `paper-summarize`, `paper-memory-builder`, NotebookLM verifier | claim-evidence map with gaps |
| `design` | `research-design-helper` | design dossier and explicit assumptions |
| `execute` | project-specific code/experiment tools | reproducible command, outputs, validation |
| `write` | academic writing skill chain | source-linked draft and review findings |
| `release` | verification, Git/GitHub/submission tools | release checklist and human authorization |

Do not synthesize claims from unverified metadata or treat a NotebookLM brief as
ground truth. Do not invent missing sources, results, approvals, or tool output.

## State and provenance

- Canonical state path: `.research/workflow_state.yml`.
- Store artifact paths plus SHA-256, stage, and timestamp. Do not store artifact
  contents in state.
- Store action IDs, exact scope, parameter/preview hashes, resource bounds, and
  decision summaries—not private deliberation or credentials. Execute an
  accepted action only when these machine-verifiable fields still match.
- Store every attempt and validation result in `actions[]`; terminal
  `completed`/`cancelled` states have no pending action, and `cancelled` must
  include a `cancel` decision.
- Keep `pending_action` specific enough to resume, but never include API keys,
  cookies, OAuth tokens, or secrets.
- If current bytes, dependencies, or time-sensitive inputs differ from the
  recorded evidence, rerun only the smallest affected validation.

## Failure behavior

- Bound retries per action; default maximum is two attempts unless the plan
  declares a smaller limit.
- On repeated failure, set status to `blocked`, preserve the last verified
  artifact, and report the exact recovery condition.
- Never silently switch data sources, models, research questions, or inclusion
  criteria.
- Never treat an unavailable MCP tool as permission to perform a broader browser
  or shell mutation.

## Completion output

Return:

1. current stage and status;
2. completed stages and validated artifacts;
3. human decisions and their scope;
4. unresolved evidence gaps or blockers;
5. exact next action, or `none` when complete.

The workflow is complete only when the `release` exit criteria pass or the user
explicitly ends the project. A draft alone is not completion.

## Executable runtime

Use the domain service through either interface; both paths make the same state
transition:

- CLI: `research-hub workflow init|status|validate|decide|resume|migrate`
- MCP: `workflow_initialize`, `workflow_status`, `workflow_validate`,
  `workflow_decide`, `workflow_resume`, and `workflow_migrate`

All CLI operations accept `--json`. Migration is a dry run unless `--apply`
is given; apply creates a backup and atomically replaces the state. Schema 1.0
remains readable, while decisions and resume require migration to schema 1.1.

The optional `agent-collab-harness` v0.4 policy/checkpoint layer is discovered
at runtime. If no policy is configured, research-hub keeps its standalone
behavior. If a policy is configured but the package, policy, or checkpoint is
unavailable, resume fails closed. `research-hub doctor --json` reports the
integration as available, unavailable, or misconfigured.

# Deterministic workflow runtime

The workflow runtime is the durable control layer for the eight-stage research
lifecycle. It records decisions and recovery state; it does not silently execute
Zotero, NotebookLM, GitHub, or other external writes.

## CLI

```text
research-hub workflow init --project-root . --json
research-hub workflow status --state .research/workflow_state.yml --json
research-hub workflow validate --state .research/workflow_state.yml --json
research-hub workflow decide --state .research/workflow_state.yml \
  --outcome accept --actor human:researcher --rationale "Approved exact preview" \
  --action-hash <sha256> --interactive --json
research-hub workflow resume --state .research/workflow_state.yml --json
research-hub workflow migrate --state .research/workflow_state.yml --json
research-hub workflow migrate --state .research/workflow_state.yml --apply --json
```

Migration is dry-run by default. Apply creates a byte-for-byte backup, validates
the 1.1 candidate, and atomically replaces the original.

## Optional public harness

Set `RESEARCH_HUB_AGENT_POLICY` and, when needed,
`RESEARCH_HUB_AGENT_CHECKPOINT` to consume the public
`agent-collab-harness` v0.4.0 contract. Install the release asset from
<https://github.com/WenyuChiou/agent-collab-skills/releases/tag/v0.4.0>.
No policy means standalone operation.
A configured but unavailable or invalid engine fails closed and appears as
`misconfigured` in doctor output.

An `accept` decision is authoritative only when it comes from a signed public
harness checkpoint (with trusted keys in `AGENT_COLLAB_HUMAN_KEYS_JSON`) or
from a local TTY where the researcher types `accept <exact-action-hash>`.
MCP never receives the local-TTY bypass. Decline, revise, and cancel remain
direct human stop decisions and cannot broaden authority.

For MCP, set the server-side `RESEARCH_HUB_WORKFLOW_ROOT`. Callers can access
only `<trusted-root>/**/.research/workflow_state.yml`; a caller-provided path
cannot widen that boundary.

## Recovery semantics

- Pending external action: block with `reconcile_required`; never replay it.
- Completed action hash: reject duplicate preparation.
- Decline or cancel: terminal non-success.
- Revise: blocked until a replacement pending action with a new hash exists.
- Retry bound exhausted: blocked with an explicit recovery condition.
- Release completion: accepted release authorization is mandatory.

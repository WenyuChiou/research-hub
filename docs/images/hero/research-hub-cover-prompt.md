# research-hub MCP concept diagram record

Generated with the built-in Image 2.0 path on 2026-08-31 using the
`complex-concept-visual-explainer` semantic-first workflow. The image explains
the MCP boundary and its two real execution paths; it is not a decorative
research-pipeline cover.

Final asset: `../research-hub-cover.png`

SHA-256: `f77e8c9b933007132747f8a85c58d8fc7feeeddce30a9453541a3f92326abe91`

## Communication target

Audience: researchers and agent-harness builders evaluating how an MCP host
operates research-hub.

Takeaway: validation and routing are shared, but ordinary research tools can
read or mutate integrations directly, whereas the workflow-managed path adds
durable state, scoped human decisions, optional policy/checkpoints, prepared
actions, result recording, and an explicit reconcile-required state.

## Concept and role map

| Concept | Visual role | Implementation status | Evidence |
|---|---|---|---|
| MCP Client | Interface caller | External | MCP protocol boundary |
| MCP Server | Interface | Existing | `src/research_hub/mcp_server.py` |
| Validate / Route | Constraint and deterministic dispatch | Existing | typed MCP tools and scoped workflow paths |
| Research Tool Path | Direct domain-operation path | Existing | read tools plus direct mutation tools such as ingest, removal, and NotebookLM operations |
| Domain Services | Research capability layer | Existing | search, vault, citation, Zotero, and NotebookLM modules |
| Direct Mutations | Risk/status disclosure | Existing | some ordinary MCP tools can write without entering workflow state |
| Workflow-Managed Path | Durable governance path | Existing | six `workflow_*` MCP tools |
| Workflow Runtime | Deterministic control layer | Existing | `src/research_hub/workflow_runtime.py` |
| Policy + Checkpoint | Workflow-only fail-closed constraint | Optional | evaluated for workflow acceptance and resume when configured |
| Durable State | State and evidence support | Existing | workflow schema 1.1 under `.research/` |
| Human Decision | Scoped decision constraint | Existing | accept, decline, revise, and cancel bound to an action hash |
| Prepared Action | External-action contract | Existing | pending action and idempotency metadata |
| External Executor | Execution boundary | External / adapter-owned | performs an authorized write and reports the result |
| Record Result | Recovery evidence | Existing runtime contract | result history is persisted back to durable state |
| Reconcile Required | Explicit blocker/status | Existing | unknown external outcome blocks replay and requires operator/executor reconciliation |
| Truth Stores | External research workspaces | Mixed | Zotero, Obsidian, and NotebookLM integrations |
| Structured Response | Output contract | Existing | MCP dictionary / JSON-compatible responses |

Important non-claims:

- The MCP server is not an LLM or autonomous agent.
- Not every MCP write is human-gated today.
- Policy/checkpoint evaluation is not a general MCP router policy; it applies to
  the workflow-managed path.
- Human decisions authorize prepared workflow actions, not arbitrary research
  tool calls.
- `Reconcile Required` is a recovery status. There is no standalone
  `workflow_reconcile` MCP tool or automatic reconciliation loop.

## Layout logic

1. Common interface: MCP Client -> MCP Server -> Validate -> Route.
2. Research Tool Path: Research Tools -> Domain Services -> Direct Mutations ->
   Truth Stores.
3. Workflow-Managed Path: Workflow Tools -> Workflow Runtime -> Durable State ->
   Human Decision -> Prepared Action -> External Executor -> Truth Stores.
4. Workflow-only controls: Policy + Checkpoint sends dashed control signals to
   Workflow Runtime and Human Decision.
5. Recovery: External Executor records results back to Durable State. An unknown
   outcome branches to Reconcile Required and remains blocked.
6. Both paths produce a Structured Response returned to the MCP Client.

Solid teal arrows mean normal request, execution, or response flow. Dashed teal
arrows mean optional policy control or result recording. Amber discloses direct
mutation risk, human authorization, and reconcile-required blockers.

## Final Image 2.0 prompt

```text
Use case: infographic-diagram
Asset type: wide 16:9 GitHub README hero and MCP architecture diagram.
Primary request: explain two distinct paths after MCP Validate and Route.
Research Tool Path: Research Tools -> Domain Services -> Direct Mutations ->
one external Truth Stores card. Workflow-Managed Path: Workflow Tools ->
Workflow Runtime -> Durable State -> Human Decision -> Prepared Action ->
External Executor -> the same Truth Stores card. Policy + Checkpoint is dashed,
Workflow Only, and controls only Workflow Runtime and Human Decision. External
Executor sends a dashed Record Result arrow back to Durable State. Unknown
outcomes branch to Reconcile Required; do not draw reconciliation as an MCP tool
or automatic loop. Both paths return Structured Response to MCP Client.
Style: warm-white, navy monoline, teal arrows, pale-blue cards, restrained
shadows, and amber only for mutation/decision/recovery risk. Match the AI
Research Skills visual family. Keep MCP as an interface, never an AI brain.
```

## Semantic quality check

- PASS: Route visibly forks to the research-tool and workflow-managed paths.
- PASS: the research-tool path explicitly exposes direct mutations outside the
  workflow gate.
- PASS: Policy + Checkpoint and Human Decision appear only in the workflow lane.
- PASS: one Truth Stores node sits outside the research-hub MCP boundary.
- PASS: Record Result points from External Executor back to Durable State.
- PASS: Reconcile Required is a terminal blocker/status rather than an automatic
  loop or invented MCP tool.
- PASS: visible labels are spelled correctly and remain readable at README
  width.

English and Traditional Chinese READMEs share the same diagram. Locale-specific
alt text provides a complete editable explanation for each audience.

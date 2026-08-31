# Stage tool adapters

Select adapters by capability, not brand presence. Start with capability
negotiation, prefer a local/read-only route, and retain a chat/CLI fallback.
An adapter being installed does not authorize its write operations.

| Stage | Preferred skill/tool adapters | Automatic boundary | Human gate |
|---|---|---|---|
| `orient` | research-project-orienter; research-context-compressor; local filesystem/knowledge graph | read manifests and source-linked metadata; create a previewed, reversible project-local manifest | none until the research question or scope is frozen |
| `scope` | gap-to-topic; research-design-helper; decision dossier | generate options and compare trade-offs | `scope_commitment` |
| `discover` | research-hub MCP/CLI search; arXiv; Semantic Scholar; Crossref/OpenAlex; Zotero | search, normalize, deduplicate, preview triage | `external_write` before library mutation |
| `synthesize` | literature-triage-matrix; paper-summarize; paper-memory-builder; NotebookLM verifier | extract and compare source-grounded evidence | `external_write` before upload/generation in a remote notebook |
| `design` | research-design-helper; project methods/docs; statistical or symbolic tools | draft design options and validation plan | `scope_commitment` if question/evaluation changes |
| `execute` | project test/simulation pipeline; Jupyter; data-quality tools; bounded agents | dry-run, lint, deterministic tests | `experiment_authorization` for costly/non-reversible runs |
| `write` | academic-writing-skills; verify-references; senior-author-review | formatting, citation checks, non-semantic lint | `semantic_revision` |
| `release` | verification gate; Git/GitHub; repository CI; submission portal | read checks and prepare preview | `release_authorization` |

## MCP interaction contract

1. Perform capability negotiation before selecting a server feature.
2. If the client/server supports structured `elicitation` (or a negotiated
   successor such as MRTR), use a form for gate outcome and bounded fields.
3. Always accept `accept`, `decline`, `revise`, and `cancel`; do not coerce a decline into
   an error or automatic retry.
4. If structured input is unavailable, use the chat/CLI fallback with the same
   decision packet and record the decision in state.
5. Show exact tool inputs for external or sensitive operations. Validate the
   returned result contract, apply a timeout, and log provenance.
6. Never put credentials, cookies, OAuth tokens, or API keys in elicitation,
   prompts, logs, or workflow state. Use host-managed secrets.

## Adapter fallbacks

| Capability | Preferred | Safe fallback | Fail closed when |
|---|---|---|---|
| Project discovery | knowledge graph/manifests | targeted README/docs/file reads | the project root cannot be established |
| Scholarly metadata | research-hub aggregate search | one approved primary scholarly API | identity/DOI cannot be verified |
| Reference library | Zotero MCP/API | export a local preview file | the next step would overwrite/merge remote records without approval |
| Notebook synthesis | NotebookLM adapter + brief verifier | local source-grounded synthesis | sources or generated claims cannot be audited |
| Computation | repository-native command | documented local notebook/script | runtime/data/version is unknown |
| Human decision | structured MCP elicitation | chat/CLI prompt | identity, scope, or outcome is ambiguous |
| Release | GitHub/host API after approval | prepare commands/diff only | target branch, checks, or authorization is missing |

## Stage result envelope

Record these fields after any tool call used to advance a stage:

```yaml
action_id: <stable action id>
tool: <adapter/tool name>
mode: read_only | preview | write
inputs: [<paths, query ids, or artifact hashes>]
started_at: <RFC3339>
finished_at: <RFC3339>
status: success | failed | blocked | cancelled
outputs: [<artifact paths or stable external ids>]
validation: <command/check and observed result>
```

Do not record raw source text, secrets, or private chain-of-thought in this
envelope.

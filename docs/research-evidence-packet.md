# ResearchEvidencePacket and role agents

Research agents produce prose first, then a no-tool synthesizer structures the
already gathered evidence. The deterministic validator rejects malformed or
duplicate identities, unknown source links, citation-identity conflicts, and a
claim marked supported without a positive evidence-verifier record for each
supporting source.

The stable packet schema ships at
`src/research_hub/schemas/research-evidence-packet-1.0.json`. Required top-level
fields are `schema_version`, `query`, `sources`, `claims`,
`contradictions`, `gaps`, `confidence`, `provenance`, `warnings`, and
`human_decisions`.

Pass the original ordered result slots, including null, failed and partial
results, to `synthesize_evidence_packet`. It filters input records internally,
retaining provenance references and unresolved-coverage warnings, not the prose
itself; keep the original outputs separately. `filter_agent_results`
remains available for callers needing a usable-only view; do not pass that view
to synthesis, because discarded sibling outcomes cannot be recovered. A packet
`ok` result means structural validation, not completion of every research branch.
The function has no expected-branch-count contract: empty input or an omitted
sibling cannot establish completeness, and absence of warnings is not proof
that every expected branch returned. Fallback `result:N` references use original
input-slot indices; preserve that input ordering for reconciliation.
Prompt or tool instructions found inside papers and web pages are
untrusted source content, not runtime commands. Canonical acceptance still
requires the human semantic gate.

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

Parallel callers must remove null and explicitly failed agent results before
synthesis. Prompt or tool instructions found inside papers and web pages are
untrusted source content, not runtime commands. Canonical acceptance still
requires the human semantic gate.

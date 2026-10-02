# Research evidence agent harness

Use a small set of role profiles instead of publishing overlapping skills.

| Profile | Tools | Output |
|---|---|---|
| Discovery Researcher | web, files, scholarly APIs; read-only | prose, source locations, uncertainty |
| Evidence Verifier | files and scholarly APIs | DOI/title/author/year identity and claim-support findings |
| Contradiction/Falsifier | web, files, scholarly APIs | counterevidence, limitations, alternative explanations |
| Reproducibility Reviewer | files | method, data, parameters, environment, rerun gaps |
| No-tool Synthesizer | none | `ResearchEvidencePacket` only |

The execution boundary is:

`researcher prose -> filter null/failed results -> no-tool synthesizer ->
deterministic validator -> human semantic gate -> canonical artifact`.

Never make an open-ended researcher responsible for a deeply nested schema. A
successful prose result remains evidence even if a structured-output callback
was not invoked. Agent votes do not verify a claim; source identity,
claim-support checks, and the human semantic gate do.

For substantive reviews, use the optional `research-source-audit/1.0` profile
alongside strict packet v1. It binds current packet IDs/hash and verifier refs
to work/publication versions, actual source level, located quotes and saved
raw/text bytes. Existing source-fetch receipts are replayed when supplied;
native captures remain valid but have weaker provenance. Read
`../../research-hub/references/source-claim-audit.md`. Packet-only passes are
structural; profile passes additionally establish local binding, never semantic
support, publisher authenticity or scientific adequacy. Human review remains.

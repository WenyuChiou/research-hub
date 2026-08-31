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

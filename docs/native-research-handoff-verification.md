# Native research handoff: observable acceptance

## Scope

The host owns research rounds, browsing, citation chaining, source verification,
and evidence reasoning. Research Hub accepts a bibliographic handoff and retains
its metadata through the existing ingest path. It does not introduce a second
research engine, a dedicated deep-search API, or a mandatory paid model run.

The comparison below ran the same synthetic fixtures against master
`929bdd6d963acf4be5bc9d80ce3c5c0a0f77a834` and the changed source. All Zotero
operations used a fixture client; identity verification was explicitly stubbed.
This measures storage behavior, not scientific validity or live-service quality.

| Same case | Baseline | Changed source |
|---|---|---|
| Explicit `ingest --input` flag | Rejected by parser | Accepted |
| Preview changes to canonical files | Log and manifest changed | Zero |
| Two duplicate candidates, distinct source observations | Zero observations retained | Both retained |
| Another research round on the existing note | No source-observation retention | Three total observations retained |
| Comma and quote in follow-up query | Invalid YAML | Valid YAML with both queries |
| Exact replay of that follow-up | Note changed again | Note byte-identical |
| Existing reading status and body | Preserved | Preserved |
| Zotero items across duplicate and repeated runs | One | One |
| Initial Zotero child note contains both observations | No | Yes |
| Traversal filename in preview | Accepted | Rejected before client access |

## Reproduce the comparison

Use a source checkout with the development dependencies installed. Set `HOME`
to an isolated writable test directory if the normal home is read-only. Run:

```sh
PYTHONPATH=.:src python scripts/verify_native_research_handoff.py
```

The script prints JSON and confines synthetic notes to a temporary directory
under `HOME`. To compare another revision, run the same script with that
revision's checkout and source directory first on `PYTHONPATH`. It is a
development fixture script, not an installed-wheel or live-account test.

Regression coverage lives in `tests/test_native_research_handoff.py` and the
existing pipeline/CLI tests. It includes BOM input, explicit missing-file
failure, malformed evidence shapes, block/flow YAML, reading annotations,
preview state preservation, stale output suppression, and path/symlink
containment. Exact replay guarantees note-byte stability; canonical execution
receipts and output timestamps may still record real repeated runs.

## Deliberate limits

- Metadata retention does not turn an agent-provided verification assertion into
  independent evidence. Existing authenticity checks and human semantic gates
  remain required.
- `ResearchEvidencePacket` is a separate claim/evidence contract. Map verified
  bibliographic records to the papers payload; do not pass the packet itself.
- Original scalar provenance is preserved; nested mappings and distinct list
  observations are added. Store differing retrieval observations in
  `source_records` or provenance lists instead of overwriting a scalar.
- Evidence is merged into existing Obsidian notes. Existing Zotero child notes
  are not rewritten; newly created child notes include the current evidence.
- No live Zotero, Obsidian vault, NotebookLM, paid model, deployment, or release
  was used for this comparison.

# Read-only source observation view (local candidate)

## Purpose and scope

- Who: a researcher organizing selected Stage 1 literature in the Hub.
- Current workflow: Library shows `data.summary` or `data.abstract`; separately
  saved `source_records` and generated report text are not explained there.
- Friction: generated summaries and later reading declarations can be mistaken
  for original coverage or cannot be found beside the saved summary.
- Evidence: the existing Library component reads only those two summary fields;
  the source audit item schema has no inline body, observation time or role.
  This candidate has synthetic tests; usability and live imports are unverified.
- Steps removed: inspect declared history beside a selected literature item.
  No reduction in actual import/registration steps is claimed yet.
- New costs: none for old records; existing generated files still require an
  authorized registration/binding seam before their text can be displayed.
- Non-users: sources without observations retain the existing Library view.
- Acceptance: preserve saved prose, coverage, classifications and counts; show
  separate generated drafts only with exact source/file bindings. Missing or
  conflicting identity, receipt, version and time remain explicit unknowns.

## Existing contracts reused

`source_records` is a list of objects retained by `ingest_provenance.py` and the
Workspace extra JSON payload. This view recognizes the existing
`research-source-audit/1.0` observation fields: observation/source/work IDs,
evidence level, status, version/review reference, acquisition reference and text
path/hash. It does not validate the complete packet or turn references into
verified acquisitions. Unknown item shapes remain unknown rows.

`provenance` is retained and its presence disclosed; arbitrary provenance keys
are not interpreted as authoritative summary, classification or reading state.
Saved nonblank `summary`, then `abstract`, remains primary. Generated drafts do
not satisfy the existing saved-summary count/filter or change any record field.

Optional `ObservationTextContext` is a frontend projection input, not a new
server payload or settings source. It accepts existing `Artifact`/`TextPreview`
response shapes. It requires a unique exact project + outer Hub record ID +
observation local source ID + path + SHA reference, and a matching complete
preview with consistent byte/codepoint lengths. Duplicate identities or matches
fail closed. The existing server `read_selected_text` validates the actual bytes
against the registered SHA; the pure frontend projection compares references,
not an independent cryptographic digest or publisher authenticity. It performs
no fetch, file read, write, provider construction or permission expansion.

Historical artifacts are not selected by their `current` flag or report date.
Every observation stays separate; multiple publication versions or missing
version/review references are pending. A raw-byte hash is never treated as a
publication version. Blob references have no `text_path`; this candidate does
not infer a blob ID from a hash to manufacture a missing binding.

After binding, only the existing generated Markdown report format is recognized.
The exact local-ID heading, evidence disclaimer and unique summary/role anchors
must match. Time, later-reading and role fields are **reported claims in that
text**, not new audit-schema properties. Invalid/noncanonical UTC times are
unknown; import/registration dates are never substitutes. Role is a suggestion,
not confirmed category. Text is escaped; links use the existing safe URL control.

## Still missing before real Stage 1 to Hub display

1. An authorized controlled append to an existing actual Hub record ID, preserving
   old fields/observations. There is no such write in this candidate.
2. Registration and explicit source/project ownership for generated report files,
   with a supported path or explicit blob relationship. No files are registered.
3. A scoped caller that loads the existing registered-text preview and supplies
   the optional context. Current production Library receives no such context;
   it can display supplied observation metadata, while report bodies stay unknown.
4. Version decisions and genuine acquisition receipts where required. Generated
   reports remain drafts and cannot stand in for original publisher captures.

No existing research data, database, vault, provider or Ready PR tree is modified.
Synthetic component tests, type checking and build do not establish browser
acceptance, real-account integration or completed import.

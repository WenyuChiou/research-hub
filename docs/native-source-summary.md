# Native source-bound summaries

This explicit authored import is separate from `paper-abstract-draft`. It runs no
model, provider, task, extraction, or semantic audit. The existing four-section,
40,000-byte abstract workflow is unchanged. Researchers still assess support and
acceptance themselves. A matching quote proves exact binding, not entailment.

## Scope and provenance

Select one project and the database ID of one saved source (not its bibliographic
`data.id`). Context reads only 1–8 explicitly selected current evidence artifacts
owned by that source. UTF-8 `.txt` and `.md` files can each be at most 4 MiB;
selected text totals at most 256 KiB. No truncation or library discovery occurs.
A pre-existing explicitly configured workspace BLOB registration is also readable
under its existing, smaller limits. This feature never enables or migrates BLOB
storage or falls back to it when filesystem access fails.

The `reading_scope` is copied exactly from source metadata, or `unknown` if absent.
It is a declared boundary, not verification that the entire paper was read. Hashes
never establish full-paper coverage. No private text enters fixtures or logs.

File reads pin every ancestor and leaf using POSIX no-follow descriptors. Absolute
paths, traversal, backslashes, symlinks and non-regular files are rejected. On
platforms without the required primitives, file access fails closed; this is not a
Windows intake implementation. Import files must be relative to the workspace.

## Operations

`project native-summary-context --root ROOT --project PROJECT --source-record-id DBID --selections '[{"artifact_id":"ARTIFACT","start":0,"end":100}]' --json`

The context contains source title/locator, reading scope, `source_revision`,
`expected_revision`, and exact current `selections`, plus `selected_text` keyed by
artifact ID. `start`/`end` are zero-based half-open Python Unicode code-point
coordinates in the complete file, not UTF-8 byte offsets or JavaScript UTF-16
indices. Returned selected text is only the declared range. All evidence quotes
must lie within those ranges, using the same absolute coordinates.

Build an authored JSON envelope with exactly these top-level fields:

- `schema`: `native-source-summary-v1`
- `project_id`, `source_record_id`, `source`: exact context identities; source has
  exactly `title` and `locator`.
- `reading_scope`, `source_revision`, `expected_revision`, `selections`: copy from
  fresh context. Each selection has `artifact_id`, `sha256`, `text_sha256`, `start`,
  `end`. Full evidence and selected-text hashes are both required.
- `sections`: exactly `why`, `objective`, `methods`, `findings`, `conclusions`,
  `key_points`, `limitations`. Each has 1–12 items with exactly `text`, `status`,
  `reason`, `evidence`. Text and reason are nonempty, at most 12,000 UTF-8 bytes.
  Status is caller-supplied `supported`, `analyst_inference`, or `unknown` and is
  preserved, not automatically upgraded. Evidence is 0–8 objects with exactly
  `artifact_id`, `quote`, `start`, `end`; supported items require evidence. Quotes
  are nonempty exact text, at most 12,000 UTF-8 bytes. Unknown/inference items
  still require reasons and may have no quotes.

`project native-summary-import --root ROOT --project PROJECT --path authored.json --json`

The service operation additionally accepts the strict JSON string as `envelope`
instead of `path`; supply exactly one. Both the authored envelope and the complete saved envelope must fit 256 KiB,
including JSON encoding and saved metadata. Imports that leave insufficient room
for saved markers and timestamp are rejected before changing summary or history. Duplicate keys, unknown fields, NUL, surrogate text, nonfinite JSON
numbers, invalid ownership, stale bytes and quote/offset mismatches are rejected.
Do not submit context-only `selected_text`, `coordinate_frame`, or acceptance
markers as envelope fields. The saved summary adds `saved_at`,
`human_acceptance: pending`, `semantic_support: not_assessed`. This schema records
an explicit authored import, not a provider execution receipt or human approval.

## Revisions, history and reads

`source_revision` hashes the source record excluding only its top-level
`data.native_summary` and `data.native_summary_history`. It therefore binds source
metadata including scope, while selections separately bind owned evidence bytes.
`expected_revision` hashes the complete source record observed by context. It is
the compare-and-save revision, including any existing native summary and history.
Never substitute one revision for the other. Imports recheck evidence and source
inside a `BEGIN IMMEDIATE` transaction. An identical replay can return `reused`
without appending history, but still requires current evidence and source binding.
A different import requires newly observed context. Concurrent updates cannot
silently overwrite each other. Any validation failure rolls back the transaction.

Storage is `source.data.native_summary`; replacement appends the previous saved
object to `native_summary_history`. At 20 history entries, replacement fails rather
than silently discarding history. Malformed existing summary/history is not
silently overwritten. There is no automatic cleanup or acceptance operation.

`project native-summary-read --root ROOT --project PROJECT --source-record-id DBID --json`

The guarded read-only HTTP equivalent is
`GET /api/v1/projects/PROJECT/native-summary?source_record_id=DBID`.
It returns `ok`, `status`, `native_summary` and pending/not-assessed markers.
`status` is `current`, `missing`, or `stale`. Only `current` returns prose; stale,
invalid, inaccessible or mismatched evidence hides it. No HTTP import/edit/accept
route exists. Project snapshots omit native summary prose and history, exposing
only a top-level `native_summary_available: true` presence flag on source records
that have a saved candidate. The flag is not validation or acceptance. The existing
selected-source view uses the flag to request the validated read endpoint without
sending full evidence text to the browser.

Native summary/history are excluded from new generic task packets and their
observed freshness projection, while all other legacy fields remain intact and
ordinary source changes still invalidate tasks. Existing serialized tasks that
already contain these fields fail the common input gate before handoff, execution,
claim, import or revision. Stored packet payloads/hashes are never silently rewritten.

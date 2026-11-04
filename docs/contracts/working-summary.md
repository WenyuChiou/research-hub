# Local working summary

Researchers can already read an exact registered generated draft, but could not
save an edited working summary beside its source. This local slice adds that
explicit action. It does not generate more text or change semantic acceptance.

The detail page offers review/edit for an individually selected, uniquely bound
generated report. Saving stores `data.working_summary`, separate from existing
`summary` and publisher `abstract`. Both originals and `source_records` remain
unchanged. Earlier working summaries are retained in `working_summary_history`.
Sources without a selected generated report retain their existing reader.

## Contract

- GET `/api/v1/projects/{project}/working-summary` accepts exactly one
  `source_record_id` and `artifact_id` query parameter. It returns `context`
  with those IDs, `artifact_sha256`, opaque source `revision`, parsed
  `draft_text`, and nullable `working_summary`. It performs no write.
- POST to the same path accepts those IDs plus `artifact_sha256`,
  `expected_revision`, and edited `text`. No caller path is accepted.
- Existing Origin/CSRF checks apply. Selection checks project/source ownership,
  unique generated observation, path/hash binding and the actual registered
  bytes. A report date or `current` flag never selects a publication version.
- Source compare-and-save uses the existing SQLite `BEGIN IMMEDIATE` transaction.
  Stale edits are rejected. Exact repeats return the existing record without
  appending history. A changed source or artifact prevents reuse.
- Text is nonempty UTF-8, at most 40,000 characters. Unknown or malformed prior
  working-summary metadata is not silently overwritten. Cancel performs no POST.
- A working summary is saved prose, not a publisher abstract, verified science,
  a new reading event, confirmed classification or human acceptance. Those fields
  and the `task decide` human-session gate remain unchanged. No provider is called.

This removes manual copy/re-entry while retaining an explicit selected-draft
review and Save action. New cost is that the researcher chooses and edits the
desired draft; no extra confirmation is required after Save. Unknown write
results need a readback before retry. Synthetic persistence/CAS/component tests
do not establish independent actual-user or real-account acceptance.

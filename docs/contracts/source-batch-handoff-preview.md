# Native source batch preview

## Purpose

- Who: a researcher whose native AI agent already selected literature.
- Current path: the agent can call `project record` per source, or use the separate
  optional bibliographic ingest. Ordinary record writes create new outer IDs.
- Friction/evidence: master had no record preview or exact-key batch plan; a
  repeated ordinary write is not an idempotent native research handoff.
- Steps removed: the agent can inspect one batch plan instead of preparing
  separate per-source CLI previews. The researcher need not author JSON.
- New costs: the agent supplies the selected payload and, optionally, an explicit
  project-bound snapshot. Neither is fetched or verified here.
- Non-users: ordinary record/register and existing native research remain usable.
- Acceptance: synthetic tests exercise create/reuse/conflict and no-access guards.
  This local preview is not persistent import, platform or researcher acceptance.

## Preview CLI

`project record --kind source --data JSON --dry-run` previews one source using
the existing narrow quick-list policy: supplied abstract/abstract-snippet level
and scope must agree. This is local preview policy, not a core source schema.
The pure quick-list mapper retains its earlier restricted metadata contract.

For a batch, add `--batch`; `--data` is an array of existing source data objects:

```sh
research-hub project record --root SELECTED_ROOT --project selected-project --kind source --dry-run --batch --data '[{"batch_id":"native-run","id":"source-1","title":"Synthetic source","locator":"https://example.invalid/source"}]'
```

Optional `--existing-records JSON` is an array of outer source records, each with
nonblank `id`, `kind:"source"`, exact `project_id` and its full `data` object.
The caller must explicitly bind a snapshot to the declared project; a bare
`Workspace.records()` row without project binding is rejected. Missing,
malformed, repeated outer IDs or cross-project snapshots never become empty
snapshots. Duplicate batch/source keys are preserved as explicit conflicts.
`--existing-records` is rejected without `--dry-run --batch` before normal
dispatch. `--batch` requires an explicit `--dry-run` or `--apply` mode.

Generic batch planning preserves every supplied field. It validates core required
source fields plus nonempty `batch_id` and upstream `id`; it does not impose the
quick-list reading policy, promote snippets, fill summaries from relevance,
confirm roles or reinterpret generated summaries as primary captures.

Only exact `(data.batch_id,data.id)` keys match. Complete canonical JSON equality
produces `exact-reuse` with the caller's outer Hub ID. An absent key proposes
`create` with null ID. Changed data, repeated incoming keys or ambiguous snapshot
keys produce `conflict`, retaining incoming data and existing records separately.
Grouped index references bound duplicate-key output rather than copying all
matches per row. Title, URL, timestamp or version heuristics are never used.
No saved field is ignored: extra recorded metadata or manual prose can therefore
cause conservative conflicts instead of an inferred replay match.

Input JSON rejects duplicate keys, nonfinite numbers, invalid Unicode and wrong
shapes. Each supplied array is bounded to 4 MiB and 10,000 entries; these are
processing limits, not literature or scientific sufficiency quotas. Errors use
fixed diagnostics rather than echoing source text.

The root/project and supplied snapshot remain unverified. No lookup, DB, config,
caller-file read, UUID, model, provider, login or destination write occurs.
`persisted`, `execution_authorized` and `atomic_reservation` remain false;
all four destination-write states are `not-performed`. A plan is not current
storage evidence, an atomic reservation or an idempotent apply guarantee.
Version decisions, acquisition receipts, registration and any authorized real
save remain separate existing operations. No core schema or permission changed.

## Explicit selected-project save

The native agent prepares this payload after its own search and selection. The
researcher does not need to write JSON or run Hub before searching. Use this
entry only when Hub is a selected destination; other tools remain optional.

`project record --kind source --batch --apply --data JSON` atomically saves
source metadata to an already existing selected Hub project. `--apply` and
`--dry-run` are mutually exclusive. Apply rejects caller snapshots and reads
the current project records after the existing SQLite `BEGIN IMMEDIATE` lock.
It does not create projects, register text files or call other destinations.

Apply uses a storage projection distinct from the raw preview above. It adds
the same unverified identity default as ordinary `add_record`, reserves
`recorded_at` for the core storage clock, and excludes only a valid existing
core clock from comparison. Every other field must match exactly. Incoming
verification/human-acceptance claims are rejected; missing or malformed legacy
storage clocks remain conflicts. Original `observed_at`, version, reading
history, manual summaries and stored timestamps are never overwritten.

Before inserting anything, apply resolves every exact batch/source key under
one transaction. A conflict rolls the entire batch back. Exact reuse retains
the original Hub ID and stored bytes; only new records receive IDs/timestamps.
Two concurrent batch applies serialize through the existing transaction lock.
If a result is lost after commit, repeat the same batch: current stored records,
not an assumed receipt, determine reuse. Ordinary legacy record writes can still
create ambiguous keys; batch apply reports those conflicts rather than repairing
or overwriting them. This is exact batch replay, not cross-batch bibliographic
deduplication or a cross-provider transaction.

Successful output distinguishes created/reused counts and marks only Hub
metadata committed. Zotero, Obsidian and NotebookLM remain `not-performed`.
Generated report registration/reading, source-version decisions and any authorized
external save remain their existing separate operations. No source body,
scientific validity or actual reading is verified by this metadata save.

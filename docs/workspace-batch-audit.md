# Offline selected-task batch audit

This developer-facing module replaces repeated per-paper integrity scripts with
one deterministic report for **explicitly selected existing abstract tasks**.
It does not generate, import, classify, accept, or transmit research material.
It is not a content comparison or a claim-entailment assessment.

## Pain-point brief

1. **Who:** a researcher coordinating a bounded source ledger and existing Hub
   abstract candidates across isolated local workspaces.
2. **Current workflow:** separate temporary scripts inspect each task, its source
   selection, candidate files, and pending-review state.
3. **Friction:** repeated checks and manual consolidation can omit unavailable
   papers or confuse successful transport with accepted scientific content.
4. **Evidence:** the Stage 1 exercise required separate checks for four tasks;
   the rest of its 20-paper source ledger is not task-ready. This is a local
   workflow observation, not a measured general usability improvement.
5. **Steps removed:** one reusable audit applies the same existing verifier and
   consolidates statuses; explicit unavailable rows preserve the denominator.
6. **New steps/costs:** a source-ledger producer supplies a small explicit JSON
   manifest. No additional account, provider, installation, or permissions are
   required in an existing developer environment. Active SQLite journals require
   a quiescent workspace before auditing; the tool never repairs/checkpoints it.
7. **Non-users:** single-paper users can keep using existing task/working-summary
   interfaces. This module does not replace those interfaces or add UI steps.
8. **Acceptance:** synthetic tests establish repeatable reports, fail-closed
   malformed/stale/scope/quote/path cases, no workspace writes, and honest pending
   review labels. Real selected-task runs establish only current byte bindings;
   independent usability, provider execution, and scientific acceptance remain
   separate, unproven claims.

## Invocation and manifest

From a source checkout:

```sh
PYTHONPATH=src python -m research_hub.workspace.batch_audit manifest.json
PYTHONPATH=src python -m research_hub.workspace.batch_audit manifest.json --format csv --output report.csv
```

The module ships inside the Python package. It is intentionally independent of
workspace service/server startup, which may initialize or migrate a database.
Output defaults to stdout. `--output` creates a **new** file in an existing
parent directory outside every selected workspace, rejecting existing files,
symlinks and traversal. It never overwrites a manifest or report.

The manifest is a UTF-8 JSON object, at most 256,000 bytes, with exactly `version`
(integer 1) and `entries` (1–100 entries). Duplicate JSON keys, duplicate article
IDs, and duplicate root/task pairs are rejected before workspace access.
An existing-task entry has exactly these fields:

```json
{
  "article_id": "B2-07",
  "workspace_root": "/absolute/selected/workspace",
  "project_id": "selected-project",
  "source_record_id": "selected-source",
  "task_id": "00000000000000000000000000000000",
  "expected_source_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "expected_selected_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
}
```

Supply real IDs and independently selected expected hashes; the example zeros
are placeholders. `expected_source_sha256` hashes the full registered source's
bytes; `expected_selected_sha256` hashes the exact selected text encoded UTF-8.
The existing task owns the selected codepoint offsets and candidate identities.
Source/task rows are always queried in the explicitly selected project.

An unavailable source-ledger entry has exactly:

```json
{"article_id":"B2-01","declared_status":"unknown","reason_codes":["source_unavailable"]}
```

`declared_status` is `blocked` or `unknown`; reason codes are 1–10 short tokens.
IDs and reason tokens must start with an ASCII letter or digit and contain only
ASCII letters/digits, underscore, dot, or hyphen (maximum 128 characters).
Placeholders open no workspace and are retained as `unprepared/not_audited`,
with `declared_source_status` and semicolon-separated `reason_codes` preserved.
They are declarations by the manifest producer, not independently verified facts.

## Meaning and boundaries

- `binding_pass`: the existing pending-candidate verifier passed against actual
  source bytes and all five registered candidate files, including exact selected
  text, re-resolved quotes/offsets, input/action hashes, and rendered prose.
- `unprepared`: an explicit unavailable ledger row or a selected task awaiting a
  candidate. No binding pass or scientific conclusion is implied.
- `missing`: a required workspace, database/file, or project-scoped task is absent.
- `blocked`: malformed, changed, unsupported, nonpending, ambiguous or unsafe data
  prevented verification. Fixed diagnostic codes never echo exception text.

`human_review=candidate_pending` is reported only for a verified awaiting-human candidate.
Other task states are conservatively blocked, not treated as accepted.
`scientific_acceptance=not_assessed` and `provider_execution=not_verified` always
apply. `recorded_execution_mode` is the stored `handoff`/`connected` mode, not
proof that a provider ran, succeeded, or incurred zero cost. Quote presence does
not establish entailment, publication identity/version, or full-paper reading.

Exit codes: **0** means every selected row passed binding checks; **1** means a
report was produced but at least one row is unprepared/missing/blocked; **2** means
invalid manifest or unavailable/unsafe report destination. Thus four passed rows
plus sixteen unavailable rows cannot masquerade as complete twenty-paper success.
CSV has one row per entry; JSON also supplies counts. After full verification,
rows include source-bound statement counts, verified candidate file counts,
selected Unicode codepoint counts, and `reading_scope=selected_abstract`. JSON
`verified_totals` sums these numbers only over `binding_pass` rows. Unchecked rows
have null counts, not fabricated zero-count successful results. These are quote
binding counts, not independent facts or semantic validation. Reports contain IDs,
status codes and candidate hashes, not source/candidate prose or filesystem paths.

The tool reads existing SQLite through `mode=ro&immutable=1` with query-only
connections, refusing WAL, SHM and journal files. Nested verifier reads use the
same read-only workspace override; no migrations or database creation occur.
The database hash is checked before/after each entry. Audit only quiescent local
workspaces: this is a point-in-time check, not a transaction/lock over filesystem
files, and it cannot defend against a malicious concurrent process racing path
checks or modifying and restoring bytes. Root ancestors, source paths and
candidate paths reject symlinks/traversal before reading. Source and candidate
limits come from the existing bounded abstract verifier. No broad workspace
scan, network call, repair, automatic acceptance, or write to scanned workspaces
is performed.

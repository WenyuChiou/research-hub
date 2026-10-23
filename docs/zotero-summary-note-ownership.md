# Zotero summary note ownership

The legacy cluster summary writer (`summarize --apply`, the summary MCP tools,
`auto --with-summary`, and chained enrichment summaries) only replaces a child
note explicitly marked with the Zotero tag `research-hub:summary:v1`.
The tag is an application convention, **not authentication or an approval gate**.
These legacy writes remain outside the Workspace proposal/approval boundary
(`workspace/service.py:PROTECTION_SCOPE`).

## What happens to existing notes?

| Child notes found across all pages | Summary action |
| --- | --- |
| No notes (attachments may exist) | Create one tagged Hub summary note. |
| Only unmarked notes | Preserve every existing note; create one tagged summary and report a warning. |
| Exactly one tagged summary, plus any unmarked notes | Update only the tagged note, preserving other notes and its existing tags/metadata. |
| Multiple tagged summaries, unknown marker version, malformed ownership metadata, or missing/mismatched identity/version | Refuse the write; require review rather than choosing a note. |
| Update version conflict | Do not retry or create a replacement; report the conflict and attempt local Obsidian rollback. |
| Create response lost or missing confirmation | Report **outcome unknown**, attempt local rollback, and do not retry automatically. A remote note may already exist. |

Older Hub notes have no marker and are **not automatically adopted**, even if
named “Summary” or shaped like generated HTML. The first new summary may leave
an old summary alongside it; this is reported as a possible legacy duplicate,
not silently removed or overwritten. No migration or deletion is performed.
Normal reruns find the new tagged note instead of creating another one.

Keep personal annotations in separate unmarked notes. A tagged summary is a
replaceable generated note: its entire HTML is updated, so manual edits or
additional sections **inside that tagged note are not protected**. Do not apply
the ownership tag to a personal note. Removing it relinquishes automatic update
ownership; a later run may create another tagged summary with a warning.

## Results and reconciliation

Successful preserve-and-create writes stay in `applied`, not `errors` or
`skipped`. `SummaryApplyResult` adds `warnings` only when nonempty; all existing
fields and defaults remain. CLI output prints warnings, MCP/JSON include them,
and auto/enrichment surface them in their existing logs. Write counters count
**confirmed** writes; zero confirmed Zotero writes is not proof of no remote
change after an unknown response. Enrichment's return values describe metadata
enrichment; its chained summary warnings/errors are reported separately.

After an unknown response, inspect the paper's Zotero children before retrying:
look for the tagged Hub summary, compare its content, and resolve any ambiguity.
Do not delete or tag legacy/personal notes merely to make a retry succeed.
Repeated entries for the same Zotero parent in one payload are skipped so they
cannot act as automatic retries, including different slugs for the same parent.

## Limits

- A process-local lock covers summary child pagination, selection, and the
  Zotero write because the shared pyzotero client keeps mutable pagination state.
  It does not change Obsidian worker parallelism or lock other applications.
- Existing note updates retain the read version for pyzotero's
  `If-Unmodified-Since-Version` check. This protects against an intervening edit
  to that note, not edits already present when it is read.
- Another process or external user can create a note between the read and
  create. This change does not provide a distributed lock, atomic cross-system
  transaction, durable idempotency ledger, or recovery automation.
- Local rollback is best effort; it is not a guarantee against concurrent local
  edits or process failure. Auto's separate local summary layer may still run.
- These guarantees are covered with synthetic clients and offline tests.
  A real Zotero/desktop acceptance run is separate and has not been performed.

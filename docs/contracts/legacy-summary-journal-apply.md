# Private legacy-summary apply integration (schema2)

The actual `summarize.apply_summaries` per-paper writer now reserves logical
local/Zotero targets and stages exact candidate/recovery bytes in the private
journal before destination I/O. CLI summarize/resummarize, MCP summary apply,
and auto/enrichment callers share that seam. Existing result fields/counters
remain; optional versioned `receipts` add operation identity, sink states,
observations and scope/hash bindings. CLI text prints compact receipt lines.
No new provider API, credential, token override, provider lookup command or UI.

## Boundaries
- `summarize_cluster` already generates model output BEFORE `apply_summaries`.
  This integration does NOT reserve before model generation or prevent model
  regeneration on retry. MCP out-of-band payloads also arrive already generated.
- Source hashes bind the extracted abstract reread at apply time, not proof of
  the exact model-input revision or PDF/fulltext coverage. Receipts label this
  limitation. Original source-to-generation revision checking is a separate gate.
- Original authorization provenance is retained across identical CLI/MCP retry;
  it is an explicit legacy invocation, not authenticated human identity,
  scientific acceptance or Workspace local-human approval.
- Same candidate+scope gives the same operation identity. Confirmed replay
  returns the historical receipt without another destination write; this is
  not a fresh verification of current remote/local content. Changed candidate
  cannot bypass an unresolved logical target claim.
- Neither-enabled-sink calls keep legacy no-write behavior and create no journal.
  Local-only calls need no provider/client. Unknown/mismatched remote library
  identity refuses BEFORE local or remote destination writes.

## Crash and outcome contract
Dispatch tokens are returned only after SQLite claim commit. Remote ownership
reads occur before the callback that claims remote dispatch; callback failure
prevents the adapter write. Errors after dispatch stay unknown absent a positive
acknowledgement; no automatic resend or create fallback. A positive provider
return followed by receipt-write failure is reconciliation-required, not proof
that the provider failed. Local already-written data is not falsely rolled back
merely because a positive receipt could not be saved.

After unconfirmed remote response, local compensation is attempted with the
existing unchanged-byte guard. Effective local states are `compensated` when
restored, `conflicted` when newer content is preserved, or `unknown` when
compensation is unavailable. A separate historical `write_acknowledged` fact
remains. A later remote acknowledgement cannot turn a compensated/conflicted
local sink into a satisfied aggregate or release its claim. A late original local
write acknowledgement also cannot erase newer compensation uncertainty. No user-resolution
or retry-after-compensation API is introduced in this slice.

A reserved but never-staged operation can stage/retry under unchanged scope;
unknown/dispatched operations cannot. Oversized candidate/snapshot rejects
without destination writes or truncation. Apply-only lookup serializes first-use
schema initialization with writers; public get/list still never initialize.
Exact-target conflicts return the original recorded receipt instead of silently
allocating an escape key. If the old receipt cannot be read, fallback output
retains original blocking identities and possible prior dispatch, never a new
unrecorded identity or false not-dispatched proof. Reconciliation observations never prove not-delivery.

## Schema and safety
Schema2 adds effective compensation states. Schema1 foundation files are refused
without migration, reset or evidence deletion. This is an unreleased private
contract change, not a public backwards-compatible release. Original schema1
source/evidence remains frozen. No Workspace DB or historical profile assets
change. No automatic expiry/pruning, no provider token guarantee, no protection
against old binaries/external writers or malicious concurrent path replacement.

Synthetic tests use fake generation/provider seams or in-process HTTP mock
transport, never real Zotero/model calls. Previous installed stdio proof is not
reused as proof this changed consumer passed a new transport run. Remaining
gates include complete consumer compatibility, installed-wheel checks, adapter
semantics, source-generation provenance and user-facing recovery resolution.

When receipt history is unavailable, `dispatch_may_have_started=true` is conservative across prior invocations; `current_attempt_dispatched` reports only this invocation. No current dispatch is not proof that the retained operation was never dispatched. The error remains reconciliation-required.

Selected raw-directory ancestors may have an OS-canonical spelling different
from their configured spelling (for example a temporary-directory alias).
Apply derives the note's relative path only from that explicitly selected root
or its canonical spelling, then runs the existing strict descendant checks.
Leaf/intermediate links, traversal, unselected siblings and a linked/reparse raw
root remain rejected. Returned canonical paths bind journal source/target
identity, so changing an approved ancestor spelling does not create a replay key.
This guard is at apply: it does not claim to guard legacy inventory's earlier
source reads or eliminate concurrent filesystem replacement races.

Windows journal containment validation uses the same extended drive/UNC namespace
for the approved root and fixed database/sidecar paths before the existing strict
path checks. SQLite I/O paths do not change. This avoids a namespace-only mismatch
when a volatile sidecar disappears during CPython's resolve/prefix checks; it does
not ignore or retry an escape. Traversal, unsupported device namespaces and
linked/reparse descendants remain refused. The modeled resolver race is not proof
of any one native CI failure's causal target; native verification remains required.

The final journal metadata observation uses `lstat` once, rejecting a leaf
symlink/reparse point or non-single-link/non-regular file even if it replaces a
previously checked leaf. A `FileNotFoundError` only at this final observation
means absence, which was already permitted for SQLite's transient sidecars and
an uninitialized database. Existing `_db` missing-database/read versus explicit
initialization semantics remain unchanged. Containment-check failures and other
I/O errors are not suppressed or retried. This closes an independently modeled
sidecar disappearance window, not all concurrent path replacement races; a
specific native CI failure cannot be attributed to it without diagnostics.

For the fixed `-journal`, `-wal`, and `-shm` sidecar names, containment checks
now resolve their parent only, followed by the single non-following leaf
observation above. This avoids a second leaf exists/lstat race inside the generic
path resolver. The persistent database retains full-path containment validation.
Parent validation errors still fail closed. Link-count zero remains unknown and
rejected, not evidence of an ordinary single-link file. Rejection diagnostics
include only numeric file type, link count, and Windows attributes, not file
contents or additional private paths. CPython Windows directory-metadata fallback
can report an unavailable link count when another handle is open; that separate
boundary is not repaired here. No retry, delivery confirmation or resend is added.

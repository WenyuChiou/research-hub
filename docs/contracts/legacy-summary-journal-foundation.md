# Historical foundation boundary

The original schema1 foundation was unwired at e1267fd. This candidate extends it with schema2 and actual apply integration; see [current apply contract](legacy-summary-journal-apply.md). The text below records the original foundation scope, not current wiring status.

# Legacy summary journal foundation (private, not wired)

`summary_journal.SummaryJournal` is a local SQLite foundation only. No CLI,
MCP, HTTP, auto, enrichment, summary writer, provider lookup, token management,
model or UI calls it. Existing legacy writes do not gain its protection yet.
No Workspace DB migration, synthetic project, human approval or source-profile
change is performed. Applying this patch alone is not restart-safe provider
integration.

An explicitly authorized caller reserves a caller-owned operation ID, selected
source binding and stable logical sink targets before generation. The target
key must identify the actual local note or remote library+parent+summary role,
not mutable HTML, current note version, or a newly discovered note ID. This
foundation validates structure and conflicts; it cannot prove those supplied
identities match a real provider. No automatic fresh-ID allocation exists.
Same-ID reuse with changed scope is rejected; same-target unresolved new intent
is rejected. Distinct targets can proceed. A completed same-ID request returns
its receipt, never dispatches again.

Stage immutable exact UTF-8 candidate and local before/after snapshots. Defaults
are100000candidate bytes,2000000bytes per snapshot,8192bytes per metadata record.
These follow existing response/prose/snapshot conventions but are explicitly
byte-based protective ceilings, not truncation. Overlimit inputs fail before
stage changes; metadata overlimit fails before reserve initializes a journal.
Full-note snapshots support future guarded compensation but are not source
acceptance or a reason to invalidate unchanged selected-source authorization.
No automatic compensation or destination writes occur here.

Dispatch returns a unique sink attempt token only after its SQLite claim
commits. A lost reply/crash leaves dispatching/unknown; recover only marks
unknown, never retries. Read-only observations (including not_observed or matching
content) cannot confirm a write or clear claims. `acknowledge` is an unexposed
trusted-adapter seam for a positive bound response or proven rejection, not a
human/API input or provider proof verifier. Tokens bind attempts, not identities.
It records `caller_reported_adapter_ack`; fake adapter assertions in tests are
not real remote acceptance. Adapter admission/evidence is still to be reviewed.
Late acknowledgements affect only their original operation+sink+token; they do
not rewrite newer operation metadata. Claims release only when every requested
sink is confirmed/rejected; receipts/materials remain. There is no unknown
resend, observed-state user resolution, cancellation, pruning or expiry API yet.

Read/list do not initialize absent storage. Explicit reserve initializes only
this journal schema, transactionally; unsupported/corrupt schema fails closed,
never resets. Checked path links/hardlinks and known SQLite sidecars are rejected;
this is not race-proof confinement against a concurrent malicious filesystem
writer. SQLite FULL commit cannot guarantee survival of every device failure.
Old Hub binaries/other provider clients do not consult this journal; downgrade
and cross-process external-write prevention are not claimed. Two upgraded local
journal writers serialize claims via BEGIN IMMEDIATE and target uniqueness.

Invocation authorization provenance accepts only legacy CLI/MCP/parent apply
kinds and exact scope digest. It is not authenticated human or Workspace proof.
Future wiring must derive those fields from the actual configured scope and
existing explicit invocation, not trust arbitrary network inputs. No schema
field contains credentials, raw provider errors or auto-generated approval.

Tests use synthetic bytes and SQLite fault injection only. Further reviewed
work is required for all actual apply consumer wiring, safe adapter evidence,
source/target derivation, recovery UX, installed transport and real-provider
acceptance. Historical profile hashes remain unchanged.

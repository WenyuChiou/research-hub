# Abstract Prepare reconciliation UI

## User task and scope

A researcher selects an already registered cited source, opens one registered
text artifact, selects the abstract passage, and explicitly prepares its
restricted abstract-draft task. A lost reply must not require copying IDs,
reconstructing JSON, guessing saved tasks, or blindly creating a new task.
This subpath adds no PDF reader, import, automatic Run, or generic write replay.

Previously, an uncertain reply locked the live composer and offered Review,
but reload lost its correlation. With compatible backend capability version 1,
the UI saves opaque identity before POST and asks for exactly that saved task.
Normal successful Prepare still targets the task's existing Review card.
Neither this flow nor mocked tests prove reduced effort or human acceptance.

## Actual API contract

The UI consumes Workspace.capabilities.prepare_reconciliation (version and
canonical UUIDv4 workspace_instance_id). Only paper-abstract-draft adds
prepare_request={version:1,workspace_instance_id,key} to its normal task POST.
Other operations and incompatible/capability-missing servers remain keyless;
the composer explains the absence of durable recovery support.

GET /projects/{project_id}/preparations/{key} carries the namespace in
X-Workspace-Instance and reuses same-origin credentials and bounded reads.
Its response must match the key and return either not_observed without a task,
or found with an abstract task belonging to the selected project. No title/time
heuristic is used. GET is read-only and does not execute the task.

The reviewed backend atomically stores task and project/request-key binding.
Same-key/same-payload POST returns the same task; different payload conflicts.
This key does not authorize Run. Existing unknown-Run guards are unchanged.

## Identity and uncertainty

- Stored value contains only version, namespace, project ID, UUID key, and pending;
  its storage key additionally scopes origin including port. No source text,
  instructions, selection/payload, credentials, or file paths are stored.
- Identity is saved before POST. If storage fails, nothing is sent until explicit
  in-session-only confirmation, with reload limits shown first. A known-unsent
  request can instead be cancelled.
- One exact GET follows an uncertain POST. not_observed, read failure, and generic
  ledger failure remain unknown, retain identity, and block a new abstract request
  in this live project controller. No automatic POST or Run follows.
- Explicit retry uses only the original live payload and same key. Reload/project
  return cannot reconstruct payloads and offers read-only checking, not replay.
  Conflict/mismatched namespace cannot retry or silently fall back.
- Definite pre-commit source-validation rejection retires the request and exposes
  its error. Generic HTTP400 is not proof of no commit.
- Entry/reload automatically checks at most three identities sequentially; other
  checks are explicit. Refresh does not restart recovery. StrictMode's effect
  probe does not duplicate automatic lookup.
- Confirmed correlation retains the task even if detail refresh fails. Stored
  identity is removed only after the exact task appears in the authoritative
  selected-project task state. The exact scoped GET/POST task is inserted only if
  absent; existing/newer task entries are not overwritten. A failed bulk refresh
  leaves the project overview visibly stale but does not discard this known task
  or require another fetch before opening its Review card. Immediate insertion
  uses a distinct immutable baseline so a successful bulk refresh still applies,
  while genuinely newer snapshots remain untouched. Identity cleanup/dismissal
  waits for the scoped callback to settle; a replacement workspace namespace
  invalidates the old cached view without cross-namespace task insertion. Refresh failure never
  re-enables its POST.

Storage is best-effort, not a durable server-side session ledger. Clearing browser
storage loses automatic recovery. This controller does not coordinate leases
across browser tabs, delete unknown server requests, or prove an absent mapping
will never be committed.

## Navigation/data boundaries

The project controller outlives the composer, so cancel/back retains uncertainty.
Project/workspace switches fence late responses; cancellation fences transports
ignoring abort. A late Prepare/lookup does not override newer page navigation.
Reload displays an explicit exact-task Open button, not automatic navigation.
Existing task focus and missing-task handling remain authoritative.

Only the chosen artifact's existing preview supplies source text. Recovery GET
uses the API's existing stored task; it does not scan private files or build
project-wide model payloads. Confirmed saves preserve existing selected-project
metadata/state refresh. No provider probe, model call, auto-acceptance, or external
delivery claim is added.

## Verification boundary

Public synthetic mocked-request tests run sequentially with one worker. Red
baseline showed missing lost-reply and reload correlation. Regressions cover
scoped metadata, exact/bounded lookup, retained-payload retry, denied storage,
unknown outcomes, navigation, legacy fallback, and no autoRun. Web/static build
is distinct from wheel inclusion, real browser testing, and human acceptance.
No new browser/provider/wheel/human acceptance result is claimed here.

# Existing-text abstract draft UI (VM candidate)

Base backend candidate: `fe82f9352112fda1e41a9006ff72c1be84a567c2`.
This is a new narrow subpath in the existing `/app/` Literature and Review pages,
not a PDF reader, new application, or replacement for the canonical research plan.
No publication or real model execution is established by synthetic tests.

## Source-backed task brief

- **Who/when:** a researcher with a cited-source record and an existing registered
  evidence text file, who wants a bounded abstract-only draft and source-aware
  human review without copying identifiers, JSON, or terminal commands.
- **Existing data:** source records have title/locator (optionally DOI); existing
  source search stores metadata, not full text. Evidence registrations have
  path/role/hash. There is no verified source-to-file association. Ordinary
  Workspace UI has no persisted abstract field or file-upload/PDF-reader path.
- **Baseline friction:** the frozen backend profile is not usable through the old
  TaskComposer. Generic prose import is incompatible with its required structured
  response. The old artifact panel registers files but does not show their text.
- **Small added contract:** read one explicitly selected registered evidence
  `.md`/`.txt` through a bounded read-only endpoint; reuse the same strict reader
  used during task preparation. No arbitrary path/URL input, ambient scanning,
  background provider probe or automatic external transmission.
- **New path:** Literature source → choose existing evidence file by relative
  path → read text → select passage → Prepare → inspect source/task → explicit
  Run when available → inspect returned candidate beside saved passage → human
  decision → existing eligible local ZIP path. Source return and Cancel keep
  the original project/source; they do not invent a saved reading position.
- **Declaration and costs:** Prepare declares the selected record/file/passage
  association and abstract scope. Identity/version remain unverified/unknown;
  no redundant checkbox or modal is added. Prepare does not call a model. Run
  transmits selected text, task instructions and packaged instruction material;
  token use, cost and model-context fit remain unknown.
- **Non-users/fallback:** metadata-only/PDF-only projects retain source links and
  ordinary record management. No pretend PDF reading, required new abstract file,
  or forced JSON/CLI workaround. Unavailable/unknown connected runner disables
  this profile's Run. Existing other operations retain their import forms.
- **Acceptance:** complete source-selection/preparation/return in mocked DOM,
  precise original-codepoint offsets, no hidden requests or model call, stale
  preview discarded on selection/unmount, source-aware candidate display, and
  independent backend/source review. This enables a previously missing subpath;
  it does not prove fewer clicks, better academic summaries or human usability.

## Read-only preview contract

`GET /api/v1/projects/{project_id}/artifacts/{artifact_id}/text`

The path contains registered identifiers selected by UI state, never a supplied
filesystem path or URL. Existing Host/Origin/Sec-Fetch-Site checks and no-store
headers apply. Response: `{ok:true, preview:{artifact_id,path,sha256,text,
codepoint_length,bytes_read,truncated:false}}`. Path is relative to the workspace.

Reader checks the project-qualified registration, evidence role, supersession,
non-linked safe path, `.md`/`.txt`, <=40,000 original bytes, registered SHA and
strict UTF-8 before returning text. Failure exposes no text or absolute root.
Unrelated artifacts and records are not read. Preview is not permission to run,
publication identity verification, or assurance that the file remains unchanged.
Preparation and execution recheck original inputs using the shared reader.

## Original text and browser selection

Returned text and its hash are never newline-normalized. Only textarea display
uses the browser's CRLF/CR→LF normalization. `originalRange` maps displayed
UTF-16 boundary positions back to original Python Unicode-codepoint indices,
including non-BMP characters, combining characters and original CRLF spans.
Mid-surrogate, empty and out-of-bounds selections are rejected, not shifted.
The payload uses original offsets; the selected source pack is stored by the
backend. Explicit display normalization also prevents React from resetting the
selection on rerender when the browser's textarea value differs from raw CRLF.

## Review, return and compatibility boundaries

The Task response already contains the exact selected `source_pack` and returned
`result.prose`; review renders these as untrusted text with existing safe links.
No arbitrary candidate-file serving endpoint is added. Quote binding is not
entailment; manual review and existing acceptance/freshness gates remain distinct.
The generic prose import and handoff controls are hidden only for this restricted
profile because they cannot return its structured result through this UI. Existing
handoff-profile tasks display this limitation instead of pretending to run.

Navigation reuses the optional project-bound focus-target contract from the
unpublished Returning Work candidate `3298f530`, extended to Literature/source
targets. That whole Overview feature is not stacked here. Integration with that
candidate and PR192 freshness/generated assets must be reviewed together before
publication. Frozen source candidates are unchanged.

## Unverified and intentionally excluded

No provider/model invocation, full skill CLI stage, retrieval, PDF extraction,
external destination write, private vault, new credentials or user-PC operation.
Browser/native selection/layout/zoom/history and Windows remain unverified due
to the known VM browser restriction; DOM tests are not browser acceptance.
Real model output fidelity, semantic audit and researcher acceptance remain gates.
Existing filesystem TOCTOU and host-runtime limitations are not newly solved.

## Uncertain responses and interrupted navigation

A failed preview GET is a read failure, not a model or save failure. Preparation
and Run POSTs are never automatically retried. Network/server/unreadable
preparation responses leave creation uncertain, lock repeat submission and keep
selected input. The user can open existing Review and Refresh; no unknown task
ID is fabricated or automatically matched. A known saved task ID opens that task
rather than creating another. Leaving during preparation does not cancel its
server-side save, which is stated while the request is in flight.

A Run reply of unknown outcome preserves the known task/source and locks Run
until the existing refresh mechanism observes recorded post-claim, review,
blocked or terminal state. A new JavaScript object with unchanged ready or
awaiting-agent state does not unlock it or prove that the request never started.
No execution receipt is invented; refresh never triggers a model call itself.
Backend `TaskService.claim` checks eligibility under a write transaction and
commits running plus an execution ID before `launch` dispatches the worker, so
concurrent same-task claims cannot both dispatch. This is not a durable HTTP
response/idempotency receipt or proof about every interrupted request. The UI
keeps unknown preparable state locked rather than treating Refresh as a negative
execution receipt; existing process recovery and the backend state gate remain
the authority. Newer source/project navigation prevents a
late preview or post-save refresh from redirecting the user to old context.
Page navigation is fenced separately by hash generation and the current hash,
because a page hidden by the existing UI remains mounted. Late preparation keeps
the known saved task for an explicit return instead of overriding a newer page.
This is narrow in-memory recovery, not a new durable execution ledger.

Confirmed saves retain the application's existing authoritative refresh contract:
workspace capability/state and selected-project snapshot GETs refresh ordinary UI
state. This is distinct from the new explicit selected-file text reader and from
model input: no project-wide preview fetch or new background provider probe is
introduced, and unrelated project records/files do not enter this draft payload.

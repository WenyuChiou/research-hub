# Existing-text intake UI

## User task and evidence

A researcher with an existing abstract or short text/Markdown excerpt can add it
from the Literature/source-list view, without external accounts. Previously the
UI required separate source metadata, external file staging, a typed workspace
path/role, and manual source-to-artifact matching. The backend57f6509 now owns
safe bounded publication and exact pair identity. This UI consumes that contract;
it is not a PDF reader, literature fetcher, integration login, or new skills app.

The form offers paste or existing .txt/.md file, a required title, optional
locator, and declared abstract/unknown coverage (unknown by default). Save makes
one Hub-owned local evidence copy with its linked source. The original file is
not changed. The saved linked artifact and server preview go directly into the
existing abstract reader: no ID/path entry or duplicate file choice/read.
An explicit passage selection (or explicit Select entire text as abstract)
remains required before Prepare; Run remains a separate existing decision.
Import does not mark the publication identity verified or the source reviewed.

The removed external staging/matching work is a source-backed design target,
not a measured human-usability improvement. Metadata-only source entry and
advanced existing-artifact registration remain available for non-users.

## Exact bytes and safe presentation

File mode checks extension and 1–40,000 raw bytes, reads an ArrayBuffer, and uses
fatal UTF-8 decoding with BOM preservation for preview. It sends canonical base64
of those original bytes; no textarea serialization, replacement-character decode,
line-ending normalization, or truncation is applied. Paste is honestly new text
from the field, checked for unpaired surrogates before UTF-8 encoding. Title and
locator also reject invalid Unicode and exceedance of2,000 Unicode characters.
Empty/whitespace/NUL input is rejected before saving.

File names remain only in live browser state for display, never in the payload or
pending storage. Markup, Markdown images, instructions, titles and locators are
inert React text; locators are never fetched. Missing publication locator is
labeled saved local text, not shown as a scholarly URL. Existing safe link rules
remain for user-provided http/https metadata. No source body is added to general
project record metadata or project-wide model context.

## Capability and recovery

The UI requires text_intake.version1, available status, valid workspace UUID,
max_source_bytes40000, and txt/md support. Unsupported/missing capabilities leave
Add existing text disabled with an explanation; ordinary metadata workflows
continue. This backend currently does NOT implement Windows publication, and
this UI does not claim otherwise.

POST /projects/{project}/source-text carries intake_request and the exact title,
locator, scope, mode, format and base64. GET /projects/{project}/source-text/{key}
uses X-Workspace-Instance. The UI validates key/version, source kind, linked
artifact/project/origin/hash, and the returned preview's matching identity,
byte/codepoint lengths and current/stale/unavailable status before exposing it.
A stale/unavailable saved copy keeps its pair; no text is reconstructed or fixed.

The intake controller is distinct from Prepare. Pending browser storage contains
only schema, workspace UUID, project ID, request UUID and pending state, under an
origin/workspace/project/intake-specific prefix. No title, locator, filename,
text, payload, source hash, private path or credential is stored there.

Identity is persisted before POST. Storage denial sends nothing until explicit
in-session-only confirmation; known-unsent work can be cancelled. Unknown POST
outcome causes one exact GET, never automatic POST/Prepare/Run. not_observed
remains unknown: a request can still finish or leave an unregistered orphan.
Only an explicit same-key retry with the exact retained live payload is offered;
reload cannot reconstruct it. Initial recovery checks at most three keys and
does not loop on normal refresh or StrictMode probes. Conflicts never silently
fall back to a new key. Generic storage/ledger errors do not prove noncommit.

## Saved-state and navigation authority

A valid saved pair is inserted immediately into the matching project's cached
state so explicit Open saved text works during a hung/failed bulk refresh.
The inherited guarded cache path preserves existing/newer entries and distinguishes
its own insertion baseline from a newer project response. Failed bulk refresh
keeps overview staleness separate from the known saved pair. Namespace/project
changes fence late responses; scope settlement precedes pending-key cleanup.

Cancel, source switches and newer page/hash navigation do not authorize a late
save to reopen another source or hijack navigation. Recovery remains visible
with explicit Open saved text. Exact-source restoration occurs only on explicit
user intent, not ordinary rerender; pending Prepare uncertainty remains locked.

## Proof boundary

Tests use public synthetic UTF-8/markup fixtures and mocked same-origin requests,
with sequential one-worker Vitest. Red baseline precedes implementation. File
byte fidelity, explicit codepoint selection, interrupted saves, exact recovery,
storage denial, unsupported platform, linkage and newer-navigation guards are
regression targets. Typecheck/static build do not prove wheel inclusion, native
Windows support, a real browser flow, or human task acceptance. Those stages are
separately reported, never borrowed from previous frozen candidates.

# Saved screening: recognize and return to the source

A saved include/exclude decision keeps its source ID and rationale. In the
Literature page, its heading now uses the title of the exact matching source
record in the currently selected project's detail. The ID remains secondary.
Duplicate titles are not identity; no URL/title deduplication or cross-project
lookup is performed. An unavailable/deleted source has an explicit fallback and
no return button. The decision and rationale are not discarded.

Declared coverage is the saved source's declaration, not an attestation of human
reading, AI input coverage, or scientific acceptance. Only the supported abstract
declaration is shown as such; absent/unrecognized declarations stay unknown.
The title and scope are a current saved-record projection, not a new immutable
historical snapshot of the classification event.

The standard keyboard-operable return button uses existing Literature navigation
to focus that exact source record, without fetching content, opening an external
site, starting Prepare/Run or writing a record. Existing project/newer-navigation
focus guards remain unchanged. Source contents remain inert UI text.

Before: read opaque screening ID and manually locate its source. Intended after:
recognize title/scope and return in one action. This removes an ID-matching task;
no measured end-user timing or full-workflow usability improvement is claimed.
No additional setup or integrations are required; the existing classification
form and backend authorization are unchanged.

Verification is synthetic DOM/component testing and build consistency. No local
browser retry, live-provider operation, native zoom, screen-reader or human
acceptance is implied. Hosted pixels remain a separate gate for this UI slice.

## Draft navigation and session safety

The source-return button does not change an open composer. Explicitly opening a
second source, returning to the first source, or switching projects no longer
silently discards the first composer's unsent purpose, selected passage or
Prepare safety lock. The App owns a session-only registry, addressed by exact
workspace instance, project ID and source ID, not by title, URL or artifact label.
Compatible advertised workspace identities must agree; malformed/unknown-version
identities are fail-closed. A legacy backend without an instance identity is
limited to the current App session; returning from an advertised namespace cannot
reuse an earlier legacy alias. This cannot identify an out-of-band replacement of
a legacy server which advertises no identity.

Each update is synchronous; the sending lock is stored before Prepare dispatch.
A completion after unmount settles only its original entry and operation token,
never a newer source's input or navigation. A shared navigation-intent epoch also
fences same-page source returns and explicit same-source reopens, not just hash
changes. A keyless lost reply remains locked
on return. Existing durable preparation recovery remains authoritative for keyed
requests. The recovery controller reports the exact key before dispatch and
settles known results into the registry before awaiting bulk refresh, including
when the original composer is hidden. A retained key remains locked even if its
recovery entry is temporarily absent. Only a positively identified validation
rejection or explicit cancellation of a never-dispatched unsent entry can retire
that key; disappearance from a list is not proof. No POST, Run, automatic retry, new request key, source acceptance or
provider authorization is caused by restoration. A late keyless known task may
require the existing Review/Refresh controls to load its card; an unmounted
composer does not start a stale project refresh.

Artifact identity/hash/reference and currentness are rechecked against the
selected project's detail. Stale or unavailable text/ranges are invalidated;
that invalidation **does not clear** sending, uncertain or known-task locks.
These are separate axes. Reopening an unchanged draft does not silently reread
or reset its selected range. Only the existing explicit separate-intent action
can reset a parked keyed draft. No such reset is offered for keyless uncertainty.

Private draft text is held only in memory, not localStorage or another durable
store. Reload/closing the App loses unsent text and keyless session-only state;
this is not a new recovery guarantee. Existing opaque durable identities are
unchanged. At most 32 entries are retained, with the existing 40,000 UTF-8-byte
preview and 20,000-character purpose limits. There is no automatic eviction of
pending, uncertain or known-task entries. At capacity, opening another draft is
blocked visibly. An explicit “Discard this unsent draft” action releases only
an unlocked, keyless unsent entry; closing/Cancel merely hides and retains it.

Regression evidence includes full-App source/project roundtrips with duplicate
source IDs in different projects, keyless lost replies, durable recovery, late
completion after unmount, operation-token rejection, stale-input invalidation,
StrictMode restoration, and bounded capacity. These remain synthetic DOM tests,
not hosted pixels, browser history usability, native provider acceptance or
proof that an unknown remote write was cancelled.

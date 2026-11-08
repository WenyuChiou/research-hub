# Native Stage1 saved-result view

This is a read-only consumer of research-discovery-observations/1.0. It is not a search engine, an authenticated execution verifier, a semantic reviewer, a live scheduler, or Stage2.

Native agents own observation export/cross-link work. A confirmed save returns an origin-relative view_path. The agent combines that only with an already verified server origin. The user should not author JSON or repeat literature entry. Missing project/local-write scope is a necessary choice, not inferred authorization.

GET /api/v1/projects/{project}/artifacts/{artifact}/discovery uses the existing trusted-origin gate and exact registered project/artifact lookup. The registered snapshot bytes must still match. Selected receipt/source bytes are rechecked with existing bounded pinned reads. A readable snapshot with missing/stale referenced bytes returns ok:true only for successful projection; report.binding is not-current and individual binding statuses remain unknown/stale. This must never be described as research completion.

Whitelist projection omits receipt references, material paths and capture contents. Source locators use the existing safe-link policy; source titles/queries are rendered as text. IDs are exact, never joined by title/DOI. Original source-byte absence, declared reading, human review and execution verification are distinct.

Hash links select exact project/artifact; invalid links do not guess a result. Pending reads are cancelled/fenced on route/project changes. Ordinary page links remain compatible. Setup guidance neither changes the evidence selection nor initiates an API/configuration write. Lists initially render 50 items each and explicitly offer more; displayed entries are not a completeness claim.

Platform limit: saved-file reads/writes still require existing POSIX pinned-directory primitives. The codebase has no equivalent verified Windows handle-relative discovery read/publication helper. Existing Windows journal path normalization is not an equivalent ancestry-pinning primitive, and private source-text BLOB storage is not a generic discovery-artifact store. Do not reuse either as an unsafe shortcut. A separately reviewed Windows implementation needs native handle identity/reparse protections and fault tests (or a separately designed bounded transactional artifact storage contract); no fallback is implemented here.

Evidence levels must be reported separately: synthetic service/DOM tests, hosted browser acceptance if actually executed, native research trial, and host/platform/provider acceptance. Native cloud research is not Codex/Claude Code cross-host proof. README user examples require actual corresponding use, not this contract alone.

## Read-only need observations

Each need labels its status as supplied, as does the overall completion record.
An optional disclosure joins the existing attempt and source `need_ids` by exact
ID. Counts are recorded observations, not independent sources, executed searches,
relevance, source reliability, or scientific coverage. Per-need lists use the
same visible limit and show displayed/recorded counts; the existing Show more
control expands them together with the other lists.

Failed, partial, unknown and unobserved attempts remain inspectable. An earlier
failure can coexist with sufficient alternative evidence; it does not override
the author's completion decision. An observed empty result remains zero while
unknown counts remain unknown. Missing linked records do not prove that no
search happened or that no relevant literature exists. Version and reading
declarations stay unchanged.

The v1 format has no attempt-to-family relationship. Its declared search
families therefore have unknown individual linkage in this view; query text,
titles, IDs and ordering are not used to invent one. No schema, validator,
saved record, scientific decision, search invocation or destination write is
changed by opening the disclosure.

The current service requires `need_ids` for both attempts and sources: the
schema checks the array shape, relationship validation requires nonempty unique
known IDs, and the view projects those fields directly. A missing field is not
an optional current-endpoint default. For an incomplete response, the client
compares individual links with every need ID in the snapshot, not just the
current need. Absent, null, empty, malformed, duplicate and foreign-ID links
are exposed as snapshot-wide record issues. A mixed record retains its exact
known-need links and its original data while its other links remain unassigned;
it can therefore appear in both the linked list and the issue list. A foreign
ID never acquires a relationship just because it is queried. Links to a
different known need are not errors. Issue counts count records, not bad links;
the bounded issue-ID lists show displayed/recorded totals and use the existing
more control. This is neither a coverage verdict nor a server validation pass.
The fallback does not relax the server contract or authenticate the response.

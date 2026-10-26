# Native Stage1 saved-result view

This is a read-only consumer of research-discovery-observations/1.0. It is not a search engine, an authenticated execution verifier, a semantic reviewer, a live scheduler, or Stage2.

Native agents own observation export/cross-link work. A confirmed save returns an origin-relative view_path. The agent combines that only with an already verified server origin. The user should not author JSON or repeat literature entry. Missing project/local-write scope is a necessary choice, not inferred authorization.

GET /api/v1/projects/{project}/artifacts/{artifact}/discovery uses the existing trusted-origin gate and exact registered project/artifact lookup. The registered snapshot bytes must still match. Selected receipt/source bytes are rechecked with existing bounded pinned reads. A readable snapshot with missing/stale referenced bytes returns ok:true only for successful projection; report.binding is not-current and individual binding statuses remain unknown/stale. This must never be described as research completion.

Whitelist projection omits receipt references, material paths and capture contents. Source locators use the existing safe-link policy; source titles/queries are rendered as text. IDs are exact, never joined by title/DOI. Original source-byte absence, declared reading, human review and execution verification are distinct.

Hash links select exact project/artifact; invalid links do not guess a result. Pending reads are cancelled/fenced on route/project changes. Ordinary page links remain compatible. Setup guidance neither changes the evidence selection nor initiates an API/configuration write. Lists initially render 50 items each and explicitly offer more; displayed entries are not a completeness claim.

Platform limit: saved-file reads/writes still require existing POSIX pinned-directory primitives. The codebase has no equivalent verified Windows handle-relative discovery read/publication helper. Existing Windows journal path normalization is not an equivalent ancestry-pinning primitive, and private source-text BLOB storage is not a generic discovery-artifact store. Do not reuse either as an unsafe shortcut. A separately reviewed Windows implementation needs native handle identity/reparse protections and fault tests (or a separately designed bounded transactional artifact storage contract); no fallback is implemented here.

Evidence levels must be reported separately: synthetic service/DOM tests, hosted browser acceptance if actually executed, native research trial, and host/platform/provider acceptance. Native cloud research is not Codex/Claude Code cross-host proof. README user examples require actual corresponding use, not this contract alone.

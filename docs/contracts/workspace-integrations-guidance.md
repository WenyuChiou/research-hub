# Optional integration guidance in Workspace

This is a discovery/navigation improvement, not a new credential editor or complete one-click setup.

## Existing functionality reused

`config.py` resolves explicit/platform/legacy local configuration. `init_wizard.py` saves vault/library selections and a Zotero key (encryption depends on optional secrets support); NotebookLM uses its separate local session store. Existing setup and doctor flows remain authoritative. Workspace already projects sanitized historical setup observations, not credentials or live authentication. No second configuration store is introduced.

The bottom-sidebar entry is available before selecting a project. It provides service-specific official links and existing commands in English/Traditional Chinese. Nothing executes when it opens: no login, setup, provider read, credential read/write, clipboard or localStorage change. It never displays vault paths, keys, cookies or arbitrary snapshot strings. Only schema1 known-source saved observations can display allowlisted historical statuses; stale/missing/unsupported observations remain unknown, not disconnected. Services are optional; local saved-text/review work remains available without integration accounts.

## Before / after and remaining steps

These are source/DOM navigation observations, not measured human task times:

- Find setup from another page: previously navigate to Overview, find Readiness and expand saved observations, then separately locate setup documentation. Now one bottom-sidebar entry exposes the exact commands and per-service links on every page, including loading/no-project state. It removes the Overview navigation and independent documentation search; it does not remove the terminal or configuration inputs.
- Returning user: existing local settings/session reuse is unchanged; no request to re-enter them every visit. This panel cannot know current authentication. Historical pass does not become connected or trigger a reconnect.
- Reconnect: guidance points directly to doctor and the existing NLM login command only when needed; the user still checks failure scope and completes provider authentication locally. Credentials can expire/be revoked; never promise permanent authentication.
- Unknown write recovery: unchanged, not solved here. Setup/reconnect cannot unlock a journal claim, authorize resend or replace an unresolved intent.

## Next bounded secure-editor design (not implemented)

Expose a sanitized settings projection identifying selected local configuration and nonsecret destination choices, with redacted configured/unconfigured flags rather than keys. Separate nonsecret vault/library editing from write-only credential/session handoff. Require origin/CSRF/local authorization checks, explicit destination changes, atomic persisted updates and validation, no secret echo/browser storage/logging. Preserve existing config precedence and unknown operation claims when destinations change; do not overwrite an existing config without an explicit diff/confirmation. Optional read-only connection checks must be distinct user actions with truthful scope and result timestamps. Provider login remains a local-provider handoff; expiry/revocation prompts only when supported evidence justifies them. This requires a reviewed security/API contract before adding any web setter.

## Verification boundary

New DOM tests cover footer discovery, independent nonmodal panel focus, close/Escape restoration and navigation/project interruptions; they also cover discovery before project load, disclosure with no extra API request, bilingual guidance/official targets, inert sensitive payload omission and unknown/stale status handling. Type/build are separate from browser pixels, keyboard/native assistive technology or user acceptance. Existing denied local browser routes are not retried. Hosted browser evidence is required for the new separate panel; no current visual/mobile acceptance claim. Existing commands can install/configure/login or probe when the user explicitly executes them; this UI does not execute them.

### Integration/publication gate

Do not publish the initial guidance independently of the current NotebookLM SDK compatibility repair: the old Hub login capture assumes an obsolete host/cookie heuristic. The existing command spelling is intended to remain, but guidance depends on tested delegation to the supported upstream login. Synthetic adapter tests are not a native login success. The pinned setup-document URL was retrieved through the GitHub connector and matched local content; official Obsidian guidance was read, Zotero API documentation confirms the key-settings destination (the account page itself requires access), and the old NotebookLM site redirects to the current Google host. No authenticated service-site acceptance was performed.

The hosted smoke adds a 390×844 independent-panel capture, keyboard Enter open/Escape close and focus restoration, viewport bounds and unchanged sidebar height; these are future CI assertions, not a local browser result. Detailed guidance lives outside the sidebar in a scrollable nonmodal panel, leaving only a compact optional/current-status-unknown entry below navigation. Hash/Back/Forward or project changes close without stealing newer navigation focus. Native200% zoom remains unverified.

### Combined candidate documentation

This UI is combined with the reviewed pinned NotebookLM SDK0.8.5 adapter/login repair. The guide link targets `fix/nlm-085-integrations-guidance/docs/setup.md`, a mutable branch document matching this integration, labeled SDK0.8.5 in the UI. It becomes available when the reviewed branch is published; it is not a preexisting release URL or immutable acceptance record. Earlier c096 setup content was independently retrieved but predates the SDK repair and is no longer the UI link target. Normal `login --auto-detect` delegates to the pinned upstream validated login; legacy `--wait-file` is unsupported and fails before launch. Synthetic integration tests do not establish native authentication or live-provider acceptance.

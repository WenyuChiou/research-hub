# NotebookLM integration

## Attribution

The v0.42 browser foundation and ask-flow selector patterns are adapted from
[PleasePrompto/notebooklm-skill](https://github.com/PleasePrompto/notebooklm-skill)
(MIT). `research-hub` does not vendor that package; it adapts the Chrome
launch arguments, persistent-session cookie replay pattern, and streaming-answer
stability polling into its own NotebookLM modules.

## Current transport and its limits

`research-hub` uses the base dependency `notebooklm-py` through
`src/research_hub/notebooklm/client.py`, a synchronous wrapper around its
asynchronous `NotebookLMClient`. This is an unofficial integration using
undocumented consumer-service interfaces, **not an official consumer REST API
or the NotebookLM Enterprise API**. Upload, generation, query and download do
not primarily drive web-page selectors. Upstream interface/authentication drift
can still break them.

Visible browser automation is used for login/session acquisition. The optional
`[playwright]` extra installs Patchright, but the current `--auto-detect` login
implementation imports `playwright.sync_api`. These are different packages:
that extra alone does not prove this path is installed. `[browser-auth]` supplies optional
cookie-import helpers. Neither extra, a cached notebook ID, nor a saved cookie
file proves that a current authenticated operation will succeed. Login and
real connector operations require separate, authorized native-PC verification.

## Architecture at a glance

The current login path is `--auto-detect`: research-hub launches a
visible browser context, opens NotebookLM, waits for you to complete
Google sign-in, and saves the session only after two signals are true:

- the live page is on `notebooklm.google.com`
- the browser context contains a Google session cookie

This avoids the old failure mode where a transient anonymous
NotebookLM page flash was saved as if it were a real login.

```text
research-hub notebooklm login --auto-detect
    |
    v
src/research_hub/notebooklm/auth.py :: _login_with_auto_detect()
    |
    v
visible browser sign-in
    |
    v
Playwright storage_state -> <vault>/.research_hub/nlm_sessions/state.json
```

Upload, generate, query, and download reuse that saved storage state through
`notebooklm-py` (the wrapper calls `NotebookLMClient.from_storage`).
The login signals above only govern session saving; they do not verify all
remote operations. Later selector troubleshooting applies to browser/login
paths and historical fallbacks, not the primary operation transport.

## One-time login

For `--auto-detect`, install its actual Playwright dependency and browser in
your virtual environment, then run (installation downloads software; login
opens a visible browser):

```bash
python -m pip install research-hub-pipeline playwright
python -m playwright install chromium
research-hub notebooklm login --auto-detect
```

Expected behavior:

```text
[nlm] Browser opened. Sign in to NotebookLM in the window.
      The session saves automatically once the homepage loads -- no ENTER needed.
```

Google may still require a visible new-device challenge or phone
verification. Complete it in the browser. If the command times out,
nothing is saved; rerun it after finishing the challenge.

Fallback login paths still exist for advanced use:

```bash
research-hub notebooklm login
research-hub notebooklm login --wait-file ./nlm-ready.txt
research-hub notebooklm login --from-browser chrome
research-hub notebooklm login --import-from <other-vault>
```

Use `--from-browser` only when you installed the browser-cookie import
extra and understand that browser cookie access is OS/browser-specific.

The saved session file is:

```text
<vault>/.research_hub/nlm_sessions/state.json
```

Treat that file like a password store. It contains Google session
cookies for the local OS user.

## Binding a cluster to a notebook

Before the first automated upload, bind the cluster to the visible
NotebookLM notebook name that appears on the NotebookLM home page.

```bash
research-hub clusters bind my-cluster --notebooklm "My NotebookLM Notebook"
```

Expected output:

```text
Bound my-cluster:
  Zotero collection:   (unset)
  Obsidian folder:     (unset)
  NotebookLM notebook: My NotebookLM Notebook
```

The lookup during upload is by visible notebook name, not notebook ID.
On the first successful automated upload, `src/research_hub/notebooklm/upload.py`
stores the resolved notebook URL and notebook ID back into
`.research_hub/clusters.yaml`.

## Bundle -> upload -> generate

This is the normal happy path for a cluster.

1. Build the latest NotebookLM bundle.

```bash
research-hub notebooklm bundle --cluster my-cluster
```

Expected output:

```text
Bundle written to C:/path/to/vault/.research_hub/bundles/my-cluster-20260411-142500
Papers: 18 total (11 PDFs, 5 URLs, 2 skipped)
```

2. Preview the upload plan without opening NotebookLM.

```bash
research-hub notebooklm upload --cluster my-cluster --dry-run
```

Expected output:

```text
Notebook: My NotebookLM Notebook
Uploads: 16 succeeded, 0 failed, 2 skipped from cache
  [OK] pdf: C:/path/to/vault/.research_hub/bundles/my-cluster-20260411-142500/pdfs/paper-01.pdf
  [OK] pdf: C:/path/to/vault/.research_hub/bundles/my-cluster-20260411-142500/pdfs/paper-02.pdf
  [OK] url: https://example.org/paper-03
  [OK] url: https://example.org/paper-04
```

3. Run the actual upload.

```bash
research-hub notebooklm upload --cluster my-cluster
```

Expected output:

```text
Notebook: My NotebookLM Notebook
Notebook URL: https://notebooklm.google.com/notebook/12345678-90ab-cdef-1234-567890abcdef
Uploads: 16 succeeded, 0 failed, 2 skipped from cache
  [OK] pdf: C:/path/to/vault/.research_hub/bundles/my-cluster-20260411-142500/pdfs/paper-01.pdf
  [OK] pdf: C:/path/to/vault/.research_hub/bundles/my-cluster-20260411-142500/pdfs/paper-02.pdf
  [OK] url: https://example.org/paper-03
```

Upload defaults to visible mode in v0.4.1 because
`src/research_hub/notebooklm/upload.py` and the `research-hub notebooklm upload`
CLI path both default `headless=False`. That lets you watch the first
run and catch selector problems early. Headless mode is opt-in with
`research-hub notebooklm upload --cluster my-cluster --headless`.

4. Trigger generation.

```bash
research-hub notebooklm generate --cluster my-cluster --type brief
```

Expected output:

```text
brief: https://notebooklm.google.com/notebook/12345678-90ab-cdef-1234-567890abcdef
```

Generation is also visible by default. Headless generation is opt-in
with `research-hub notebooklm generate --cluster my-cluster --type brief --headless`.

Supported artifact types are:

- `brief`
- `audio`
- `mind-map`
- `video`
- `all`

## Session health check

Both upload and generation run a pre-flight probe before touching the
notebook. The probe lives in `_check_session_health` inside
`src/research_hub/notebooklm/upload.py`.

What it does:

- Opens `https://notebooklm.google.com/`
- Waits for the page to settle
- Checks whether the current URL is still inside NotebookLM rather than
  a Google sign-in or OAuth flow

If the saved browser session has expired, the command fails fast with a
`NotebookLMError` before upload or generation starts. The error message
tells you to rerun `research-hub notebooklm login --auto-detect`.

The failure text is sourced from `src/research_hub/notebooklm/upload.py`
and includes the page URL it landed on, for example:

```text
Saved Google session appears to be expired (landed on https://accounts.google.com/...).
Run `research-hub notebooklm login --auto-detect` to re-auth.
```

## Rate limiting and resumption

The upload flow is intentionally conservative.

- `BETWEEN_UPLOADS_MS` in `src/research_hub/notebooklm/selectors.py` is
  `2000`, so there is a 2-second pause between successful source
  uploads.
- `upload_cluster` in `src/research_hub/notebooklm/upload.py` caps each
  run at `rate_limit_cap=50`.
- `.research_hub/nlm_cache.json` records `uploaded_sources`, notebook
  metadata, artifact URLs, and `last_synced`.

That cache is what makes re-runs resumable. If an upload stops halfway,
run the same command again and already-uploaded sources are skipped.

Example rerun output:

```text
Notebook: My NotebookLM Notebook
Notebook URL: https://notebooklm.google.com/notebook/12345678-90ab-cdef-1234-567890abcdef
Uploads: 3 succeeded, 0 failed, 13 skipped from cache
  [OK] url: https://example.org/new-paper-15
  [OK] url: https://example.org/new-paper-16
  [OK] pdf: C:/path/to/vault/.research_hub/bundles/my-cluster-20260411-142500/pdfs/new-paper-17.pdf
```

## When Google ships a UI update

If NotebookLM changes its DOM and a selector breaks, use this recovery
playbook.

1. Reproduce the failing operation with a visible browser session when
   possible, or rerun `research-hub notebooklm login --auto-detect`
   and inspect the opened browser before it closes.

2. Open DevTools with `F12`.
3. Inspect the broken element in the Elements panel.
4. Update the matching constant in `src/research_hub/notebooklm/selectors.py`.

Selector priority order in `src/research_hub/notebooklm/selectors.py` is:

1. Custom element tag
2. Semantic CSS class
3. `aria-label`
4. `href` pattern

Why those are preferred:

- NotebookLM is an Angular + Material Design SPA.
- Custom tags such as `project-button`, `source-panel`, and
  `studio-panel` are the most durable anchors.
- Semantic classes such as `create-new-button` and
  `source-stretched-button` tend to survive layout shifts.
- `aria-label` text is localized, but stable within a locale.
- `a[href*='/notebook/']` is a durable way to find notebook tiles.

Do not target `_ngcontent-ng-*` attributes. Those are Angular-generated
build artifacts and are not stable across releases.

After updating a selector, re-run a safe verification pass first:
`research-hub notebooklm upload --cluster my-cluster --dry-run`.

If the issue is inside the upload dialog itself, run the visible upload
path after the dry run so you can watch the browser:
`research-hub notebooklm upload --cluster my-cluster`.

## Locale support

NotebookLM follows the language of the signed-in Google account. The
selector tables in `src/research_hub/notebooklm/selectors.py` include
localized strings for:

- `zh-TW`
- `zh-CN`
- `en`
- `ja`

If auto-detection picks the wrong locale, override it before running a
NotebookLM command:

```bash
RESEARCH_HUB_NLM_LOCALE=en research-hub notebooklm upload --cluster my-cluster
```

Expected output still follows the normal upload summary format:

```text
Notebook: My NotebookLM Notebook
Notebook URL: https://notebooklm.google.com/notebook/12345678-90ab-cdef-1234-567890abcdef
Uploads: 16 succeeded, 0 failed, 2 skipped from cache
```

## Security notes

- Add `<vault>/.research_hub/nlm_sessions/` to local ignore rules if it
  is not already excluded. That directory contains Google session
  cookies and should never be shared.
- Do not commit `.research_hub/nlm_cache.json`. It contains notebook
  URLs and auth-scoped metadata; it is safer as local-only state.
- Do not run `research-hub` under a shared OS user account. The
  NotebookLM browser profile is tied to that local user profile.

## Troubleshooting

**Browser automation dependency missing**

Install the browser automation extra:

```bash
pip install "research-hub-pipeline[playwright]"
```

**Session expired**

Re-run the one-time login flow to refresh the saved Google session.

**Add-source button not found**

Google may have shipped a UI change. Follow the recovery playbook in
section 8 and patch `src/research_hub/notebooklm/selectors.py`.

**Upload hangs on Website tab**

That usually means selector drift inside the source dialog. Log an
issue and include the DOM dump or screenshots from a
visible NotebookLM browser session.

**Browser profile is locked**

Another browser process using the same local profile is probably still
running. Close it and rerun the command.

## What this does NOT do

- No real-time NotebookLM source count query from the live UI
- No multi-user shared NotebookLM workspace support
- No custom video rendering pipeline beyond clicking NotebookLM's own
  video overview button
- No backfilling of legacy `## Summary` blocks in old notes

## Comparison to public NotebookLM MCP servers

Several public NotebookLM MCP servers exist on GitHub, including
`jacob-bd/notebooklm-mcp-cli`, `julianoczkowski/notebooklm-mcp-2026`,
`PleasePrompto/notebooklm-mcp`, `roomi-fields/notebooklm-mcp`,
`Pantheon-Security/notebooklm-mcp-secure`, and
`moodRobotics/notebooklm-mcp-server`. Those projects focus on the read
side: listing notebooks and asking questions against notebooks that
already exist. `research-hub` covers the write side in
v0.4.1: bundle sources from a Zotero-backed cluster, upload them
through the NotebookLM UI, and trigger NotebookLM artifact generation.
The two approaches are complementary.

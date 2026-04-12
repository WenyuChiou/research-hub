# NotebookLM Automation in v0.4.1

## Why automation, not an API

NotebookLM does not expose a public REST API for personal Google
accounts, so `research-hub` has to drive the web UI. In practice that
means Playwright is the only realistic automation layer for upload and
generation. Selector drift is an accepted maintenance cost, and the
recovery workflow is documented below in the UI-update section.

## Architecture at a glance

The primary v0.4.1 path is CDP attach: `research-hub` launches a normal
Chrome process with `--remote-debugging-port`, then Playwright connects
to that already-running browser with `connect_over_cdp`. Because Chrome
is started as a normal user process instead of being launched by
Playwright, Google's bot check for `navigator.webdriver` does not fire.

```text
research-hub CLI
    |
    v
src/research_hub/notebooklm/session.py :: open_cdp_session()
    |
    v
src/research_hub/notebooklm/cdp_launcher.py :: launch_chrome_with_cdp()
    |
    v
subprocess Chrome --remote-debugging-port=<port> --user-data-dir=<session-dir>
    |
    v
Playwright chromium.connect_over_cdp(...)
    |
    v
NotebookLM web UI
```

## One-time login

Use CDP mode for the initial Google sign-in. This is the primary login
path in v0.4.1.

```bash
research-hub notebooklm login --cdp
```

Expected success output looks like:

```text
Launching Chrome with CDP remote debugging enabled...
  Chrome binary: C:/Program Files/Google/Chrome/Application/chrome.exe
  Session dir:   C:/path/to/vault/.research_hub/nlm_sessions/default
  Mode:          cdp-attach (no Playwright automation fingerprint)
  Timeout:       300s  (will auto-close 5s after login)

>>> Sign in with your Google account in the opened Chrome.
>>> The window will close AUTOMATICALLY when login is detected.
  [14:23:07] On https://accounts.google.com/...
  [14:23:41] On notebooklm.google.com - waiting 5s for session to stabilize...
  [14:23:46] Login detected. Session saved.
```

If Chrome is not installed, or the binary is not auto-detected, the
command exits early with output like:

```text
  [ERR] Could not find Chrome binary on this system.
  [ERR] Install Chrome, or pass --chrome-binary <path>.
```

Pass an explicit Chrome path if needed with
`research-hub notebooklm login --cdp --chrome-binary "C:/Program Files/Google/Chrome/Application/chrome.exe"`.

For DOM inspection and selector repair, keep the browser open:

```bash
research-hub notebooklm login --cdp --keep-open
```

Expected output for inspection mode:

```text
Launching Chrome with CDP remote debugging enabled...
  Chrome binary: C:/Program Files/Google/Chrome/Application/chrome.exe
  Session dir:   C:/path/to/vault/.research_hub/nlm_sessions/default
  Mode:          cdp-attach (no Playwright automation fingerprint)
  Keep-open:     YES - will NOT auto-close on login detection.
  Timeout:       300s (wall-clock max, press Enter to close sooner)

>>> Chrome is open for manual inspection / F12 DevTools work.
>>> Press ENTER in this terminal when you are done - window will close.
  [14:30:04] Chrome is ready. Press Enter here when finished.
```

The saved session directory is:

```text
<vault>/.research_hub/nlm_sessions/default/
```

Treat that directory like a password store. It contains the persistent
Google-authenticated browser profile used by `src/research_hub/notebooklm/session.py`.

`--use-system-chrome`, `--from-chrome-profile`,
`--chrome-profile-path`, and `--chrome-profile-name` still exist in
`research-hub notebooklm login`, but they are non-CDP fallback paths.
The recommended path is `--cdp`.

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
tells you to rerun `research-hub notebooklm login --cdp`.

The failure text is sourced from `src/research_hub/notebooklm/upload.py`
and includes the page URL it landed on, for example:

```text
Saved Google session appears to be expired (landed on https://accounts.google.com/...).
Run `research-hub notebooklm login --cdp` to re-auth.
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

1. Start an inspection session:
   `research-hub notebooklm login --cdp --keep-open`

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

**Chrome binary not found**

Install Chrome, or pass `--chrome-binary` to the CDP login command.

**Session expired**

Re-run the one-time login flow to refresh the saved Google session.

**Add-source button not found**

Google may have shipped a UI change. Follow the recovery playbook in
section 8 and patch `src/research_hub/notebooklm/selectors.py`.

**Upload hangs on Website tab**

That usually means selector drift inside the source dialog. Log an
issue and include the DOM dump or screenshots from a
`research-hub notebooklm login --cdp --keep-open` inspection session.

**CDP port in use**

Another Chrome process using the same `user_data_dir` is probably still
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

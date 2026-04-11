# NotebookLM Automation

Research Hub v0.4.1 adds a Playwright-based browser automation layer for
NotebookLM. There is no public NotebookLM REST API for personal use, so
all upload and generation flows go through the web UI.

## One-time setup

NotebookLM automation uses a persistent Chromium profile so your Google
session survives across runs.

```bash
research-hub notebooklm login
```

This opens a visible browser window. Sign in to your Google account and
wait until NotebookLM shows your notebook list or an empty create page.
Then return to the terminal and press Enter.

Security warning:
The saved browser profile lives under
`.research_hub/nlm_sessions/default/`. That folder contains Google auth
cookies and should be treated like a password store. Do not copy it into
public repos or shared storage.

## First upload

Build the cluster bundle first:

```bash
research-hub notebooklm bundle --cluster my-cluster
```

Preview the upload plan:

```bash
research-hub notebooklm upload --cluster my-cluster --visible --dry-run
```

Then run the real upload:

```bash
research-hub notebooklm upload --cluster my-cluster --visible
```

The upload command:

- Finds the newest bundle under `.research_hub/bundles/`
- Opens the target notebook or creates it if missing
- Uploads PDFs first when available, otherwise website URLs
- Records uploaded sources in `.research_hub/nlm_cache.json`
- Saves the notebook URL and notebook ID back into the cluster registry

If the saved Google session is still valid, you can omit `--visible` and
let the browser run headless.

## Generate artifacts

Generate one artifact at a time:

```bash
research-hub notebooklm generate --cluster my-cluster --type brief
research-hub notebooklm generate --cluster my-cluster --type audio
research-hub notebooklm generate --cluster my-cluster --type mind-map
research-hub notebooklm generate --cluster my-cluster --type video
```

Generate all four:

```bash
research-hub notebooklm generate --cluster my-cluster --type all
```

Artifact URLs are written back into `.research_hub/nlm_cache.json` using
these keys:

- `briefing_url`
- `audio_url`
- `mind_map_url`
- `video_url`

## Rate limits and resume from cache

NotebookLM upload is intentionally conservative.

- Uploads pause briefly between sources
- Sources already recorded in `nlm_cache.json` are skipped
- If a run stops midway, rerunning resumes from cache
- Each run caps uploads to a bounded number of sources

This keeps the flow easier to resume when NotebookLM times out or Google
changes a selector.

## Troubleshooting

### Selector errors

NotebookLM does not expose a stable DOM API. If a run fails with a
selector error:

1. Open [src/research_hub/notebooklm/selectors.py](/C:/Users/wenyu/Desktop/research-hub/src/research_hub/notebooklm/selectors.py)
2. Find the constant mentioned by the error context
3. Update that selector in `selectors.py`
4. Retry with:

```bash
research-hub notebooklm upload --cluster my-cluster --dry-run
```

If needed, rerun with `--visible` so you can inspect the page while the
automation is active.

### Google session expired

If the browser lands on a sign-in page, refresh the persistent profile:

```bash
research-hub notebooklm login
```

### Missing bundle

If upload reports that no bundle exists for a cluster, regenerate it:

```bash
research-hub notebooklm bundle --cluster my-cluster
```

## Manual fallback

The bundle output remains usable even if selectors need patching.

1. Open NotebookLM manually in your browser
2. Drag files from the bundle `pdfs/` folder into Sources
3. Paste URLs from `sources.txt` using the Website source flow
4. Re-run artifact generation after the selector fix lands

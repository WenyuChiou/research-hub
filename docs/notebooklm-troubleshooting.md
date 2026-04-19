# NotebookLM automation troubleshooting

v0.42+ — research-hub's NotebookLM layer uses [patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) (stealth-patched Playwright fork) + real Chrome + persistent context. This document covers the most common failure modes and how to diagnose them.

---

## Architecture (v0.42)

```
research-hub notebooklm <cmd>
  └─ src/research_hub/notebooklm/upload.py
      └─ browser.launch_nlm_context(...)
          ├─ patchright.sync_api + channel="chrome"
          ├─ persistent user_data_dir (default: .research_hub/nlm_sessions/default/)
          ├─ anti-automation launch args
          │   - --disable-blink-features=AutomationControlled
          │   - ignore_default_args=["--enable-automation"]
          │   - --no-sandbox, --disable-dev-shm-usage, ...
          └─ cookie injection from .research_hub/nlm_sessions/state.json
              (Playwright bug #36139 workaround)
```

Every `upload` / `ask` / `download` / `generate` run writes a structured JSONL log to `<vault>/.research_hub/nlm-debug-<UTC-timestamp>.jsonl`. Always look at that file first.

---

## Failure mode 1 — "Upload succeeded but NotebookLM shows 0 sources"

**Symptom.** `research-hub notebooklm upload --cluster X` returns 0, prints `Uploaded: N`, but the notebook page shows no sources.

**Diagnosis.** Google's frontend detected automation and silently dropped the sources. Pre-v0.42 users hit this constantly because `--disable-blink-features=AutomationControlled` was missing. If you are on v0.42+ and still seeing it:

1. Check `nlm-debug-<UTC>.jsonl` for `"kind": "upload_ok"` lines — if they are there but the UI is empty, Google is rejecting at a layer patchright cannot see.
2. Run `research-hub notebooklm login` again (fresh session). Sometimes Google invalidates the session between runs.
3. Delete `.research_hub/nlm_sessions/` entirely and re-login. This wipes `user_data_dir` + `state.json` and forces a fresh fingerprint.

---

## Failure mode 2 — "Dialog did not close" errors

**Symptom.** `NotebookLMError: Upload dialog did not close` in the debug log.

**Diagnosis.** The Angular SPA's upload dialog sometimes lingers after the source is accepted. v0.42 retries up to 3 times (1 s → 3 s → 9 s) before giving up; if you see 3 consecutive failures for the same paper:

1. Re-run with `--visible` (`research-hub notebooklm upload --cluster X --no-headless`) and watch the UI.
2. Check if NotebookLM rate-limited you — a 429 will show as lingering "processing" dialogs. Wait 5 minutes and retry.
3. If only specific PDFs fail, they may exceed NotebookLM's file-size or page-count limits. Check the bundle manifest.

---

## Failure mode 3 — "No answer received within 120s" from `ask`

**Symptom.** `research-hub notebooklm ask --cluster X --question "..."` reports timeout.

**Diagnosis.**

1. Is the notebook actually populated? Run `research-hub notebooklm read-briefing --cluster X` first; if that fails the source upload never completed.
2. Did your Google session expire? Run `research-hub notebooklm login` again.
3. Use `--visible` + `--timeout 300` to watch the question being typed and the generation stream live.
4. NotebookLM occasionally rotates response DOM selectors. If nothing appears in `RESPONSE_SELECTORS`, open F12 DevTools in a real browser, find the new selector, and add it to `src/research_hub/notebooklm/ask.py::RESPONSE_SELECTORS`.

---

## Failure mode 4 — "Selectors not found" on non-English UI

**Symptom.** `NotebookLMError: Add-source button not found` or similar.

**Diagnosis.** Google's account language determines NotebookLM's UI language. v0.42 ships aria-label fallbacks for **zh-TW, zh-CN, en, ja, ko, es, fr, de**. If your account is in a language not in that list:

1. Set `RESEARCH_HUB_NLM_LOCALE=en` to force English fallbacks:
   ```bash
   RESEARCH_HUB_NLM_LOCALE=en research-hub notebooklm upload --cluster X
   ```
2. Or file an issue with the translated strings for your locale and we add them.

---

## Failure mode 5 — "patchright not installed" ImportError

**Symptom.** `ModuleNotFoundError: No module named 'patchright'`.

**Diagnosis.** v0.42 swapped `playwright` for `patchright`. Reinstall:

```bash
pip install --upgrade 'research-hub-pipeline[playwright]'
```

If patchright wheels are not available for your platform, install from source:

```bash
pip install 'patchright>=1.55'
patchright install chrome
```

---

## Reading the debug log

`.research_hub/nlm-debug-<UTC>.jsonl` — one line per event. Event kinds:

| `kind`              | When emitted                                |
|---------------------|---------------------------------------------|
| `run_start`         | At the top of `upload_cluster`              |
| `session_health_ok` | After NotebookLM home responded             |
| `upload_attempt`    | Per retry attempt per paper                 |
| `upload_ok`         | Upload succeeded                            |
| `upload_fail`       | Attempt failed (will retry or give up)     |
| `upload_skip`       | Manifest action was `skip`                  |
| `run_summary`       | At the end, with success/fail/retry tallies|

Quick tally of failed papers:

```bash
grep '"upload_fail"' .research_hub/nlm-debug-*.jsonl | head
```

---

## Escalation

Persistent issues → file at <https://github.com/WenyuChiou/research-hub/issues> and attach:

1. `.research_hub/nlm-debug-<UTC>.jsonl` (redact the cluster slug if sensitive)
2. Output of `research-hub doctor`
3. Your Google account language + NotebookLM locale (check browser URL)

---

## Attribution

The browser stealth patterns (anti-automation flags, persistent context + state.json hybrid auth, 3-read stability polling) are adapted from [PleasePrompto/notebooklm-skill](https://github.com/PleasePrompto/notebooklm-skill) (MIT, 5.9k⭐). We do not vendor the package — we adapted the concrete patterns into our module idiom.

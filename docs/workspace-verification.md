# Workspace preview verification — 2026-09-08

This is implementation evidence, not scientific acceptance or release approval.
Baseline: `bb00775822bf856333cba8388631f16be3831ea4`; candidate is the
`codex/researcher-workspace` branch. CI binds later results to its exact commit.
Local environment: Windows 11, CPython 3.14.0, FastMCP 3.2.4.

| Verification | Actual result | Scope |
|---|---|---|
| Default Python suite: `python -m pytest -q --timeout=90` | 3,422 passed, 24 skipped, 11 deselected, 2 xfailed; 469.67 s | Pre-review-fix candidate; default marker exclusions unchanged; not a live-provider claim |
| README/diagram locale acceptance | 8 passed, 0.77 s | Node/edge parity, links, required terms and exact image provenance |
| Workspace integration: six `test_workspace_*.py` modules | 71 passed, 1 skipped, 13.27 s | Real SQLite, files, process containment, replay, demo, local HTTP and docs |
| Final writing-scope/runtime/docs recheck | 33 passed, 4.43 s | Code/data remain authority sources; manuscript prose scope and exact asset hashes |
| Review fixes: `python -m pytest -q tests/test_workspace_executor.py tests/test_workspace_runtime.py tests/test_workspace_docs.py tests/test_workspace_actions.py --timeout=90` | 56 passed, 15.74 s | Actual revision prompt/handoff, exact candidate hashes, stderr-only failure, byte bounds and persisted protocol errors |
| `cd web && npm run typecheck && npm test && npm run build` | 36 frontend tests passed, 20.95 s | State semantics, persisted errors/log paths, severity, input preservation, EN/TW and bundled assets |
| `python scripts/workspace_browser_smoke.py --output PATH` | 19 checks passed, 11.372 s; zero page errors | Actual Chromium/server/database; six EN/TW routes, download/import, human gate, responsive width and keyboard |
| `python -m build --wheel --no-isolation` | Built wheel with installed Hatchling 1.31.0 | Isolated build/install downloads timed out; local clean installation is **not verified** |

Earlier failed runs, including the then-missing diagram, are preserved rather
than rewritten. Existing Python 3.14 dependency/encoding warnings remain.
Test counts
overlap and must not be added together. Local JUnit, browser traces, model
receipts and reports remain in the implementation task's evidence directory.
The workspace CI job separately rebuilds assets, installs a clean wheel and
serves it with Node absent from PATH. Consult that job's actual result before
calling a clean installation verified.

Independent review identified missing prior-proposal revision context, discarded
stderr and hidden persisted UI errors. The targeted regressions above exercise
those corrections; they do not replace a live provider or semantic review.

## Live dogfood and evidence-driven corrections

`python scripts/workspace_dogfood.py --root NEW_PATH --run-codex` is opt-in;
it may use paid host capacity and is never part of default CI.

- Empirical lane: real three-case summation output and source code produced a
  bounded paragraph-level outline in **38.555 s**. Provider usage: 28,887 input
  tokens, 702 output tokens; monetary cost unavailable.
- Reading-review lane: curator notes with original source locations, unavailable
  full text and a labelled malicious instruction produced a bounded synthesis in
  **36.484 s**. Usage: 28,758 input tokens, 614 output tokens; cost unavailable.
  The proposal did not claim a systematic review, direct contradiction, or
  unsupported theorem and did not follow the source injection.
- Both ended **awaiting_human**, with zero tool items and exact candidate hashes.
  No human acceptance, canonical manuscript edit, upload or publication occurred.
- Earlier attempts retained completed prose but failed on host skill-context
  diagnostics. A corrected strict Codex configuration passed a minimal live
  probe before the two successful runs; warning events are never silently ignored.
- A live timeout exposed asynchronous Windows job termination; cleanup now waits
  for all owned descendants, covered by real process tests.
- Empirical prose checks initially rejected the registered Python analysis file.
  Binding now distinguishes manuscript documents from research authority sources.
  A fresh **offline** two-project handoff run passed all four public checks in
  each project (state, consistency, prose, regression); no model was rerun for
  that correction and no scientific approval was manufactured.

## Remaining human and external checks

The public writing producer is [PR #17](https://github.com/WenyuChiou/academic-writing-skills/pull/17),
not a released dependency. Exact manuscript acceptance and local delivery approval
remain human actions. NotebookLM's last recorded authentication failure has not
been reverified. Screen-reader testing and broader browser coverage remain open.
These cases are bounded pilots, not evidence of publishable research quality or a
comparative framework benchmark. No skills were removed by this workspace change.

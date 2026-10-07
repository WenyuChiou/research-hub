# Merged producer integration — 2026-10-07

The producer [PR #17](https://github.com/WenyuChiou/academic-writing-skills/pull/17)
is merged. The consumer source pin and integrity values are recorded in
[workspace-writing-source.json](workspace-writing-source.json). The Hub workspace
remains an unreleased preview; producer merge does not install or release Hub.

- Producer commit: `bc15e29e976cd6ade3484aeaa4f1230444697f8a`
- Manifest SHA256: `0bce611e91bd0bf01ad6aa59eccc46ae52321b645c04f6a71225f01e90f7a3ec`
- Reproducible ZIP SHA256: `0b084edb82233fc43bf3465a8a8cc11551f5d6a15e4b98c6ea7cdfcb95a94ef7`
- Explicit-source integration rebuilds/checks the producer bundle, extracts it,
  verifies consumer instruction closure, and runs all four writing audits for
  both empirical and reading-review demos. Both remain offline handoffs in
  `awaiting_agent`, with no scientific acceptance or publication authorization.
- CI checks out this immutable producer commit and runs the integration test;
  the ordinary suite skips the producer-dependent case without an explicit
  `RESEARCH_HUB_TEST_WRITING_ADAPTER` checkout. No network fetch occurs inside
  the test and no live model is invoked.

Reproduce against a reviewed checkout of that exact producer commit:

```sh
RESEARCH_HUB_TEST_WRITING_ADAPTER=/absolute/path/to/academic-writing-adapter \
  python -m pytest -q tests/test_workspace_producer_integration.py
```

The earlier Hub integration snapshot
[`dda3cee30f43e7eca658bfeb9b20aac35ec19ce8`](https://github.com/WenyuChiou/research-hub/commit/dda3cee30f43e7eca658bfeb9b20aac35ec19ce8)
has the same workspace runtime as this documentation/source-pin update. Its
[PR CI](https://github.com/WenyuChiou/research-hub/actions/runs/37630994839) passed,
including 19 real Chromium checks, clean installed-wheel checks and frontend
asset reproducibility. Its offline suite passed 3,999 tests; 18 skipped,
17 deselected and 2 expected failures. The separate stress suite passed 15 tests.
These historical counts do not substitute for this update's exact-head CI.

The September implementation and live-proposal evidence below is historical.
It was not rerun with the merged producer and is not a claim of current live
provider access, scientific acceptance, release approval or local installation.

## Historical workspace preview verification — 2026-09-08

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

The public writing producer [PR #17](https://github.com/WenyuChiou/academic-writing-skills/pull/17)
was merged on 2026-10-07. The explicitly configured source is now immutable main
commit `bc15e29e976cd6ade3484aeaa4f1230444697f8a`; it is not a permanent runtime dependency. Exact manuscript acceptance and local delivery approval
remain human actions. NotebookLM's last recorded authentication failure has not
been reverified. Screen-reader testing and broader browser coverage remain open.
These cases are bounded pilots, not evidence of publishable research quality or a
comparative framework benchmark. No skills were removed by this workspace change.

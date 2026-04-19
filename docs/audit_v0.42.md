# v0.42 audit — NotebookLM reliability rewrite + Obsidian markdown conventions

Release date: **2026-04-19**. Shipped ~36 hours after v0.41.1.

---

## The forcing function

The maintainer, running the end-to-end pipeline on their own harness-engineering research cluster, reported:

> **"從 Obsidian 到 NotebookLM 總是很卡 … 很多次都沒有辦法把資料傳到 NotebookLM"**

This was a load-bearing UX complaint on a feature research-hub ships as a selling point. The original v0.42 plan (monolith split of `cli.py` / `mcp_server.py`) was shelved in favour of fixing the NLM automation layer.

---

## Root-cause audit

Three Explore agents in parallel investigated:
1. [PleasePrompto/notebooklm-skill](https://github.com/PleasePrompto/notebooklm-skill) (5.9k⭐) — what a working NLM automation looks like
2. research-hub's own `src/research_hub/notebooklm/` — what we were doing wrong
3. [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) (25.3k⭐) — what Obsidian conventions we could adopt

The audit pinpointed seven concrete failure modes in our NLM module, ranked by likelihood:

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 1 | CRITICAL | Missing `--disable-blink-features=AutomationControlled` | `cdp_launcher.py:144` |
| 2 | CRITICAL | Bundled Chromium, not real Chrome (`channel="chrome"` missing) | `session.py:116` |
| 3 | HIGH | Standard `playwright`, not `patchright` | all imports |
| 4 | HIGH | Zero retry logic — silent `pass` on failures | `upload.py:196` |
| 5 | MEDIUM | Selector drift — only zh-TW/en/ja aria-label fallbacks | `selectors.py` |
| 6 | MEDIUM | Dialog detach timeout ignored | `client.py:256-260` |
| 7 | LOW | No rate-limit / backoff awareness | `selectors.py:BETWEEN_UPLOADS_MS` |

95% of the v0.42 scope is direct targeting of these modes.

---

## What shipped

### Track A — NotebookLM reliability rewrite (Codex, ~650 LOC + tests)

- **Dependency swap**: `playwright>=1.40` → `patchright>=1.55` (MIT fork with stealth patches)
- **NEW `browser.py`** — unified launcher. `channel="chrome"` + persistent `user_data_dir` + anti-automation launch args + `ignore_default_args=["--enable-automation"]` + cookie injection from `state.json` (Playwright bug #36139 workaround)
- **NEW `save_auth_state` / `_load_auth_state`** helpers
- **Retry wrapper** on every per-paper upload (1 s / 3 s / 9 s exponential backoff)
- **Structured JSONL debug log** at `.research_hub/nlm-debug-<UTC>.jsonl` — every attempt, failure, retry, success recorded
- **Locale expansion** — zh-CN, ko, es, fr, de aria-label variants added
- **Dialog close hardening** — `client.py` now raises `NotebookLMError` instead of swallowing timeouts
- **CDP launcher deprecated** — `cdp_launcher.py` is a back-compat shim that raises `NotImplementedError` with a pointer to `browser.py`; `session.py` is a shim routing legacy `open_cdp_session` / `login_interactive*` to the new launcher

### Track B — `research-hub notebooklm ask` command (Codex, ~200 LOC + tests)

- **NEW `ask.py`** — ad-hoc Q&A against a cluster's NotebookLM notebook
- **CLI**: `research-hub notebooklm ask --cluster X --question Y`
- **MCP tool** `ask_cluster_notebooklm(cluster, question)` for Claude Desktop
- Adapted from PleasePrompto/notebooklm-skill's `ask_question.py`: `QUERY_INPUT_SELECTORS` / `RESPONSE_SELECTORS` / `THINKING_MESSAGE_SELECTORS` / human-type cadence / 3-read stability polling
- 120 s timeout, answer saved to `.research_hub/artifacts/<slug>/ask-<UTC>.md`

### Track C — Obsidian markdown conventions (Claude direct, ~200 LOC + 12 tests)

Adopted kepano/obsidian-skills conventions:

- **NEW `markdown_conventions.py`** — `wrap_callout`, `unwrap_callout`, `upgrade_paper_body`, `summary_section_to_callout`
- **Paper notes** (via `pipeline.py` + `autofill.py`) now emit `> [!abstract]` / `> [!success]` / `> [!info]` / `> [!note]` callouts with `^summary` / `^findings` / `^methodology` / `^relevance` block IDs. Heading anchors stay clean (`## Summary`) so existing regex extractors work.
- **Cluster overview** (`topic.py::OVERVIEW_TEMPLATE`) — TL;DR, Core question, Open problems all use callouts
- **Crystals** — TL;DR wrapped in `> [!abstract]` + `^tldr` block ID; `from_markdown` unwraps idempotently
- **NEW `research-hub vault polish-markdown [--cluster X] [--apply]`** — migration CLI, dry-run by default, idempotent

### Track D — Release (Claude direct)

- `pyproject.toml`: 0.41.1 → 0.42.0
- `CHANGELOG.md` v0.42.0 entry
- `docs/release-notes-v0.42.zh-TW.md` (Claude-written, no Gemini retry)
- `docs/notebooklm-troubleshooting.md`
- Live test: upload harness papers, verify `nlm-debug-*.jsonl` has 0 retries
- CI green on all 9 multi-OS jobs

---

## Numbers

- **Tests**: 1423 → ~1441+ (≥ 18 new: 10 browser, 8 ask — plus 12 markdown conventions = 30 total)
- **LOC**: ~+1000 new, ~500 removed
- **Files**: 3 new modules (browser.py, ask.py, markdown_conventions.py) + 3 new test files
- **Dependency**: `playwright>=1.40` → `patchright>=1.55` (same `[playwright]` extra name for install compat)

---

## Attribution

- **[PleasePrompto/notebooklm-skill](https://github.com/PleasePrompto/notebooklm-skill)** (MIT) — browser launch args, auth persistence pattern, stable-polling quorum, human-type cadence. Adapted, not vendored.
- **[kepano/obsidian-skills/obsidian-markdown](https://github.com/kepano/obsidian-skills)** (MIT, by Steph Ango / Obsidian CEO) — callout + block ID conventions.

Source comments, CHANGELOG, and `docs/notebooklm-troubleshooting.md` credit both.

---

## What's NOT in v0.42 (deferred)

- **Obsidian Bases (`.base`) auto-generation per cluster** — high value, needs design time. v0.43.
- **JSON Canvas (`.canvas`) citation-graph export** — after Bases.
- **`readability-lxml → defuddle` URL extraction swap** — defuddle is NPM-only; evaluate trafilatura / newspaper3k in v0.43.
- **`cli.py` / `mcp_server.py` monolith split** — still deferred, no user forcing function.
- **NLM audio / mind-map / video artifact downloads** — v0.43+.
- **library-management-a-la-notebooklm-skill** — our cluster → notebook URL mapping already covers this need.

---

## Lessons from prior releases (applied)

- **Post-v0.37** — sys.modules pollution caught after 16 red CI builds. Mitigation this release: new tests extend existing conftest fixtures, reuse `_get_mcp_tool` helper.
- **Post-v0.40.0** — Windows CI broke on tmp_path outside HOME. Already fixed via autouse `RESEARCH_HUB_ALLOW_EXTERNAL_ROOT=1`.
- **Post-v0.41.0** — PEP 701 f-string Python 3.10/3.11 incompat. Codex brief explicitly forbade PEP 701 syntax.
- **Gemini Windows** — AttachConsole / non-interactive shell issue unresolved. Per user decision, zh-TW release notes were written directly by Claude.

---

## The cycle

v0.41.1 shipped 36 hours ago. v0.42.0 scope was shaped entirely by using the tool on the maintainer's own data and hitting the NLM upload wall. The pattern that produced v0.41 (ingest-run finding real bugs → 4+3 CLIs) produced v0.42 (NLM upload run hitting silent failure → patchright rewrite). Ship → use → fix what hurts.

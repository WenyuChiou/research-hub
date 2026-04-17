# research-hub v0.32.0 — Polish: high-quality screenshots + housekeeping

**Released:** 2026-04-17
**Theme:** Pure polish. No architectural changes. Closes the visible quality complaint that demo screenshots were 800-1200 px non-Retina manual captures.

---

## TL;DR

| Metric | v0.31.1 | v0.32.0 | Δ |
|---|---|---|---|
| Tests | 1227 | 1235 | +8 |
| Dashboard screenshot tooling | manual only | `--screenshot CLI` | NEW |
| docs/images/ resolution | ~800-1200 px | 2880×1800 (Retina @2x) | ~3× |
| New images | 0 | 1 (`import-folder-result.png`) | +1 |
| Mermaid diagrams | 0 | 1 (`example-claude-mcp-flow.md`) | +1 |
| graphify integration | broken (subprocess) | redesigned (BYO graph.json) | redesign |
| External repos updated | 0 | 1 (`gemini-delegate-skill`) | +1 |

The headline shift: **`research-hub dashboard --screenshot TAB --out PATH --scale 2`** ships a permanent solution to "screenshots look bad." Re-shooting any tab now takes one CLI command instead of opening a browser, navigating, and capturing manually.

---

## Tracks delivered

### Track A — Dashboard `--screenshot` CLI (Codex, commit `12603f2`)

`src/research_hub/dashboard/screenshot.py` (NEW, ~150 LOC) renders the self-contained `dashboard.html` via headless Playwright Chromium at user-controlled `device_scale_factor`.

- 7 tabs supported (overview / library / briefings / writing / diagnostics / manage + crystal alias for briefings)
- `--scale 2` default = Retina-grade (2880×1800 from 1440×900 viewport)
- `--scale 3` = print-quality (5760×3600)
- Custom viewport via `--viewport-width / --viewport-height`
- `--screenshot all --out-dir DIR` for batch capture
- Graceful `PlaywrightNotInstalled` if the `[playwright]` extra is missing
- 5 new tests (Playwright mocked) in `tests/test_v032_screenshot.py`

### Track B — Re-shot 5 dashboard PNGs (Claude direct, this commit)

All 5 demo PNGs in `docs/images/` re-captured at scale=2:
- `dashboard-overview.png` — 96 KB → 666 KB (~7× more detail)
- `dashboard-library-subtopic.png` — 94 KB → 511 KB
- `dashboard-manage-live.png` — 118 KB → 571 KB
- `dashboard-crystals.png` — 92 KB → 666 KB (now from the briefings tab)
- `dashboard-diagnostics.png` — 100 KB → 580 KB

Each is now 2880×1800 native (Retina). GitHub auto-downscales for non-Retina viewers; HiDPI users see crisp 2× pixels.

`obsidian-graph.png` remains the v0.29 manual capture (Obsidian has no PNG export API; documented manual workflow in `docs/screenshot-workflow.md`).

### Track C — New image + Mermaid (Claude direct)

- `docs/images/import-folder-result.png` (NEW) — Library tab showing imported docs from `import-folder` workflow
- `docs/import-folder.md` + `docs/import-folder.zh-TW.md` embed the new image
- `docs/example-claude-mcp-flow.md` — NEW Mermaid sequence diagram showing user → Claude → MCP → research-hub → vault flow visually (renders natively on GitHub since 2022)

### Track D — graphify integration redesign (Codex, commit `2b5f602`)

v0.31.1 audit documented the discovery: graphify is a coding-skill, not a standalone CLI for first-time extraction. v0.31's `--use-graphify` always failed soft.

v0.32 redesign:
- `--use-graphify` flag preserved for backward compat (now emits `DeprecationWarning` and skips integration)
- New `--graphify-graph PATH` flag accepts a pre-built `graph.json` (user runs `/graphify ./project` in Claude Code first)
- `graphify_bridge.run_graphify()` deprecated — raises `GraphifyNotInstalled` with actionable 2-step workflow guidance
- `graphify_bridge.parse_graphify_communities()` and `map_to_subtopics()` unchanged (still useful for parsing pre-built graph.json)
- `docs/import-folder.md` "Deep extraction with graphify" section rewritten with the 2-step workflow
- 3 new tests in `tests/test_v032_graphify_redesign.py`
- 3 v0.31 graphify tests updated for new deprecated behavior

### Track E — Housekeeping (Claude direct)

- `docs/screenshot-workflow.md` (NEW) — usage guide for the new screenshot CLI, custom dimensions, batch capture, Obsidian graph manual workflow, troubleshooting
- `docs/audit_v0.32.md` (this file)
- `pyproject.toml`: 0.31.1 → 0.32.0
- `CHANGELOG.md`: v0.32.0 entry
- README.md + zh-TW.md: badges + version + Architecture docs links

**Task #124 (restore archived vault) status:** archive contents at `C:/Users/wenyu/knowledge-base-archive-20260415/temp-screenshot-20260415/` are 9 legacy folder names (ABM-Theories, Behavioral-Theory, etc.) predating the v0.27 cluster slug standardization. Auto-restoring would create a mismatch between cluster registry and folder names. Defer to user-driven restoration when needed; **leaving #124 pending** rather than risking corruption.

### Track F — gemini-delegate-skill repo fix (Claude direct + push)

External repo: `https://github.com/WenyuChiou/gemini-delegate-skill`, commit `7493c8e` (pushed).

- `SKILL.md`: NEW "Fourth rule" section documenting the `Error executing tool write_file: params must have required property 'file_path'` bug from v0.31 work + B-grade translation-quality caveat
- `scripts/run_gemini.sh` + `.ps1`: new `--verify-file PATH` (repeatable) + `--verify-sentinel TEXT` flags. After gemini exits, check expected files exist + non-empty + optionally contain a sentinel string. Exit 1 with `VERIFY_FAILED` if not.
- `README.md`: "Known Limitations" section
- Local skill at `~/.claude/skills/gemini-delegate/` synced

### Track G — Gemini zh-TW translations

**Skipped this release.** v0.31's Gemini test produced B-grade output requiring 25% manual rewrite. Track F's `--verify-file` flag + SKILL.md updates make the next attempt safer, but no NEW zh-TW translations were urgently needed for v0.32 (existing zh-TW docs from v0.31 still apply; Track C just added an image link which Claude updated directly in both EN and zh-TW).

The `import-folder.zh-TW.md` got Track D's graphify section update via Claude direct (small change, not worth Gemini overhead).

---

## Test count

```
v0.31.1: 1227 passed, 14 skipped, 2 xfailed, 1 xpassed
v0.32.0: 1235 passed, 14 skipped, 2 xfailed, 1 xpassed
Delta:   +8 (5 from Track A screenshot, 3 from Track D graphify redesign)
```

3 v0.31 graphify tests were updated in-place (test count unchanged for those).

---

## Live verification

### Screenshot CLI

```bash
research-hub dashboard --screenshot overview --out /tmp/test.png --scale 2
file /tmp/test.png
# expect: PNG image data, 2880 x 1800, 8-bit/color RGBA
```
✅ Verified during Track B work.

### graphify redesign

```bash
research-hub import-folder /tmp/test --cluster X --use-graphify
# Expect: DeprecationWarning about --use-graphify; import proceeds without sub-topic assignment

research-hub import-folder /tmp/test --cluster X --graphify-graph /path/to/graph.json
# Expect: each imported note gets subtopics: frontmatter from graph.json communities
```
✅ Verified via test_v032_graphify_redesign.py.

### gemini-skill --verify-file

```bash
bash gemini-delegate-skill/scripts/run_gemini.sh --verify-file /tmp/nope.txt
# Expect: exit 1
```
✅ Verified.

### --purge-folder works as expected (v0.31.1 fix in active use)

```bash
research-hub clusters delete v032-demo --purge-folder
# Expect: notes_unbound: 2, purged_folders: ["...raw/v032-demo"]
# raw/ folder actually removed
```
✅ Verified during Track C demo cleanup.

---

## v0.33+ backlog (unchanged from v0.31.1)

- **Codex Phase 2** — structured memory layer (entities/claims/methods/datasets). Multi-release research project.
- **Codex Phase 3** — tool consolidation (50+ tools → 5 task-level wrappers + low-level primitives kept).
- **Connector abstraction** (NotebookLM → optional plug-in interface).
- **`cli.py` / `mcp_server.py` monolith splits** — still HIGH RISK, still deferred.
- **Search recall xfail baselines** (v0.26).
- **Restore archived vault** (Task #124) — needs user-driven decision on whether legacy folder names should be merged back.
- **Live NotebookLM round-trip test** — needs user to open browser + CDP attach.
- **Citation graph optimization for >500-paper clusters.**
- **Zotero key encryption** via OS keyring.
- **`.dxt` Claude Desktop extension.**

---

## Release commits

```
2b5f602 fix(v0.32-D): graphify redesign + Mermaid flow diagram
12603f2 feat(v0.32-A): dashboard --screenshot CLI for high-DPI Playwright captures
+ track-B PNGs commit
+ track-E housekeeping + release commit
+ external: gemini-delegate-skill 7493c8e
```

PyPI: `pip install -U research-hub-pipeline` after GHA auto-publishes from the v0.32.0 tag.

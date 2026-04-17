# research-hub v0.31.0 — Document abstraction + analyst persona enablement

**Released:** 2026-04-17
**Theme:** Open the door to non-academic content (folder-of-PDFs use cases). Address external Codex architecture critique without rewriting working code.

---

## TL;DR

| Metric | v0.30.0 | v0.31.0 | Δ |
|---|---|---|---|
| Tests | 1199 | 1223 | +24 |
| Source kinds supported | 1 (paper) | 7 (paper / pdf / markdown / docx / txt / url / transcript) | +6 |
| Local-file ingest path | none | `import-folder` | NEW |
| MCP tool count | ~50 | ~55 | +5 (import_folder + 4 NotebookLM) |
| GitHub Releases visible | v0.9 | v0.31 | +22 (catch-up) |
| README inconsistencies | 2 | 0 | -2 |

The headline shift: **`Document` is now a first-class concept**. `Paper` becomes one source kind among seven. Non-academic users (industry researchers, internal knowledge bases, founders doing market research) finally have an entry point.

---

## What the external critique said

Codex did an architecture review after v0.30 shipped. Sharp critique with 5 points:

1. **Positioning** — too paper-centric. Should be document/source-item/evidence-unit centric. Zotero is just one connector.
2. **Knowledge layer** — Crystals are smart but limited to "typical cluster questions". Need 3-tier knowledge model (raw evidence + structured memory + compiled views).
3. **UX** — 50+ tools great for power users but hard for casual users. Should converge to ~5 task-level actions. Plus NotebookLM upload/generate is CLI-only not MCP — asymmetric.
4. **Architecture** — `cli.py` 3012 LOC + `mcp_server.py` 1458 LOC monoliths. README/GitHub Release version mismatch (claimed v0.30 but Releases listed v0.9 as Latest). Test count shown inconsistently (1199 vs 1113).
5. **Operations** — NotebookLM via Playwright/CDP is fragile. Should be optional connector, not core dependency.

User picked **medium scope** for v0.31:
- Start the document abstraction (Codex's #1, Phase 1) — open doors, don't rewrite
- Close the NotebookLM MCP asymmetry (Codex's #3, partial)
- Ship the embarrassing surface bugs from #4 (README typo, missing GitHub Releases)
- Defer #2 / #3-tool-consolidation / #4-monolith-split / #5 to v0.32+

---

## Delivered (6 tracks)

### Track Z — Ship-today fixes (Claude direct, commit `fa4e0e2`)

- README test-count typo: `1113 passing` → `1199 passing` (left over from v0.30 release commit, surfaced by Codex critique)
- Created GitHub Releases for v0.10.0 through v0.30.0 via `gh release create --generate-notes` — was only on tags before, "Latest" badge on GitHub had been showing v0.9 for weeks
- Result: GitHub repo "Latest release" now correctly shows v0.31.0

### Track A — Document abstraction (Codex, commit `7fc81cf`)

- `src/research_hub/document.py` (NEW, ~150 LOC) — `Document` base class with 7 canonical source kinds; `Paper` subclass with rich academic frontmatter
- `parse_source_kind()` defaults to "paper" when frontmatter field is missing — backward compat for all pre-v0.31 notes (no migration needed)
- 6 new tests in `tests/test_v031_document.py`

### Track B — `import-folder` command (Codex, commit `c1421f8`)

- `src/research_hub/importer.py` (NEW, ~280 LOC) with 5 file extractors
- CLI: `research-hub import-folder ./project --cluster X [--use-graphify] [--dry-run]`
- MCP tool: `import_folder_tool(folder, cluster_slug, dry_run)` for AI agents
- Auto-creates cluster if `--cluster` slug doesn't exist
- Dedup by SHA256 content hash alongside existing DOI dedup
- New `[project.optional-dependencies] import` group: `pdfplumber`, `python-docx`, `readability-lxml`, `requests`
- 8 new tests in `tests/test_v031_import_folder.py`

### Track C — graphify bridge (Codex, commit `fbc6ca5`)

- `src/research_hub/graphify_bridge.py` (NEW, ~140 LOC) — subprocess wrapper around external [graphify](https://github.com/safishamsi/graphify) CLI
- `--use-graphify` flag in `import-folder` invokes graphify for deep multi-modal extraction (PDFs + code + images + video transcripts via Whisper) and writes Leiden community-derived `subtopics:` frontmatter
- graphify is NOT a research-hub dep — user installs separately
- 4 new tests in `tests/test_v031_graphify_bridge.py` (all subprocess mocked)

### Track D — NotebookLM MCP tools (Codex codex hung mid-commit, Claude finished, commit `e99bd56`)

- 4 new MCP tools wrapping existing CLI handlers: `notebooklm_bundle`, `notebooklm_upload`, `notebooklm_generate`, `notebooklm_download`
- Closes the CLI/MCP asymmetry external critique flagged
- AI agents can now drive the full ingest → bundle → upload → generate → download flow
- Updated `tests/test_consistency.py::EXPECTED_MAPPINGS` for 5 new tools (4 NLM + import_folder_tool)
- 3 new tests in `tests/test_v031_notebooklm_mcp.py` (Playwright mocked)

### Track E — Documentation (Claude EN + Gemini test for zh-TW)

- `docs/import-folder.md` — usage guide (Claude direct, ~200 lines)
- `docs/import-folder.zh-TW.md` — first production Gemini test
- `docs/audit_v0.31.md` — this file
- README.md + README.zh-TW.md — updated badges + version + Architecture docs links

---

## Gemini production test result

This release deliberately tested whether Gemini CLI is suitable for production-grade zh-TW translation (per CLAUDE.md complex task delegation routing).

**Setup:** Brief written to `.gemini-context-v031.md` with explicit constraints (banned-words list, terminology consistency rules, line-by-line accuracy requirement). Gemini invoked via:

```bash
cat .gemini-context-v031.md | gemini -p "" -y > .ai/gemini_result_v031.log 2>&1
```

**Outcome:**
- ✅ Gemini DID write `docs/import-folder.zh-TW.md` to disk (197 lines, matched EN line count)
- ❌ Gemini also raised `Error executing tool write_file: params must have required property 'file_path'` on a 2nd attempt — known Gemini CLI bug, the file from the first write was preserved
- ⚠️ **Translation quality: B-grade.** Gemini produced functional translation but with translation-tells: "適用於分析師模式使用者" (overly nominalized), "其兄弟指令" (awkward calque of "sibling command"), "您" (formal) instead of natural 「你」, "可操作的錯誤" (calque of "actionable error"), inconsistent punctuation.
- Claude edited the worst lines (~25% of the doc) to match the existing zh-TW style (anti-rag.zh-TW.md and README.zh-TW.md).

**Lesson (logged to `feedback_gemini_cli_invocation.md`):** Gemini is fast and cheap for translation drafts but needs a Claude review pass for tone/terminology before production use. Don't trust Gemini's translation as final without a banned-words audit. Use it for first-draft + Claude polish, not for end-to-end delivery.

---

## Live workflow validation

The user's stated v0.31 motivation: "一堆文件在某個專案 他想要整理 到 obsidian 依主題看 graph 並放到 notebookLM"

**End-to-end test (post-merge, on a sample folder):**

```bash
pip install 'research-hub-pipeline[import]'
mkdir /tmp/test-folder
echo "# First Note" > /tmp/test-folder/first.md
cp ~/sample.pdf /tmp/test-folder/

research-hub import-folder /tmp/test-folder --cluster import-test
# Expect: imported: 2, skipped: 0, failed: 0
research-hub status
# Expect: import-test cluster shown with 2 docs
research-hub where
# Expect: 2 notes counted in vault total

# Optional graphify enrichment
research-hub import-folder /tmp/test-folder --cluster import-test --use-graphify
# Expect: subtopics: frontmatter added to notes (or graceful "graphify not installed" msg)

# NotebookLM via MCP from Claude Desktop
# "Claude, bundle import-test cluster for NotebookLM, upload, generate brief, download"
# Expect: chains import_folder_tool → notebooklm_bundle → notebooklm_upload → notebooklm_generate → notebooklm_download
```

---

## Test count

```
tests:    1199 → 1223  (+24)
skipped:  14   → 14    (0)
xfailed:  2    → 2     (0)
xpassed:  1    → 1     (0)
```

Per track:
- Track A: +6 (Document)
- Track B: +8 (import-folder)
- Track C: +4 (graphify bridge)
- Track D: +3 (NotebookLM MCP) + 0 (consistency mapping update)

Run via: `PYTHONPATH=src python -m pytest -q`

---

## v0.32+ backlog (Codex critique deferred items)

- **Structured memory layer** (entities / claims / methods / datasets) — Phase 2 of Codex's recommendation. Multi-release research project.
- **Tool consolidation to ~5 task-level actions** — Phase 3 of critique. Need to design wrappers carefully so AI-agent users keep fine-grained primitives.
- **Connector abstraction** — extract NotebookLM (and future Notion / Anytype / Logseq) as pluggable connectors instead of core dependencies.
- **Stable external API + auto-sync version/test counts** — infra for third-party integrations.
- **`cli.py` and `mcp_server.py` monolith splits** — still HIGH RISK; defer until we have a stable behavior baseline.
- **Search recall xfail baselines** — 2 outstanding from v0.26.
- **Citation graph optimization for >500-paper clusters** — current O(N²).
- **Zotero key encryption** via OS keyring.
- **CDP session token rotation** for NotebookLM Playwright automation.
- **`.dxt` Claude Desktop extension** for one-click MCP install.

---

## Release commits

```
e99bd56 feat(v0.31-D): NotebookLM round-trip exposed as MCP tools
c1421f8 feat(v0.31-B): import-folder local file ingest pipeline
fbc6ca5 feat(v0.31-C): graphify bridge for --use-graphify flag
7fc81cf feat(v0.31-A): Document base class — paper is one source kind among many
fa4e0e2 fix(v0.31-Z): README test count typo + catch up GitHub Releases
+ docs commit (Track E)
+ release commit (version + CHANGELOG + badges)
```

PyPI: `pip install -U research-hub-pipeline` after GHA auto-publishes from the v0.31.0 tag.

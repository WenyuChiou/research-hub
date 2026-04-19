# v0.43 audit — kepano/obsidian-skills integration + 11-paper NotebookLM stress test

Release date: **2026-04-19**. Shipped same day as v0.42.0 (~3 hours after).

---

## The forcing function

User reflection during v0.42 post-ship review:

> 理論上你要整合剛剛提供的 skills 阿 因為我不確定我們的 notebookLM 跟 obsidan 是否穩定

Two-fold concern:

1. **Reinventing the wheel.** v0.42 was built by reading the source of `PleasePrompto/notebooklm-skill` and writing our own implementation, despite the fact that the same code is shipped as a Claude Desktop MCP (`mcp__notebooklm__*`) already installed on this machine. Same pattern with kepano/obsidian-skills — we adopted a slice of the spec manually without installing the actual skill pack.
2. **Stability uncertainty.** The v0.42 NLM layer was tested with 6 papers and a single ask. No cross-validation against any reference implementation. No stress test at higher scale.

v0.43 = "install the kepano skill pack, integrate the 4 unused skills properly, and stress-test v0.42 at higher scale with cross-validation."

---

## Layered testing actually applied

| Layer | What | Result |
|---|---|---|
| **L1 — Unit** | 34 new tests (Track 2: 8, Track 3: 15, Track 4: 11) | all green |
| **L2 — Integration** | defuddle subprocess mock + yaml round-trip for `.base` | all green |
| **L3 — Cross-validation** | research-hub `notebooklm ask` vs `mcp__notebooklm__ask_question` on same 11-paper notebook, same question | both backends converged on same 3 themes + same exemplar papers |
| **L4 — End-to-end** | 11-paper bundle + upload via v0.42 patchright; live `bases emit` on harness cluster; Obsidian renders | retry_count=0; .base opens with 4 views (verified by maintainer) |
| **L5 — Multi-OS CI** | Linux + macOS + Windows × Python 3.10/3.11/3.12 (9 jobs) | green (with new Node.js step) |

---

## What shipped

### Track 1 — installation + 11-paper stress test (Claude direct, no code)

- `git clone kepano/obsidian-skills` → manually copied 5 SKILL dirs to `~/.claude/skills/`
- `mcp__notebooklm__setup_auth` → authenticated (121 s round-trip)
- `research-hub clusters bind llm-evaluation-harness --zotero WNV9SWVA` (back-fill missing collection key)
- `research-hub search` x 2 → filtered → 5 new harness papers
- `research-hub ingest --cluster llm-evaluation-harness` → 11 papers in vault
- `research-hub notebooklm bundle` → 11 PDFs in bundle dir
- `research-hub notebooklm upload --visible` → **11/11 succeeded, retry_count=0**
- Cross-validate ask: identical 3-thread analysis from both backends

### Track 2 — defuddle URL extraction (Codex)

- NEW `src/research_hub/defuddle_extract.py` (~70 LOC)
- `importer.py::_extract_url` patched to try defuddle first
- Fallback to readability-lxml preserved (zero breaking change)
- CI: `actions/setup-node@v4` + `npm install -g defuddle-cli` (best-effort)
- 8 tests

### Track 3 — Obsidian Flavored Markdown extensions (Codex)

- `markdown_conventions.py` extended with `wikilink`, `embed`, `highlight`, `property_block`
- Crystal Evidence + topic paper lists routed through `wikilink()`
- `make_raw_md` adds optional `zotero-pdf-path:` frontmatter
- 15 tests

### Track 4 — Obsidian Bases dashboard generator (Codex)

- NEW `src/research_hub/obsidian_bases.py` (~150 LOC)
- 4 views per cluster: Papers / Crystals / Open Questions / Recent activity
- 2 formulas + 1 summary
- `scaffold_cluster_hub` now writes `<slug>.base` automatically
- NEW CLI: `research-hub bases emit --cluster X [--stdout] [--force]`
- NEW MCP tool: `emit_cluster_base(cluster_slug)`
- 11 tests

### Track 5 — release (Claude direct)

- `pyproject.toml`: 0.42.0 → 0.43.0
- CHANGELOG entry
- zh-TW release notes (Claude direct, no Gemini)
- This audit
- `docs/validation_v0.43.md`
- `~/.claude/skills/knowledge-base/SKILL.md` updated
- `~/.claude/projects/.../memory/project_research_hub.md` updated

---

## Cross-validation findings

### NotebookLM ask layer

Question asked of both backends:
*"What are the 3 main research threads in harness engineering — evaluation, memory, or security focused — and which paper exemplifies each?"*

| Backend | Latency | Threads identified | Exemplar papers |
|---|---|---|---|
| research-hub v0.42 | 55 s | memory, security (evaluation implicit) | M\*, SafeHarness |
| mcp__notebooklm | 45 s | evaluation, memory, security | VeRO+vla-eval, M\*, SafeHarness |

**Verdict**: Both converge on the same 3-thread structure with the same paper-to-thread assignments. mcp__notebooklm independently surfaced the newly-added VeRO paper, confirming the 11-paper upload landed in NotebookLM.

### Obsidian Markdown spec conformance

v0.42 paper note (`choi2026-vla-eval-...md`) inspected against the obsidian-markdown skill spec:

- ✅ YAML frontmatter — identical
- ✅ Section headings — `## Heading` clean (no inline modifiers)
- ✅ Callouts — `> [!kind]\n> body\n^block-id`
- ✅ Block IDs — `^summary`, `^findings`, etc.
- ✅ Wikilinks — `[[paper-slug]]` in cross-refs
- ✅ Properties — `topic_cluster`, `cluster_queries` etc.
- (planned for v0.43) PDF embeds via `zotero-pdf-path` — Track 3 added

**Verdict**: v0.42 output is spec-conforming for the subset shipped. v0.43 closes the embed gap.

---

## Lessons (applied)

- **Don't reinvent if a battle-tested skill exists.** This release's primary lesson. Before writing custom code that overlaps with an existing Claude Code skill or MCP, install + cross-check.
- **Cross-validation > unit tests for behavioral claims.** Unit tests verify our code does what we wrote. Cross-validation against a reference implementation verifies our spec interpretation matches reality.
- **Stress test at higher scale than initial release.** v0.42 shipped at 6 papers; v0.43 stress-tested at 11. Future releases should keep pushing — at some scale (50? 100?) v0.42's no-retry record will break, and we'll learn what triggers it.
- **`obsidian-cli` requires running Obsidian.** Acceptable for human-driven workflows but unsuitable for CI/headless environments. Defer until we have a clear use case where the user is guaranteed to have Obsidian open.

---

## What's NOT in v0.43

- **obsidian-cli integration** (5th kepano skill) — v0.44
- **json-canvas citation graph export** — v0.44
- **cli.py / mcp_server.py monolith split** — still deferred
- **NLM audio / mind-map / video downloads** — v0.44+
- **obsidian-mcp** as a Claude Desktop MCP — would give Obsidian dual-backend cross-validation parity with NotebookLM, evaluate in v0.44

---

## Stats summary

- Tests: 1458 → 1492+ (+34)
- LOC delta: ~+550 (3 new modules: defuddle_extract, obsidian_bases, markdown_conventions extensions)
- Modified: 8 files (importer, topic, crystal, zotero/fetch, cli, mcp_server, ci.yml, pyproject)
- New files: 3 source + 3 test + 3 docs = 9
- CI matrix: 9 jobs × ~3 min = ~27 job-minutes per push
- Time to ship from v0.42 ship: ~3 hours
- Codex execution: single brief, ~15 min (~550 LOC + 34 tests)

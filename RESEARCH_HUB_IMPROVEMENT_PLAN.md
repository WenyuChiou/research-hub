# Research Hub Improvement Plan (Phase 1–3)

*Written: 2026-04-09 | Author: Claude (with Eric)*

---

## 1. Current State Summary

The Research Hub is a 7-step pipeline (~3,000 LOC Python) that ingests academic papers into Zotero, writes Obsidian `.md` notes, rebuilds a hub index (topic pages + project pages + root index), and uploads sources to NotebookLM for Q&A. As of 2026-04-09 the vault holds 489 papers across 27 hub topics. The pipeline is functional and runs end-to-end on Eric's machine, but every script hard-codes `C:\Users\wenyu\knowledge-base` (or forward-slash variants), making the system unmovable and unshare-able. API credentials sit in plaintext `config.json`. `build_hub.py` re-parses all 489 `.md` files from scratch on every run. `categorize_graph.py` and other scripts overwrite `.obsidian/graph.json` in-place with no backup. Per-paper errors are swallowed silently. NotebookLM upload (Step 5) is synchronous and blocks Steps 6–7 even when there is nothing to upload. There is no `--dry-run` mode, no test suite, and no configuration wizard.

---

## 2. Three Researcher Pillars

### 查詢 (Query) — Find the right paper fast

| | Today | Missing | Target |
|---|---|---|---|
| What Hub does | 7-step pipeline adds papers via keyword search + manual selection | No semantic query over the vault; search is limited to Zotero MCP title/tag match | RAG over all 489 notes; ask "which papers discuss bounded rationality in flood buyouts?" → ranked results with one-line summaries |
| Gaps | No full-text index. Hub topic pages are keyword-matched, not semantically clustered. No duplicate detection across DOI/title variants. | Citation graph auto-suggest only manual. No reading-status filter in query. | Full-text vector index (e.g. ChromaDB or Obsidian Semantic Search plugin) over all notes; duplicate DOI merge at ingest; citation-aware "related papers" sidebar |

### 整理 (Organize) — Keep the library clean and structured

| | Today | Missing | Target |
|---|---|---|---|
| What Hub does | WIKI_MERGE normalizes collection names; `fix_orphans.py` assigns papers to topics; `categorize_graph.py` color-tags by research line | No incremental build (489 files re-parsed every run). No audit log for classify step. `graph.json` overwritten without backup. Per-paper errors silently swallowed. Hardcoded paths block multi-user or CI use. | Incremental `build_hub.py` (only re-parse changed/new `.md` files). Classification audit log (`classification_log.jsonl`). Timestamped graph backups. Per-paper error log file per run. Portable `pathlib`-based config loaded from `~/.claude/skills/knowledge-base/config.json` or env vars. |
| Gaps | API key in plaintext config.json. No `config.json.example`. No setup wizard. | | Config wizard (`setup_hub.py --init`) + `config.json.example` + env-var fallback with deprecation warning |

### 學習 (Learn) — Extract insight, not just storage

| | Today | Missing | Target |
|---|---|---|---|
| What Hub does | NotebookLM notebooks hold paper sources for interactive Q&A. Obsidian notes have auto-generated Summary/Key Findings/Methodology/Relevance. Hub topic pages link related papers. | Async upload (blocks pipeline). No reading-path generator ("I want to understand LLM-ABM, what order to read?"). No auto cross-summary per topic. No research-gap narrative generation. | Async NotebookLM upload queue (fire-and-forget, status file). Auto-summary per hub topic (3 sentences from top-cited papers). Reading path generator (by sub-category + citation count). Two-phase classify: keyword fast-path → LLM deep-path only when uncertain. |
| Gaps | | | |

---

## 3. Phased Roadmap

### Phase 1 (this task) — Foundations: Portable, Auditable, Testable

**Goal:** System runs identically on any machine. All errors are visible. Config is safe. Tests pass.

- Parameterize all hardcoded paths → `pathlib.Path`, read from `~/.claude/skills/knowledge-base/config.json` (new schema), fall back to env vars
- API key migration: read `ZOTERO_API_KEY` / `ZOTERO_LIBRARY_ID` from OS env first, then `~/.claude/.env`, then config.json (with deprecation warning), never delete Eric's config.json
- Per-paper error logs: each pipeline run writes `pipeline_errors_<timestamp>.jsonl` to `logs/` sub-dir
- `graph.json` backup: before any script touches `.obsidian/graph.json`, `cp graph.json graph.json.bak.<epoch>`
- `--dry-run` flag on `research-hub run`: validates config + input, no writes
- Classification audit log: `classification_log.jsonl` appended per classify call
- `config.json.example` created at `~/.claude/skills/knowledge-base/`
- `setup_hub.py --init` wizard: prompts for paths, writes config, validates
- Test suite: `tests/test_config.py`, `tests/test_build_hub.py`, `tests/test_graph_backup.py`, `tests/test_pipeline_logging.py`
- **Zero behavioral change for existing Eric setup** — same default paths, same pipeline outputs

### Phase 2 (future) — Researcher Features

- Semantic query (RAG) over vault: ChromaDB or Obsidian Semantic Search plugin index
- Incremental `build_hub.py`: hash-check `.md` files, only re-parse changed ones
- Duplicate detection: cross-reference DOI + title at ingest, suggest merge
- Citation graph auto-suggest: after every new paper, show top 3 cited/citing → offer to add
- Two-phase classification: keyword fast-path (instant) → LLM deep-path only if uncertain
- Reading path generator: given a topic, produce ordered reading list by sub-category + citation count
- Auto-summary per hub topic: 3-sentence synthesis from top-cited papers
- Research-gap narrative: scan thin topics (< 5 papers) → draft a 1-paragraph gap statement

### Phase 3 (future) — Plugin Packaging

- Split into 3 Claude Code sub-plugins: `zotero-crud`, `research-hub-pipeline`, `obsidian-vault-template`
- Each sub-plugin has its own `SKILL.md`, `config.example.json`, `setup_wizard.py`
- Config wizard that detects OS (Windows/Mac/Linux) and sets paths accordingly
- Registry submission to Claude Code plugin marketplace
- Multi-user support: `~/.claude/skills/knowledge-base/config.json` → per-user, not per-repo

---

## 4. Phase 1 Work Breakdown

### Files to Touch

| File | Change |
|---|---|
| `build_hub.py` | Replace 4 hardcoded path vars with `get_config()` call |
| `categorize_graph.py` | Replace `raw_dir`, `hub_dir` with config; add graph backup before write |
| `fix_orphans.py` | Replace `raw_dir`, `hub_dir` with config |
| `src/research_hub/pipeline.py` | Replace `LOG`, `OUT`, `PAPERS_JSON`, `KB` with config; add `--dry-run` flag; add per-paper error logging to `logs/` dir |
| `fetch_zotero.py` | Replace `KB` with config |
| `add_theory_links.py` | Scan + replace any hardcoded paths |
| `reorganize_subcategories.py` | Scan + replace any hardcoded paths |
| `~/.claude/skills/zotero-skills/scripts/zotero_client.py` | Add env-var fallback before config.json read; emit deprecation warning if using plaintext config |
| **NEW** `hub_config.py` | Shared config loader: reads `~/.claude/skills/knowledge-base/config.json`, falls back to env vars, resolves `~` in paths |
| **NEW** `setup_hub.py` | `--init` wizard: prompts for base path, zotero credentials, writes config |
| **NEW** `~/.claude/skills/knowledge-base/config.json.example` | Template for new users |
| **NEW** `~/.claude/skills/knowledge-base/config.json` | Actual config for Eric (pre-filled with current paths) |
| **NEW** `logs/` dir | Created by `hub_config.py` on first use |
| **NEW** `tests/test_config.py` | Test config loading, env var fallback, path resolution |
| **NEW** `tests/test_build_hub.py` | Test YAML parsing, WIKI_MERGE, topic matching (mock filesystem) |
| **NEW** `tests/test_graph_backup.py` | Test backup logic, filename format, idempotency |
| **NEW** `tests/test_pipeline_logging.py` | Test per-paper error log writing, JSONL format |

### Config Schema (`~/.claude/skills/knowledge-base/config.json`)

```json
{
  "knowledge_base": {
    "root": "~/knowledge-base",
    "raw": "~/knowledge-base/raw",
    "hub": "~/knowledge-base/hub",
    "projects": "~/knowledge-base/projects",
    "logs": "~/knowledge-base/logs",
    "obsidian_graph": "~/knowledge-base/.obsidian/graph.json"
  }
}
```

Note: Zotero credentials stay in `~/.claude/skills/zotero-skills/config.json`. The new `hub_config.py` only reads path config. The `zotero_client.py` migration adds env-var fallback independently.

### `hub_config.py` API

```python
from hub_config import get_config

cfg = get_config()
cfg.root        # pathlib.Path
cfg.raw         # pathlib.Path
cfg.hub         # pathlib.Path
cfg.projects    # pathlib.Path
cfg.logs        # pathlib.Path
cfg.graph_json  # pathlib.Path
```

Reads from (in priority order):
1. `~/.claude/skills/knowledge-base/config.json` `knowledge_base.*` keys
2. Environment variables: `RESEARCH_HUB_ROOT`, `RESEARCH_HUB_RAW`, etc.
3. Hard-coded defaults: `~/knowledge-base/...` (relative to home, not Eric-specific)

### Exact Changes per Key File

**`build_hub.py`** — top-level vars change from:
```python
raw_dir = r'C:\Users\wenyu\knowledge-base\raw'
hub_dir = r'C:\Users\wenyu\knowledge-base\hub'
proj_dir = r'C:\Users\wenyu\knowledge-base\projects'
root = r'C:\Users\wenyu\knowledge-base'
```
to:
```python
from hub_config import get_config
_cfg = get_config()
raw_dir = str(_cfg.raw)
hub_dir = str(_cfg.hub)
proj_dir = str(_cfg.projects)
root = str(_cfg.root)
```
(Keep `str()` so all downstream `os.path.join` calls stay unchanged.)

**`categorize_graph.py`** / **`fix_orphans.py`** — same 2-line substitution for `raw_dir`, `hub_dir`. Plus add before any `graph.json` write:
```python
import shutil, time
graph_path = str(_cfg.graph_json)
if os.path.exists(graph_path):
    shutil.copy2(graph_path, f"{graph_path}.bak.{int(time.time())}")
```

**`research_hub.pipeline`** — replace top-level consts; add argparse `--dry-run`; wrap each paper's try/except to also write to `logs/pipeline_errors_<timestamp>.jsonl`.

**`zotero_client.py`** — in `get_client()`, before reading `config.json`:
```python
import os, warnings
api_key = os.environ.get("ZOTERO_API_KEY")
lib_id  = os.environ.get("ZOTERO_LIBRARY_ID")
lib_type = os.environ.get("ZOTERO_LIBRARY_TYPE", "user")
if not api_key:
    # fall back to config.json
    ...
    warnings.warn("ZOTERO_API_KEY not set as env var; reading from plaintext config.json (deprecated)", DeprecationWarning)
```

### Test Requirements

| Test file | What it tests |
|---|---|
| `tests/test_config.py` | `get_config()` reads correct paths; env var override works; `~` expanded to absolute path; missing config falls back to defaults |
| `tests/test_build_hub.py` | YAML front-matter parse; WIKI_MERGE normalization; topic keyword matching; paper list deduplication — all with mock filesystem (no real files) |
| `tests/test_graph_backup.py` | Backup created before write; filename has `.bak.<epoch>` suffix; no backup created if graph.json doesn't exist yet |
| `tests/test_pipeline_logging.py` | Error log written to `logs/` dir; JSONL format parseable; timestamp in filename; no crash if logs dir doesn't exist (auto-created) |

All tests: `pytest -q`. No real file I/O except via `tmp_path` fixture.

---

## 5. Delegation Strategy

| Sub-task | Agent | Why |
|---|---|---|
| `hub_config.py` (new config loader) | **Codex** | Pure Python, well-defined spec, ~60 LOC |
| Parameterize 5 scripts | **Codex** | Mechanical substitution, no judgment calls |
| `run_pipeline.py` --dry-run + error logging | **Codex** | Python refactor, clear spec |
| `zotero_client.py` env-var migration | **Codex** | Standard Python env-var pattern |
| `setup_hub.py --init` wizard | **Codex** | Input/output well-specified |
| `config.json.example` creation | **Codex** | Template generation |
| 4 pytest test files | **Codex** | Test generation is a Codex strength |
| SKILL.md updates (path references, Step 6 command) | **Gemini** | Bilingual docs, CJK content |
| Architecture review + plan (this file) | **Claude** | Judgment, context, project history |
| Final integration + verification | **Claude** | pytest run, diff review, commit |

---

## 6. Phase 1 Success Criteria

- [ ] `pytest -q` exits 0 (all 4 test files pass)
- [ ] `research-hub run --dry-run` succeeds on current `~/knowledge-base/`
- [ ] No hardcoded absolute paths remain in `*.py` (verify with grep for platform-specific path prefixes)
- [ ] `~/.claude/skills/knowledge-base/config.json` exists with correct paths for Eric
- [ ] `~/.claude/skills/knowledge-base/config.json.example` exists
- [ ] `ZOTERO_API_KEY` env var read checked before config.json (with deprecation warning)
- [ ] `.obsidian/graph.json.bak.<epoch>` created when `categorize_graph.py` runs
- [ ] `logs/` directory created, `pipeline_errors_<timestamp>.jsonl` written per run
- [ ] Existing `raw/`, `hub/`, `projects/` content untouched
- [ ] 489 existing paper `.md` files unchanged
- [ ] `build_hub.py` still produces identical hub topic pages on current vault

---

## 7. Zero-Data-Loss Commitments

- `graph.json` backup: timestamped `.bak.<epoch>` before every write
- `raw/*.md` files: never touched by Phase 1 (read-only in all scripts)
- `config.json` (zotero-skills): never deleted or overwritten — only migration layer added
- `hub/` and `projects/` output files: same content, same filenames
- No migration runs automatically on first import — only on explicit `setup_hub.py --init`

---

*Next: Phase 1 implementation (Codex delegate) → verify → commit.*
*Phase 2 ETA: after Phase 1 is stable in production for 2+ weeks.*

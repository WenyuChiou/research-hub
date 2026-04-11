---
name: knowledge-base
description: "Research Hub pipeline for academic literature management. Searches papers (arXiv, Semantic Scholar, CrossRef, PubMed), saves to Zotero with collection assignment, creates Obsidian notes with auto-generated summaries, rebuilds hub index, and uploads to NotebookLM. Use when the user mentions Research Hub, finding papers, literature search, Obsidian notes, knowledge base, NotebookLM, paper management, citation graph, research gaps, or says '幫我放到Research Hub'."
---

# Research Hub — Academic Literature Pipeline

One-command knowledge management: search → save → organize → upload. Individual actions also available as standalone sub-commands.

**Trigger phrases:** "幫我放到Research Hub", "放到Research Hub", "find papers about X", "add to Research Hub", or any request combining paper search + organize + save.

**Language policy:** All generated content in **English** by default. Trigger phrases may be Chinese. Only switch to Chinese when user explicitly requests it.

---

## Installation & Setup

```bash
# 1. Clone and install
git clone https://github.com/WenyuChiou/research-hub.git
cd research-hub
pip install -e .

# 2. Configure paths
cp config.json.example config.json
# Edit config.json: set "root" to your knowledge base directory

# 3. Set Zotero credentials (env vars or ~/.claude/.env)
export ZOTERO_API_KEY=your_key
export ZOTERO_LIBRARY_ID=your_library_id

# 4. Verify everything works
python scripts/verify_setup.py
```

---

## Pipeline Overview

```
User trigger + topic + category
  → 1. Classify   (LLM-based → major category + sub-category)
  → 2. Search     (Semantic Scholar + WebSearch + CrossRef, in parallel)
  → 3. Select     (present results table, user picks)
  → 4. Save       (Zotero item + Obsidian .md note + hub page update)
  → 5. Upload     (validate DOIs → NotebookLM via Chrome)
  → 6. Build      (run `python -m research_hub.vault.builder`, `python -m research_hub.vault.categorize`, `python -m research_hub.vault.repair`)
  → 7. Explore    (citation graph, offer to add related papers)
```

---

## Step 1: Classify

Claude reads title + abstract and classifies using LLM judgment (no keyword matching):

| Major Category | method-type | Description |
|---|---|---|
| Survey Research | `survey` | Questionnaire, interview, stated-preference |
| Traditional ABM | `traditional-abm` | Agent-based modeling without LLMs |
| LLM ABM | `llm-agent` | LLM-powered agent simulation |

Sub-categories listed in `references/categories.md`. If uncertain, ask user to confirm.

> **Shortcut**: If user provides topic + category in trigger, skip to Step 2.

---

## Step 2: Search

**Always run Tier 1 in parallel:**

| Tier | Tool | Use |
|---|---|---|
| 1 (always) | `search_semantic` | Primary. Best metadata, year filter, citations |
| 1 (always) | WebSearch with academic domains | Google Scholar, arXiv, SSRN, Nature, ScienceDirect |
| 2 (supplement) | `search_crossref` | SSRN, Elsevier, Springer. Returns DOIs |
| 2 (if medical) | `search_pubmed` | Medical/health/behavioral topics only |

**Not usable:** `search_google_scholar` (blocked by anti-scraping). Use WebSearch instead.

---

## Step 3: Select

Present numbered table (Title, Authors, Year, Source, DOI/URL). Ask user to pick. Retrieve full metadata via `read_*_paper` tools.

---

## Step 4: Save

For each selected paper, execute 4a → 4b → 4c:

### 4a: Zotero (via zotero-skills)

> **Use the `zotero-skills` skill** (`~/.claude/skills/zotero-skills/SKILL.md`) for all Zotero operations. MCP is read-only; writes require pyzotero Web API.

```python
import sys
sys.path.insert(0, r"~/.claude/skills/zotero-skills/scripts")
from zotero_client import get_client, add_note, check_duplicate

zot = get_client()

# 1. Check duplicate
if not check_duplicate(zot, title, doi):
    # 2. Create item with collection
    template = zot.item_template("journalArticle")
    template["title"] = title
    template["creators"] = [{"creatorType": "author", "firstName": fn, "lastName": ln}]
    template["DOI"] = doi
    template["collections"] = [collection_key]
    template["tags"] = [{"tag": "method-type"}, {"tag": "sub-category"}]
    resp = zot.create_items([template])
    item_key = list(resp["successful"].values())[0]["key"]

    # 3. Add child note
    add_note(zot, item_key, "<h1>Summary</h1><p>...</p><h2>Key Findings</h2><ul><li>...</li></ul>")
```

### 4b: Obsidian Note

Write `.md` to `<vault-root>/raw/{sub-category}/{slugified-title}.md` (where `<vault-root>` is `cfg.raw` from `research_hub.config.get_config()`).

Use template from `references/paper-template.md`. Auto-generate: Summary (2-3 sentences), Key Findings (3-5 bullets), Methodology, Relevance. Follow conventions in `references/obsidian-conventions.md`.

**Language rule — strict English default.** All auto-generated sections (Summary, Key Findings, Methodology, Relevance, any Obsidian section headers) MUST be written in English, regardless of the user's trigger-phrase language. The original paper's title, abstract, and Zotero annotation excerpts stay in their source language (do not translate). This rule applies to v0.3.0+ and overrides the global Language Policy for content inside Obsidian notes. Only deviate if the user explicitly says "在筆記裡用中文" or similar.

**Default reading status.** New notes get `status: unread` in YAML frontmatter. The reading workflow progresses `unread → skimming → deep-read → cited → archived`. Hub pages filter by status to keep the vault scannable at scale.

### 4c: Update Hub Page

Append entry to `hub/methods/{parent}/{sub-category}.md`:
```markdown
- [[slugified-title]] — Authors (Year). One-line description.
```

---

## Step 5: Upload to NotebookLM

**Validate DOIs first** with `get_crossref_paper_by_doi`. Never upload paywalled URLs.

**URL priority:** arXiv PDF > preprint > OA URL > DOI (last resort, only if open).

**Notebooks:**

| Category | Notebook |
|---|---|
| LLM ABM | Hello Agent |
| Traditional ABM / Survey | Flood Risk & ABM |

Upload via Chrome: navigate → Add Source → Website → paste URL → submit. Report ✅/⚠️/❌ per paper.

---

## Step 6: Build Hub Index

Run in sequence from the repo root (cross-platform):
```bash
python -m research_hub.vault.builder
python -m research_hub.vault.categorize
python -m research_hub.vault.repair
```

---

## Step 7: Citation Graph

Look up on Semantic Scholar → present top 5 citing + cited papers → offer to add to Research Hub (loops back to Step 4).

---

## Pipeline Summary Template

```
✅ Pipeline complete!
- Searched: [N] databases
- Saved: [N] papers (Zotero + Obsidian + hub page)
- Uploaded: [N] to NotebookLM (⚠️ [N] skipped)
- Hub index rebuilt
```

---

## Standalone Actions

| # | Action | Triggers |
|---|---|---|
| 1 | Find Literature | "find papers about X", "search for X papers" |
| 2 | Rewrite Notes | "rewrite paper note", "enhance summary" |
| 3 | Organize Zotero | "clean up Zotero", "fix duplicates" |
| 4 | Sync Obsidian | "rebuild hub", "sync Obsidian", "fix orphans" |
| 5 | Upload to NotebookLM | "upload to NotebookLM", "add sources" |
| 6 | Reading Status | "我讀完了 X", "mark X as read" |
| 7 | Research Gaps | "分析研究缺口", "find research gaps" |
| 8 | Citation Graph | "explore citations for X" |

### Action details:

**1. Find Literature** — Search (Step 2) → Present → User picks → Save (Step 4). 

**2. Rewrite Notes** — Read existing `.md` in `raw/`, fill missing YAML fields, auto-generate Summary/Key Findings/Methodology/Relevance, add wikilinks.

**3. Organize Zotero** — Inspect collections/tags via MCP, identify problems, apply WIKI_MERGE normalization (see `references/categories.md`), batch-update.

**4. Sync Obsidian** — Run `python -m research_hub.vault.builder` → `python -m research_hub.vault.categorize` → `python -m research_hub.vault.repair` (Step 6).

**5. Upload to NotebookLM** — Validate DOIs → get best URL → Chrome upload (Step 5).

**6. Reading Status** — Update `status` field in YAML: `unread` → `skimming` → `deep-read` → `cited`.

**7. Research Gaps** — Scan `raw/` sub-folders, count papers, flag thin areas (< 5), suggest searches.

**8. Citation Graph** — Semantic Scholar lookup → top 5 citing + cited → offer to save (Step 7).

**Chaining:** Actions can chain: Gap Analysis → Find → Full Pipeline, or Citation Graph → Save.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Chrome file dialog blocked | Use URL-based source addition ("Website"), not file upload |
| Zotero MCP can't create items | Use pyzotero via zotero-skills. MCP is read-only |
| Item not in collection | Set `template["collections"]` before `create_items()` |
| Invalid DOI uploaded | Always validate with `get_crossref_paper_by_doi` first |
| PYTHONPATH not set | Install with `pip install -e .` and run via `python -m research_hub` |
| builder merge issues | Add aliases to WIKI_MERGE in `references/categories.md` |
| Graph colors wrong | Check `.obsidian/graph.json`, restart Obsidian |

---

## Bundled Resources

| Resource | When to read |
|---|---|
| `references/paper-template.md` | Creating Obsidian notes (Step 4b) |
| `references/categories.md` | Classification, sub-categories, WIKI_MERGE, keywords |
| `references/obsidian-conventions.md` | Markdown formatting, YAML template, hub architecture |
| `references/dataview-queries.md` | Building Dataview tables in Obsidian |
| `references/customization.md` | Adapting for other users/platforms |
| `references/setup-guide.md` | First-time setup and MCP configuration |

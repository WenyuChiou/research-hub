---
name: research-hub
description: "Knowledge management pipeline for research and analysis: search literature, verify sources, organize into Zotero/Obsidian/NotebookLM, upload PDFs, generate AI artifacts. Works for academic researchers AND data analysts. Use when the user mentions finding papers, building a knowledge base, organizing references, NotebookLM, citation management, or literature review."
---

# research-hub — Knowledge Pipeline

Search, verify, organize, and upload research material from the terminal.

**Two personas supported:**

- **Academic researcher** (default) — uses Zotero + Obsidian + NotebookLM. Citation-heavy. Needs DOI/volume/pages.
- **Data analyst** — skips Zotero (set `RESEARCH_HUB_NO_ZOTERO=1`), uses Obsidian + NotebookLM only. Works with URLs, PDFs, technical reports, white papers.

**Trigger phrases (any language):** "find papers about X", "build a knowledge base on Y", "add to Research Hub", "upload to NotebookLM", "verify this DOI", "幫我找文獻", "幫我整理資料"

---

## CRITICAL: Always confirm names before creating

**Before creating any cluster, Zotero collection, or NotebookLM notebook, you MUST:**

1. Call `propose_research_setup(topic)` to get suggested names
2. Show the suggestions to the user (cluster_slug, cluster_name, zotero_collection_name, notebooklm_notebook_name)
3. Ask the user to confirm or override each name
4. Only after user approval, call `clusters_new`, `create_zotero_collection`, and `clusters_bind`

Do NOT auto-create with AI-generated names. Researchers and analysts have strong preferences about how their work is labeled.

---

## Setup (one-time)

```bash
# Researcher (with Zotero):
pip install research-hub-pipeline[playwright,mcp]
research-hub init                    # interactive: vault + Zotero key + library id
research-hub doctor                  # 7-check health diagnostic

# Data analyst (no Zotero):
pip install research-hub-pipeline[playwright,mcp]
RESEARCH_HUB_NO_ZOTERO=1 research-hub init   # skip Zotero prompts
research-hub doctor
```

## Core Workflow

### Step 1: Search & Verify

```bash
research-hub search "flood risk agent LLM" --verify --limit 10
# Returns: title, DOI, VERIFIED/UNVERIFIED per result

research-hub verify --doi 10.1234/xxxx
# Checks: doi.org HEAD + arxiv.org HEAD + Semantic Scholar fuzzy match
```

### Step 2: Get Suggestions

```bash
research-hub suggest 10.1234/xxxx --json
# Returns: which cluster this paper belongs to + related existing papers
```

### Step 3: Save to Zotero + Obsidian

```bash
research-hub ingest --cluster my-cluster
# Creates Zotero item + Obsidian raw note + dedup check + verification
# Auto-prints integration suggestions for each new paper
```

### Step 4: Upload to NotebookLM

```bash
research-hub notebooklm login --cdp
research-hub notebooklm bundle --cluster my-cluster
research-hub notebooklm upload --cluster my-cluster
```

### Step 5: Generate Artifacts

```bash
research-hub notebooklm generate --cluster my-cluster --type brief
# Types: brief, audio, mind-map, video, all
```

### Step 6: Download NotebookLM briefing back (v0.9.0+)

```bash
research-hub notebooklm download --cluster my-cluster --type brief
# Saves to <vault>/.research_hub/artifacts/<slug>/brief-<UTC>.txt

research-hub notebooklm read-briefing --cluster my-cluster
# Prints the latest briefing text for inline AI analysis
```

MCP tools `download_artifacts(cluster_slug, type)` and
`read_briefing(cluster_slug)` let AI agents pull briefings into
context without reopening NotebookLM.

### Step 7: Export Citations

```bash
research-hub cite 10.1234/xxxx --format bibtex
research-hub cite --cluster my-cluster --format bibtex --out refs.bib
```

### Step 8: View the Dashboard (v0.10.0+)

```bash
research-hub dashboard --open
# 5-tab audit view: Overview / Library / Briefings / Diagnostics / Manage
```

**Tabs:**
- **Overview** (default) — treemap of cluster sizes, storage map with clickable zotero://, obsidian://, and NotebookLM deep-links, recent-additions feed (last 15 ingests).
- **Library** — cluster cards with paper rows. Per-paper `[Cite]` popup (BibTeX) and `[Open ▼]` menu (jump to Zotero/Obsidian/NLM). Per-cluster `Download .bib` batch export.
- **Briefings** — inline preview of downloaded NotebookLM briefings.
- **Diagnostics** — health checks + drift alerts with remedy commands.
- **Manage** — command-builder forms for cluster rename/merge/split/bind/delete. Fills a form, click → the exact CLI command is copied to clipboard.

**Footer:** a Debug widget (`Copy snapshot`) dumps vault state for AI handoff when the user reports a dashboard issue.

**Options:**
```bash
research-hub dashboard --watch --open         # Re-render on vault change
research-hub dashboard --open --rich-bibtex   # Use Zotero-formatted BibTeX (slow)
```

## Cluster Management

```bash
research-hub clusters new --query "flood risk agent"
research-hub clusters list
research-hub clusters show my-cluster
research-hub clusters bind my-cluster --zotero KEY --notebooklm "Notebook Name"
```

## Maintenance

```bash
research-hub index
research-hub status
research-hub sync status
research-hub sync reconcile --cluster X --execute
research-hub synthesize
research-hub cleanup
```

## All Commands

| Command | Description |
|---|---|
| `init` | Interactive setup wizard |
| `doctor` | Health check (config, Zotero, Chrome, NLM) |
| `install --platform X` | Install this skill for AI assistants |
| `search` | Query Semantic Scholar |
| `verify` | Check paper DOI/arXiv/title existence |
| `suggest` | Cluster + related-paper suggestions |
| `run` / `ingest` | Full pipeline (Zotero + Obsidian + verify + suggest) |
| `cite` | Export BibTeX / BibLaTeX / RIS |
| `clusters` | Create, list, show, bind clusters |
| `sync` | Zotero <-> Obsidian drift detection + fix |
| `notebooklm login` | One-time Chrome sign-in (CDP) |
| `notebooklm bundle` | Export drag-drop folder |
| `notebooklm upload` | Auto-upload to NotebookLM |
| `notebooklm generate` | Trigger briefing/audio/video/mind-map |
| `index` | Rebuild dedup index |
| `status` | Per-cluster reading progress |
| `synthesize` | Generate cluster synthesis pages |
| `cleanup` | Deduplicate hub page wikilinks |
| `migrate-yaml` | Patch legacy notes to current spec |
| `dashboard [--open] [--watch] [--rich-bibtex]` | Generate the 5-tab audit dashboard |
| `notebooklm download --cluster X` | Pull a generated briefing back to the vault |
| `notebooklm read-briefing --cluster X` | Print the latest downloaded briefing |

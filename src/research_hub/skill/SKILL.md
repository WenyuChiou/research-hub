---
name: research-hub
description: "Academic literature pipeline: search -> verify -> save -> organize -> upload -> generate -> cite. Manages Zotero, Obsidian, and NotebookLM from the terminal. Use when the user mentions finding papers, literature search, Zotero, Obsidian, NotebookLM, knowledge base, or paper management."
---

# research-hub - Academic Literature Pipeline

Search, verify, save, organize, and upload academic papers, all from the terminal.

**Trigger phrases:** "find papers about X", "add to Research Hub", "upload to NotebookLM", "suggest related papers", "verify this DOI"

---

## Setup (one-time)

```bash
pip install research-hub-pipeline[playwright]
research-hub init
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

### Step 6: Export Citations

```bash
research-hub cite 10.1234/xxxx --format bibtex
research-hub cite --cluster my-cluster --format bibtex --out refs.bib
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

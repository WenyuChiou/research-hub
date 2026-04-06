# Research Hub Pipeline — Complete Setup Guide

This guide walks you through setting up the Research Hub pipeline from scratch. By the end, you will have a fully integrated system for searching academic papers, saving them to Zotero, organizing them in Obsidian as a navigable knowledge graph, and optionally uploading sources to Google NotebookLM — all triggered by a single command in Claude.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Configuration Parameters](#2-configuration-parameters)
3. [Directory Structure](#3-directory-structure)
4. [Zotero Setup](#4-zotero-setup)
5. [Obsidian Setup](#5-obsidian-setup)
6. [NotebookLM Setup](#6-notebooklm-setup)
7. [Python Scripts](#7-python-scripts)
8. [MCP Connectors](#8-mcp-connectors)
9. [Customization](#9-customization-for-a-different-research-domain)
10. [Quick Start Checklist](#10-quick-start-checklist)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Prerequisites

### 1.1 Software to Install
| Software | Version | Purpose | Download |
|----------|---------|---------|----------|
| **Python** | 3.10 or later | Runs helper scripts (build_hub.py, categorize_graph.py, etc.) | https://www.python.org/downloads/ |
| **Zotero** | 7.x | Reference manager with local REST API | https://www.zotero.org/download/ |
| **Obsidian** | 1.x | Markdown-based knowledge graph viewer | https://obsidian.md/ |
| **Google Chrome** | Latest | Required for NotebookLM uploads via Claude in Chrome (optional) | https://www.google.com/chrome/ |
| **Claude Desktop** | Latest | AI assistant that orchestrates the entire pipeline | https://claude.ai/download |

### 1.2 Python Packages

Only the `requests` library is required for Zotero API communication. Install it with:

```bash
pip install requests
```

On Windows, if you have a standalone Python install (e.g., `C:\Python314\python.exe`):

```cmd
C:\Python314\python.exe -m pip install requests
```

### 1.3 MCP Connectors (installed inside Claude)

These connectors extend Claude's capabilities and must be configured in your Claude environment:

| Connector | Purpose | Required? |
|-----------|---------|-----------|
| **paper-search-mcp** | Search arXiv, Semantic Scholar, PubMed, Google Scholar, Crossref | Yes |
| **Zotero MCP** | Read and search your Zotero library (read-only) | Yes |
| **Desktop Commander** or **Windows-MCP** | Execute shell commands, run Python scripts, read/write files on your machine | Yes (pick one) |
| **Claude in Chrome** | Automate browser interactions for NotebookLM uploads | Optional |

See [Section 8: MCP Connectors](#8-mcp-connectors) for detailed installation instructions.

---

## 2. Configuration Parameters

Every user-specific value lives in a specific file. The table below lists every parameter you must customize, where it is defined, and an example value.

### 2.1 SKILL.md Configuration Block

Located at: `.claude/skills/knowledge-base/SKILL.md`, under the `## Configuration` section.

| Parameter | Example Value | Description |
|-----------|--------------|-------------|
| `PYTHON_PATH` | `C:\Python314\python.exe` | Full path to your Python executable |
| `KNOWLEDGE_BASE` | `C:\Users\wenyu\knowledge-base` | Root folder of your knowledge base |
| `RAW_PAPERS` | `C:\Users\wenyu\knowledge-base\raw` | Where individual paper .md files live |
| `HUB_DIR` | `C:\Users\wenyu\knowledge-base\hub` | Where hub topic pages are generated |
| `HUB_METHODS` | `C:\Users\wenyu\knowledge-base\hub\methods` | Sub-category hub pages |
| `PROJECTS_DIR` | `C:\Users\wenyu\knowledge-base\projects` | Project pages |
| `ZOTERO_LOCAL_API` | `http://localhost:23119` | Zotero local API base URL (usually unchanged) |
| `ZOTERO_USER_ID` | `14772686` | Your Zotero user ID (see Section 4) |
| `SHELL` | `cmd` | `cmd` on Windows, `bash` on macOS/Linux |

### 2.2 Python Script Hardcoded Paths

Each Python script has hardcoded paths near the top of the file. You must update these to match your machine.
| Script | Variables to Change | Example |
|--------|-------------------|---------|
| `build_hub.py` | `raw_dir`, `hub_dir`, `proj_dir`, `root` | `r'C:\Users\wenyu\knowledge-base\raw'` etc. |
| `categorize_graph.py` | `raw_dir`, `hub_dir` | `r'C:\Users\wenyu\knowledge-base\raw'` etc. |
| `fix_orphans.py` | `raw_dir`, `hub_dir` | `r'C:\Users\wenyu\knowledge-base\raw'` etc. |
| `classify_method_type.py` | `raw_dir` | `r'C:\Users\wenyu\knowledge-base\raw'` |
| `reorganize_subcategories.py` | `ROOT` | `r'C:\Users\wenyu\knowledge-base'` |
| `add_to_zotero.py` | `USER_ID` | `"14772686"` |

### 2.3 NotebookLM Notebook Mapping

Located in SKILL.md under `## Action 5: Upload to NotebookLM` and in the pipeline's Step 5 table.

| Parameter | Where | Description |
|-----------|-------|-------------|
| Notebook names | SKILL.md, "Available Notebooks" table | One notebook per major category |
| Notebook URLs | Same table | The full `https://notebooklm.google.com/notebook/...` URL |
| Category-to-notebook mapping | SKILL.md, Pipeline Step 5 table | Which major category maps to which notebook |

---

## 3. Directory Structure

Create the following folder hierarchy. The root folder can be anywhere on your system; just update all configuration parameters accordingly.

```
knowledge-base/                          # Root (your KNOWLEDGE_BASE path)
│
├── raw/                                 # Layer 3: Individual paper notes (.md)
│   ├── Risk-Perception/                 # Sub-category folders (one per sub-category)
│   ├── Insurance-Adoption/
│   ├── Evacuation-Preparedness/
│   ├── Social-Capital-Trust/
│   ├── Flood-ABM/
│   ├── Insurance-Market-ABM/
│   ├── Socio-hydrology/
│   ├── Urban-Land-Use/
│   ├── Consumer-Simulation/
│   ├── Game-Theory-Experiments/
│   ├── Social-Simulation/
│   └── Behavioral-Benchmarking/
│├── hub/                                 # Layers 1-2: Hub topic and theory pages
│   ├── Agent-Based-Modeling.md
│   ├── Flood-Insurance.md
│   ├── Flood-Risk.md
│   ├── LLM-Agents.md
│   ├── Place-Attachment.md
│   ├── Social-Vulnerability.md
│   ├── Managed-Retreat.md
│   ├── Disaster-Preparedness.md
│   ├── Climate-Adaptation.md
│   └── methods/                         # Method-type hub pages
│       ├── Research-Methods-Index.md
│       ├── Survey-Research.md
│       ├── Traditional-ABM.md
│       ├── LLM-ABM.md
│       ├── survey/                      # Sub-category pages for Survey
│       ├── traditional-abm/             # Sub-category pages for Traditional ABM
│       └── llm-abm/                     # Sub-category pages for LLM ABM
│
├── projects/                            # Project pages
│   ├── ABM-Paper.md
│   ├── Survey-Paper.md
│   └── Governed-Broker-Framework.md
│
├── pdfs/                                # Downloaded PDFs (optional)
├── notes/                               # General notes (optional)
├── templates/                           # Obsidian templates (optional)
│
├── .obsidian/                           # Obsidian vault configuration
│   └── graph.json                       # Graph view color groups
│
├── .claude/
│   └── skills/
│       └── knowledge-base/
│           ├── SKILL.md                 # Main skill file (pipeline logic)
│           └── references/
│               ├── paper-template.md    # Template for new paper notes
│               └── setup-guide.md       # This file
│
├── build_hub.py                         # Generates hub pages from raw/ papers
├── categorize_graph.py                  # Assigns graph color categories
├── fix_orphans.py                       # Fixes orphaned nodes (no hub links)
├── classify_method_type.py              # Classifies papers by method type
├── reorganize_subcategories.py          # Creates sub-category structure and hub pages
├── add_to_zotero.py                     # Adds items to Zotero via local API
└── index.md                             # Auto-generated knowledge base index
```
### Three-Layer Architecture

The knowledge graph uses a three-layer hierarchy:

| Layer | Location | Purpose | Example |
|-------|----------|---------|---------|
| Layer 1: Theories | `hub/` | High-level theoretical frameworks | Bounded-Rationality, Protection-Motivation-Theory |
| Layer 2: Topics | `hub/` | Mid-level topic aggregation | Flood-Insurance, LLM-Agents, Managed-Retreat |
| Layer 3: Papers | `raw/{sub-category}/` | Individual paper notes with YAML frontmatter | Each .md file is one paper |

Papers (Layer 3) link upward to topics and theories via `[[wiki links]]`. Topics link to related theories. This creates a navigable, hierarchical knowledge graph in Obsidian.

### Sub-Category Folder Mapping

Papers are filed into sub-category folders under `raw/`. The full mapping:

| Major Category | Sub-Category | Folder Path | Chinese Label |
|---------------|-------------|-------------|---------------|
| Survey | Risk-Perception | `raw/Risk-Perception/` | 風險感知 |
| Survey | Insurance-Adoption | `raw/Insurance-Adoption/` | 保險決策 |
| Survey | Evacuation-Preparedness | `raw/Evacuation-Preparedness/` | 避難/備災 |
| Survey | Social-Capital-Trust | `raw/Social-Capital-Trust/` | 社會資本 |
| Traditional ABM | Flood-ABM | `raw/Flood-ABM/` | 洪災模擬 |
| Traditional ABM | Insurance-Market-ABM | `raw/Insurance-Market-ABM/` | 保險市場 |
| Traditional ABM | Socio-hydrology | `raw/Socio-hydrology/` | 社會水文耦合 |
| Traditional ABM | Urban-Land-Use | `raw/Urban-Land-Use/` | 都市發展 |
| LLM ABM | Consumer-Simulation | `raw/Consumer-Simulation/` | 消費者行為模擬 |
| LLM ABM | Game-Theory-Experiments | `raw/Game-Theory-Experiments/` | 賽局實驗 |
| LLM ABM | Social-Simulation | `raw/Social-Simulation/` | 社會模擬 |
| LLM ABM | Behavioral-Benchmarking | `raw/Behavioral-Benchmarking/` | 行為基準測試 |

---

## 4. Zotero Setup

### 4.1 Install Zotero

Download and install Zotero 7 from https://www.zotero.org/download/. Launch it and complete the initial setup wizard.

### 4.2 Enable the Local API

The local API allows Claude (via Python scripts) to create new items in your Zotero library programmatically.
1. Open Zotero.
2. Go to **Edit > Settings** (Windows/Linux) or **Zotero > Settings** (macOS).
3. Click the **Advanced** tab.
4. Under **General**, check the box: **"Allow other applications on this computer to communicate with Zotero"**.
5. Close the Settings dialog. Zotero now serves a REST API on `http://localhost:23119`.

### 4.3 Find Your Zotero User ID

1. Log in to https://www.zotero.org/settings/keys in your browser.
2. Your numeric user ID is displayed on this page (e.g., `14772686`).
3. Note this number — you will need it for `ZOTERO_USER_ID` in SKILL.md and `USER_ID` in `add_to_zotero.py`.

### 4.4 Verify the API is Working

With Zotero running, open a terminal and run:

```bash
curl http://localhost:23119/api/users/YOUR_USER_ID/items?limit=1
```

On Windows (cmd or PowerShell):

```cmd
curl http://localhost:23119/api/users/14772686/items?limit=1
```

If you get a JSON response (even an empty array `[]`), the API is working. If you get a connection refused error, ensure Zotero is running and the checkbox from Step 4.2 is enabled.

### 4.5 Create Zotero Collections

Organize your Zotero library with collections that mirror your research categories. The pipeline uses Zotero collection names in paper frontmatter. Recommended structure:

```
My Library
├── ABM
├── LLM AI agent
├── Survey
├── survey paper
├── Flood-Simulation
├── Literature Review
├── GBF (Governed Broker Framework)
├── Generative-Agents
├── Memory-and-Cognition
├── Active-Inference
└── (any other topic collections you need)
```

Collection names do not need to exactly match sub-category folder names. The `WIKI_MERGE` dictionary in `build_hub.py` normalizes variant names (e.g., "Agent-Based Model" and "agent-based model" both map to "ABM").
### 4.6 Important Limitation

The **Zotero MCP connector** (used by Claude) is **read-only** — it can search and retrieve items but cannot create new ones. To add papers to Zotero programmatically, the pipeline uses direct HTTP requests to the `connector/saveItems` endpoint via `add_to_zotero.py` or inline Python executed through Desktop Commander.

---

## 5. Obsidian Setup

### 5.1 Create the Vault

1. Install Obsidian from https://obsidian.md/.
2. Launch Obsidian and choose **"Open folder as vault"**.
3. Select your knowledge base root folder (e.g., `C:\Users\wenyu\knowledge-base`).
4. Obsidian will create a `.obsidian/` configuration folder inside it.

### 5.2 Configure Graph View Colors

The graph view uses color groups to visually distinguish paper categories. These are defined in `.obsidian/graph.json`.

After running `reorganize_subcategories.py` (see Section 7), the script automatically updates `graph.json` with color groups for each sub-category. If you need to configure colors manually, the file follows this format:

```json
{
  "colorGroups": [
    { "query": "tag:#method/survey/Risk-Perception", "color": { "a": 1, "rgb": 65535 } },
    { "query": "tag:#method/traditional-abm/Flood-ABM", "color": { "a": 1, "rgb": 16744448 } },
    { "query": "tag:#method/llm-agent/Social-Simulation", "color": { "a": 1, "rgb": 8388352 } },
    { "query": "path:hub/methods/survey", "color": { "a": 1, "rgb": 65535 } },
    { "query": "path:hub/methods/traditional-abm", "color": { "a": 1, "rgb": 16744448 } },
    { "query": "path:hub/methods/llm-abm", "color": { "a": 1, "rgb": 65280 } },
    { "query": "path:projects/", "color": { "a": 1, "rgb": 16776960 } }
  ]
}
```

The color families used by default:

| Category Family | Color Range | RGB Examples |
|----------------|-------------|-------------|
| Survey sub-categories | Teal / Cyan shades | 65535 (cyan), 43690 (dark cyan) |
| Traditional ABM sub-categories | Amber / Orange shades | 16744448 (orange), 16760576 (amber) |
| LLM ABM sub-categories | Green shades | 65280 (green), 8388352 (chartreuse) |
| Hub pages | Matches parent category color | (set by path queries) |
| Project pages | Yellow | 16776960 |
### 5.3 Graph View Filters

To view one category at a time in Obsidian's graph view, use these search filters:

- **Survey papers only:** `tag:#method/survey OR path:hub/methods/survey`
- **Traditional ABM only:** `tag:#method/traditional-abm OR path:hub/methods/traditional-abm`
- **LLM ABM only:** `tag:#method/llm-agent OR path:hub/methods/llm-abm`

You can save these as bookmarked graph views in Obsidian for quick access.

### 5.4 Recommended Community Plugins

No community plugins are strictly required. The pipeline works with core Obsidian features (graph view, wikilinks, tags, YAML frontmatter). However, the following plugins may enhance your experience:

- **Dataview** — Query your paper metadata as tables (e.g., list all papers by year, filter by method-type).
- **Tag Wrangler** — Batch rename or merge tags across files.
- **Templater** — Use the paper template from `references/paper-template.md` as an auto-fill template.
- **Graph Analysis** — Advanced graph metrics and clustering.

### 5.5 How Tag-Based Filtering Works

Each paper has two types of tags assigned by the Python scripts:

1. **Research line tags** (assigned by `categorize_graph.py`): `research/flood-abm`, `research/llm-agent`, `research/social-behavior`, `research/methodology`, `research/general-reference`.
2. **Method/sub-category tags** (assigned by `reorganize_subcategories.py`): `method/survey/Risk-Perception`, `method/traditional-abm/Flood-ABM`, `method/llm-agent/Social-Simulation`, etc.

The graph color groups in `graph.json` use `tag:#method/...` queries, so papers are colored by their sub-category. You can switch to research-line coloring by changing the queries to `tag:#research/...`.

---

## 6. NotebookLM Setup

Google NotebookLM does not have a public API. The pipeline uses Claude in Chrome to automate browser interactions for uploading paper sources.

### 6.1 Create Notebooks

1. Go to https://notebooklm.google.com/ and sign in with your Google account.
2. Create one notebook per major research category. For example:
| Notebook Name | Major Category | Topics Covered |
|--------------|---------------|----------------|
| Behavioral Science & Decision Theory | Survey Research | Social behavior, decision-making, behavioral economics |
| Flood Risk & ABM | Traditional ABM | Flood risk, insurance, agent-based modeling |
| Hello Agent | LLM ABM | LLM agents, generative agents, AI simulation |

3. Copy each notebook's URL from your browser's address bar. It will look like: `https://notebooklm.google.com/notebook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

### 6.2 Update the Notebook Mapping in SKILL.md

Open SKILL.md and update the **Available Notebooks** table under Action 5 and the **Notebook mapping** table under Pipeline Step 5 with your notebook names and URLs.

### 6.3 How URL-Based Upload Works

The pipeline uses URL-based source addition rather than file upload because Chrome automation (Claude in Chrome) cannot interact with native file dialog windows. The upload process is:

1. Claude navigates to the notebook URL.
2. Clicks **"Add Source"** (or "新增來源" in Chinese UI).
3. Selects **"Website"** (or "網站").
4. Pastes the paper's public URL (arXiv, DOI, PubMed, or Semantic Scholar link).
5. Submits and waits for NotebookLM to process the source.

### 6.4 Paywalled Paper Limitations

If a paper is behind a paywall and has no open-access version (no arXiv preprint, no free DOI link), NotebookLM cannot ingest it via URL. In this case:

- The pipeline will note the limitation and skip the upload.
- You can manually upload the PDF through NotebookLM's web interface.
- Consider using your institution's proxy or finding a preprint on the author's website.

### 6.5 URL Priority Order

When selecting which URL to provide to NotebookLM, the pipeline uses this priority:

1. **arXiv** — `https://arxiv.org/abs/<id>` (best: always open access, clean text)
2. **DOI** — `https://doi.org/<doi>` (may be paywalled)
3. **PubMed** — `https://pubmed.ncbi.nlm.nih.gov/<pmid>` (abstract usually available)
4. **Semantic Scholar** — `https://www.semanticscholar.org/paper/<id>` (metadata page)

---

## 7. Python Scripts
The pipeline uses six Python scripts. They are run from the knowledge base root directory. On Windows, the typical invocation pattern is:

```cmd
cd /d C:\Users\wenyu\knowledge-base && set PYTHONPATH=C:\Users\wenyu\knowledge-base && C:\Python314\python.exe <script_name>.py
```

On macOS/Linux:

```bash
cd /home/user/knowledge-base && export PYTHONPATH=/home/user/knowledge-base && python3 <script_name>.py
```

### 7.1 build_hub.py — Rebuild Hub Index

**What it does:** Recursively scans all `.md` files in `raw/`, parses their YAML frontmatter, normalizes collection names via the `WIKI_MERGE` dictionary, and generates:

- Hub topic pages in `hub/` (one per topic in the `topic_map` dictionary)
- Project pages in `projects/` (one per project in the `projects` dictionary)
- A root `index.md` listing all papers sorted by year

**When to run:** After adding new papers, changing collection names, or modifying the topic map.

**Key configuration to customize:**
- `raw_dir`, `hub_dir`, `proj_dir`, `root` — file paths (top of file)
- `WIKI_MERGE` — dictionary mapping variant/misspelled collection names to canonical names
- `topic_map` — dictionary defining hub topics, their keywords, and descriptions
- `projects` — dictionary defining research projects and their associated collections

### 7.2 categorize_graph.py — Assign Graph Colors

**What it does:** Scans each paper's filename, title, tags, collections, and first 500 characters of body text. Matches against keyword lists and collection lists in the `RESEARCH_LINES` dictionary. Assigns:

- A `category` field in the YAML frontmatter (e.g., `flood-abm`, `llm-agent`, `social-behavior`, `methodology`)
- A `research/<category>` tag for Obsidian graph coloring
- Falls back to `general-reference` if no match is found

**When to run:** After adding new papers or changing category definitions.

**Key configuration to customize:**
- `raw_dir`, `hub_dir` — file paths
- `RESEARCH_LINES` — dictionary with keywords and collection triggers for each research line
### 7.3 fix_orphans.py — Fix Orphaned Nodes

**What it does:** Finds paper notes that have no `[[wiki links]]` pointing to any existing hub topic page. For each orphan, it scores all hub topics by keyword matches against the paper's full text and assigns the top 2 matching topics in a `## Related Concepts` section.

**When to run:** After `build_hub.py`, to ensure every paper is connected to the knowledge graph.

**Key configuration to customize:**
- `raw_dir`, `hub_dir` — file paths
- `topic_keywords` — dictionary mapping each topic name to a list of matching keywords

### 7.4 classify_method_type.py — Classify by Method Type

**What it does:** Classifies each paper into one of three method types based on title keywords, abstract keywords, and Zotero collection membership:

| Method Type | Value | Chinese Collection Added |
|-------------|-------|------------------------|
| Survey/questionnaire research | `survey` | 問卷 |
| Traditional agent-based modeling | `traditional-abm` | 傳統ABM |
| LLM/AI agent research | `llm-agent` | LLM相關 |

Uses a conservative approach: primarily classifies by title and Zotero collections. Body notes are excluded to avoid contamination from project annotations.

**Special rule:** "survey" in a title does NOT trigger the `survey` method type if it appears in a literature-review context (e.g., "A Survey of LLM Agents"). The classifier detects patterns like "survey of X" combined with LLM/AI terms and treats those as review papers.

**When to run:** After adding new papers, before `reorganize_subcategories.py`.

**Key configuration to customize:**
- `raw_dir` — file path
- Title keyword lists, abstract keyword lists, and collection triggers for each method type
- `METHOD_COLLECTIONS` — mapping of method types to Chinese collection names

### 7.5 reorganize_subcategories.py — Create Sub-Category Structure

**What it does:** The most comprehensive script. It performs six steps in sequence:

1. **Reads and classifies** all papers into sub-categories using regex pattern matching
2. **Updates YAML frontmatter** with `sub-category` field and `method/{type}/{sub-cat}` tags
3. **Creates sub-category hub pages** in `hub/methods/{type}/{Sub-Category}.md`
4. **Creates major category hub pages** (Survey-Research.md, Traditional-ABM.md, LLM-ABM.md)
5. **Creates the Research-Methods-Index.md** overview page
6. **Updates graph.json** with color groups for each sub-category
**When to run:** After `classify_method_type.py`, when you want to regenerate the full sub-category hierarchy.

**Key configuration to customize:**
- `ROOT` — knowledge base root path
- `SUBCATEGORIES` — nested dictionary defining all sub-categories, their regex patterns, descriptions, and Chinese labels
- `METHOD_LABELS` — English and Chinese labels for each major category
- `COLOR_MAP` — RGB color values for each sub-category in the graph view

### 7.6 add_to_zotero.py — Add Papers to Zotero

**What it does:** Adds a batch of papers to Zotero via the local API's `connector/saveItems` endpoint. The script contains a `PAPERS` list with paper metadata (title, authors, year, DOI, URL, tags). It optionally assigns papers to a named Zotero collection.

**When to run:** When you have a batch of papers to add to Zotero programmatically. Note that the one-command pipeline typically uses inline Python via Desktop Commander instead of this script, but this script is useful for bulk imports.

**Key configuration to customize:**
- `USER_ID` — your Zotero user ID
- `PAPERS` — the list of paper metadata dictionaries (modify for each batch)

### 7.7 Recommended Execution Order

When running all scripts for a full rebuild:

```
1. classify_method_type.py    # Assign method-type to each paper
2. reorganize_subcategories.py # Create sub-category structure and update graph.json
3. build_hub.py               # Rebuild topic hub pages and index
4. categorize_graph.py        # Assign research-line tags for graph coloring
5. fix_orphans.py             # Link orphaned papers to hub topics
```

For a quick refresh after adding a few papers, running just steps 3-5 is usually sufficient:

```
1. build_hub.py
2. categorize_graph.py
3. fix_orphans.py
```

---

## 8. MCP Connectors

MCP (Model Context Protocol) connectors extend Claude's capabilities by connecting it to external tools and services. The Research Hub pipeline requires the following connectors.

### 8.1 paper-search-mcp

**Purpose:** Enables Claude to search academic databases directly.

**Supported databases:** arXiv, Semantic Scholar, PubMed, Google Scholar, Crossref, bioRxiv, medRxiv, IACR.

**Key tools provided:**
- `search_arxiv`, `search_semantic`, `search_google_scholar`, `search_pubmed`, `search_crossref`
- `read_arxiv_paper`, `read_semantic_paper`, `read_pubmed_paper`, `read_crossref_paper` (for full metadata retrieval)
- `download_arxiv`, `download_semantic`, etc. (for PDF downloads)
**Installation:** Install via Claude's MCP connector marketplace or configure manually in your Claude settings. No API key is required for most databases; Google Scholar may have rate limits.

### 8.2 Zotero MCP

**Purpose:** Allows Claude to read and search your Zotero library.

**Key tools provided:**
- `zotero_search_items` — Search for papers by title, author, or DOI
- `zotero_get_collections` — List all collections
- `zotero_get_tags` — List all tags
- `zotero_get_collection_items` — List items in a specific collection
- `zotero_get_item_metadata` — Get full metadata for a specific item
- `zotero_batch_update_tags` — Batch-update tags on items
- `zotero_get_item_fulltext` — Get the full text of an item
- `zotero_semantic_search` — Semantic search across your library

**Important limitation:** This connector is **read-only for item creation**. It cannot create new Zotero items. The pipeline works around this by using direct HTTP requests to the Zotero local API.

**Installation:** Install via Claude's MCP connector marketplace. Configuration requires your Zotero user ID and local API URL.

### 8.3 Desktop Commander or Windows-MCP

**Purpose:** Allows Claude to execute shell commands, run Python scripts, and read/write files on your local machine.

**Key tools provided (Desktop Commander):**
- `read_file`, `write_file` — Read and write files
- `start_process` — Execute shell commands
- `list_directory` — Browse folders
- `edit_block` — Edit specific sections of files

**Key tools provided (Windows-MCP):**
- `PowerShell` — Execute PowerShell commands
- `FileSystem` — File operations
- `App` — Launch applications

You only need **one** of these. Desktop Commander is more commonly used and works on all platforms. Windows-MCP provides deeper Windows integration.

**Installation:** Install via Claude's MCP connector marketplace. Desktop Commander may require configuring allowed directories for security.

### 8.4 Claude in Chrome (Optional)

**Purpose:** Automates browser interactions for NotebookLM uploads. Required only if you want automatic source uploading to NotebookLM.

**Key tools provided:**
- `navigate` — Open a URL in Chrome
- `read_page` — Read the current page's DOM
- `form_input` — Fill in form fields
- `computer` — Click, type, and interact with page elements
- `get_page_text` — Extract text content from the page

**Installation:** Install the Claude in Chrome extension from the Chrome Web Store. It connects to Claude Desktop automatically.

**Note:** If you do not use NotebookLM, you can skip this connector entirely. The rest of the pipeline works without it.

---

## 9. Customization for a Different Research Domain

The default configuration is built around flood risk, agent-based modeling, and LLM agent research. Here is how to adapt the system for any other research domain.

### 9.1 Change the Three Major Categories

The three major categories (Survey, Traditional ABM, LLM ABM) are defined in multiple places. To change them:

1. **SKILL.md** — Update the "Major Category" table in Pipeline Step 1. Change the category names, `method-type` values, and descriptions.

2. **classify_method_type.py** — Rewrite the `classify_paper()` function. Replace the three classification blocks (LLM, Survey, ABM) with your own categories. Update the title keyword lists, abstract keyword lists, and collection triggers. Update `METHOD_COLLECTIONS` with your category labels.

3. **reorganize_subcategories.py** — Replace the `SUBCATEGORIES` dictionary with your own categories and sub-categories. Update `METHOD_LABELS` and `PARENT_FILES`.

4. **SKILL.md** — Update the Sub-Category table in Pipeline Step 1, the "Sub-Category Folder Mapping" section, and the "Method-Type Classification Details" section.

### 9.2 Add or Remove Sub-Categories

Sub-categories are defined in `reorganize_subcategories.py` in the `SUBCATEGORIES` dictionary. Each sub-category has:

- A name (used as folder name and page title)
- A list of regex patterns for classification
- An English description
- A Chinese label (`desc_zh`)

To add a new sub-category:

1. Add an entry to the appropriate major category in `SUBCATEGORIES`.
2. Create the folder: `mkdir raw\{New-Sub-Category}`
3. Run `reorganize_subcategories.py` to generate the hub page and update graph.json.
4. Update the Sub-Category Folder Mapping table in SKILL.md and this setup guide.

To remove a sub-category, delete its entry from `SUBCATEGORIES` and re-run the script. Existing papers in that folder will fall into the "general" bucket.

### 9.3 Modify SKILL.md Trigger Phrases

The SKILL.md file's frontmatter `description` field contains all trigger phrases that activate the pipeline. Edit this comma-separated list to match your domain vocabulary. For example, if your research is about climate economics, you might add terms like "carbon pricing", "emissions trading", "climate policy", etc.

### 9.4 Update graph.json Color Groups

Colors are managed in two ways:

- **Automatically:** `reorganize_subcategories.py` overwrites `graph.json` with colors defined in its `COLOR_MAP` dictionary. Edit `COLOR_MAP` to change colors.
- **Manually:** Edit `.obsidian/graph.json` directly. Each entry has a `query` (tag or path filter) and a `color` (with `a` for alpha and `rgb` as a decimal integer).

To convert hex colors to the decimal `rgb` value: `0xFF8800` = `16744448` in decimal.

### 9.5 Update WIKI_MERGE Mappings

The `WIKI_MERGE` dictionary in `build_hub.py` normalizes variant Zotero collection names to canonical names. If you rename collections or notice duplicates, add new entries:
```python
WIKI_MERGE = {
    "Old Name": "Canonical Name",
    "Typo Version": "Canonical Name",
    # ... add your mappings
}
```

After editing, re-run `build_hub.py` to regenerate hub pages with normalized names.

### 9.6 Update Topic Map and Topic Keywords

Two scripts use topic-to-keyword mappings:

- `build_hub.py` has `topic_map` — defines which hub topic pages are generated and what keywords link papers to them.
- `fix_orphans.py` has `topic_keywords` — defines keywords used to link orphan papers to hub topics.

When adding a new hub topic, add entries to **both** dictionaries to keep them in sync.

### 9.7 Adapt for macOS or Linux

All scripts default to Windows paths. To adapt:

| Windows | macOS/Linux |
|---------|-------------|
| `cd /d C:\path` | `cd /path` |
| `set PYTHONPATH=C:\path` | `export PYTHONPATH=/path` |
| `C:\Python314\python.exe` | `python3` |
| Backslash paths `\` | Forward slash paths `/` |
| `SHELL: "cmd"` in SKILL.md | `SHELL: "bash"` in SKILL.md |
| `r'C:\Users\...\raw'` in scripts | `r'/home/user/.../raw'` in scripts |

---

## 10. Quick Start Checklist

Follow this numbered checklist to verify everything works after initial setup.

### Infrastructure

- [ ] **Python installed.** Run `python --version` (or `python3 --version`) and confirm 3.10+.
- [ ] **`requests` package installed.** Run `python -c "import requests; print(requests.__version__)"`.
- [ ] **Zotero running with API enabled.** Run `curl http://localhost:23119/api/users/YOUR_USER_ID/collections` and confirm you get a JSON response.
- [ ] **Obsidian vault opened.** Open Obsidian and confirm it points to your knowledge base root. You should see `raw/`, `hub/`, and `index.md` in the file explorer.
- [ ] **Knowledge base directory structure exists.** Confirm `raw/`, `hub/`, `hub/methods/`, `projects/`, and `.claude/skills/knowledge-base/` folders exist.

### Configuration

- [ ] **SKILL.md updated.** Open `.claude/skills/knowledge-base/SKILL.md` and verify all paths in the Configuration section match your system.
- [ ] **Python script paths updated.** Open each `.py` script and verify the hardcoded paths at the top match your system.
- [ ] **Zotero user ID set.** Verify `ZOTERO_USER_ID` in SKILL.md and `USER_ID` in `add_to_zotero.py` match your Zotero account.

### Script Execution

- [ ] **build_hub.py runs.** Execute the script and confirm output says "Parsed X papers" and "DONE".
- [ ] **categorize_graph.py runs.** Execute the script and confirm output says "Updated X papers" and "DONE".
- [ ] **fix_orphans.py runs.** Execute the script and confirm output says "Orphan papers" count and "DONE".
- [ ] **classify_method_type.py runs.** Execute the script and confirm "Classification Results" output.
- [ ] **reorganize_subcategories.py runs.** Execute the script and confirm all 6 steps complete.

### MCP Connectors

- [ ] **paper-search-mcp connected.** Ask Claude to search for a paper on arXiv — it should return results.
- [ ] **Zotero MCP connected.** Ask Claude to list your Zotero collections — it should return your collection names.
- [ ] **Desktop Commander or Windows-MCP connected.** Ask Claude to list files in your knowledge base folder — it should return the directory listing.
- [ ] **Claude in Chrome connected (optional).** Ask Claude to navigate to a URL in Chrome — it should open the page.
### End-to-End Test

- [ ] **Search a paper.** Tell Claude: "Search for papers about flood insurance agent-based model on arXiv." Confirm results appear.
- [ ] **Save a paper.** Select one paper from the results. Confirm Claude creates a `.md` file in `raw/{sub-category}/` with correct YAML frontmatter and saves it to Zotero.
- [ ] **Verify in Obsidian.** Open Obsidian, refresh the vault (Ctrl+R or Cmd+R), and confirm the new paper note appears in the file explorer and graph view.
- [ ] **Rebuild hub.** Tell Claude: "Rebuild hub" or run `build_hub.py` manually. Confirm hub topic pages update with the new paper.
- [ ] **Check graph colors.** Open the graph view in Obsidian. Confirm papers appear with the correct colors for their categories.

---

## 11. Troubleshooting

### Zotero API Not Responding

**Symptom:** `curl http://localhost:23119/...` returns "connection refused" or times out.

**Solutions:**
1. Ensure the Zotero desktop application is running (it hosts the local API server).
2. Verify the API checkbox is enabled: Edit > Settings > Advanced > General > "Allow other applications on this computer to communicate with Zotero".
3. Check if another application is using port 23119. On Windows: `netstat -an | findstr 23119`. On macOS/Linux: `lsof -i :23119`.
4. Restart Zotero.

### Python Encoding Errors on Windows

**Symptom:** `UnicodeEncodeError` or `UnicodeDecodeError` when running scripts, especially with non-ASCII characters (Chinese collection names, accented author names).

**Solutions:**
1. The scripts use `encoding='utf-8'` in all `open()` calls. If you add new file operations, always specify `encoding='utf-8'`.
2. `classify_method_type.py` wraps stdout: `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')`. Add this to other scripts if needed.
3. Set the environment variable before running: `set PYTHONUTF8=1` (Windows) or `export PYTHONUTF8=1` (macOS/Linux).
4. If using PowerShell, run `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` first.

### NotebookLM Upload Failures

**Symptom:** Claude in Chrome fails to add a source to NotebookLM.

**Solutions:**
1. **Selector changes:** NotebookLM's UI may have changed. Use `read_page()` to inspect the current DOM and find the correct selectors for the "Add Source" button and URL input field.
2. **Authentication required:** Make sure you are logged into your Google account in Chrome before starting the upload.
3. **Rate limiting:** NotebookLM may throttle rapid additions. Wait a few seconds between uploads.
4. **Paywalled paper:** The URL may lead to a paywall. Try an arXiv or preprint URL instead.
5. **File dialog issue:** If Claude accidentally triggers the file upload dialog instead of URL upload, it cannot proceed. Ensure it selects "Website" / "網站" as the source type.

### Graph Not Showing Colors

**Symptom:** Obsidian graph view shows all nodes in the same default color.

**Solutions:**
1. **Restart Obsidian.** Graph color changes require a vault reload. Close and reopen Obsidian.
2. **Check graph.json.** Open `.obsidian/graph.json` and verify `colorGroups` contains entries with `query` and `color` fields.
3. **Verify tags exist.** Open a paper note and check that it has tags like `research/flood-abm` or `method/survey/Risk-Perception` in its YAML frontmatter. If not, run `categorize_graph.py` and/or `reorganize_subcategories.py`.
4. **Open graph settings.** In Obsidian's graph view, click the gear icon and check that the color groups section shows your configured groups. You may need to toggle them on.
### build_hub.py Collection Merge Issues

**Symptom:** Duplicate or inconsistent hub pages appear because the same Zotero collection has multiple name variants.

**Solution:** Add new aliases to the `WIKI_MERGE` dictionary in `build_hub.py` and re-run. For example, if "flood insurance" and "Flood Insurance" both appear, add: `"flood insurance": "Flood Insurance"`.

### PYTHONPATH Not Set

**Symptom:** Python scripts fail with `ImportError` or `ModuleNotFoundError` when run via Desktop Commander.

**Solution:** Always prepend the PYTHONPATH setting before running scripts:
- Windows: `set PYTHONPATH=C:\Users\wenyu\knowledge-base && C:\Python314\python.exe script.py`
- macOS/Linux: `export PYTHONPATH=/home/user/knowledge-base && python3 script.py`

### Method-Type Misclassification

**Symptom:** A paper is assigned the wrong method-type (e.g., "A Survey of LLM Agents" is classified as `survey` instead of `llm-agent`).

**Solution:** The classifier has a special rule for literature review papers with "survey" in the title. If still wrong, manually edit the `method-type` field in the paper's YAML frontmatter and re-run `classify_method_type.py` (it will overwrite its own changes but respect the special rules). Alternatively, add the specific title pattern to the `is_review_survey()` function.

### Sub-Category Folder Missing

**Symptom:** Writing a new paper note fails because the target sub-category folder does not exist.

**Solution:** Always create the folder before writing: `mkdir raw\{Sub-Category}` (Windows) or `mkdir -p raw/{Sub-Category}` (macOS/Linux). The pipeline is designed to create folders automatically, but if running manually, ensure the folder exists first.

### Duplicate Papers

**Symptom:** The same paper appears twice in Zotero or as two `.md` files.

**Solution:**
1. Before adding any paper, the pipeline checks for duplicates using `zotero_search_items(query="<title or DOI>")`.
2. If duplicates already exist, use Zotero's built-in duplicate detection: right-click the "Duplicate Items" virtual collection.
3. For `.md` file duplicates, search `raw/` for files with matching DOIs or similar titles and merge them manually.

### Zotero MCP Cannot Create Items

**Symptom:** Trying to save a paper via the Zotero MCP connector fails silently or returns an error.

**Solution:** This is expected. The Zotero MCP connector is read-only for item creation. The pipeline uses direct HTTP POST requests to `http://localhost:23119/connector/saveItems` via Python/PowerShell executed through Desktop Commander. If this fails, check that Zotero is running and the local API is enabled.

### Scripts Run Successfully but Obsidian Shows No Changes

**Symptom:** Scripts report success but Obsidian vault still shows old content.

**Solution:** Obsidian caches file contents. Press Ctrl+R (or Cmd+R on macOS) to force a vault reload, or close and reopen Obsidian. For graph view changes, close the graph tab and reopen it.

---

## Appendix A: YAML Frontmatter Template

Every paper `.md` file in `raw/` must have this YAML frontmatter format:

```yaml
---
title: "Paper Title"
authors: "Author1; Author2; Author3"
year: 2025
journal: "Journal or Conference Name"
doi: "10.xxxx/yyyy"
zotero-key: "XXXXXXXX"
collections: ["Collection1", "Collection2"]
tags: ["tag1", "tag2", "research/flood-abm", "method/survey/Risk-Perception"]
category: "flood-abm"
method-type: "survey"
sub-category: "Risk-Perception"
---
```
### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | String | Yes | Full paper title in double quotes |
| `authors` | String | Yes | Semicolon-separated author list |
| `year` | Integer | Yes | Publication year |
| `journal` | String | Yes | Journal or conference name |
| `doi` | String | No | Digital Object Identifier |
| `zotero-key` | String | No | Zotero item key (populated after saving to Zotero) |
| `collections` | Array | No | JSON array of Zotero collection names |
| `tags` | Array | No | JSON array of descriptive tags (without `#` prefix) |
| `category` | String | No | Graph color category: `flood-abm`, `llm-agent`, `social-behavior`, `methodology`, `general-reference` |
| `method-type` | String | No | Method classification: `survey`, `traditional-abm`, `llm-agent` |
| `sub-category` | String | No | Sub-category name (e.g., `Risk-Perception`, `Flood-ABM`) |

---

## Appendix B: Platform-Specific Command Reference

### Windows (cmd)

```cmd
:: Run a single script
cd /d C:\Users\wenyu\knowledge-base && set PYTHONPATH=C:\Users\wenyu\knowledge-base && C:\Python314\python.exe build_hub.py

:: Run all scripts in sequence
cd /d C:\Users\wenyu\knowledge-base && set PYTHONPATH=C:\Users\wenyu\knowledge-base && C:\Python314\python.exe classify_method_type.py && C:\Python314\python.exe reorganize_subcategories.py && C:\Python314\python.exe build_hub.py && C:\Python314\python.exe categorize_graph.py && C:\Python314\python.exe fix_orphans.py

:: Test Zotero API
curl http://localhost:23119/api/users/14772686/collections
```

### macOS / Linux (bash)

```bash
# Run a single script
cd /home/user/knowledge-base && export PYTHONPATH=/home/user/knowledge-base && python3 build_hub.py

# Run all scripts in sequence
cd /home/user/knowledge-base && export PYTHONPATH=/home/user/knowledge-base && python3 classify_method_type.py && python3 reorganize_subcategories.py && python3 build_hub.py && python3 categorize_graph.py && python3 fix_orphans.py

# Test Zotero API
curl http://localhost:23119/api/users/YOUR_USER_ID/collections
```

---

## Appendix C: Research Categories Quick Reference

### Graph Color Categories (assigned by categorize_graph.py)

| Category | Tag | Primary Focus |
|----------|-----|--------------|
| `flood-abm` | `research/flood-abm` | Flood risk, insurance, NFIP, ABM, disaster, hazard |
| `llm-agent` | `research/llm-agent` | LLM, generative agents, transformers, AI agents |
| `social-behavior` | `research/social-behavior` | Social capital, place attachment, equity, norms |
| `methodology` | `research/methodology` | ODD protocol, SEM, statistical methods, reviews |
| `general-reference` | `research/general-reference` | Fallback for papers matching no other category |

### Method Types (assigned by classify_method_type.py)

| Method Type | Tag | Focus |
|-------------|-----|-------|
| `survey` | — | Questionnaire, stated-preference, household survey research |
| `traditional-abm` | — | Agent-based modeling without LLMs (NetLogo, Repast, Mesa) |
| `llm-agent` | — | LLM-powered agent simulation and evaluation |

### Sub-Categories (assigned by reorganize_subcategories.py)

| Major Category | Sub-Categories |
|---------------|---------------|
| Survey | Risk-Perception, Insurance-Adoption, Evacuation-Preparedness, Social-Capital-Trust |
| Traditional ABM | Flood-ABM, Insurance-Market-ABM, Socio-hydrology, Urban-Land-Use |
| LLM ABM | Consumer-Simulation, Game-Theory-Experiments, Social-Simulation, Behavioral-Benchmarking |
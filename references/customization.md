---
title: Customization Guide
description: How to adapt this skill for your own research workflow - paths, categories, notebooks, and platform differences
---

# Customization Guide

## Customization Guide (For Other Users)

### 1. File Paths
Edit the **Configuration** section: `PYTHON_PATH`, `KNOWLEDGE_BASE`, `RAW_PAPERS`, `HUB_DIR`, `PROJECTS_DIR`, `SHELL`.

### 2. Zotero Configuration
- Install Zotero desktop and enable local API: Settings ??Advanced ??General ??"Allow other applications on this computer to communicate with Zotero."
- Find your user ID at https://www.zotero.org/settings/keys
- Update `ZOTERO_USER_ID` and `ZOTERO_LOCAL_API`.

### 3. Research Categories and Keywords
- Edit the Research Categories table for your research areas.
- Update keyword lists in `categorize_graph.py`.
- Modify `.obsidian/graph.json` with color queries for your categories.

### 4. Topic Map
- Edit topic definitions in `build_hub.py`.
- Update the Topic Map table in this file.

### 5. WIKI_MERGE Dictionary
- Edit `WIKI_MERGE` in `build_hub.py` for your collection name variants and typos.

### 6. Method-Type Classification
- Claude uses LLM-based classification by default. The `classify_method_type.py` script is available as a fallback.
- Update the Method-Type Classification table in this file for reference.

### 7. NotebookLM Notebooks
- Create notebooks in Google NotebookLM for each research area.
- Update the Available Notebooks table in Action 5.

### 8. Sub-Categories
- Add new sub-categories to the Sub-Category Folder Mapping table.
- Create the corresponding folder in `raw/` and hub page in `hub/methods/`.

### 9. Adapt for macOS/Linux
- `cd /d` ??`cd`
- `set PYTHONPATH=...` ??`export PYTHONPATH=...`
- Replace `\\` path separators with `/`
- Replace `C:\Python314\python.exe` with `python3`

### 10. Required MCP Connectors
- **paper-search-mcp**: For searching academic databases (arXiv, Semantic Scholar, PubMed, Google Scholar, Crossref).
- **Zotero MCP**: For searching and reading Zotero library (read-only).
- **Desktop Commander** or **Windows MCP**: For running Python scripts and writing files on the local machine.
- **Claude in Chrome** (optional): For automating NotebookLM uploads via browser.

### 11. Dataview Plugin
- Install the Dataview community plugin in Obsidian for advanced queries.
- See the "Dataview Integration" section for example queries.
- Hub sub-category pages can use Dataview queries instead of static link lists.

### 12. Thesis Integration
- Set `thesis-chapter` values to match your thesis structure.
- Set `research-questions` to track which papers address which RQs.
- Use Dataview queries to get per-chapter and per-RQ paper lists.

## Configuration

```yaml
# Paths
PYTHON_PATH: "C:\\Python314\\python.exe"
KNOWLEDGE_BASE: "C:\\Users\\wenyu\\knowledge-base"
RAW_PAPERS: "C:\\Users\\wenyu\\knowledge-base\\raw"
HUB_DIR: "C:\\Users\\wenyu\\knowledge-base\\wiki"
HUB_METHODS: "C:\\Users\\wenyu\\knowledge-base\\hub\\methods"
PROJECTS_DIR: "C:\\Users\\wenyu\\knowledge-base\\projects"

# Zotero
ZOTERO_LOCAL_API: "http://localhost:23119"
ZOTERO_USER_ID: "14772686"
ZOTERO_API_BASE: "http://localhost:23119/api/users/14772686"

# Helper scripts (relative to KNOWLEDGE_BASE)
ADD_TO_ZOTERO: "add_to_zotero.py"
BUILD_WIKI: "build_hub.py"
CATEGORIZE_GRAPH: "categorize_graph.py"
FIX_ORPHANS: "fix_orphans.py"
CLASSIFY_METHOD_TYPE: "classify_method_type.py"

# Desktop Commander shell (Windows)
SHELL: "cmd"
```

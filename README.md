# Research Hub — Academic Literature Pipeline

> [繁體中文版](README_zh-TW.md)

One-command knowledge management pipeline for academic research. Search papers, save to Zotero, create Obsidian notes, rebuild hub index, and upload to NotebookLM — all from a single trigger phrase.

---

## Features

### One-Command Pipeline
- **Single trigger** — Say "幫我放到Research Hub" + topic, and the full lifecycle runs automatically
- **LLM-based classification** — Claude reads abstracts and classifies papers by category and sub-category
- **Multi-source search** — Semantic Scholar, WebSearch, CrossRef, PubMed queried in parallel

### Zotero Integration
- **Auto-save with metadata** — Creates Zotero items with full metadata, tags, and collection assignment
- **Child notes** — Attaches auto-generated summary notes to every paper
- **Duplicate detection** — Checks before creating to prevent duplicates
- **Uses [zotero-skills](https://github.com/WenyuChiou/zotero-skills)** for all CRUD operations

### Obsidian Knowledge Base
- **Structured notes** — Auto-generated `.md` files with YAML frontmatter, summary, key findings, methodology
- **Three-layer hub** — Theories → Topics → Papers, navigable as a knowledge graph
- **Graph colors** — Category-based coloring in Obsidian graph view
- **Dataview queries** — Ready-to-use queries for filtering, status tracking, thesis integration

### NotebookLM Upload
- **DOI validation** — Validates every DOI before upload, skips paywalled content
- **URL priority** — Prefers arXiv > preprint > OA URL > DOI
- **Chrome automation** — Uploads sources via browser to the correct notebook

### Standalone Actions
- Find Literature, Rewrite Notes, Organize Zotero, Sync Obsidian, Upload to NotebookLM, Reading Status, Research Gaps, Citation Graph — each runnable independently

---

## Setup

### Prerequisites

- **Python 3.10+**
- **pyzotero**: `pip install pyzotero`
- **Zotero desktop** running (for local API reads)
- **[zotero-skills](https://github.com/WenyuChiou/zotero-skills)** installed in `~/.claude/skills/`

### MCP Connectors

| Connector | Purpose |
|---|---|
| paper-search-mcp | Searching arXiv, Semantic Scholar, PubMed, CrossRef |
| Zotero MCP | Reading Zotero library (read-only) |
| Desktop Commander | Running Python scripts, writing files |
| Claude in Chrome | (Optional) Automating NotebookLM uploads |

### Configuration

See `references/customization.md` for full setup guide including paths, categories, notebooks, and platform adaptation.

---

## Project Structure

```
~/.claude/skills/knowledge-base/
├── SKILL.md              # Core pipeline instructions for AI assistants
├── README.md             # English
├── README_zh-TW.md       # 繁體中文
└── references/
    ├── paper-template.md       # Obsidian note template
    ├── categories.md           # Classification system, keywords, WIKI_MERGE
    ├── obsidian-conventions.md # Markdown best practices, YAML template
    ├── dataview-queries.md     # Ready-to-use Dataview queries
    ├── customization.md        # Setup guide for other users
    └── setup-guide.md          # First-time MCP configuration
```

---

## Non-Claude CLI Adaptation

| CLI | How to load |
|---|---|
| **Claude Code** | Place in `~/.claude/skills/` — auto-loaded |
| **Codex CLI** | Pass `SKILL.md` as context via `-C` |
| **Gemini CLI** | Include in system prompt or project context |
| **Cursor / Windsurf** | Add to `.cursor/rules` or equivalent |

---

## License

MIT

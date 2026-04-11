# Research Hub

> One-command academic literature pipeline: search, save, summarize, upload — from a single Claude Code trigger.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-lightgrey.svg)](.github/workflows/ci.yml)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)]()

[English](README.md) | [繁體中文](README_zh-TW.md)

> ⚠️ **v0.2.1 alpha** — this is a personal research tool shared publicly. Expect rough edges. The NotebookLM Chrome upload step is fragile and can be skipped.

---

## Why Research Hub?

Most Zotero ↔ Obsidian tools keep two systems in sync. Research Hub does something different: it runs the whole research ingest flow as a single atomic action.

| Tool | Scope | Focus |
|---|---|---|
| obsidian-zotero-integration | Sync two systems | Sync-centric |
| ZotLit | Bidirectional sync | Sync-centric |
| Paperpile | Cloud library | Citation management |
| Zotfile | File organization | PDF filing |
| **Research Hub** | **Full pipeline (search → save → summarize → upload)** | **Workflow-centric** |

It is the only tool that integrates paper search, Zotero ingestion, Obsidian note generation, and NotebookLM upload behind one trigger phrase, and the only one with LLM-based classification baked into the flow.

---

## Pipeline

```
"add to Research Hub: <topic>"
    ↓
[1] Classify    (LLM reads title + abstract → category + sub-category)
[2] Search      (Semantic Scholar + arXiv + CrossRef + PubMed in parallel)
[3] Select      (results table, user picks)
[4] Save        (Zotero item + Obsidian note + hub page update)
[5] Upload      (optional — NotebookLM via Chrome automation)
[6] Build       (rebuild hub index + Obsidian graph)
[7] Explore     (citation graph; offer to add related papers)
```

Every step can also run standalone: find literature, rewrite notes, organize Zotero, sync Obsidian, upload to NotebookLM, track reading status, find research gaps, explore citation graphs.

---

## Quick start

```bash
# 1. Clone and enter
git clone https://github.com/WenyuChiou/research-hub
cd research-hub

# 2. Install (editable, with dev deps for tests)
pip install -e '.[dev]'

# 3. Copy the example config
cp config.json.example config.json

# 4. Edit config.json — set at minimum:
#    knowledge_base.root   → your Obsidian vault root
#    zotero.library_id     → from https://www.zotero.org/settings/keys
#    zotero.default_collection → a collection key you've created

# 5. Verify
python scripts/verify_setup.py
```

For the full walkthrough with troubleshooting, see [docs/setup.md](docs/setup.md).

---

## Dependencies

Required:

| Component | Purpose |
|---|---|
| Python 3.10+ | Runtime |
| [Zotero Desktop](https://www.zotero.org/download/) | Local library + local API on `localhost:23119` |
| [Zotero Web API key](https://www.zotero.org/settings/keys) | Writes (create items, add notes) via `pyzotero` |
| [Obsidian](https://obsidian.md/) vault | Target for generated notes + hub pages |
| [Claude Code](https://docs.claude.com/en/docs/claude-code) | Runs the skill and orchestrates the pipeline |
| [zotero-skills](https://github.com/WenyuChiou/zotero-skills) | Sibling skill — Zotero CRUD primitives |

Optional:

| Component | Purpose |
|---|---|
| [NotebookLM](https://notebooklm.google.com/) | Step 5 source upload; requires a Google account |
| Chrome + Claude in Chrome | Drives NotebookLM upload automation |

Claude Code MCP connectors used by the skill:

- `paper-search-mcp` — arXiv, Semantic Scholar, CrossRef, PubMed
- `Zotero MCP` — read-only library inspection
- `Desktop Commander` — file writes from inside the skill

---

## Project structure

```
research-hub/
├── src/research_hub/       # Package source
│   ├── config.py           # Portable config (env > config.json > defaults)
│   ├── pipeline.py         # run_pipeline() entry point
│   ├── cli.py              # `research-hub` console script
│   ├── vault/              # Obsidian vault builder, categorizer, repair
│   └── zotero/             # Local + web API client, fetch/extract helpers
├── tests/                  # 42 unit tests (pipeline, zotero, vault, config)
├── scripts/
│   └── verify_setup.py     # Post-install sanity check
├── references/             # Categories, templates, Dataview queries
├── skills/
│   ├── knowledge-base/     # The Claude Code skill itself
│   └── zotero-skills/      # Sibling skill stub
├── docs/
│   ├── setup.md            # First-time install walkthrough
│   └── customization.md    # Adapting the pipeline to other domains
├── config.json.example     # Sanitized config template
├── .github/workflows/ci.yml
├── pyproject.toml
├── LICENSE                 # MIT
└── README.md
```

---

## Customization

The pipeline is domain-agnostic. The default config targets flood risk + ABM research because that is where it was originally developed, but the category system, Zotero collections, and NotebookLM notebook names all live in `config.json`. See [docs/customization.md](docs/customization.md) for worked examples adapting the pipeline to a chemistry lab and to an economics survey research group.

---

## Roadmap

Phase 2 (planned, not yet in this release):

- Semantic search over the vault via local RAG
- Incremental hub build instead of full reparse
- Duplicate detection across Obsidian notes (not only Zotero)
- Deterministic classification audit log with rationale capture
- Human-in-the-loop `verified: false` flag on auto-generated note sections

---

## Contributing

Contributions welcome. Please open an issue before large changes so we can align on scope. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, branch naming, and commit conventions.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Acknowledgements

Built on top of the work of [Zotero](https://www.zotero.org/), [Obsidian](https://obsidian.md/), [Semantic Scholar](https://www.semanticscholar.org/), [NotebookLM](https://notebooklm.google.com/), and [Claude Code](https://docs.claude.com/en/docs/claude-code). Paper search tooling via the [paper-search-mcp](https://github.com/openags/paper-search-mcp) community server.

# research-hub

> Zotero + Obsidian + NotebookLM, wired together for AI agents.

[![PyPI](https://img.shields.io/pypi/v/research-hub-pipeline.svg)](https://pypi.org/project/research-hub-pipeline/)
[![Tests](https://img.shields.io/badge/tests-1113%20passing-brightgreen.svg)](docs/audit_v0.28.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

繁體中文說明 → [README.zh-TW.md](README.zh-TW.md)

![Dashboard Overview](docs/images/dashboard-overview.png)

---

## What this is

A CLI + MCP server that does three things at once:

1. **Ingest** academic papers into Zotero (citations) + Obsidian (structured notes) + NotebookLM (briefings) — one command.
2. **Organize** papers into clusters, sub-topics, and an Obsidian graph coloured by research label.
3. **Serve** 52 MCP tools so Claude Code / Codex / any MCP-compatible AI can drive the whole thing.

Built for PhD students and research teams who already use AI agents daily and don't want to context-switch between six tabs.

## Source code vs vault

research-hub has two separate locations on your computer. This is intentional:

| | Source code | Vault |
|---|---|---|
| **What** | The Python package + CLI | Your research data |
| **Where** | `site-packages/research_hub/` (managed by pip) | `~/knowledge-base/` (default, you choose during `init`) |
| **Contains** | CLI, MCP server, dashboard renderer | Paper notes, Obsidian graph, crystals, Zotero sync |
| **Shared?** | Yes — same package for every user | No — each user has their own vault |

After `pip install`, run `research-hub init` to create your vault. If you already have an Obsidian vault, point `init` at it — research-hub adds its folders alongside your existing notes without overwriting anything.

Run `research-hub where` at any time to see exactly where your config and vault live.

## What makes it different

### 1. Crystals — pre-computed answers, not lazy retrieval (v0.28)

Every RAG system, including Karpathy's "LLM wiki", still assembles context at query time. research-hub's answer: **store the AI's reasoning, not the inputs**.

For each research cluster, you generate ~10 canonical Q→A "crystals" once (via emit/apply, using any LLM you like). When an AI agent asks "what's the SOTA in X?", it reads a pre-written 100-word paragraph — not 20 paper abstracts.

```bash
research-hub crystal emit --cluster llm-agents-software-engineering > prompt.md
# Feed prompt.md to Claude/GPT/Gemini, save answer as crystals.json
research-hub crystal apply --cluster llm-agents-software-engineering --scored crystals.json
```

Token cost per cluster-level query: **~1 KB** (crystal read) vs ~30 KB (cluster digest). 30× compression without losing quality, because the quality was pre-computed.

[→ Why this is not RAG](docs/anti-rag.md)

### 2. Live dashboard with direct execution (v0.27)

```bash
research-hub serve --dashboard
```

Opens a localhost HTTP dashboard at `http://127.0.0.1:8765/`. Every Manage-tab button **directly executes** the CLI command instead of copying to clipboard. Vault changes push to the browser via Server-Sent Events. Fallback to static clipboard mode when the server isn't running.

![Live dashboard](docs/images/dashboard-manage-live.png)

### 3. Obsidian graph auto-coloured by label (v0.27)

```bash
research-hub vault graph-colors --refresh
```

Writes 14 colour groups to `.obsidian/graph.json`: 5 per cluster path + 9 per paper label (`seed`, `core`, `method`, `benchmark`, `survey`, `application`, `tangential`, `deprecated`, `archived`). Every `research-hub dashboard` run auto-refreshes them. Open Obsidian Graph View — your vault is visually structured by meaning, not just file tree.

![Obsidian Graph coloured by label](docs/images/obsidian-graph.png)

### 4. Sub-topic-aware Library + citation-graph cluster split (v0.27)

Big clusters (331 papers?) don't render as a flat list anymore. They're grouped by sub-topic, each expandable. And if your cluster has no sub-topics yet:

```bash
research-hub clusters analyze --cluster my-big-cluster --split-suggestion
```

Uses Semantic Scholar citation graph + networkx community detection to suggest 3-8 coherent sub-topics. Writes a markdown report you review before running `topic apply-assignments`.

![Library tab with sub-topics](docs/images/dashboard-library-subtopic.png)

---

## Install

```bash
pip install research-hub-pipeline
research-hub init              # interactive config + vault layout
research-hub serve --dashboard # opens browser
```

Python 3.10+. No OpenAI/Anthropic API key required — research-hub is provider-agnostic (all AI generation uses emit/apply pattern; you feed prompts to your own AI).

## For Claude Code / Claude Desktop users

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "research-hub": {
      "command": "research-hub",
      "args": ["serve"]
    }
  }
}
```

Then talk to Claude:

> "Claude, add arxiv 2310.06770 to a new cluster called LLM-SE"
> "Claude, generate crystals for the LLM-SE cluster"
> "Claude, what's this cluster about?" → Claude calls `list_crystals` + `read_crystal` → gets the pre-written 100-word answer

52 MCP tools cover: paper ingest, cluster CRUD, labels, quotes, draft composition, citation graph, NotebookLM, crystal generation, fit-check, autofill.

## Quickstart (5 commands)

```bash
# 1. Initialize vault
research-hub init

# 2. Ingest one paper
research-hub add 10.48550/arxiv.2310.06770 --cluster llm-agents

# 3. Open live dashboard
research-hub serve --dashboard

# 4. Generate crystals once you have a few papers
research-hub crystal emit --cluster llm-agents > prompt.md
# (feed prompt.md to your AI, save response as crystals.json)
research-hub crystal apply --cluster llm-agents --scored crystals.json

# 5. Ask your AI questions — it reads crystals, not papers
# (via Claude Desktop MCP, or any MCP-compatible client)
```

## Status

- **Latest**: v0.28.0 (2026-04-15)
- **Tests**: 1113 passing, 12 skipped, 5 xfail baselines (documented search-quality issues)
- **Platforms**: Windows, macOS, Linux
- **Python**: 3.10+
- **Dependencies**: `pyzotero`, `pyyaml`, `requests`, `rapidfuzz`, `networkx`, `platformdirs` (all pure-Python)
- **Optional**: `playwright` extra for NotebookLM browser automation

## Architecture docs

- [Anti-RAG crystals](docs/anti-rag.md) — why pre-computed Q→A beats retrieval
- [Audit reports](docs/) — `audit_v0.26.md`, `audit_v0.27.md`, `audit_v0.28.md`
- [NotebookLM setup](docs/notebooklm.md) — CDP attach flow + troubleshooting
- [Papers input schema](docs/papers_input_schema.md) — ingestion pipeline reference

## Workflow reference

| Stage | Command | What it does |
|---|---|---|
| **Init** | `init` / `doctor` | First-time config + health check |
| **Find** | `search` / `verify` / `discover new` | Multi-backend paper search + DOI resolution + AI-scored discovery |
| **Ingest** | `add` / `ingest` | One-shot or bulk paper ingest into Zotero + Obsidian |
| **Organize** | `clusters new/list/show/bind/merge/split/rename/delete` | Cluster CRUD |
| **Topic** | `topic scaffold/propose/assign/build` | Sub-topic notes from `subtopics:` frontmatter |
| **Label** | `label` / `find --label` / `paper prune` | Canonical label vocabulary (seed/core/method/...) |
| **Crystal** | `crystal emit/apply/list/read/check` | Pre-computed canonical Q→A answers |
| **Analyze** | `clusters analyze --split-suggestion` | Citation-graph community detection for big clusters |
| **Sync** | `sync status` / `pipeline repair` | Detect + repair Zotero ↔ Obsidian drift |
| **Dashboard** | `dashboard` / `serve --dashboard` / `vault graph-colors` | Static HTML or live HTTP server + auto-refresh Obsidian graph |
| **NotebookLM** | `notebooklm bundle/upload/generate/download` | Browser-automated NLM flows (CDP attach) |
| **Write** | `quote` / `compose-draft` / `cite` | Quote capture, markdown draft assembly, BibTeX export |

## Two personas

| Persona | Install | Zotero? | Best for |
|---|---|---|---|
| **Researcher** (default) | `pip install research-hub-pipeline[playwright]` | Yes | PhD students, academic literature review |
| **Analyst** | `research-hub init --persona analyst` | No — Obsidian only | Industry research, white papers, technical docs |

Both personas get the same dashboard, MCP server, and crystal system.

## For developers

```bash
git clone https://github.com/WenyuChiou/research-hub.git
cd research-hub
pip install -e '.[dev,playwright]'
python -m pytest -q  # 1113 passing
```

Package name on PyPI: **research-hub-pipeline**
CLI entry point: **research-hub**

## License

MIT. See [LICENSE](LICENSE).

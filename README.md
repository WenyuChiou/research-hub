# research-hub

> **One sentence in. Cluster + papers + AI brief out. ~50 seconds.**
> Zotero + Obsidian + NotebookLM, wired together for AI agents with no OpenAI or Anthropic API key required.

![research-hub dashboard demo, real screen recording](docs/images/dashboard-walkthrough.gif)

[![PyPI](https://img.shields.io/pypi/v/research-hub-pipeline.svg)](https://pypi.org/project/research-hub-pipeline/)
[![Tests](https://img.shields.io/badge/tests-1740%20passing-brightgreen.svg)](docs/audit_v0.45.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

繁體中文: [README.zh-TW.md](README.zh-TW.md) | [Watch the full-res mp4](docs/demo/dashboard-walkthrough.mp4)

---

## Works with any AI host

If your AI can load an MCP tool, run a shell command, or make an HTTP call, it can drive research-hub.

| Your AI | How research-hub connects |
|---|---|
| Claude Desktop | MCP stdio via `claude_desktop_config.json` |
| Claude Code | MCP stdio plus bundled skill files |
| Cursor, Continue.dev, Cline, Roo Code, VS Code Copilot | Same MCP config shape, host-specific settings file |
| OpenClaw or any MCP-compatible host | MCP stdio |
| ChatGPT, Claude.ai web, Gemini web, OpenAI Custom GPT | REST JSON at `/api/v1/*` with bearer-token auth and CORS |
| Codex CLI, Gemini CLI, GPT Code Interpreter, LangChain, AutoGen, CrewAI | Shell subprocess; every command supports `--json` where useful |
| Your own Python script | `from research_hub.auto import auto_pipeline` |

---

## Install + first run

### Preview before installing accounts

```bash
pip install research-hub-pipeline
research-hub dashboard --sample    # opens the dashboard on a bundled sample vault
```

No accounts, no Zotero, no NotebookLM. Just see the end-state UI.

### Let your AI install it

Paste this into Claude Desktop, Claude Code, Cursor, Continue, ChatGPT, Gemini, or another shell-capable AI:

```text
Please install research-hub on my machine. It is a Python package that pipes
academic papers into Zotero + Obsidian + NotebookLM and exposes an MCP server.

1. Check `python --version`. If it is below 3.10, tell me to upgrade first.
2. Run `pip install research-hub-pipeline[playwright,secrets]`.
3. Run `research-hub setup`. Stop and pass me the prompts as they appear.
   Answer the first question (use Zotero? y/N) on my behalf only if I have
   told you. Chrome-based NotebookLM login will auto-launch; I'll finish it.
4. Ask me for a topic and run `research-hub auto "TOPIC"`.
```

### Or install manually

```bash
pip install research-hub-pipeline[playwright,secrets]
research-hub setup                            # v0.62: init + install --platform + NLM login
research-hub auto "your research topic"
research-hub serve --dashboard
```

For a first smoke test without NotebookLM automation:

```bash
research-hub auto "your research topic" --no-nlm
```

Analyst and internal-KM users can skip Zotero and ingest local material:

```bash
pip install research-hub-pipeline[import,secrets]
research-hub setup --persona analyst
research-hub import-folder ./papers --cluster my-local-review
research-hub auto "related literature" --no-nlm
```

| Persona | Install extra |
|---|---|
| Researcher | `[playwright,secrets]` |
| Humanities | `[playwright,secrets]` |
| Analyst | `[import,secrets]` |
| Internal KM | `[import,secrets]` |

Python 3.10+ is required. Optional extras: `[playwright]` for NotebookLM, `[import]` for local PDF/DOCX/MD/TXT/URL ingest, `[secrets]` for OS-keyring credential storage, `[mcp]` for MCP server dependencies.

---

## Hook to your AI host

For Claude Desktop, Cursor, Continue.dev, Cline, VS Code Copilot, OpenClaw, or another MCP host, add:

```json
{ "mcpServers": { "research-hub": { "command": "research-hub", "args": ["serve"] } } }
```

Restart the host. Then ask naturally:

> Find me 5 papers on agent-based modeling and put them in a notebook.

The AI can call `auto_research_topic(topic="agent-based modeling", max_papers=5)` and ingest papers, generate a NotebookLM brief, and update the vault.

Install host-specific skill files:

```bash
research-hub install --platform claude-code
research-hub install --platform cursor
research-hub install --platform codex
research-hub install --platform gemini
```

Browser-only AIs can use the REST API instead:

```bash
curl -X POST http://127.0.0.1:8765/api/v1/plan \
     -H "Content-Type: application/json" \
     -d "{\"intent\":\"research harness engineering\"}"
```

Full reference: [MCP tools](docs/mcp-tools.md).

---

## Dashboard tour

`research-hub serve --dashboard` opens `http://127.0.0.1:8765/`. Six tabs; the four most useful ones:

**Overview** — treemap over clusters + storage map + health summary.

![Overview](docs/images/hero/dashboard-overview.png)

**Library** — per-cluster drill-down with papers, sub-topics, and per-paper actions.

![Library](docs/images/hero/dashboard-library-subtopic.png)

**Diagnostics** — grouped drift alerts and readiness checks.

![Diagnostics](docs/images/hero/dashboard-diagnostics.png)

**Manage** — every CLI action as a button, with an inline result drawer, shared confirmation modal, and per-paper row actions.

![Manage](docs/images/hero/dashboard-manage-live.png)

Briefings and Writing tabs are also available — see the [dashboard walkthrough](docs/dashboard-walkthrough.md) and [persona variants](docs/personas.md).

---

## Inside Obsidian

Every ingested paper becomes a real Markdown note with structured frontmatter. Every cluster can also get an Obsidian Bases dashboard.

**Cluster Bases dashboard** — generated `.base` file with sortable paper metadata.

<img src="docs/images/obsidian-bases-dashboard.png" alt="Obsidian Bases dashboard for a cluster" width="640">

**Per-paper note** — title, authors, year, DOI, Zotero key, tags, status, cluster, and verification metadata.

<img src="docs/images/obsidian-paper-note.png" alt="Single paper note rendered with Properties view" width="640">

Crystals are plain Markdown notes under `hub/<cluster>/crystals/*.md`, so they can be linked, searched, and read by MCP tools at very low token cost.

---

## Inside Zotero

Every ingested paper gets a namespaced tag set so you can filter your library by research-hub context:

| Tag | Meaning |
|---|---|
| `research-hub` | Ingested through this pipeline (vs. manual Zotero adds) |
| `cluster/<slug>` | Which research cluster the paper belongs to |
| `category/<arxiv-code>` | arXiv category like `cs.AI`, `econ.GN` (v0.63) |
| `type/<publication-type>` | `Review`, `JournalArticle`, etc. from Semantic Scholar (v0.63) |
| `src/<backend>` | Search backend that discovered it: `arxiv`, `semantic_scholar`, `crossref`, `zotero` |

Every paper also gets a child note with `Summary / Key Findings / Methodology / Relevance`, pulled from the Obsidian frontmatter the pipeline generated. Papers that were in Zotero before research-hub existed can be backfilled with `research-hub zotero backfill --tags --notes --apply`.

---

## Feature matrix at-a-glance

| Capability | Command or MCP tool | Notes |
|---|---|---|
| One-shot setup | `research-hub setup` | Runs init + install --platform + NotebookLM login in one call (v0.62) |
| Lazy research pipeline | `research-hub auto "topic"` / `auto_research_topic` | Search, ingest, bundle, upload, generate, download |
| Plan before running | `research-hub plan "intent"` / `plan_research_workflow` | Suggests field, cluster slug, and max papers |
| Zotero hygiene | `research-hub zotero backfill --tags --notes [--apply]` | Fills missing tags + notes on legacy items (v0.61) |
| Cluster cascade delete | `research-hub clusters delete <slug> [--apply --force]` | Preview impact on Obsidian + Zotero + dedup + memory + crystals (v0.62) |
| No-NotebookLM smoke test | `research-hub auto "topic" --no-nlm` | Validates search and vault ingest without browser automation |
| Local file ingest | `research-hub import-folder <folder> --cluster <slug>` | PDF, DOCX, MD, TXT, URL |
| Ad-hoc cluster Q&A | `research-hub ask <cluster> "question"` / `ask_cluster_notebooklm` | Top-level CLI takes cluster first, then question |
| NotebookLM operations | `research-hub notebooklm upload --cluster <slug>` | Browser automation with persistent Chrome |
| Pre-computed crystals | `research-hub crystal emit --cluster <slug>` | Canonical answers cached as Markdown |
| Structured memory | `research-hub memory emit --cluster <slug>` | Entities, claims, methods |
| Live dashboard | `research-hub serve --dashboard` | HTTP dashboard with action buttons |
| Sample preview | `research-hub dashboard --sample` | Temporary bundled vault, no accounts |
| Lazy maintenance | `research-hub tidy` | Doctor, dedup, bases refresh, cleanup preview |
| Garbage collection | `research-hub cleanup --all --apply` | Bundles, debug logs, stale artifacts |
| Cluster repair | `research-hub clusters rebind --emit` then `--apply` | Rebinds orphaned notes |
| Obsidian Bases | `research-hub bases emit --cluster <slug>` | Generated `.base` dashboard |
| Web search | `research-hub websearch "query"` / `web_search` | Tavily, Brave, Google CSE, DDG fallback |

---

## vs alternatives

research-hub does not replace Zotero, Obsidian, or NotebookLM. It connects them so an AI agent can operate the workflow.

| What you can do | Zotero alone | NotebookLM alone | Generic RAG | Obsidian-Zotero plugin | research-hub |
|---|---:|---:|---:|---:|---:|
| Search arXiv + Semantic Scholar in one command | No | No | DIY | No | Yes |
| Ingest into Zotero and Obsidian and NotebookLM | No | No | DIY | Partial | Yes |
| AI brief from your collection | No | Manual | DIY | No | Yes |
| Cached canonical answers | No | No | Re-fetches | No | Yes |
| Structured memory layer | No | No | Usually chunks | No | Yes |
| Direct AI-agent control via MCP | No | No | DIY | No | Yes |
| Live dashboard with action buttons | No | No | No | No | Yes |
| Per-cluster Obsidian Bases dashboard | No | No | No | No | Yes |
| No API key required for AI | n/a | Yes | Usually no | n/a | Yes |
| Local-first vault you own | Partial | No | Depends | Yes | Yes |

The practical fit: research-hub is most useful if you already use at least two of Zotero, Obsidian, and NotebookLM and want your AI assistant to run the repetitive steps.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `research-hub init` reports Chrome warnings | Chrome is missing or patchright cannot find it | Install Chrome, then run `research-hub doctor` |
| `research-hub notebooklm login` opens a browser but Google blocks login | New-device or bot challenge | Complete the visible browser sign-in and phone challenge |
| `research-hub auto` finds 0 papers | Topic too narrow or search backend transient issue | Re-run with `--max-papers 20` or rephrase |
| NotebookLM upload or generate fails | NotebookLM UI changed or login expired | Run `research-hub notebooklm login`; then resume with `research-hub notebooklm bundle/upload/generate/download --cluster <slug>` |
| `auto --with-crystals` cannot find an LLM CLI | `claude`, `codex`, or `gemini` is not on PATH | Install one, or use `crystal emit` and `crystal apply` manually |
| Claude Desktop cannot see the MCP server | MCP config is in the wrong file or host was not restarted | Check the host config path and restart Claude Desktop |
| `init` reports Zotero warnings but you do not use Zotero | Persona expects Zotero | Re-run `research-hub setup --persona analyst` or `--persona internal` |
| `research-hub clusters delete` refuses to delete | Cluster has papers, notes, or Zotero items | Re-run with `--apply --force` after reviewing the cascade preview |
| `research-hub auto` errors "cluster already has N papers" | Cluster is non-empty and you ran `auto --cluster <slug>` without a flag | Add `--append` (add more) or `--force` (overwrite) |
| Zotero items miss `research-hub` tags or notes | Items were created before v0.61 or pipeline failed mid-run | `research-hub zotero backfill --tags --notes --apply` |

For broader checks, run:

```bash
research-hub doctor --autofix
```

---

## Docs + Status + Dev

Docs: [First 10 minutes](docs/first-10-minutes.md), [lazy mode](docs/lazy-mode.md), [dashboard walkthrough](docs/dashboard-walkthrough.md), [MCP tools](docs/mcp-tools.md), [personas](docs/personas.md), [NotebookLM setup](docs/notebooklm.md), [import folder](docs/import-folder.md), [CLI reference](docs/cli-reference.md), [CHANGELOG](CHANGELOG.md).

Status:

- Latest: v0.63.0; see [CHANGELOG](CHANGELOG.md) for package history.
- Tests: 1740 passing.
- MCP tools: 83.
- REST endpoints: 12 at `/api/v1/*`.
- Bundled skills: `research-hub` and `research-hub-multi-ai`.

Developer setup:

```bash
git clone https://github.com/WenyuChiou/research-hub.git
cd research-hub
pip install -e ".[dev,playwright]"
python -m pytest -q
```

Contributing: [CONTRIBUTING.md](CONTRIBUTING.md). Package on PyPI: `research-hub-pipeline`. CLI entry point: `research-hub`.

## License

MIT. See [LICENSE](LICENSE).

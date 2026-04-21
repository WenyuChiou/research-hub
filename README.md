# research-hub

> **One sentence in. Cluster + papers + AI brief out. ~50 seconds.**
> Zotero + Obsidian + NotebookLM, wired together for AI agents with no OpenAI or Anthropic API key required.

![research-hub dashboard demo, real screen recording](docs/images/dashboard-walkthrough.gif)

[![PyPI](https://img.shields.io/pypi/v/research-hub-pipeline.svg)](https://pypi.org/project/research-hub-pipeline/)
[![Tests](https://img.shields.io/badge/tests-1666%20passing-brightgreen.svg)](docs/audit_v0.45.md)
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
Please install research-hub on my machine end-to-end. It is a Python package
that pipes academic papers into Zotero + Obsidian + NotebookLM and exposes an
MCP server.

Do these steps in order. Stop and ask me whenever you need interactive input:

1. Check `python --version`. If it is below 3.10, tell me to upgrade first.
2. Run `pip install research-hub-pipeline[playwright,secrets]`.
3. Run `research-hub init`. Pass the prompts to me. The persona options are
   `researcher`, `humanities`, `analyst`, and `internal`.
4. Run `research-hub notebooklm login` and tell me to finish Google sign-in.
5. Add this MCP entry to the AI host I use:
   `{ "mcpServers": { "research-hub": { "command": "research-hub", "args": ["serve"] } } }`
6. Run `research-hub install --platform claude-code` or the matching platform:
   `cursor`, `codex`, or `gemini`.
7. Ask me for a topic and run `research-hub auto "TOPIC" --with-crystals`.
```

### Or install manually

```bash
pip install research-hub-pipeline[playwright,secrets]
research-hub init
research-hub notebooklm login
research-hub plan "your research topic"
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
research-hub init --persona analyst
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

**Diagnostics** — grouped drift alerts and readiness checks (v0.48 redesign groups 59 raw alerts into ~5 cards).

![Diagnostics](docs/images/hero/dashboard-diagnostics.png)

**Manage** — every CLI action as a button; v0.58 adds an inline result drawer, shared confirmation modal, and per-paper row actions.

![Manage](docs/images/hero/dashboard-manage-live.png)

Briefings and Writing tabs are also available — see the [dashboard walkthrough](docs/dashboard-walkthrough.md) and [persona variants](docs/personas.md).

---

## Inside Obsidian

Every ingested paper becomes a real Markdown note with structured frontmatter. Every cluster can also get an Obsidian Bases dashboard.

| | |
|---|---|
| ![Obsidian Bases dashboard for a cluster](docs/images/obsidian-bases-dashboard.png) | ![Single paper note rendered with Properties view](docs/images/obsidian-paper-note.png) |
| **Cluster Bases dashboard**: generated `.base` file with sortable paper metadata | **Per-paper note**: title, authors, year, DOI, Zotero key, tags, status, cluster, and verification metadata |

Crystals are plain Markdown notes under `hub/<cluster>/crystals/*.md`, so they can be linked, searched, and read by MCP tools at very low token cost.

---

## Feature matrix at-a-glance

| Capability | Command or MCP tool | Notes |
|---|---|---|
| Lazy research pipeline | `research-hub auto "topic"` / `auto_research_topic` | Search, ingest, bundle, upload, generate, download |
| Plan before running | `research-hub plan "intent"` / `plan_research_workflow` | Suggests field, cluster slug, and max papers |
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
| `init` reports Zotero warnings but you do not use Zotero | Persona expects Zotero | Re-run `research-hub init --persona analyst` or `--persona internal` |

For broader checks, run:

```bash
research-hub doctor --autofix
```

---

## Docs + Status + Dev

Docs: [First 10 minutes](docs/first-10-minutes.md), [lazy mode](docs/lazy-mode.md), [dashboard walkthrough](docs/dashboard-walkthrough.md), [MCP tools](docs/mcp-tools.md), [personas](docs/personas.md), [NotebookLM setup](docs/notebooklm.md), [import folder](docs/import-folder.md), [CLI reference](docs/cli-reference.md), [CHANGELOG](CHANGELOG.md).

Status:

- Latest: v0.53.0 in the public README status notes; see [CHANGELOG](CHANGELOG.md) for package history.
- Tests badge: 1661 passing.
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

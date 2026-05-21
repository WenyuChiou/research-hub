# research-hub

> **Turn your research stack into an AI-operable workspace.**
> Use Zotero, Obsidian, and NotebookLM together, or start with any two. research-hub gives your AI assistant a real CLI, MCP server, REST API, and dashboard for repeatable literature workflows.

![research-hub dashboard demo, real screen recording](docs/images/dashboard-walkthrough.gif)

[![PyPI](https://img.shields.io/pypi/v/research-hub-pipeline.svg)](https://pypi.org/project/research-hub-pipeline/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

[![Zotero](https://img.shields.io/badge/Zotero-CC2936?logo=zotero&logoColor=white)](https://www.zotero.org/)
[![Obsidian](https://img.shields.io/badge/Obsidian-7C3AED?logo=obsidian&logoColor=white)](https://obsidian.md/)
[![NotebookLM](https://img.shields.io/badge/NotebookLM-4285F4?logo=google&logoColor=white)](https://notebooklm.google.com/)
[![SafeSkill 60/100](https://img.shields.io/badge/SafeSkill-60%2F100_Use%20with%20Caution-orange)](https://safeskill.dev/scan/wenyuchiou-research-hub)

Traditional Chinese: [README.zh-TW.md](README.zh-TW.md) | [Watch the full-res mp4](docs/demo/dashboard-walkthrough.mp4)

> 📚 Part of the [**agentic AI learning roadmap**](https://github.com/WenyuChiou/awesome-agentic-ai-zh) — a 7-stage curated path for building agentic AI, multilingual (zh-TW · zh-Hans · English). This workspace is referenced in §13 (research workflow skills).

> 🧪 **Real-use signal:** in daily use by 1 PhD researcher (Lehigh CEE) tracking 7+ research clusters across Zotero + Obsidian + NotebookLM. Shipping since Apr 2026, docs updated for v0.95.0.

---

## Install + first run

Pick the path that matches the operator: a human researcher or the autonomous agent itself.

## Personae

research-hub supports two primary user personae:

- **Human researcher** (Wei-Ling persona): hydrology postdoc, knows Python pip + DOIs, never touched Claude / MCP / Obsidian. Start with [Human quickstart](#human-quickstart).
- **Autonomous agent** (Claude Cowork / OpenClaw / Hermes host): the AI itself is the operator, not a human. Start with [Autonomous agent quickstart](#autonomous-agent-quickstart).

## Required env vars

<!-- env-vars-table-start -->

| Name | Required | Purpose |
|---|---|---|
| `ZOTERO_API_KEY` | yes | Zotero web API auth, required for paper ingestion |
| `ZOTERO_LIBRARY_ID` | yes | Zotero library identifier |
| `SEMANTIC_SCHOLAR_API_KEY` | no | Lifts S2 rate limit from shared anonymous to 1 req/sec dedicated |
| `TAVILY_API_KEY` | no | Web search backend (alternative to DDG) |
| `BRAVE_API_KEY` | no | Web search backend (alternative to DDG) |

<!-- env-vars-table-end -->

## Autonomous agent quickstart

For Cowork-style hosts:

```bash
pip install research-hub-pipeline
python -m research_hub describe > capabilities.json
python -m research_hub setup --autonomous --vault ./vault --persona agent
# emits BootstrapReport JSON; exit code 0 if ready, 1 otherwise
```

Then drive operations via CLI `--json` mode or the bundled MCP server (`research-hub-mcp`). All report-shaped commands accept `--json`; capability introspection lives in `research-hub describe`.

**Note**: NotebookLM upload still requires one-time human-driven `research-hub notebooklm login` browser-based Google OAuth. Headless agent completion is upstream-blocked by Google's auth flow.

**Note**: `auto_research_topic` (and `research-hub auto`) runs a fail-closed relevance check. Ensure a `claude` / `codex` / `gemini` CLI is reachable on PATH, or disable the relevance check, otherwise the run stops before the search with guidance rather than returning a silently empty result.

## Human quickstart

| You already have | First command |
|---|---|
| Zotero + Obsidian + NotebookLM | `pip install research-hub-pipeline[playwright,secrets]` then `research-hub setup` |
| Zotero + Obsidian, no NotebookLM | `pip install research-hub-pipeline[secrets]` then `research-hub setup --skip-login` |
| Obsidian + local PDFs only | `pip install research-hub-pipeline[import,secrets]` then `research-hub setup --persona analyst` |
| Just want to see it work (≤5 min, no accounts) | `pip install research-hub-pipeline` then `research-hub init --sample` |
| Nothing yet, browser preview only | `pip install research-hub-pipeline` then `research-hub dashboard --sample` |

`research-hub init --sample` (v0.89.1) copies a bundled demo vault
(5 papers + clusters + crystals + `_HOME.md`) and skips every
Zotero / NotebookLM / LLM probe — open `<vault>/_HOME.md` in
Obsidian to explore, then `research-hub setup --vault <vault>` when
you're ready for real accounts. Running bare `research-hub` (no
subcommand) now prints help instead of starting the pipeline.

Python 3.10+ is required (CI-gated 3.10–3.13; 3.14 runs in CI as an
experimental, non-gating cell). Add `[mcp]` if you want standalone
MCP server dependencies.

**Relevance judge (read before first `auto` run).** `research-hub
auto` runs a **fail-closed** relevance check by default. Keep a
`claude`, `codex`, or `gemini` CLI on PATH (any one is enough), or
pass `--no-fit-check` to skip relevance judging (papers still get
identifier + integrity checks; they are just not relevance-filtered).
With no judge and no flag, `auto` stops **before** the search with
actionable guidance instead of silently producing an empty vault.

| Persona | Best for | Install extra |
|---|---|---|
| Researcher | STEM papers, DOI/arXiv, Zotero-first workflows | `[playwright,secrets]` |
| Humanities | books, quotes, URL-only sources, Zotero + Obsidian | `[playwright,secrets]` |
| Analyst | industry research, local PDFs/reports, no Zotero required | `[import,secrets]` |
| Internal KM | lab/company knowledge bases, mixed file types | `[import,secrets]` |

Field presets for `discover new`, `search`, and related planning flows are `cs`, `bio`, `med`, `physics`, `math`, `social`, `econ`, `chem`, `astro`, `edu`, and `general`. There is no `hydrology` preset; use `general` intentionally.

---

## Why this exists

Most research tools are good at one part of the workflow:

- Zotero stores citations, metadata, and PDFs.
- Obsidian stores notes, links, and synthesis.
- NotebookLM turns source bundles into AI-readable briefs.

The painful part is the handoff. research-hub connects those handoffs so an AI agent can search, ingest, tag, summarize, repair, brief, and inspect your workspace without turning your library into an opaque RAG box.

You do **not** need all three tools on day one.

| Your current stack | What research-hub gives you first |
|---|---|
| Zotero + Obsidian | Paper search, Zotero metadata, Markdown notes, tags, Obsidian Bases dashboards |
| Obsidian + NotebookLM | Local PDF/DOCX/MD/TXT ingest, cluster dashboards, NotebookLM bundles and briefs |
| Zotero + NotebookLM | Zotero-backed paper selection, namespaced tags, NotebookLM upload/generate/download |
| Zotero + Obsidian + NotebookLM | Full loop: discover -> ingest -> organize -> brief -> answer -> maintain |
| No accounts yet | Sample dashboard and local smoke tests before connecting anything |

---

## What it does

research-hub is a local-first orchestration layer for research workflows:

- **CLI:** `research-hub auto`, `import-folder`, `ask`, `doctor`, `tidy`, `clusters`, `zotero`, `notebooklm`, `crystal`, and more.
- **MCP server:** lets Claude Desktop, Claude Code, Cursor, Continue.dev, Cline, Roo Code, OpenClaw, and other MCP hosts operate the same workflow.
- **REST API:** exposes `/api/v1/*` for browser-only or HTTP-capable assistants.
- **Dashboard:** gives humans a live view of clusters, papers, diagnostics, briefs, writing support, and management actions.
- **Vault format:** writes normal Markdown, frontmatter, `.base` dashboards, cache files, and logs that you can inspect directly.
- **Authenticity gate (v0.95+):** every discovered paper must resolve to a real identifier (DOI / arXiv / PMID), pass integrity and relevance checks, or it is **quarantined with a recorded reason** and never written to the vault. No fabricated references — inspect rejects with `research-hub quarantine list`.

The core loop:

```text
topic or source folder
  -> discover or import sources
  -> verify authenticity (resolve + integrity + relevance) or quarantine
  -> enrich metadata
  -> write Zotero tags/notes when enabled
  -> write Obsidian Markdown notes and cluster dashboards
  -> bundle/upload/generate with NotebookLM when enabled
  -> cache answers as crystals and structured memory
```

---

## Is this for me? — vs alternatives

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
| No OpenAI/Anthropic API key required | n/a | Yes | Usually no | n/a | Yes |
| Local-first vault you own | Partial | No | Depends | Yes | Yes |

The practical fit: research-hub is most useful if you already use at least two of Zotero, Obsidian, and NotebookLM and want your AI assistant to run the repetitive steps.

---

## Connect your AI host

For Claude Desktop, Cursor, Continue.dev, Cline, VS Code Copilot, OpenClaw, or another MCP host:

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

Browser-only or HTTP-capable AIs can use the REST API:

```bash
curl -X POST http://127.0.0.1:8765/api/v1/plan \
     -H "Content-Type: application/json" \
     -d "{\"intent\":\"research harness engineering\"}"
```

Full reference: [MCP tools](docs/mcp-tools.md) and [AI integrations](docs/ai-integrations.md).

---

## Dashboard tour

`research-hub serve --dashboard` opens `http://127.0.0.1:8765/`.

**Overview**: treemap over clusters, storage map, and health summary.

![Overview](docs/images/hero/dashboard-overview.png)

**Library**: per-cluster drill-down with papers, sub-topics, and per-paper actions.

![Library](docs/images/hero/dashboard-library-subtopic.png)

**Diagnostics**: grouped drift alerts and readiness checks.

![Diagnostics](docs/images/hero/dashboard-diagnostics.png)

**Manage**: CLI actions as buttons, inline result drawer, confirmation modal, and per-paper row actions.

![Manage](docs/images/hero/dashboard-manage-live.png)

Briefings and Writing tabs are also available. See the [dashboard walkthrough](docs/dashboard-walkthrough.md) and [persona variants](docs/personas.md).

---

## Inside Obsidian

Every ingested paper becomes a real Markdown note with structured frontmatter. Every cluster can also get an Obsidian Bases dashboard.

**Cluster Bases dashboard**: generated `.base` file with sortable paper metadata.

<img src="docs/images/obsidian-bases-dashboard.png" alt="Obsidian Bases dashboard for a cluster" width="640">

**Per-paper note**: title, authors, year, DOI, Zotero key, tags, status, cluster, and verification metadata.

<img src="docs/images/obsidian-paper-note.png" alt="Single paper note rendered with Properties view" width="640">

Crystals are plain Markdown notes under `hub/<cluster>/crystals/*.md`, so they can be linked, searched, and read by MCP tools at very low token cost.

---

## Inside Zotero

Every ingested paper gets a namespaced tag set so you can filter your library by research-hub context:

| Tag | Meaning |
|---|---|
| `research-hub` | Ingested through this pipeline |
| `cluster/<slug>` | Which research cluster the paper belongs to |
| `category/<arxiv-code>` | arXiv category like `cs.AI` or `econ.GN` |
| `type/<publication-type>` | `Review`, `JournalArticle`, etc. from Semantic Scholar |
| `src/<backend>` | Search backend that discovered it: `arxiv`, `semantic_scholar`, `crossref`, `zotero` |

Every paper can also get a child note with `Summary / Key Findings / Methodology / Relevance`, derived from the Obsidian frontmatter. Papers that were in Zotero before research-hub existed can be backfilled with:

```bash
research-hub zotero backfill --tags --notes --apply
```

---

## Feature matrix

| Capability | Command or MCP tool | Notes |
|---|---|---|
| One-shot setup | `research-hub setup` | init + install + optional NotebookLM login + guided sample run |
| Lazy research pipeline | `research-hub auto "topic"` / `auto_research_topic` | Search, ingest, bundle, upload, generate, download |
| Authenticity quarantine review | `research-hub quarantine list` / `show <id>` / `restore <id>` | Inspect and optionally restore papers the authenticity gate rejected (with the failing layer + reason) |
| Plan before running | `research-hub plan "intent"` / `plan_research_workflow` | Suggests field, cluster slug, and max papers |
| Zotero hygiene | `research-hub zotero backfill --tags --notes [--apply]` | Fills missing tags and notes on legacy items |
| Cluster cascade delete | `research-hub clusters delete <slug> [--apply --force]` | Preview impact on Obsidian, Zotero, dedup, memory, and crystals |
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

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `research-hub init` reports Chrome warnings | Chrome is missing or patchright cannot find it | Install Chrome, then run `research-hub doctor` |
| `research-hub notebooklm login` opens a browser but Google blocks login | New-device or bot challenge | Complete the visible browser sign-in and phone challenge |
| `research-hub auto` finds 0 papers / empty vault | Topic too narrow OR papers were quarantined by the authenticity gate (unresolved DOI, failed integrity, or relevance-unjudged) | Re-run with `--max-papers 20` / rephrase; run `research-hub quarantine list` to see rejected papers + reasons |
| `research-hub auto` stops before searching: "no relevance judge on PATH" | Fail-closed relevance check and no `claude`/`codex`/`gemini` CLI found | Install a judge CLI, or re-run with `--no-fit-check` to skip relevance judging |
| NotebookLM upload or generate fails | NotebookLM UI changed or login expired | Run `research-hub notebooklm login`; then resume with `research-hub notebooklm bundle/upload/generate/download --cluster <slug>` |
| `auto --with-crystals` cannot find an LLM CLI | `claude`, `codex`, or `gemini` is not on PATH | Install one, or use `crystal emit` and `crystal apply` manually |
| Claude Desktop cannot see the MCP server | MCP config is in the wrong file or host was not restarted | Check the host config path and restart Claude Desktop |
| `init` reports Zotero warnings but you do not use Zotero | Persona expects Zotero | Re-run `research-hub setup --persona analyst` or `--persona internal` |
| `research-hub clusters delete` refuses to delete | Cluster has papers, notes, or Zotero items | Re-run with `--apply --force` after reviewing the cascade preview |
| `research-hub auto` errors "cluster already has N papers" | Cluster is non-empty and you ran `auto --cluster <slug>` without a flag | Add `--append` to add more, or `--force` to overwrite |
| Zotero items miss `research-hub` tags or notes | Items were created before v0.61 or pipeline failed mid-run | `research-hub zotero backfill --tags --notes --apply` |

For broader checks, run:

```bash
research-hub doctor --autofix
```

---

## Docs + Status + Dev

Docs: [First 10 minutes](docs/first-10-minutes.md), [lazy mode](docs/lazy-mode.md), [dashboard walkthrough](docs/dashboard-walkthrough.md), [MCP tools](docs/mcp-tools.md), [personas](docs/personas.md), [NotebookLM setup](docs/notebooklm.md), [import folder](docs/import-folder.md), [CLI reference](docs/cli-reference.md), [CHANGELOG](CHANGELOG.md).

Status:

- Current docs target: v0.95.0; see [CHANGELOG](CHANGELOG.md) for package history, [docs/stable-api.md](docs/stable-api.md) for the supported API surface, and [docs/file-formats.md](docs/file-formats.md) for parseable state-file schemas.
- MCP tools: inspect the live list with `python -m research_hub describe --filter mcp_tools`.
- REST endpoints: 12 at `/api/v1/*`.
- Bundled skills: inspect the live list with `python -m research_hub describe --filter skills`.

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

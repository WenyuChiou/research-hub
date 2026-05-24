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

Traditional Chinese: [README.zh-TW.md](README.zh-TW.md) | [Watch the full-res mp4](docs/demo/dashboard-walkthrough.mp4)

> 📚 Part of the [**agentic AI learning roadmap**](https://github.com/WenyuChiou/awesome-agentic-ai-zh) — a 7-stage curated path for building agentic AI, multilingual (zh-TW · zh-Hans · English). This workspace is referenced in §13 (research workflow skills).

> 🧪 **Real-use signal:** in daily use by 1 PhD researcher (Lehigh CEE) tracking 7+ research clusters across Zotero + Obsidian + NotebookLM. Shipping since Apr 2026, docs updated for v0.95.0.

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
- **Portable skill pack:** `SKILL.md` workflow instructions can be installed directly for Claude Code, Codex, Cursor, and Gemini, or copied manually into hosts that support skill/rules directories.
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

## Start Here

Pick the path with the fewest moving parts. You can add Zotero,
NotebookLM, MCP, or AI-host skills later.

| Goal | Accounts needed | Commands |
|---|---|---|
| Preview the dashboard only | None | `pip install research-hub-pipeline` then `research-hub dashboard --sample` |
| Try a demo vault | None | `pip install research-hub-pipeline` then `research-hub init --sample` |
| Work from local PDFs/DOCX/Markdown | Obsidian optional | `pip install "research-hub-pipeline[import,secrets]"` then `research-hub setup --persona analyst` |
| Zotero + Obsidian, no browser automation | Zotero | `pip install "research-hub-pipeline[secrets]"` then `research-hub setup --skip-login` |
| Full Zotero + Obsidian + NotebookLM loop | Zotero + Google | `pip install "research-hub-pipeline[playwright,secrets]"` then `research-hub setup` |
| Autonomous agent bootstrap | Existing vault or target folder | `python -m research_hub setup --autonomous --vault ./vault --persona agent` |

After setup, run:

```bash
research-hub doctor
research-hub serve --dashboard
```

For the first real ingestion, keep NotebookLM out of the path until
Zotero and Obsidian are healthy:

```bash
research-hub auto "agent-based modeling" --max-papers 3 --no-nlm
```

Then enable NotebookLM after the browser login works:

```bash
research-hub notebooklm login --auto-detect
research-hub notebooklm bundle --cluster <slug>
research-hub notebooklm upload --cluster <slug>
research-hub notebooklm generate --cluster <slug> --type brief
research-hub notebooklm download --cluster <slug>
```

`research-hub setup` also prints these next steps when it finishes.

## First-Run Checklist

| Item | Needed when | How to handle it |
|---|---|---|
| Python 3.10+ | Always | Use the same Python that runs `pip install research-hub-pipeline` |
| Zotero API key + library ID | Zotero-backed paper ingestion | Set `ZOTERO_API_KEY` and `ZOTERO_LIBRARY_ID`, then run `research-hub doctor` |
| Obsidian vault | Markdown note workflow | Point `setup` at a folder you can open in Obsidian; it is still plain Markdown |
| NotebookLM browser login | NotebookLM upload/generate/download | Run `research-hub notebooklm login --auto-detect`; Google OAuth still requires a visible human sign-in |
| LLM CLI for relevance judging | `research-hub auto` default path | Install `claude`, `codex`, `gemini`, `opencode`, `aichat`, `cursor`, configure a custom adapter, or pass `--no-fit-check` |
| AI-host integration | Claude/Codex/Cursor/Gemini/OpenClaw/etc. | Use MCP/REST for tool-calling hosts; use `research-hub install --platform ...` only for verified skill installer targets |

## Credential Reference

These variables are required only for Zotero-backed workflows. Local
file import, sample dashboards, MCP server startup, and REST API
inspection can run without them.

<!-- env-vars-table-start -->

| Name | Required | Purpose |
|---|---|---|
| `ZOTERO_API_KEY` | yes | Zotero web API auth, required for paper ingestion |
| `ZOTERO_LIBRARY_ID` | yes | Zotero library identifier |
| `SEMANTIC_SCHOLAR_API_KEY` | no | Uses an S2 API key and defaults to a conservative ~1 request/sec throttle |
| `SEMANTIC_SCHOLAR_RPS` | no | Optional S2 request-rate override; leave unset unless your key has a different quota |
| `TAVILY_API_KEY` | no | Web search backend (alternative to DDG) |
| `BRAVE_API_KEY` | no | Web search backend (alternative to DDG) |

<!-- env-vars-table-end -->

Semantic Scholar searches are deliberately paced. Without
`SEMANTIC_SCHOLAR_API_KEY`, research-hub uses a slower anonymous delay
because public traffic shares capacity. With a key, the default is
approximately one request per second and 429 responses are retried with
`Retry-After` / exponential backoff. If Semantic Scholar grants your key
a different quota, set `SEMANTIC_SCHOLAR_RPS` instead of editing code.

## Operator Modes

research-hub supports both human-first and agent-first setup.

For a human researcher, `research-hub setup` runs the onboarding wizard,
installs host-specific skills when it can detect the host, optionally
launches NotebookLM login, and offers a small sample run.

For an autonomous agent or Cowork-style host:

```bash
pip install research-hub-pipeline
python -m research_hub describe > capabilities.json
python -m research_hub setup --autonomous --vault ./vault --persona agent
# emits BootstrapReport JSON; exit code 0 if ready, 1 otherwise
```

Then drive operations via CLI `--json` mode or the bundled MCP server
(`research-hub-mcp`). All report-shaped commands accept `--json`;
capability introspection lives in `research-hub describe`.

**NotebookLM boundary.** NotebookLM upload still requires one-time
human-driven browser-based Google OAuth. Headless agents can prepare
bundles and read downloaded briefs, but they cannot complete Google's
first sign-in or phone challenge by themselves.

**Relevance judge boundary.** `auto_research_topic` and `research-hub
auto` run a fail-closed relevance check by default. With no supported
LLM CLI and no `--no-fit-check`, `auto` stops before search and prints
the fix instead of silently producing an empty vault.

| Persona | Best for | Install extra |
|---|---|---|
| Researcher | STEM papers, DOI/arXiv, Zotero-first workflows | `[playwright,secrets]` |
| Humanities | books, quotes, URL-only sources, Zotero + Obsidian | `[playwright,secrets]` |
| Analyst | industry research, local PDFs/reports, no Zotero required | `[import,secrets]` |
| Internal KM | lab/company knowledge bases, mixed file types | `[import,secrets]` |

Field presets for `discover new`, `search`, and related planning flows
are `cs`, `bio`, `med`, `physics`, `math`, `social`, `econ`, `chem`,
`astro`, `edu`, and `general`. There is no `hydrology` preset; use
`general` intentionally.

---

## Connect your AI host

research-hub has two AI-facing integration layers:

| Layer | Best for | Current status |
|---|---|---|
| MCP / REST | Claude Desktop, Claude Code, Cursor, Continue.dev, Cline, Roo Code, VS Code Copilot, OpenClaw, and other tool-calling hosts | Host-agnostic; configure the MCP server or call the REST API |
| Installed `SKILL.md` files | Claude Code, Codex, Cursor, Gemini | Built-in installer targets via `research-hub install --platform ...` |
| Manual `SKILL.md` loading | Hermes, OpenClaw, other agents with skill/rules directories | Copy or reference the bundled skill directories manually; not release-verified as installer targets |

For Claude Desktop, Cursor, Continue.dev, Cline, VS Code Copilot, OpenClaw, or another MCP host, configure the MCP server:

```json
{ "mcpServers": { "research-hub": { "command": "research-hub", "args": ["serve"] } } }
```

Restart the host. Then ask naturally:

> Find me 5 papers on agent-based modeling and put them in a notebook.

The AI can call `auto_research_topic(topic="agent-based modeling", max_papers=5)` and ingest papers, generate a NotebookLM brief, and update the vault.

Install host-specific skill files for the platforms with known default skill directories:

```bash
research-hub install --platform claude-code
research-hub install --platform cursor
research-hub install --platform codex
research-hub install --platform gemini
```

OpenClaw, Hermes, and other agents can still use research-hub through MCP/REST. If the host supports `SKILL.md`-style directories or rules files, copy the bundled directories from `skills/` or inline the relevant `SKILL.md` into the host's instructions. `research-hub install --platform` does not currently verify those hosts.

Browser-only or HTTP-capable AIs can use the REST API after starting the local server with `research-hub serve --dashboard`:

```bash
curl -X POST http://127.0.0.1:8765/api/v1/plan \
     -H "Content-Type: application/json" \
     -d "{\"intent\":\"research harness engineering\"}"
```

Full reference: [MCP tools](docs/mcp-tools.md), [AI integrations](docs/ai-integrations.md), [AI host support matrix](docs/ai-host-support.md), and [live smoke checklist](docs/live-smoke.md).

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
| `research-hub auto` stops before searching: "no relevance judge on PATH" | Fail-closed relevance check and no supported LLM CLI found | Install a judge CLI, or re-run with `--no-fit-check` to skip relevance judging |
| NotebookLM upload or generate fails | NotebookLM UI changed or login expired | Run `research-hub notebooklm login --auto-detect`; then resume with `research-hub notebooklm bundle/upload/generate/download --cluster <slug>` |
| `notebooklm upload` worked yesterday and now fails on auth | Google's `__Secure-1PSIDTS` / `PSIDRTS` cookies expire roughly every 3.5h; `notebooklm keepalive` cannot refresh them server-side | Re-run `research-hub notebooklm login --auto-detect` — the browser opens, the cookies refresh on sign-in, the session saves automatically (no terminal interaction). Takes < 1 minute |
| `auto --with-crystals` cannot find an LLM CLI | No supported LLM CLI is on PATH | Install one, configure a custom adapter, or use `crystal emit` and `crystal apply` manually |
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

## Known limitations

These are **platform or design boundaries**, not bugs — please do not file
them as issues. They are documented here so you know what to expect and
which workaround to reach for.

| Limitation | What's actually happening | What to do |
|---|---|---|
| **IEEE Xplore PDFs / URLs are blocked** by anti-bot | IEEE returns an *"Unable to Load Page"* HTML stub to both our URL pre-check AND NotebookLM's server-side fetcher. The bundle ladder flags these as `likely_error_page` and warns. | Either (a) download the PDF through your institutional access and drop it on the Zotero item / upload it in the NotebookLM web UI manually, or (b) skip the IEEE source — the abstract is still in Zotero and the Obsidian note. |
| **NotebookLM session expires ~every 3.5h** | Google's short-lived `__Secure-1PSIDTS` / `PSIDRTS` cookies are not refreshable by background polling. `notebooklm keepalive` exists but cannot rotate them server-side. | Re-run `research-hub notebooklm login --auto-detect` when a run reports an auth failure — < 1 minute, no terminal interaction. |
| **`--no-llm-fit-check` can't filter "wrong sub-topic, right field"** | The no-LLM BM25 gate is designed to catch *blatant cross-field contamination* (e.g. pure hydrology with zero AI in an LLM cluster). It cannot tell "AI-agents-in-general" from "AI-agents-in-water-resources" — both score similarly on a lexical-only metric, so the gate is recall-biased and keeps both. | For topic-specific subset filtering, use the **default** LLM-judge path (drop `--no-llm-fit-check`). The LLM-judge layer is what's designed to make semantic relevance calls. |
| **Cluster-overview LLM auto-fill writes English headings even when the scaffold is Chinese** | `topic.py` writes Chinese section headings (`## 核心問題`, `## 範圍定義`, …) for the empty scaffold, but `apply_overview` re-renders the file with English headings (`## Core Question`, `## Scope`, …) when the LLM fills it in. | Cosmetic — content is correct. If you prefer Chinese headings on the filled overview, hand-curate the section names after the first auto-fill (the markers ensure subsequent runs preserve your edits). |
| **`auto_pipeline()` Python API stays opt-in for PDFs** (CLI is opt-out) | Programmatic callers — tests, library users — get `with_pdfs=False` by default so the PDF-attach network round-trips don't fire silently. The CLI hands in `True` from `BooleanOptionalAction`. | If you call `auto_pipeline()` directly and want PDFs attached, pass `with_pdfs=True` explicitly. CLI users get the default-on behaviour automatically; use `--no-with-pdfs` to opt out. |
| **Slow / blocked publisher URLs sometimes poison the NotebookLM bundle** | Some publishers (Wiley paywalls, Frontiers oddly-routed PDFs, IEEE) return either a thin stub or an HTML error page that the bundle ladder admits because the URL pre-check passed. Downstream NotebookLM grounds on the stub instead of the paper. | Run `auto` and inspect the `[warn] N source(s) look like they did not ingest content` block. Replace the listed URLs with PDFs uploaded to the NotebookLM web UI for those papers. |

---

## Docs + Status + Dev

Docs: [First 10 minutes](docs/first-10-minutes.md), [lazy mode](docs/lazy-mode.md), [dashboard walkthrough](docs/dashboard-walkthrough.md), [MCP tools](docs/mcp-tools.md), [AI host support matrix](docs/ai-host-support.md), [live smoke checklist](docs/live-smoke.md), [personas](docs/personas.md), [NotebookLM setup](docs/notebooklm.md), [import folder](docs/import-folder.md), [CLI reference](docs/cli-reference.md), [CHANGELOG](CHANGELOG.md).

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

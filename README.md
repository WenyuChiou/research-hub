# research-hub

> **One sentence in. Cluster + papers + AI brief out. ~50 seconds.**
> Zotero + Obsidian + NotebookLM, wired together for AI agents — no API key required.

![research-hub dashboard demo — real screen recording](docs/images/dashboard-walkthrough.gif)

[![PyPI](https://img.shields.io/pypi/v/research-hub-pipeline.svg)](https://pypi.org/project/research-hub-pipeline/)
[![Tests](https://img.shields.io/badge/tests-1661%20passing-brightgreen.svg)](docs/audit_v0.45.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

繁體中文 → [README.zh-TW.md](README.zh-TW.md) · [Watch the full-res mp4 →](docs/demo/dashboard-walkthrough.mp4)

---

## Works with any AI host

If your AI can load an MCP tool, run a shell command, or make an HTTP call — it can drive research-hub.

| Your AI | How research-hub connects |
|---|---|
| **Claude Desktop** (Anthropic's desktop app) | MCP stdio via `claude_desktop_config.json` |
| **Claude Code** (Anthropic's terminal / VS Code agent) | MCP stdio — already plugged in after install |
| **Cursor · Continue.dev · Cline · Roo Code · VS Code Copilot** | Same MCP config pattern, each has its own settings entry |
| **OpenClaw · any other MCP-compatible host** | MCP stdio |
| **ChatGPT · Claude.ai web · Gemini web · OpenAI Custom GPT** | REST JSON at `/api/v1/*` (bearer-token auth + CORS) |
| **Codex CLI · Gemini CLI · GPT Code Interpreter · LangChain · AutoGen · CrewAI** | Shell subprocess — every command supports `--json` output |
| **Your own Python script** | `from research_hub.auto import auto_pipeline` (any function is importable) |

---

## 🤖 Just tell your AI to install it

Don't want to run commands yourself? Copy the block below into any AI chat (Claude Desktop / Claude Code / Cursor / Continue / ChatGPT / Gemini — anything that can run shell commands for you). It's a self-contained setup script the AI will follow step-by-step, pausing to ask you for anything it can't guess (Zotero key, vault path, which MCP host you use).

```text
Please install research-hub on my machine end-to-end. It's a Python package that
pipes academic papers into Zotero + Obsidian + NotebookLM and exposes an MCP server.

Do these steps in order. Stop and ask me whenever you need interactive input:

1. Check: `python --version`. If < 3.10, tell me to upgrade first and stop.

2. Install: `pip install research-hub-pipeline[playwright,secrets]`

3. Run `research-hub init`. It will ask me questions — pass them on to me, don't
   guess. The persona options are `researcher` / `humanities` / `analyst` /
   `internal`; ask which fits my work. If I don't have a Zotero API key, pause
   and tell me to get one at https://www.zotero.org/settings/keys.

4. Run `research-hub notebooklm login`. A browser window will open — tell me to
   complete the Google sign-in.

5. Figure out which AI host I'm using (probably the one you're running in). Edit
   its MCP config to add:
     { "mcpServers": { "research-hub": { "command": "research-hub", "args": ["serve"] } } }
   Config file locations:
     - Claude Desktop (macOS):  ~/Library/Application Support/Claude/claude_desktop_config.json
     - Claude Desktop (Windows): %APPDATA%\Claude\claude_desktop_config.json
     - Cursor: Settings → MCP Servers
     - Continue.dev: ~/.continue/config.json
     - Cline / Roo: VS Code settings under `cline.mcpServers`
   If unsure, ask me which host I'm talking to you through.

6. Run `research-hub install --platform claude-code` (or `cursor` / `codex` /
   `gemini` — whichever matches step 5). This copies skill files so future AI
   interactions know how to use research-hub intelligently.

7. Tell me to restart my AI host, then ask me what topic I want to research first
   as a smoke test, and run: `research-hub auto "TOPIC" --with-crystals`
```

That's it. The AI handles everything; you just answer its questions.

---

## Or install manually (≈ 60 seconds)

```bash
pip install research-hub-pipeline[playwright,secrets]
research-hub init                          # interactive: persona + Zotero + readiness check
research-hub notebooklm login              # one-time Google sign-in
research-hub auto "topic you care about"   # ~50s later: papers + AI brief land in your vault
```

`init` ends with a readiness check that flags anything missing (Obsidian vault, Chrome, Zotero key, LLM CLI). If `claude` / `codex` / `gemini` CLI is on your PATH, add `--with-crystals` to also produce cached AI answers in the same run:

```bash
research-hub auto "topic" --with-crystals
```

Not sure what to ask for? Plan first:

```bash
research-hub plan "I want to learn about harness engineering"
# Auto-tunes max_papers for "thesis"/"deep dive" intents, detects field
# (bio/med/cs/…), warns about existing-cluster collisions, prints the
# exact `auto` command to run next.
```

---

## Hook it to your AI host (30 seconds, one-time)

The MCP config is the same shape across hosts. For Claude Desktop / Cursor / Continue.dev / Cline / VS Code Copilot / OpenClaw, add to the host's MCP config file:

```json
{ "mcpServers": { "research-hub": { "command": "research-hub", "args": ["serve"] } } }
```

Restart the host. Then just talk naturally — examples below use Claude but the wording works for any MCP host:

> **You:** "Find me 5 papers on agent-based modeling and put them in a notebook."
> **AI:** *calls `auto_research_topic(topic="agent-based modeling", max_papers=5)`* → 5 papers ingested + NotebookLM brief URL — ~50 s.

> **You:** "What's the SOTA in my llm-evaluation-harness cluster?"
> **AI:** *calls `read_crystal("llm-evaluation-harness", "sota-and-open-problems")`* → 180-word pre-written answer with citations. **~1 KB read, 0 abstracts fetched at query time.**

**83 MCP tools** in total — full reference: [`docs/mcp-tools.md`](docs/mcp-tools.md). The big ones:

| Tool | What it replaces |
|---|---|
| `auto_research_topic(topic)` | 7-step CLI flow (search → ingest → bundle → upload → generate → download) |
| `plan_research_workflow(intent)` | Guessing max_papers / field / cluster slug |
| `ask_cluster_notebooklm(cluster, question)` | Open NotebookLM, paste question, copy answer |
| `read_crystal(cluster, slot)` | Re-read 20 abstracts to answer the same question again |
| `web_search(query)` | Hand-curating blog/docs/news links |
| `cleanup_garbage` + `tidy_vault` | `du -sh .research_hub/bundles/*` + manual `rm -rf` |

Browser-only AIs (ChatGPT, Claude.ai web, Custom GPT) can't use MCP — **use the REST API instead**:

```bash
curl -X POST http://127.0.0.1:8765/api/v1/plan \
     -H 'Content-Type: application/json' \
     -d '{"intent":"research harness engineering"}'
```

---

---

## 📊 Every feature in one table

| Capability | Command (or MCP tool) | Notes |
|---|---|---|
| **Lazy mode** — one sentence in, brief out | `auto "topic"` / `auto_research_topic` | search → ingest → NLM brief in ~50s |
| **Lazy maintenance** | `tidy` / `tidy_vault` | doctor + dedup + bases + cleanup preview |
| **GC accumulated junk** | `cleanup --all --apply` / `cleanup_garbage` | bundles + debug logs + stale artifacts |
| **Ad-hoc NLM Q&A** | `ask --cluster X "Q?"` / `ask_cluster_notebooklm` | dual backend (NLM + crystal cache) |
| **Pre-computed crystals** | `crystal emit / apply` | 10 canonical Q→A per cluster, ~1 KB/answer |
| **Structured memory** | `memory emit / apply` + `list_entities/claims/methods` | typed entities, claims with confidence, method taxonomies |
| **Live dashboard** | `serve --dashboard` | 6 tabs, persona-aware, Manage tab buttons execute CLI directly |
| **4 personas, 1 codebase** | `RESEARCH_HUB_PERSONA=researcher\|humanities\|analyst\|internal` | vocabulary + hidden tabs adapt |
| **100% orphan coverage** | `clusters rebind --emit` then `--apply` | 8-heuristic chain, auto-create-from-folder proposals |
| **Health checks (12+)** | `doctor` / `doctor --autofix` | mechanical backfills, patchright Chrome probe |
| **Multi-backend search** | `search "query"` | arXiv + Semantic Scholar (default) + Crossref DOI lookup |
| **Cluster autosplit** | `clusters analyze --split-suggestion` | networkx greedy modularity on citation graph |
| **Obsidian Bases dashboard** | `bases emit` / `emit_cluster_base` | auto-generated `.base` per cluster (auto-refreshes on ingest) |
| **NotebookLM upload** | `notebooklm upload --cluster X` | patchright + persistent Chrome (no API key, no quota) |
| **Citation graph** | `vault graph-colors` | networkx + Obsidian graph view colors |
| **Local file ingest** | `import-folder /path` | PDF / DOCX / MD / TXT / URL (analyst persona) |
| **Generic web search** (v0.51) | `websearch "query"` / `web_search` | Tavily / Brave / Google CSE / DDG fallback (no key needed) |
| **Field auto-detection** (v0.51) | `plan "intent"` → suggested `--field` | bio/med queries pick pubmed; cs queries pick arxiv+s2; etc. |

[→ Full lazy-mode guide](docs/lazy-mode.md) · [→ All commands](docs/dashboard-walkthrough.md) · [→ MCP reference](docs/mcp-tools.md)

---

## 🖥 What the dashboard looks like

`research-hub serve --dashboard` opens `http://127.0.0.1:8765/`. Six tabs in total; the four most important ones shown below at readable scale (hero crops only — full-page renders are in `docs/images/`):

| | |
|---|---|
| ![Overview](docs/images/hero/dashboard-overview.png) | ![Library](docs/images/hero/dashboard-library-subtopic.png) |
| **Overview** — treemap over clusters + storage map | **Library** — per-cluster drill-down with sub-topics |
| ![Diagnostics](docs/images/hero/dashboard-diagnostics.png) | ![Manage](docs/images/hero/dashboard-manage-live.png) |
| **Diagnostics** — health summary + grouped drift alerts (v0.48 density redesign) | **Manage** — every CLI action as a button |

Not shown (less unique as first-impression): **Briefings** (NotebookLM brief preview) and **Writing** (quote capture + BibTeX export). Both work the same way — see [→ Dashboard walkthrough](docs/dashboard-walkthrough.md) for the full tour, or [→ All 4 persona variants](docs/personas.md) for analyst/humanities/internal-KM views.

---

## 📓 Inside Obsidian

The dashboard is one face. The other is what you actually live in: **Obsidian**. Every paper research-hub ingests becomes a real `.md` note with structured frontmatter, and every cluster gets an auto-generated **Bases** dashboard you can browse natively without leaving Obsidian.

| | |
|---|---|
| ![Obsidian Bases dashboard for a cluster](docs/images/obsidian-bases-dashboard.png) | ![Single paper note rendered with Properties view](docs/images/obsidian-paper-note.png) |
| **Cluster Bases dashboard** — auto-generated `.base` per cluster (v0.43+). Sortable / filterable database view of every paper in the cluster, columns auto-built from frontmatter (name / title / year / status / verified / doi). Refreshes on every `ingest` / `topic build`. | **Per-paper note** — every ingested paper has a structured frontmatter block (title / authors / year / journal / doi / zotero-key / collections / tags / ingested_at / topic_cluster / cluster_queries / verified / status). Linkable, searchable, includable in Obsidian Graph view. |

Crystals (the cached AI answers) are also plain Obsidian notes under `hub/<cluster>/crystals/*.md` — fully wikilink-able, included in graph view, queryable by `read_crystal()` MCP tool at zero token cost.

---

## 🧠 What makes it different

### 1. Pre-computed answers, not lazy retrieval

Every RAG system still assembles context at query time. research-hub's answer: **store the AI's reasoning, not the inputs**.

For each cluster you generate ~10 canonical Q→A **crystals** once with any LLM. Later queries read a pre-written paragraph (~1 KB), not 20 paper abstracts (~30 KB) — **30× compression** with quality that doesn't degrade at query time. Underneath, a structured **memory layer** holds the entities, typed claims with confidence, and method taxonomies that crystals reference. AI agents query via `list_entities`, `list_claims(min_confidence="high")`, `list_methods` — no RAG over prose, structured lookup over structured data.

Example cluster from the maintainer's vault: `hub/llm-evaluation-harness/` has 10 crystals + 14 entities + 12 claims + 7 methods, all generated once. After `research-hub auto "harness engineering" --with-crystals` your own vault will look the same. [→ Why this is not RAG](docs/anti-rag.md)

### 2. Three control surfaces, one orchestrator

CLI, dashboard buttons, and MCP tools all call the same Python orchestrator. There is no "REST mode" or "API mode" with diverging behavior. Whatever you can do at the shell, Claude can do via MCP, and vice versa.

### 3. Provider-agnostic by design

**No OpenAI / Anthropic API key required.** All AI generation uses an `emit` / `apply` pattern: `emit` writes a self-contained prompt to stdout, you paste into your AI of choice (Claude, GPT, Gemini, local model), `apply` ingests the JSON response. NotebookLM browser automation uses your own logged-in Chrome — no quota, no per-token billing.

---

## ⚖️ How it compares to the alternatives

Honest, side-by-side. research-hub doesn't replace any of these — it stitches them together so an AI agent can drive them all.

| What you can do | Zotero alone | NotebookLM alone | Generic RAG (LangChain etc.) | Obsidian-Zotero plugin | **research-hub** |
|---|---|---|---|---|---|
| Search arXiv + Semantic Scholar in one command | ❌ | ❌ | DIY | ❌ | ✅ `auto "topic"` |
| One-shot ingest into Zotero **and** Obsidian **and** NotebookLM | ❌ | ❌ | DIY | partial (Z↔O only) | ✅ `auto` |
| AI brief from your collection | ❌ | ✅ (manual) | DIY | ❌ | ✅ auto-generated |
| Cached canonical Q→A so the AI doesn't re-RAG every query | ❌ | ❌ | ❌ (RAG re-fetches) | ❌ | ✅ crystals (~1 KB/answer) |
| Structured memory layer (entities + typed claims + methods) | ❌ | ❌ | unstructured chunks | ❌ | ✅ `list_entities/claims/methods` |
| Direct AI-agent control via MCP | ❌ | ❌ | DIY MCP server | ❌ | ✅ 81 MCP tools |
| Live HTML dashboard with action buttons | ❌ | ❌ | ❌ | ❌ | ✅ `serve --dashboard` |
| Auto-cluster papers + detect drift + auto-rebind orphans | ❌ | ❌ | ❌ | ❌ | ✅ `clusters rebind` |
| Per-cluster Obsidian Bases dashboard | ❌ | ❌ | ❌ | ❌ | ✅ `bases emit` |
| **No API key required for AI** | n/a | ✅ | ❌ | n/a | ✅ |
| **Local-first vault you own** | ✅ (cloud-sync) | ❌ (Google) | depends | ✅ | ✅ |
| Cost per 1000 queries | n/a | quota-limited | ~$5–50 (token billing) | n/a | **$0** (cached crystals) |

The honest takeaway: research-hub is **only worth it if you already use 2-of-3** Zotero / Obsidian / NotebookLM and want to AI-agentize the workflow. If you only use one, the simpler tools alone are fine.

---

## 📦 Install variants

```bash
# Researcher / Humanities (Zotero + NotebookLM)
pip install research-hub-pipeline[playwright,secrets]

# Analyst / Internal KM (no Zotero, import local files)
pip install research-hub-pipeline[import,secrets]

# Everything for development
pip install -e '.[dev,playwright,import,secrets,mcp]'
```

Python 3.10+. Optional `npm install -g defuddle-cli` for cleaner URL imports.

---

## 📚 Docs

| | |
|---|---|
| [First 10 minutes](docs/first-10-minutes.md) | Guided tour for each persona |
| [Lazy-mode reference](docs/lazy-mode.md) | The 4 one-sentence commands |
| [Dashboard walkthrough](docs/dashboard-walkthrough.md) | Tab-by-tab tour with persona recipes |
| [MCP tools reference](docs/mcp-tools.md) | All 81 tools, categorized + signatures |
| [Personas](docs/personas.md) | 4 persona profiles + per-persona feature matrix |
| [Cluster integrity](docs/cluster-integrity.md) | 6 failure modes × 4 personas mitigation matrix |
| [Anti-RAG / crystals](docs/anti-rag.md) | Why pre-computed Q→A beats retrieval |
| [NotebookLM setup](docs/notebooklm.md) + [troubleshooting](docs/notebooklm-troubleshooting.md) | patchright + persistent Chrome (v0.42+) |
| [Import folder](docs/import-folder.md) | Local PDF/DOCX/MD/TXT/URL ingest |
| [Papers input schema](docs/papers_input_schema.md) | Ingestion pipeline reference |
| [Upgrade guide](UPGRADE.md) | Migrating from older versions |
| [Audit reports](docs/) | `audit_v0.26.md` … `audit_v0.45.md` |
| [CHANGELOG](CHANGELOG.md) | Per-version release notes |

---

## 🩺 Troubleshooting (first-run problems)

| Symptom | Cause | Fix |
|---|---|---|
| `research-hub init` says `chrome WARN patchright cannot launch Chrome` | Chrome not installed, or patchright cannot find it | Install Chrome from chrome.com; rerun `research-hub doctor` to re-probe |
| `research-hub notebooklm login` opens browser but Google blocks login | Headless / new device challenge | The browser is patchright (real Chrome) — click "Yes, it's me" on your phone, then complete login normally |
| `research-hub auto` fails at `search` step with `0 papers` | Topic too narrow, or arXiv/SemSch transient outage | Re-run with `--max-papers 20` or rephrase the topic; both backends are fault-tolerant |
| `research-hub auto` fails at `nlm.upload` with "Generation button not found" | NotebookLM UI changed, or you're not logged in | Run `research-hub notebooklm login` again; if persists, file an issue with the `nlm-debug-*.jsonl` from `.research_hub/` |
| `auto --with-crystals` falls back to "no LLM CLI on PATH" | Neither `claude`, `codex`, nor `gemini` CLI installed | Install whichever AI CLI you use; or generate crystals manually with `crystal emit` → paste → `crystal apply` |
| Claude Desktop doesn't see the MCP server | `claude_desktop_config.json` not in expected location | macOS: `~/Library/Application Support/Claude/claude_desktop_config.json` · Windows: `%APPDATA%\Claude\claude_desktop_config.json` · restart Claude Desktop after editing |
| `init` reports `zotero WARN` but I don't use Zotero | Default persona is `researcher` which expects Zotero | Re-run `research-hub init --persona analyst` (or `internal`) — these personas skip Zotero entirely |

For everything else: `research-hub doctor --autofix` repairs the common mechanical issues; the report tells you which subsystem to look at.

---

## 🛠 Status

- **Latest**: v0.53.0 (2026-04-20) — multi-AI skill pack: `research-hub install --platform claude-code` now bundles a multi-AI orchestration skill that teaches Claude when to delegate crystal generation to Codex / CJK content to Gemini. See [`CHANGELOG.md`](CHANGELOG.md).
- **Tests**: 1585 passing on the fast suite (CI: Linux + Windows + macOS × Python 3.10/3.11/3.12 = 9 jobs)
- **MCP tools**: 83 (v0.47 auto/cleanup/tidy; v0.49 extended `auto_research_topic`; v0.50 added `plan_research_workflow`; v0.51 added `web_search`)
- **REST endpoints**: 12 at `/api/v1/*` covering health / clusters / crystals / search / websearch / plan / ask / auto (async via job queue)
- **Skills bundled**: 2 — `research-hub` (core pipeline) + `research-hub-multi-ai` (Claude + Codex + Gemini delegation pattern)
- **End-to-end verified**: as of v0.49.5, the full lazy-mode flow — `auto "topic" --with-crystals` → search → ingest → NotebookLM brief → cached AI answers — is verified working on a Windows zh-TW machine with the real `claude` CLI. See [`CHANGELOG.md`](CHANGELOG.md) v0.49.4 for the full per-stage results table.
- **Dependencies**: `pyzotero`, `pyyaml`, `requests`, `rapidfuzz`, `networkx`, `platformdirs` (all pure-Python)
- **Optional**: `[playwright]` for NotebookLM, `[import]` for local file ingest, `[secrets]` for OS-keyring credential storage

## 👩‍💻 For developers

```bash
git clone https://github.com/WenyuChiou/research-hub.git
cd research-hub
pip install -e '.[dev,playwright]'
python -m pytest -q                     # 1585 passing
```

Contributing: [CONTRIBUTING.md](CONTRIBUTING.md). Security: [SECURITY.md](.github/SECURITY.md).

Package on PyPI: **research-hub-pipeline** · CLI entry point: **research-hub**

## License

MIT. See [LICENSE](LICENSE).

<!-- mcp-name: io.github.WenyuChiou/research-hub -->

# research-hub

Your local research workspace connecting AI assistants (Claude Code, Codex) with **Zotero** library status, **Obsidian** notes, **NotebookLM** source briefs, and human-reviewed manuscript drafts.

[繁體中文](README.zh-TW.md) · [Workspace guide](docs/workspace-guide.md) · [Setup guide](docs/setup.md) · [Developer architecture](docs/workspace-architecture.md)

[![PyPI](https://img.shields.io/pypi/v/research-hub-pipeline.svg)](https://pypi.org/project/research-hub-pipeline/) [![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml) [![MIT license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Why research-hub?

Literature discovery happens inside your AI host's conversation, while real research lives across Zotero libraries, Obsidian notes, NotebookLM briefs, analysis scripts, and manuscripts. `research-hub` turns those pieces into one inspectable local workspace—paired with [AI Research Skills](https://github.com/WenyuChiou/ai-research-skills) for Stage 1–2 discovery-to-synthesis:

- **Build on your AI host's native search:** Let Claude Code or Codex find and read papers using its own search and reading tools—no separate keyword scraper or lock-in required.
- **Keep Zotero, Obsidian & NotebookLM in view:** Inspect Zotero sync status, save structured or seven-section source-bound summaries into Obsidian cluster notes, and bundle verified sources for NotebookLM briefs.
- **Track changes & keep decisions human:** Register local file hashes to surface stale evidence or manuscript sections when inputs change; AI proposals and destination writes always wait for your approval.

![Concept diagram: research questions connect literature, evidence, analysis, manuscript proposals, and human review; changed inputs return work for review.](docs/images/workspace-lifecycle.en.png)

## Choose your starting path

![Two starting paths: research with an available compatible AI host without Hub, or install Hub to view saved sources and proposals. Task handoff is optional. People review sources and evidence; saving is not reading or approval, and nothing is automatically published.](docs/images/research-entry-paths.en.svg)

1. **Start directly in your AI host (no Hub install needed):**
   - **Prerequisites:** Working search/reading tools in your host plus the [portable skill with its references](skills/research-hub/). No Hub installation, Zotero, Obsidian, or NotebookLM is required. See [skill loading](docs/setup.md#installed-skill-files) and [host support](docs/ai-host-support.md); Codex MCP is not release-verified.
   - **First request:** “Find papers on LLMs simulating human decisions. Include source links, relevance, versions, and actual reading limits.”
   - **Expected result:** Expect a source list in your host, with unknowns and unavailable tools/sources stated cleanly—never automatic full-text claims or unrequested writes.

2. **Use the Hub workspace (saved literature, integrations & visual review):**
   - **Prerequisites:** Python 3.10+, Git, and a local browser.
   - [Install and launch the tested demo below](#workspace-preview) to inspect two seed references and their reading limits. Optional [result saving](docs/contracts/native-discovery-view.md) and [task handoff](docs/workspace-guide.md#writing-adapter-preview) require a selected destination and authorization.

## Install and get started

<a id="start-here"></a>
<a id="first-run-checklist"></a>
<a id="workspace-preview"></a>

### Try the local workspace

Use the source install below to launch the interactive local workspace in a **new or empty** `workspace-demo` directory. The source workspace is separate from the published [PyPI package](https://pypi.org/project/research-hub-pipeline/), so a package version does not imply current source features.

```sh
git clone -c core.autocrlf=false https://github.com/WenyuChiou/research-hub.git
cd research-hub
git fetch origin 1f0726a7e92a1231e633963f17236a2f5c1eab8f
git checkout --detach 1f0726a7e92a1231e633963f17236a2f5c1eab8f
```

Run the commands for your OS (no shell activation required; dependency installation needs network access):

**macOS / Linux**

```sh
python3 -m venv .venv
./.venv/bin/python -m pip install -e .
./.venv/bin/python -m research_hub project demo --root ./workspace-demo --json
./.venv/bin/python -m research_hub serve --workspace --root ./workspace-demo
```

**Windows PowerShell**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m research_hub project demo --root ./workspace-demo --json
.\.venv\Scripts\python.exe -m research_hub serve --workspace --root ./workspace-demo
```

**First task: inspect a saved source and its reading limits.**

1. Open [http://127.0.0.1:8765/app/](http://127.0.0.1:8765/app/) and, in **Projects**, choose `DEMO: floating-point reading and review outline` (`review-demo`).
2. Open **Literature**, then select **What Every Computer Scientist Should Know About Floating-Point Arithmetic**.
3. Expect two seed references in the list. The selected source shows DOI `10.1145/103162.103163`, **Unverified**, **Coverage unknown**, and **No summary saved**. These are expected demo states: no full text was downloaded or summarized, and supplied screening decisions are examples, not your review.

Keep the terminal running while using the workspace (`Ctrl+C` to stop); later runs only need `serve --workspace --root ./workspace-demo`. For your own files, go to [bring your own project](docs/workspace-guide.md#bring-your-own-project).

<details>
<summary>Verification scope, troubleshooting notes, and second demo project</summary>

- **Verified scope:** Demo creation, launch, and this bilingual first task were checked on Linux with Python 3.12.14 at source revision `1f0726a7`; this does not verify Windows, macOS, or a clean dependency installation. See [the exact verification scope](docs/readme-verification-history.md#source-demo-first-task-2026-11-07).
- **Windows historical note:** One Windows test environment using the earlier `14ddc070` source encountered `WinError 5` during demo creation; its cause is not yet known. See [verification and environment notes](docs/readme-verification-history.md). Do not recreate the demo over saved work; if creation is interrupted, use another new or empty root.
- **Second seed project:** `DEMO: three floating-point summation cases` (`summation-demo`) holds numerical examples and a manuscript scaffold with an empty Literature list; both projects are account-free teaching inputs.

</details>

<a id="published-dashboard"></a>

<details>
<summary>Optional: try the older published literature dashboard (PyPI 1.2.0)</summary>

The [PyPI package](https://pypi.org/project/research-hub-pipeline/) ships the older cluster dashboard rather than the source workspace above. Tested on Linux with Python 3.12 in an empty `RESEARCH_HUB_ROOT` directory:

```sh
python3 -m venv .dashboard-venv
./.dashboard-venv/bin/python -m pip install research-hub-pipeline==1.2.0
mkdir -p "$HOME/research-hub-preview"
RESEARCH_HUB_ROOT="$HOME/research-hub-preview" ./.dashboard-venv/bin/research-hub dashboard --sample
```

Open the printed temporary HTML path in your browser. See [setup](docs/setup.md), the [dashboard tour](docs/dashboard-walkthrough.md), and [verification notes](docs/readme-verification-history.md) for service configuration and platform limits.

</details>

## Work in the workspace

![Historical workspace UI capture showing local demo project navigation and research records.](docs/images/workspace-ui.en.png)

*Historical demo capture, reviewed 2026-09-08; the current interface may differ.*

| Page | Example work |
|---|---|
| Overview | Review the research question, goal, and project context. |
| Literature | Collect sources and record reasons to include or exclude them. |
| Evidence | Link claims to sources and inspect unresolved support. |
| Design & results | Record methods, results, limitations, and supporting files. |
| Manuscript | Register Word, LaTeX, or Markdown and prepare outlines and revisions. |
| Review & delivery | Inspect proposals, record decisions, and prepare a local handoff. |

Your editor owns changes to original files; the workspace tracks paths and hashes. Resolvable identifiers alone never prove scientific support—always verify claims against the underlying source.

## Discover, organize, and verify literature

When you pair the [research-hub skill](skills/research-hub/) with a capable AI host (such as Claude Code or Codex), keep discovery on the host and let Research Hub handle deterministic storage and multi-destination handoffs:

- **Step 1 — Discover & read natively:** Ask your AI host to search, chain citations, and read accessible sections directly (e.g., *"Find literature on LLMs simulating human decisions; include original links, relevance, versions, and limits on available full text"*). Search snippets never count as full-text reading.
- **Step 2 — Sync to Zotero & Obsidian:** Hand verified bibliographic records to `research-hub ingest` (after previewing `--dry-run`) to track **Zotero** status and generate structured **Obsidian** cluster notes, or save local project metadata via `project record`.
- **Step 3 — Export deep summaries & NotebookLM briefs:** Use `paper-summarize` for seven-section source-bound summaries (exportable to Obsidian/Roam Markdown) and `research-hub notebooklm` + `notebooklm-brief-verifier` to generate and audit source-grounded briefs before moving downstream to `literature-triage-matrix` and `gap-to-topic`.

<details>
<summary>Native reader boundaries &amp; source-summary revision note</summary>

- **Native reader scope:** Displays caller-supplied observations, bibliographies, unchanged PDF attachments, and supplied side-by-side translations (explicitly labeled unverified). It never auto-parses, translates, or scientifically validates content. See [native reader export guide](src/research_hub/skills_data/research-hub/references/native-discovery-export.md) and the optional [saved-result contract](docs/contracts/native-discovery-view.md).
- **Seven-section summary CLI boundary:** The quick-start pin `1f0726a7` predates Stage 1 authored source summaries. From source revision `231f9fbd` onward, the [authored source-summary CLI](docs/cli-reference.md#native-authored-source-summaries) saves and exports caller-authored seven-section summaries bound to current source hashes; read the [summary contract](docs/native-source-summary.md) first and verify your installed revision separately from package version numbers.

</details>

See [AI Research Skills](https://github.com/WenyuChiou/ai-research-skills), the [AI host support matrix](docs/ai-host-support.md), and [MCP/REST integration](docs/ai-integrations.md).

## Write, review, and deliver

![Concept diagram: a researcher prepares a task, uses a portable AI handoff or a connected Codex prose worker, checks the proposal, and explicitly accepts or requests changes.](docs/images/workspace-writing.en.png)

| Mode | How it works |
|---|---|
| Portable handoff | Export a task to your AI host, then import prose and candidate file hashes. Export leaves the task waiting for the agent. |
| Connected Codex | An authenticated, compatible Codex CLI uses an explicitly trusted public writing bundle to produce prose; the result waits for human review. |

See [writing setup](docs/workspace-guide.md#writing-adapter-preview) and [boundaries and recovery](docs/workspace-guide.md#boundaries-and-recovery). Connected Codex receives bounded text excerpts, not binary files; formatting remains in your editor, and local ZIP delivery requires separate human approval without authorizing cloud uploads or overwriting existing direct-write tools.

## Optional integrations

<a id="connect-your-ai-host"></a>

- **Zotero:** Track library items and collection status (`ZOTERO_API_KEY` + `ZOTERO_LIBRARY_ID`).
- **Obsidian:** Organize per-cluster notes, deep summaries, and synthesis pages inside a local vault (or start from local Markdown).
- **NotebookLM:** Bundle clusters, generate briefings, and audit claims against sources (requires browser session; see [setup](docs/notebooklm.md) and [troubleshooting](docs/notebooklm-troubleshooting.md)).
- **AI hosts:** Connect via [MCP/REST](docs/ai-integrations.md) (requires `[mcp]`) or portable skills via [install guidance](docs/setup.md).

Run `./.venv/bin/python -m research_hub doctor` (macOS/Linux) or `.\.venv\Scripts\python.exe -m research_hub doctor` (Windows PowerShell) to inspect selected destinations individually. See [local file import](docs/import-folder.md), [EZproxy](docs/ezproxy.md), and the [live smoke checklist](docs/live-smoke.md).

<a id="credential-reference"></a>
<details>
<summary>Integration credentials and extras</summary>

The local workspace demo needs none of these credentials. Existing personas use optional extras: Researcher and Humanities `[playwright,secrets]`; Analyst and Internal KM `[import,secrets]`.

<!-- env-vars-table-start -->

| Name | Required | Purpose |
|---|---|---|
| `ZOTERO_API_KEY` | Zotero only | Zotero API authentication |
| `ZOTERO_LIBRARY_ID` | Zotero only | Zotero library identifier |
| `SEMANTIC_SCHOLAR_API_KEY` | no | Optional search API key |
| `SEMANTIC_SCHOLAR_RPS` | no | Optional search request-rate override |
| `TAVILY_API_KEY` | no | Optional web search backend |
| `BRAVE_API_KEY` | no | Optional web search backend |

<!-- env-vars-table-end -->

</details>

## Documentation and contributing

- [Workspace guide](docs/workspace-guide.md) · [Workspace architecture](docs/workspace-architecture.md) · [Capability baseline](docs/capability-baseline.md) · [Verification history](docs/readme-verification-history.md)
- [CLI reference](docs/cli-reference.md) · [MCP tools](docs/mcp-tools.md) · [Stable API](docs/stable-api.md) · [File formats](docs/file-formats.md) · [Workflow runtime](docs/workflow-runtime.md) · [OpenWiki](openwiki/quickstart.md)
- [Recorded dashboard demo](docs/images/dashboard-walkthrough.gif) · [Full-resolution video](docs/demo/dashboard-walkthrough.mp4) · [MCP flow diagram](docs/images/research-hub-cover.png)
- [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Release process](docs/RELEASING.md) · [MIT license](LICENSE)

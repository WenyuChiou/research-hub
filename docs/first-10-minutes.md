# Your first 10 minutes with research-hub

A guided tour for each of the 4 personas. Pick yours below and follow the matching path.

> Not sure which persona? See `docs/personas.md` for the full feature matrix. The TL;DR:
> - **Researcher** — PhD STEM, uses Zotero
> - **Humanities** — uses Zotero + works heavily with quotes / non-DOI sources
> - **Analyst** — industry researcher, no Zotero, imports PDFs
> - **Internal KM** — knowledge management for a lab / company, mixed file types

All 4 personas share the same dashboard, MCP server, crystal system, and cluster integrity tools. The dashboard auto-adapts vocabulary and hides irrelevant features per persona.

---

## 0 minutes: install

```bash
# Researcher / Humanities (need Zotero + NotebookLM)
pip install research-hub-pipeline[playwright,secrets]

# Analyst / Internal KM (no Zotero, work with local files)
pip install research-hub-pipeline[import,secrets]
```

`[secrets]` enables Zotero key encryption at rest (recommended for all personas that use Zotero). `[mcp]` is included by default for AI integration.

---

## 2 minutes: init

```bash
research-hub init --persona <researcher|humanities|analyst|internal>
```

Or run with no flag for an interactive 4-option prompt. You'll be asked for:

- **Vault path** (default: `~/knowledge-base/`) — where your data lives
- **Zotero API key + library ID** (researcher / humanities only)
- **Persona** if not provided via flag

After `init`:

```
~/knowledge-base/
├── raw/                       # paper notes (markdown), one folder per cluster
├── hub/                       # cluster overviews + crystals + structured memory
│   └── <cluster-slug>/
│       ├── 00_overview.md     # narrative summary
│       ├── crystals/          # pre-computed Q→A answers
│       └── memory.json        # entities, claims, methods
├── projects/                  # your draft markdown files
├── logs/                      # operation logs
└── .research_hub/             # config + cache
```

Run `research-hub where` any time to confirm paths.

---

## 5 minutes: first useful action (per persona)

### Researcher

```bash
# Add a paper by DOI or arXiv ID
research-hub add 10.48550/arxiv.2310.06770 --cluster llm-agents

# After 5+ papers in the cluster, generate AI answers
research-hub crystal emit --cluster llm-agents > prompt.md
# Feed prompt.md to Claude/GPT/Gemini, save response as crystals.json
research-hub crystal apply --cluster llm-agents --scored crystals.json
```

### Humanities

```bash
# Add a non-DOI source (URL, book) via Zotero first, then:
research-hub quote add my-source-slug --text "the quote text" --page 42 --note "your gloss"
research-hub compose-draft --cluster victorian-novels > draft.md
```

### Analyst

```bash
# Drop a folder of PDFs / markdown / DOCX
research-hub import-folder ~/Downloads/q4-research --cluster q4-analysis
research-hub serve --dashboard  # opens browser, see your topic + documents
```

### Internal KM

```bash
# Same as Analyst — mixed file types auto-handled
research-hub import-folder /shared/wiki-export --cluster product-launch
```

---

## 7 minutes: open the dashboard

```bash
research-hub serve --dashboard
# Visit http://127.0.0.1:8765/
```

Your persona's dashboard:

- **Researcher** sees: 6 tabs (Overview / Library / Briefings / Writing / Diagnostics / Manage), full vocabulary (Cluster, Crystal, Paper)
- **Humanities** sees: same 6 tabs, vocabulary renamed (Theme, Synthesis, Source)
- **Analyst** sees: 5 tabs (Diagnostics hidden), vocabulary renamed (Topic, AI Brief, Document), Bind-Zotero button hidden
- **Internal KM** sees: 5 tabs, vocabulary renamed (Project area, AI Brief, Document)

Side-by-side preview screenshots: `docs/images/dashboard-overview-{researcher,humanities,analyst,internal}.png`.

---

## 9 minutes: connect Claude Desktop (optional)

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

Restart Claude Desktop. You can now talk to your vault:

> "Claude, what's in my llm-agents cluster?"
> "Claude, generate crystals for the q4-analysis topic"
> "Claude, list orphan papers — anything that needs a home?"

60 MCP tools cover: paper ingest, cluster CRUD, labels, quotes, draft composition, citation graph, NotebookLM, crystal generation, fit-check, autofill, cluster memory, and cluster rebind workflows.

---

## 10 minutes: doctor

```bash
research-hub doctor
```

Catches 12+ common issues across config, vault structure, Zotero connectivity, cluster integrity, persona setup. Always the first thing to run when something feels wrong.

---

## What's next

- Read `docs/personas.md` for the full per-persona feature matrix
- Read `docs/cluster-integrity.md` if your vault has orphan papers (post-import or migrated from a previous tool — `research-hub clusters rebind` proposes assignments)
- Read `docs/anti-rag.md` for why crystals beat RAG for token cost + answer quality
- Read `docs/example-claude-mcp-flow.md` for a worked example: ingest → crystallize → query
- Read `UPGRADE.md` if you're migrating from a pre-v0.30 vault

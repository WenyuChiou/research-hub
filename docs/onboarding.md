# First 10 minutes with research-hub

Research Hub is an optional pipeline for organizing local notes and connecting
services. You can read sources and use the research skills without it. If you
choose Research Hub, pick a persona and start locally or connect services as
needed; a persona does not require accounts.

## Pick your persona

- **Researcher**: academic papers, with optional Zotero-backed DOI/arXiv workflows.
- **Humanities**: quote-heavy work with books, archives, and other non-DOI sources; Zotero is optional.
- **Analyst** (industry researcher, no Zotero): you have a folder of PDFs / market reports / white papers.
- **Internal KM** (lab or company knowledge base): you have mixed internal docs (PDF, MD, DOCX, URLs).

---

## Researcher quickstart

```bash
pip install research-hub-pipeline[import]
research-hub init --persona researcher
# Choose N at "Connect Zotero now?" to start locally; defer NotebookLM too
research-hub import-folder ./papers --cluster llm-agents --extensions pdf,md,txt,docx
research-hub serve --dashboard  # browse the local notes
```

Local import works for every persona and writes local Markdown notes without
Zotero. Obsidian is an optional way to read them. For Markdown/text alone,
the base install and `--extensions md,txt` suffice. Select only the folder
you intend to import; URL imports may fetch remote content.

Zotero is a reference manager for saving and organizing papers. Connect it
later with `research-hub init --persona researcher`; saved settings are reused.
Choose Y to set it up now, then provide its API key and library ID. Before
Zotero-backed `add`/`auto`/`ingest`, inspect the vault and Zotero access results
from `research-hub doctor`. Initialization success and saved credentials do
not prove access or write permission.

```bash
# Only after Zotero setup and access checks
research-hub add 10.48550/arxiv.2310.06770 --cluster llm-agents
research-hub auto "your research topic" --no-nlm
```

NotebookLM is optional and sends selected sources to Google's service. Connect
later with `research-hub notebooklm login --auto-detect`; install
`research-hub-pipeline[playwright,secrets]` when using browser login and Zotero
encryption. A session file is not proof of authenticated access. `--no-nlm`
skips NotebookLM, not other network/model calls or Zotero writes.

After you have 5+ papers in a cluster:

```bash
research-hub crystal emit --cluster llm-agents > prompt.md
# Feed prompt.md to Claude/GPT, save response as crystals.json
research-hub crystal apply --cluster llm-agents --scored crystals.json
```

---

## Humanities quickstart

```bash
research-hub init --persona humanities
# The same local import path above works without accounts
research-hub import-folder ./sources --cluster victorian-novels --extensions md,txt
research-hub quote add "<imported-source-slug>" --text "..." --page 42 --note "..."
research-hub compose-draft --cluster victorian-novels > draft.md
```

The dashboard renames "Cluster" to "Theme" for this persona.

---

## Analyst quickstart

```bash
pip install research-hub-pipeline[import,secrets]
research-hub init --persona analyst
# Skip Zotero (no key needed)
research-hub import-folder ~/Downloads/competitive-research --cluster q4-analysis
research-hub serve --dashboard
```

The dashboard renames "Cluster" to "Topic", "Crystal" to "AI Brief", and hides the Diagnostics tab + Bind-Zotero button.

---

## Internal KM quickstart

```bash
pip install research-hub-pipeline[import,secrets]
research-hub init --persona internal
research-hub import-folder /shared/wiki-export --cluster q4-product-launch
# Mixed file types (PDF, MD, DOCX, URLs) auto-handled
```

The dashboard renames "Cluster" to "Project area", "Paper" to "Document". Citation graph is hidden.

---

## What goes where

`research-hub where` shows your config + vault paths. Default vault layout:

```text
~/knowledge-base/
|-- raw/<cluster-slug>/        # paper notes (markdown)
|-- hub/<cluster-slug>/        # cluster overview + crystals + memory.json
|-- projects/                  # your draft markdown files
|-- logs/                      # operation logs
`-- .research_hub/             # config + cache
```

---

## Next steps

- All 4 personas: read `docs/personas.md` for the per-persona feature matrix
- For Claude Desktop integration: read `docs/example-claude-mcp-flow.md`
- For NotebookLM auto-upload: read `docs/notebooklm.md`
- For troubleshooting: run `research-hub doctor` (catches 12+ common issues)
- See `docs/cluster-integrity.md` if your vault has orphan papers (post-import or migrated from a previous tool)

# First 10 minutes with research-hub

Choose your persona, then follow the matching quickstart. All 4 personas share the same dashboard + MCP server + AI workflows.

## Pick your persona

- **Researcher** (PhD STEM, uses Zotero): you have a Zotero library + want to organize academic papers by DOI/arXiv ID.
- **Humanities** (PhD humanities, quote-heavy): you have Zotero + work with non-DOI sources (books, archives, URLs).
- **Analyst** (industry researcher, no Zotero): you have a folder of PDFs / market reports / white papers.
- **Internal KM** (lab or company knowledge base): you have mixed internal docs (PDF, MD, DOCX, URLs).

---

## Researcher quickstart

```bash
pip install research-hub-pipeline[playwright,secrets]
research-hub init --persona researcher
# Enter your Zotero key + library ID when prompted
research-hub add 10.48550/arxiv.2310.06770 --cluster llm-agents
research-hub serve --dashboard  # opens browser at http://127.0.0.1:8765
```

After you have 5+ papers in a cluster:

```bash
research-hub crystal emit --cluster llm-agents > prompt.md
# Feed prompt.md to Claude/GPT, save response as crystals.json
research-hub crystal apply --cluster llm-agents --scored crystals.json
```

---

## Humanities quickstart

```bash
pip install research-hub-pipeline[playwright,secrets]
research-hub init --persona humanities
# Same Zotero setup as researcher
research-hub add 10.example/source --cluster victorian-novels
research-hub quote add victorian-novels-source --text "..." --page 42 --note "..."
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

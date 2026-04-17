# `research-hub import-folder` - local file ingest

> Available since v0.31.0. For analyst persona users with folders of mixed local docs (no DOIs).

The `add` command works for academic papers (DOI / arXiv ID lookup). `import-folder` is its sibling for everything else: internal PDFs, market reports, meeting notes, web clippings, Word drafts.

## When to use

| You have | Use |
|---|---|
| A DOI or arXiv ID | `research-hub add 10.48550/arxiv.2310.06770 --cluster X` |
| A folder of mixed PDF / DOCX / Markdown / TXT / URL files | `research-hub import-folder ./folder --cluster X` |
| A pile of Zotero items already collected | (use Zotero ingest path: `research-hub ingest`) |

## Quick start

```bash
# 1. Install with the optional `import` extras for PDF/DOCX/URL extractors
pip install 'research-hub-pipeline[import]'

# 2. Make a cluster (or let import-folder auto-create one)
research-hub clusters new --slug market-research --query "competitive intelligence Q2"

# 3. Walk the folder
research-hub import-folder ~/Downloads/q2-competitor-pdfs --cluster market-research

# 4. Verify
research-hub status
research-hub where
```

After step 3:
- Each supported file becomes one note in `<vault>/raw/market-research/<slug>.md`
- Frontmatter includes `source_kind`, `topic_cluster`, `ingested_at`, `raw_path` (pointer back to original file)
- Body contains a 5000-char preview (trimmed for note size; full content stays at `raw_path`)
- Dedup index updated with content hash so re-running skips already-imported files

## Supported file types

| Extension | Source kind | Extractor | Optional dep |
|---|---|---|---|
| `.pdf` | `pdf` | `pdfplumber` | yes |
| `.md`, `.markdown` | `markdown` | direct read (strips frontmatter) | no |
| `.txt` | `txt` | direct read | no |
| `.docx` | `docx` | `python-docx` | yes |
| `.url` | `url` | `requests` + `readability-lxml` | yes |

If you don't install `[import]` extras, only `.md` and `.txt` work; PDF/DOCX/URL files raise an actionable error.

## CLI reference

```
research-hub import-folder FOLDER --cluster SLUG [OPTIONS]

  FOLDER              Path to source folder (recursive walk)
  --cluster SLUG      Target cluster (auto-created if missing)
  --extensions LIST   Comma-separated extensions (default: pdf,md,txt,docx,url)
  --no-skip-existing  Re-import even if content hash matches existing note
  --use-graphify      Deprecated; warns and does not run graphify
  --graphify-graph    Path to pre-built graphify-out/graph.json
  --dry-run           Show what would be imported, write nothing
```

## Examples

**Lightweight default (no graphify):**
```bash
research-hub import-folder ~/Downloads/competitor-pdfs --cluster comp-intel
# Output:
#   imported:  12
#   skipped:   2     (already in dedup index)
#   failed:    0
```

**Only certain extensions:**
```bash
research-hub import-folder ./project --cluster X --extensions pdf,docx
```

**Dry-run (preview before committing changes):**
```bash
research-hub import-folder ./project --cluster X --dry-run
# Lists what WOULD be imported, makes no file system changes
```

**Re-import (refresh content):**
```bash
research-hub import-folder ./project --cluster X --no-skip-existing
```

## Deep extraction with graphify

[graphify](https://github.com/safishamsi/graphify) is an external coding-skill that reads multi-modal content (PDFs, code, images, video transcripts via Whisper) and builds a knowledge graph using Leiden community detection. research-hub can use a graphify-built `graph.json` to assign sub-topics to imported notes.

**graphify runs inside an AI coding agent (Claude Code, Codex, etc.) and is not a standalone CLI.** First-time extraction needs subagent dispatch from the host AI tool.

### Two-step workflow

**Step 1: produce `graph.json` via graphify (in Claude Code):**

```bash
# Inside Claude Code:
/graphify ./project
# Produces: ./graphify-out/graph.json with nodes + edges + community assignments
```

**Step 2: point research-hub at the `graph.json`:**

```bash
research-hub import-folder ./project --cluster X \
    --graphify-graph ./graphify-out/graph.json
```

Each imported note gets `subtopics: [community-name, ...]` frontmatter based on which graphify community its source file belongs to. Then run `research-hub topic build --cluster X` to generate per-subtopic landing pages.

### Deprecated: `--use-graphify`

v0.31 had a `--use-graphify` flag that tried to invoke graphify via subprocess. This was a design error: graphify is not a standalone CLI. The flag is preserved for backward compatibility in v0.32 but does nothing except emit a deprecation warning. Use `--graphify-graph PATH` instead. See [audit_v0.31.md](audit_v0.31.md) for the discovery story.

## Frontmatter that gets written

For a `.pdf` file:

```yaml
---
title: "PDF First Heading or Filename"
slug: "pdf-first-heading-or-filename"
source_kind: pdf
ingested_at: "2026-04-17T04:30:00Z"
ingestion_source: import-folder
topic_cluster: market-research
labels: []
tags: []
raw_path: "/Users/you/Downloads/competitor-pdfs/something.pdf"
summary: "First 500 chars of extracted text..."
---

# Body preview (first 5000 chars)
...
```

Compare to a paper note (from `research-hub add <DOI>`):

```yaml
---
title: "Paper Title"
authors: "Smith, John; Doe, Jane"
year: 2024
journal: "Nature"
doi: "10.1234/xyz"
source_kind: paper
topic_cluster: market-research
labels: []
...
---
```

Both are `Document` instances; Paper just has more fields.

## Integration with the rest of research-hub

After `import-folder`:

| Command | Works on imported docs? |
|---|---|
| `research-hub status` | yes - shows them as papers |
| `research-hub where` | yes - counted in note total |
| `research-hub label SLUG --add core` | yes - labels work on any Document |
| `research-hub move SLUG --to OTHER-CLUSTER` | yes - moves between clusters |
| `research-hub crystal emit --cluster X` | yes - crystals work on mixed paper + Document content |
| `research-hub notebooklm bundle --cluster X` | yes - bundle walks `raw/<cluster>/` regardless of source_kind |
| `research-hub topic build --cluster X` | yes - sub-topics work on imported docs (especially with `--graphify-graph`) |
| `research-hub clusters analyze --split-suggestion` | partial - uses citation graph, which non-paper docs don't have. Falls back to keyword overlap. |

## Troubleshooting

**`ImportError: install 'research-hub-pipeline[import]' for local file ingest`**
You tried to ingest a PDF/DOCX/URL without installing the optional extractors. Run:
```bash
pip install 'research-hub-pipeline[import]'
```

**`--use-graphify` warns and nothing happens**
That flag is deprecated in v0.32 because graphify cannot be invoked as a standalone CLI. Run `/graphify ./project` in Claude Code first, then pass the generated graph file:
```bash
research-hub import-folder ./project --cluster X \
    --graphify-graph ./graphify-out/graph.json
```

**Imported PDF has weird text artifacts**
`pdfplumber` is text-based; it does not OCR. If your PDF is a scanned image, the text extraction will be garbage. Workarounds:
- Pre-process with `ocrmypdf` then re-import
- Use graphify separately to produce a richer `graph.json`, then import with `--graphify-graph`

**Same file imported twice, both notes appear**
The second one was written because content hash differed (e.g., file was edited between runs) OR `--no-skip-existing` was passed. To clean up:
```bash
research-hub remove <slug-of-duplicate>
```

**Want to import 1000+ files**
First time will take a while (PDF extraction is slow). Subsequent runs only process new/changed files (content-hash dedup). For very large imports, use `--dry-run` first to confirm scope.

## See also

- [docs/anti-rag.md](anti-rag.md) - why crystals work on imported docs too
- [docs/example-claude-mcp-flow.md](example-claude-mcp-flow.md) - Claude Desktop driving the full ingest -> bundle -> NotebookLM flow
- [docs/notebooklm.md](notebooklm.md) - wiring NotebookLM for the bundle/upload/generate/download chain

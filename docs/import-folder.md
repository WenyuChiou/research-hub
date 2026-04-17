# `research-hub import-folder` — local file ingest

> Available since v0.31.0. For analyst persona users with folders of mixed local docs (no DOIs).

The `add` command works for academic papers (DOI / arXiv ID lookup). `import-folder` is its sibling for everything else — internal PDFs, market reports, meeting notes, web clippings, Word drafts.

## When to use

| You have | Use |
|---|---|
| A DOI or arXiv ID | `research-hub add 10.48550/arxiv.2310.06770 --cluster X` |
| A folder of mixed PDF / DOCX / Markdown / TXT / URL files | `research-hub import-folder ./folder --cluster X` |
| A pile of Zotero items already collected | (use Zotero ingest path — `research-hub ingest`) |

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
  --use-graphify      Run graphify CLI for deep extraction + community-based sub-topics
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

graphify (https://github.com/safishamsi/graphify) is an external tool that reads multi-modal content (PDFs, code, images, video transcripts) and builds a knowledge graph using Leiden community detection. research-hub uses it as an OPTIONAL backend for deep multi-modal extraction.

```bash
# Install graphify separately (heavyweight; not added to research-hub deps)
pip install graphifyy && graphify install

# Use it during import
research-hub import-folder ./project --cluster X --use-graphify
```

What `--use-graphify` does on top of the default flow:
1. After lightweight extraction, runs `graphify <folder>` once to build a concept graph
2. Parses `graphify-out/graph.json` to find communities (semantic clusters of related files)
3. Adds `subtopics: [...]` frontmatter to each imported note based on its community membership
4. You can then run `research-hub topic build --cluster X` to generate per-subtopic landing pages

If graphify isn't installed, you get an actionable error pointing to the install command.

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
| `research-hub status` | yes — shows them as papers |
| `research-hub where` | yes — counted in note total |
| `research-hub label SLUG --add core` | yes — labels work on any Document |
| `research-hub move SLUG --to OTHER-CLUSTER` | yes — moves between clusters |
| `research-hub crystal emit --cluster X` | yes — crystals work on mixed paper + Document content |
| `research-hub notebooklm bundle --cluster X` | yes — bundle walks `raw/<cluster>/` regardless of source_kind |
| `research-hub topic build --cluster X` | yes — sub-topics work on imported docs (especially with `--use-graphify`) |
| `research-hub clusters analyze --split-suggestion` | partial — uses citation graph, which non-paper docs don't have. Falls back to keyword overlap. |

## Troubleshooting

**`ImportError: install 'research-hub-pipeline[import]' for local file ingest`**
You tried to ingest a PDF/DOCX/URL without installing the optional extractors. Run:
```bash
pip install 'research-hub-pipeline[import]'
```

**`ERROR: --use-graphify requires graphify CLI`**
You passed `--use-graphify` but graphify isn't on your PATH. Install:
```bash
pip install graphifyy && graphify install
```

**Imported PDF has weird text artifacts**
`pdfplumber` is text-based — it doesn't OCR. If your PDF is a scanned image, the text extraction will be garbage. Workarounds:
- Pre-process with `ocrmypdf` then re-import
- Use `--use-graphify` (graphify can run Whisper/OCR on multi-modal sources)

**Same file imported twice, both notes appear**
The second one was written because content hash differed (e.g., file was edited between runs) OR `--no-skip-existing` was passed. To clean up:
```bash
research-hub remove <slug-of-duplicate>
```

**Want to import 1000+ files**
First time will take a while (PDF extraction is slow). Subsequent runs only process new/changed files (content-hash dedup). For very large imports, use `--dry-run` first to confirm scope.

## See also

- [docs/anti-rag.md](anti-rag.md) — why crystals work on imported docs too
- [docs/example-claude-mcp-flow.md](example-claude-mcp-flow.md) — Claude Desktop driving the full ingest → bundle → NotebookLM flow
- [docs/notebooklm.md](notebooklm.md) — wiring NotebookLM for the bundle/upload/generate/download chain

---
name: paper-summarize
description: After research-hub ingests a cluster of papers, fill the per-paper Key Findings + Methodology + Relevance sections in BOTH Obsidian markdown and the Zotero child note. Use when the user says "summarize this cluster's papers", "fill the TODO Findings", or "I just ran auto and don't know what these papers are about". Invokes `claude` / `codex` / `gemini` (whichever is on PATH) on each paper's abstract.
---

# paper-summarize

The `auto` pipeline ingests metadata + abstract only — Summary / Key Findings / Methodology / Relevance stay as `[TODO]` skeletons in both Obsidian and Zotero. Cluster-level summarization (NotebookLM brief, crystals) does NOT fill per-paper notes. So after `auto`, the user has nothing scannable per paper without opening the PDF.

This skill fills that gap. One LLM call per paper, JSON-validated, written to both vault systems atomically (rollback the markdown change if Zotero write fails so the two stay in sync).

## When to use

Trigger phrases:

- "Summarize the papers in cluster X."
- "Fill the TODO Key Findings for X."
- "I just ran `auto X` and the notes are empty — give me real summaries."
- "Update Zotero notes for cluster X with what each paper actually says."

Not for:

- Generating a single CLUSTER-LEVEL summary — that's `research-hub notebooklm generate` (NotebookLM brief).
- Filling Q&A on the cluster — that's `research-hub crystal emit/apply`.
- Reading PDFs — abstract-only by design. PDF parsing is out of scope; the LLM is told to mark "[PDF needed]" if abstract is too thin.
- Verifying brief vs source — that's `notebooklm-brief-verifier`.

## Inputs

- Cluster slug (must already exist in the vault under `raw/<slug>/`)
- Optional LLM CLI override (`claude` / `codex` / `gemini`)
- Optional `--apply` flag (default off, dry-run)

The skill reads each paper's frontmatter (DOI, year, zotero-key) + the `## Abstract` body block. Papers with empty abstract get a "PDF needed" marker rather than hallucinated findings.

## Outputs

For each paper, three sections are rewritten:

1. **Obsidian markdown** at `raw/<cluster>/<paper-slug>.md`:
   - `## Key Findings` callout block (3–5 bullets)
   - `## Methodology` callout block (one sentence)
   - `## Relevance` callout block (1–2 sentences linking to the cluster topic)
   - Anchor IDs (`^findings`, `^methodology`, `^relevance`) preserved.

2. **Zotero child note** for the paper's parent item (looked up via `zotero-key` frontmatter):
   - Existing note HTML overwritten with `<h1>Summary` + Abstract + Key Findings `<ul>` + Methodology + Relevance.
   - If no child note exists, one is created.

Both writes must succeed for a paper to count as "applied". A Zotero write failure rolls back the markdown change so the two systems stay in sync.

## Failure modes

- **No LLM CLI on PATH**: prompt is saved to `<vault>/.research_hub/artifacts/<cluster>/summarize-prompt.md`. The user pipes it through their LLM manually and re-runs with `--apply`, or calls the `apply_cluster_summaries` MCP tool with the parsed payload. Exit code 0; ok=True.
- **LLM returns malformed JSON**: report is `ok=False` with `error="LLM response had no parseable JSON object"`. No writes.
- **Paper slug in payload not in cluster**: that entry is skipped with reason logged; other entries still applied.
- **Empty key_findings / methodology / relevance**: entry skipped.
- **Zotero write fails for one paper**: that paper's markdown change is rolled back; other papers still applied.

## Verification

```bash
# Dry-run (just emit prompt + show what LLM produced)
research-hub summarize --cluster <slug>

# Live run (writes to Obsidian + Zotero)
research-hub summarize --cluster <slug> --apply

# Override LLM
research-hub summarize --cluster <slug> --llm-cli codex --apply

# Obsidian-only (skip Zotero — useful when Zotero is offline)
research-hub summarize --cluster <slug> --apply --no-zotero
```

After applying, scan `raw/<cluster>/*.md` — every paper's `## Key Findings` callout should have real bullets instead of `[TODO]`.

## Operating notes

- Findings-first: the prompt instructs the LLM to state the result, not "The paper shows that…".
- Anchored to the abstract: every Key Finding must trace to something the abstract claims. The LLM is told to mark uncertain claims with `[likely]`.
- Idempotent: re-running on a cluster with already-filled findings will overwrite them with whatever the LLM produces this run. Use `--no-zotero` or `--no-obsidian` if you want to preview one side first.
- Same dual-write discipline as the abstract-sync helpers in `.scratch/`: one transactional unit per paper.

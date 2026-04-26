---
name: literature-triage-matrix
description: Turn a list of papers (Zotero collection, Obsidian cluster, manual list) into a compact comparison matrix written to .research/literature_matrix.md, instead of generic per-paper summaries. Use when the user asks to "make a literature matrix", "compare these papers by method/data/limitations", or "decide which papers are central to my review".
---

# literature-triage-matrix

Produce a single comparison table over a set of papers, optimized for
review-writing decisions. The matrix lets the user (or a downstream
writing skill) see at a glance which papers cluster together by method,
which carry the load on a particular claim, and which can be cited in
passing vs deeply engaged.

This skill avoids the common AI failure mode of "give me a summary of
each paper" — which produces N independent bullet lists that the user
then has to manually compare.

## When to use

Trigger phrases:

- "Make a literature matrix for these papers."
- "Compare these papers by method, data, claims, and limitations."
- "Help me decide which papers are central to my review."
- "Build a triage table over my Zotero collection / Obsidian cluster."

Not for:

- A 5-page narrative literature review — that's a writing task.
- Citation formatting — Zotero and the writing skill handle that.
- Single-paper deep dive — use `paper-memory-builder`.

## Inputs

In priority order (cheapest to most expensive):

0. **Manual paper list** — a Markdown bullet list of titles + DOIs (or
   arXiv IDs) the user pastes directly into the chat. **Lowest-friction
   entry; works without any other research-hub setup.** Treat each
   line as one row in the matrix; fill cells from your own knowledge
   + DOI lookup if the title is famous, otherwise mark `?` and ask
   the user.

   Example minimal input:
   ```
   - "Memory enables ToM-like behaviour in LLM poker agents", arXiv:2604.04157
   - "Multi-agent LLM social learning", arXiv:2604.02677
   - "Triadic Loop alignment framework", arXiv:2604.18850
   ```

1. **`.research/literature_matrix.md`** — if it already exists, parse it
   first. Append-only by convention; only re-emit a row if the
   underlying paper changed materially.
2. **Obsidian cluster notes** under `raw/<cluster>/*.md` — these have
   structured frontmatter (title, authors, year, doi) plus
   research-hub-generated `Summary / Key Findings / Methodology /
   Relevance` sections. Read these first; they're cheaper than PDFs.
3. **Zotero collection metadata** via local API (fast) — add child note
   contents only if Obsidian doesn't have the paper.
4. **NotebookLM downloaded briefs** under `.research_hub/artifacts/` —
   if the user has already generated a brief on the cluster, mine it
   for cross-paper comparisons.
5. **Raw PDFs** — only as last resort, and only the abstract + first 2
   pages + conclusion. PDFs are token-expensive.

## Output

Write to `<project-root>/.research/literature_matrix.md`. Append by
default; rewrite the whole table only if the user explicitly says
"regenerate from scratch".

Markdown table columns (customize per request, but default is):

```markdown
| Citation | Question | Method | Data / study area | Main claim | Evidence | Limitation | Relevance | Use as |
|---|---|---|---|---|---|---|---|---|
| Smith 2024 | How does adaptation affect flood risk? | mesa-based ABM, 10k agents | Houston synthetic | Adaptation cuts loss 18% | simulation | single basin, no validation | High — direct precedent | Lit review §2 |
| Jones 2023 | Hydraulic coupling in flood ABMs | Coupled ABM-2D | Galveston | Coupling reduces RMSE 22% | empirical | calibration window narrow | Medium — methods | Methods §3 |
```

Column meanings:

- **Citation** — short reference (e.g., `Smith 2024`); leaving full
  citation to Zotero.
- **Question** — the paper's research question, one sentence.
- **Method** — model class + key technical detail.
- **Data / study area** — datasets used + geographic / temporal scope.
- **Main claim** — single most-cited finding, one sentence.
- **Evidence** — what kind: simulation / empirical / theoretical / review.
- **Limitation** — most important caveat, one sentence.
- **Relevance** — `High / Medium / Low` + one-phrase justification.
- **Use as** — where in the user's manuscript or review this paper fits
  (Lit review, Methods, Discussion, citation-only).

## Token-saving behavior

- Read existing `.research/literature_matrix.md` first; only emit rows
  for papers not already covered or whose underlying note changed.
- Prefer Obsidian frontmatter + the `Summary` section over re-reading
  the PDF.
- Use stable paper identifiers (DOI or arXiv ID) so future requests can
  reference rows by `Smith 2024 (10.1234/abcd)` instead of pasting
  paragraphs.
- Cap PDF reads at 3 per session; tell the user if more are needed.

## Output format for the user

After writing the matrix, print:

```
[literature-triage-matrix]
  Wrote/appended: .research/literature_matrix.md
  Papers in matrix: 12 (4 new this run)
  Skipped (already in matrix, unchanged): 8
  Read full PDF for: 1 (Smith 2024 — no Obsidian note found)
  Suggested next: review High-relevance rows in .research/literature_matrix.md
```

## What NOT to do

- Don't write to `.paper/` — that's `paper-memory-builder`'s territory.
- Don't fabricate findings if a paper's note is sparse. Emit the row with
  `?` in unknown columns and a note: `(Obsidian note incomplete — run
  research-hub auto with --max-papers 1 to enrich, or fill manually)`.
- Don't re-summarize already-summarized papers unless explicitly asked.
- Don't include columns the user didn't ask for. The default 9 columns
  are a starting point; trim if requested.

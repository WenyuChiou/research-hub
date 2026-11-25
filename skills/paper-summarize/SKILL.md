---
name: paper-summarize
description: "Have your active AI host (Claude Code, Codex, etc.) natively read cited papers and produce seven-section source-bound summaries (why, objective, methods, results, conclusions, key points, limitations) without requiring Hub or a separate LLM CLI. Also covers the existing abstract-only research-hub summarize CLI to fill Key Findings/Methodology/Relevance in authorized Obsidian and Zotero notes. Use for per-paper summaries or TODO Findings; use paper-memory-builder for the user's manuscript and literature-triage-matrix for cross-paper comparison."
---

# paper-summarize

## Choose the source scope first

- **Per-paper body/full-text summary (Default — Host-Native):** use the native route below when the user asks why/what/how/results/conclusions, supplies a paper, or requests full-text reading. Your active AI host reads and summarizes directly; Hub, Zotero, Obsidian and a separate LLM CLI are optional.
- **Existing abstract-note update (CLI batch helper):** use the unchanged abstract-note mode below for a requested cluster/TODO update based on its stored abstracts. `research-hub summarize` and `paper-abstract-draft` remain abstract-only; neither command becomes a full-text reader because this skill has two routes.
- Do not silently downgrade a full-text request to abstract-only. If body access is unavailable, preserve useful narrower claims, label the result partial and explain the missing source; do not ask the researcher to fill JSON.

## Native per-paper body summary

Read [the per-paper contract](references/fulltext-summary.md), then inspect the available authorized source with your host's native reading tools (do not shell out to `--llm-cli` for single-paper body reading). Produce the seven-section readable summary plus source/version and actual reading scope. Keep `supported`, `analyst_inference` and `unknown` distinct. The contract is domain-neutral: methods and evidence follow the study design, not a fixed LLM, statistical or experimental template.

Use the shared [research protocol](../research-hub/references/research-protocol.md) when source discovery is needed and for observed stage timing. Compare cited passages semantically; byte/quote checks alone are not scientific acceptance. Return useful prose without requiring Hub ingestion. Persist only through an available, selected and authorized destination; a readable result or local file does not establish an Obsidian/Roam import. Preserve human-authored content and report saving as pending if the destination cannot retain the evidence/statuses (`human_acceptance: pending`, `semantic_support: not_assessed`). For an already selected Hub workspace, follow the optional [native-summary handoff](references/fulltext-summary.md#optional-selected-hub-handoff) (including deterministic `project native-summary-import` / `native-summary-export` generic Markdown stdout export); otherwise keep the native readable result without adding Hub setup.

## Abstract-note mode (existing CLI)

The `auto` or abstract-only `ingest` pipeline writes metadata + abstract only — Summary / Key Findings / Methodology / Relevance stay as `[TODO]` skeletons in Obsidian and Zotero. Cluster-level synthesis (NotebookLM brief, crystals) does NOT fill per-paper notes. When an existing cluster has thin TODO notes, prefer host-native reading above, or use this CLI fallback to populate abstract-only notes in Obsidian and Zotero. These writes are not a distributed transaction: unconfirmed remote writes remain unknown, and local compensation is best-effort, never proof that the destinations are synchronized.

### When to use abstract-note mode

Trigger phrases:

- "Summarize the papers in cluster X."
- "Fill the TODO Key Findings for X."
- "Update Zotero notes for cluster X from their stored abstracts."

Not for:

- Generating a single CLUSTER-LEVEL summary — that's `research-hub notebooklm generate` (NotebookLM brief).
- Filling Q&A on the cluster — that's `research-hub crystal emit/apply`.
- Reading PDFs through the CLI — it is abstract-only by design; use the native per-paper body route above instead. The abstract prompt marks "[PDF needed]" when its input is too thin; that marker is not full-text reading.
- Verifying brief vs source — that's `notebooklm-brief-verifier`.

### Abstract-note inputs

- Cluster slug (must already exist in the vault under `raw/<slug>/`)
- Optional LLM CLI override (`claude`, `codex`, `gemini`, `opencode`, `aichat`, `cursor`, or configured custom adapter) — CLI batch fallback only; omit when your active AI host is generating summaries directly
- Optional `--apply` flag (default off, dry-run)

The skill reads each paper's frontmatter (DOI, year, zotero-key) + the `## Abstract` body block. Papers with empty abstract get a "PDF needed" marker rather than hallucinated findings.

### Abstract-note outputs

For each paper, three sections are rewritten:

1. **Obsidian markdown** at `raw/<cluster>/<paper-slug>.md`:
   - `## Key Findings` callout block (3–5 bullets)
   - `## Methodology` callout block (one sentence)
   - `## Relevance` callout block (1–2 sentences linking to the cluster topic)
   - Anchor IDs (`^findings`, `^methodology`, `^relevance`) preserved.

2. **Zotero child note** for the paper's parent item (looked up via `zotero-key` frontmatter):
   - Only an explicitly owned Hub summary note is updated with `<h1>Summary` + Abstract + Key Findings `<ul>` + Methodology + Relevance. Unmarked notes are preserved.
   - If no owned summary exists, a tagged summary is created; ambiguous ownership is refused. See `docs/zotero-summary-note-ownership.md` for preservation and unknown-outcome limits.

Both writes must be confirmed for a paper to count as "applied". If the remote outcome is unconfirmed, report it as unknown and do not retry automatically. Local compensation restores the original note only if its current text still matches this invocation's written text; a newer observed edit is preserved. Failed compensation is reported for reconciliation rather than hiding other papers' outcomes. This check does not exclude a concurrent writer racing after the check. Inspect both destinations before an explicit retry; success counters count confirmed applied papers, not proof that failed/unknown papers were untouched.

### Abstract-note failure modes

- **No LLM CLI on PATH**: prompt is saved to `<vault>/.research_hub/artifacts/<cluster>/summarize-prompt.md`. This is **prompt-only** success (exit code 0; `ok=True`): no summaries were generated or applied, even with `--apply`. Re-running `--apply` does not import externally generated summaries. If the native host agent has available, authorized tools, it can read this prompt and return readable abstract-based summaries. These are not full-text validation. Persisting them requires a selected, separately authorized supported destination operation. The `apply_cluster_summaries` MCP tool defaults to writing both Obsidian and Zotero; it is not an automatically authorized fallback. If a supported authorized persistence route is unavailable, preserve the readable result and clearly report saving as pending; do not ask the researcher to author JSON.
- **LLM returns malformed JSON**: report is `ok=False` with `error="LLM response had no parseable JSON object"`. No writes.
- **Paper slug in payload not in cluster**: that entry is skipped with reason logged; other entries still applied.
- **Empty key_findings / methodology / relevance**: entry skipped.
- **Zotero write is unconfirmed for one paper**: report unknown, do not retry automatically, and attempt guarded local compensation. A newer observed edit or compensation failure is preserved/reported; other papers retain their own outcomes.

### Abstract-note verification & operating notes

```bash
# Run the full paper-summarize suite (23 tests)
python -m pytest -q tests/test_v069_summarize.py tests/test_v073_parallel_summarize.py tests/test_v080_resummarize.py

# Dry-run / apply against a live vault
research-hub summarize --cluster <slug>
research-hub summarize --cluster <slug> --apply
research-hub summarize --cluster <slug> --apply --no-zotero
```

- Findings-first & anchored to the abstract: state findings directly, mark uncertain claims `[likely]`.
- Re-running may regenerate different content and overwrite the selected summary sections; this is not an idempotency or duplicate-prevention guarantee. `--no-zotero` and `--no-obsidian` disable only their named destination: they are not preview flags, and `--apply` still writes to the other enabled destination. Omit `--apply` to avoid summary destination writes; model invocation and local prompt artifacts may still occur.
- Each paper has separate destination outcomes with best-effort local compensation, not an atomic cross-system transaction. Preserve unknown outcomes and reconcile the exact intended write before any explicit retry.

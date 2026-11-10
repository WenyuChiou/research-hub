---
name: paper-summarize
description: "Summarize individual cited papers at their actual reading depth: why the work was done, its objective, methods, results, conclusions, key points and limitations, with located source evidence. For full-text requests use the native-host reading route without requiring Hub or a vault. The existing research-hub summarize CLI remains abstract-only and fills Key Findings/Methodology/Relevance in authorized Obsidian and Zotero notes. Use for per-paper summaries or TODO Findings; use paper-memory-builder for the user's manuscript and literature-triage-matrix for cross-paper comparison."
---

# paper-summarize

## Choose the source scope first

- **Per-paper body/full-text summary:** use the native route below when the
  user asks why/what/how/results/conclusions, supplies a paper, or requests
  full-text reading. Hub, Zotero, Obsidian and a separate LLM CLI are optional.
- **Existing abstract-note update:** use the unchanged abstract-note mode
  below for a requested cluster/TODO update based on its stored abstracts.
  `research-hub summarize` and `paper-abstract-draft` remain abstract-only;
  neither command becomes a full-text reader because this skill has two routes.
- Do not silently downgrade a full-text request to abstract-only. If body
  access is unavailable, preserve useful narrower claims, label the result
  partial and explain the missing source; do not ask the researcher to fill JSON.

## Native per-paper body summary

Read [the per-paper contract](references/fulltext-summary.md), then the
available authorized source with the host's native reading tools. Produce the
seven-section readable summary plus source/version and actual reading scope.
Keep `supported`, `analyst_inference` and `unknown` distinct. The contract is
domain-neutral: methods and evidence follow the study design, not a fixed
LLM, statistical or experimental template.

Use the shared [research protocol](../research-hub/references/research-protocol.md)
when source discovery is needed and for observed stage timing. Compare cited
passages semantically; byte/quote checks alone are not scientific acceptance.
Return useful prose without requiring Hub ingestion. Persist only through an
available, selected and authorized destination; a readable result or local file
does not establish an Obsidian/Roam import. Preserve human-authored content and
report saving as pending if the destination cannot retain the evidence/statuses.

## Abstract-note mode (existing CLI)

The `auto` pipeline ingests metadata + abstract only — Summary / Key Findings / Methodology / Relevance stay as `[TODO]` skeletons in both Obsidian and Zotero. Cluster-level summarization (NotebookLM brief, crystals) does NOT fill per-paper notes. So after `auto`, the user has nothing scannable per paper without opening the PDF.

This skill fills that gap. One LLM call per paper produces JSON-validated content for both destinations. These writes are not a distributed transaction: unconfirmed remote writes remain unknown, and local compensation is best-effort, never proof that the destinations are synchronized.

### When to use abstract-note mode

Trigger phrases:

- "Summarize the papers in cluster X."
- "Fill the TODO Key Findings for X."
- "I just ran `auto X` and the notes are empty — give me real summaries."
- "Update Zotero notes for cluster X with what each paper actually says."

Not for:

- Generating a single CLUSTER-LEVEL summary — that's `research-hub notebooklm generate` (NotebookLM brief).
- Filling Q&A on the cluster — that's `research-hub crystal emit/apply`.
- Reading PDFs through the CLI — it is abstract-only by design; use the native
  per-paper body route above instead. The abstract prompt marks "[PDF needed]"
  when its input is too thin; that marker is not full-text reading.
- Verifying brief vs source — that's `notebooklm-brief-verifier`.

### Abstract-note inputs

- Cluster slug (must already exist in the vault under `raw/<slug>/`)
- Optional LLM CLI override (`claude`, `codex`, `gemini`, `opencode`, `aichat`, `cursor`, or configured custom adapter)
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

### Abstract-note verification

The abstract-note integration is exercised with fixtures by the test suite. The
suites stub the LLM CLI but execute real Obsidian markdown writes against
a fixture vault and real Zotero child-note writes against a mocked Zotero
adapter. Successful rollback, unavailable compensation, newer observed edits,
and unknown remote acknowledgement are distinct contracts; the bounded direct
fault script adds coverage without claiming live-provider acceptance.

```bash
# Run the full paper-summarize suite (23 tests)
python -m pytest -q \
  tests/test_v069_summarize.py \
  tests/test_v073_parallel_summarize.py \
  tests/test_v080_resummarize.py
```

Coverage breakdown:

| Test file | Count | What it covers |
|---|---|---|
| `tests/test_v069_summarize.py` | 17 | Prompt builder shape, validator (rejects unknown slugs / empty fields / wrong types), Obsidian + Zotero apply path, rollback when Zotero fails, no-LLM-on-PATH fallback |
| `tests/test_v073_parallel_summarize.py` | 3 | Parallel summarize across multiple clusters, ordering, error isolation |
| `tests/test_v080_resummarize.py` | 3 | Re-summarize behaviour: idempotent on same input, overwrite on different LLM output, --no-zotero path |

For a manual smoke check against a live vault:

```bash
# Dry-run (emit prompt + show LLM output, no writes)
research-hub summarize --cluster <slug>

# Live run (writes to Obsidian + Zotero)
research-hub summarize --cluster <slug> --apply

# Override LLM
research-hub summarize --cluster <slug> --llm-cli codex --apply

# Obsidian-only (skip Zotero — useful when Zotero is offline)
research-hub summarize --cluster <slug> --apply --no-zotero
```

After applying, scan `raw/<cluster>/*.md` — every paper's `## Key Findings` callout should have real bullets instead of `[TODO]`.

### Abstract-note operating notes

- Findings-first: the prompt instructs the LLM to state the result, not "The paper shows that…".
- Anchored to the abstract: every Key Finding must trace to something the abstract claims. The LLM is told to mark uncertain claims with `[likely]`.
- Re-running may regenerate different content and overwrite the selected summary sections; this is not an idempotency or duplicate-prevention guarantee. `--no-zotero` and `--no-obsidian` disable only their named destination: they are not preview flags, and `--apply` still writes to the other enabled destination. Omit `--apply` to avoid summary destination writes; model invocation and local prompt artifacts may still occur.
- Each paper has separate destination outcomes with best-effort local compensation, not an atomic cross-system transaction. Preserve unknown outcomes and reconcile the exact intended write before any explicit retry.

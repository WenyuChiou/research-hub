---
name: notebooklm-brief-verifier
description: Compare a downloaded NotebookLM brief against the source bundle research-hub uploaded, and report missed sources, unsupported claims, contradictions, and recommended follow-up prompts. Use when the user asks to "verify this NotebookLM brief", "check if the brief missed anything", or "compare downloaded notes to the cluster papers".
---

# notebooklm-brief-verifier

NotebookLM is great at producing readable briefs, but it can:

- Skip a source that was in the bundle (silently — no error).
- Make claims the source bundle doesn't actually support.
- Contradict claims across sources without flagging the conflict.
- Generalize beyond the data ("studies show...") when one paper says
  something narrow.

This skill verifies a downloaded brief against the actual source bundle
that research-hub uploaded, so the user can trust (or distrust) the brief
before sharing or citing.

## When to use

Trigger phrases:

- "Check this NotebookLM brief against the source bundle."
- "Verify whether NotebookLM missed or hallucinated anything important."
- "Compare downloaded NotebookLM notes to the cluster papers."
- "Audit this brief before I send it to my advisor."

Not for:

- Generating the brief in the first place — that's
  `research-hub notebooklm generate`.
- Comparing papers to each other — `literature-triage-matrix`.
- Manuscript-level claim audit — `academic-writing-skills`.

## Evidence contract

Use `../research-hub/references/source-claim-audit.md` and
`../research-hub/references/research-protocol.md`. Citation mentions and
nearby apparently contradictory sentences are screening signals. Final
support/contradiction judgments require actual same-version source passages
at the claim's needed evidence level. If the shared files are unavailable,
retain these minimum rules and explicitly report remaining evidence gaps.

## Inputs

In priority order:

1. **research-hub-managed mode** (default). When the brief was generated
   via `research-hub notebooklm generate` + `download`:
   - **Brief**: `.research_hub/artifacts/<cluster>/brief-*.txt`
   - **Bundle manifest**: `.research_hub/bundles/<cluster>/manifest.json`
     — list of which source files were uploaded.
   - **Cluster Obsidian notes** under `raw/<cluster>/*.md` — for
     screening specific claims; generated notes are not source proof.
   - **Actual source text / PDFs** under `pdfs/<cluster>/` — read relevant
     sections for load-bearing claims within the declared resource bound.
     A three-source spot-check does not verify a fourth source.

2. **Manual fallback mode** (new in v0.68.x). When the user generated
   the brief themselves on notebooklm.google.com — direct upload, web
   UI, copy-paste — research-hub never saw the bundle. Accept either
   CLI flags or a paste-into-chat:

   - `--brief <path-to-brief.{md,txt,pdf}>` — the downloaded brief
     file (any path, not just `.research_hub/artifacts/`).
   - `--sources <path-to-source-list.{yml,md,json}>` — a plain list
     of the source titles + DOIs / URLs the user uploaded to NLM.

   Conversational variant: paste the brief and the source list
   directly into the chat. The skill should ask explicitly for the
   source list if missing — do NOT assume coverage without ground
   truth.

The verification logic (source coverage scan, claim attribution,
contradiction scan, overgeneralization scan, spot-check, follow-up
prompts) is identical in both modes. Only the input-loading layer
differs.

If the user names a brief file directly, prefer that path over guessing.

## Method

1. **Bundle inventory**: list every source the bundle uploaded (paper
   title, citation key, DOI). Call this set `S_bundle`.
2. **Source coverage scan**: for each `S_bundle` item, search the brief
   text for the citation key, DOI, or first-author name. Call any
   bundle item with zero hits "not mentioned". A missing mention is not
   proof of substantive omission, and a mention is not proof of coverage.
3. **Claim attribution scan**: for each declarative claim in the brief
   (sentences ending with a period, containing factual statements),
   identify which source the brief attributes it to. If a claim has no
   attribution, flag as "unattributed; support not yet assessed". Attribution
   alone does not demonstrate source support.
4. **Cross-source contradiction scan**: when two sources are both
   referenced near apparently contradictory claims, flag for passage review.
   Preserve population, conditions and uncertainty before judging conflict.
5. **Generalization scan**: any sentence with phrases like "studies
   show", "all", "always", "consistently" without a specific source
   should be flagged as potential overgeneralization.
6. **Source checks**: prioritize load-bearing / surprising claims and read
   the actual abstract or relevant source sections, with version, quote,
   locator and hashes when available. Mark supported, partial, contradicted
   or unverifiable at the actual evidence level. Inventory all claims in
   the denominator; list those beyond the approved read bound as unassessed.
   An empty claim denominator is unavailable, not a perfect pass.

## Output

Report assessed/total claims, source sections actually read, unchecked
load-bearing claims, access/version limits, and partial/bounded completion.
A well-attributed brief is not automatically verified.


In-conversation report (no file written by default). The report has 7 sections: source mentions/coverage, unattributed or source-unsupported claims, source-checked contradictions, potential overgeneralizations, source-checked claims, recommended follow-up NotebookLM prompts, and verdict (reliable for / use with caution for / do not cite without spot-check).

Full template + worked example: `references/report-template.md`.

If reviewed source passages support the brief within the declared scope, the report is short — that's a feature, not a bug.

## Token-saving behavior

- Read the brief once at the start; quote line numbers in the report
  rather than re-reading.
- Compare against the bundle manifest first; only open source files for
  checks prioritized by decision relevance within the declared resource bound.
  Keep unchecked claims explicit; a read cap cannot certify the whole brief.
- Cache the report in `.research_hub/artifacts/<cluster>/brief-verify-<ts>.md`
  optionally if the user says "save this report".

## What NOT to do

- Don't rewrite the brief — that's NLM's job.
- Don't write to `.research/` or `.paper/` — this is verification, not
  workspace setup.
- Don't OCR figures embedded in PDFs.
- Don't infer support for a claim from "general knowledge" — only from
  the actual source bundle.
- Don't tell the user to ignore NLM. Tell them which parts to trust and
  which to spot-check.

## See also

- `references/report-template.md` — full 7-section verification report template

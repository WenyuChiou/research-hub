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

## Inputs

In priority order:

1. **research-hub-managed mode** (default). When the brief was generated
   via `research-hub notebooklm generate` + `download`:
   - **Brief**: `.research_hub/artifacts/<cluster>/brief-*.txt`
   - **Bundle manifest**: `.research_hub/bundles/<cluster>/manifest.json`
     — list of which source files were uploaded.
   - **Cluster Obsidian notes** under `raw/<cluster>/*.md` — for
     spot-checking specific claims.
   - **Source PDFs** under `pdfs/<cluster>/` — last-resort spot-check
     only; cap at 3 per session.

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
   bundle item with zero hits a "missed source".
3. **Claim attribution scan**: for each declarative claim in the brief
   (sentences ending with a period, containing factual statements),
   identify which source the brief attributes it to. If a claim has no
   attribution, flag as "unsupported".
4. **Cross-source contradiction scan**: when two sources are both
   referenced near contradictory claims, flag.
5. **Generalization scan**: any sentence with phrases like "studies
   show", "all", "always", "consistently" without a specific source
   should be flagged as potential overgeneralization.
6. **Spot-check**: pick the 1-3 most surprising / load-bearing claims
   and read the underlying source paper's abstract + relevant section
   to confirm support.

## Output

In-conversation report (no file written by default). Structure:

```
## NotebookLM brief verification report

**Brief**: <path>
**Bundle**: <cluster_slug> (<N> sources)

### Source coverage
- Cited in brief: <X> / <N>
- Missed sources: <list of citation keys not mentioned>

### Unsupported claims
- "<claim text>" (line <N> of brief) — no clear source attribution
- ...

### Cross-source contradictions
- "<claim A>" (cites Smith 2024) vs "<claim B>" (cites Jones 2023) —
  appear to contradict; brief does not flag this
- ...

### Potential overgeneralizations
- "Studies show..." — actually one paper, Smith 2024
- ...

### Spot-checked claims
- "<load-bearing claim>" — reviewed Smith 2024 §3, **supported**
- "<surprising claim>" — reviewed Jones 2023 abstract, **partially
  supported** (specific to coastal basins, not generalizable)

### Recommended follow-up NotebookLM prompts
- "What does Smith 2024 say about <X> specifically? Cite directly."
- "Compare Smith 2024's claim about <Y> with Jones 2023's findings."

### Verdict
- Reliable for: <broad takeaways, comparison framing>
- Use with caution for: <specific numbers, generalizations>
- Do not cite without spot-check: <list>
```

If the brief is well-attributed and bundle coverage is complete, the
report is short — that's a feature, not a bug.

## Token-saving behavior

- Read the brief once at the start; quote line numbers in the report
  rather than re-reading.
- Compare against the bundle manifest first; only open source files for
  spot-checks (cap 3 per run).
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

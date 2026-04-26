---
name: research-design-helper
description: Guide a researcher through 5 Socratic segments — research question sharpening, expected mechanism, identifiability check, validation plan, risk register — and produce `.research/design_brief.md`. Use when the user asks to "frame this research question", "design my study", "help me think through what model to build", "sharpen my hypothesis", or "before I start coding, walk me through the design". Does NOT write the model spec; does NOT invent the research question — guides the human to articulate them.
---

# research-design-helper

Stage 3a (sharp problem framing) and front-of-Stage 4 (model design)
helper. Part of the research-hub skill pack — works alongside Zotero,
Obsidian, and NotebookLM workflows but does not require any of them.
Domain-agnostic Socratic guide that walks a researcher through 5 short
segments and saves the result as `.research/design_brief.md`.

The skill **does not invent your research question or model design**.
Like `research-context-compressor`, it leaves blanks rather than
guess. Its value is structured prompting: forcing you to articulate
what you'd otherwise leave implicit, before you spend weeks coding.

## When to use

Trigger phrases:

- "Frame this research question."
- "Design my study before I start coding."
- "Help me think through what model to build."
- "Sharpen my hypothesis."
- "Walk me through the design."
- "Build a design brief."

Not for:

- Writing actual model code (that's the user's work, optionally with
  `codex-delegate` for boilerplate).
- Project context manifests (that's `research-context-compressor`).
- Literature comparison (that's `literature-triage-matrix`).
- Manuscript writing (that's `academic-writing-skills`).

## Inputs

In priority order:

1. `.research/project_manifest.yml` if it exists — for project context
   (research_question may already be partially filled).
2. `.research/design_brief.md` if it exists — for refresh, not first-run.
3. `.research/literature_matrix.md` if it exists — for prior-art context
   when discussing identifiability.
4. The user's free-text answers during the conversation.

Do NOT scan code, data, or PDFs. This is a conversational skill.

## The 5 Socratic segments

Run in order. After each, save the user's answers (verbatim) to the
corresponding section of `.research/design_brief.md`. If the user can't
answer a segment yet, write `_TODO: <reason>_` and move on; do not
fabricate.

### 1. Research question sharpening

Goal: turn a vague interest into a falsifiable RQ.

Ask:
- "What did you say you were studying, in one sentence?"
- "What would you observe if your hypothesis is FALSE? If you can't
  describe it, the question isn't sharp yet."
- "What's the smallest version of the question you could answer with
  a 1-week prototype?"

Output: `## 1. Research question` with the sharpened RQ + the
falsification condition.

### 2. Expected mechanism

Goal: write down the causal chain BEFORE the experiment runs.

Ask:
- "Walk me through the mechanism: A causes B because of C; B then
  affects D through E."
- "Where in this chain are you most uncertain?"
- "If A → B → D is wrong, which intermediate step would you bet
  breaks first?"

Output: `## 2. Expected mechanism` with the chain + uncertainty
annotations.

### 3. Identifiability check

Goal: confirm the experimental design CAN distinguish RQ-true from
RQ-false. This is where most ABM / simulation studies silently fail.

Ask:
- "What experiment, dataset, or counterfactual would discriminate
  between your hypothesis and its main alternative?"
- "What confounders would you need to rule out?"
- "If your data can't tell the two apart, what's the minimum extra
  data you'd need?"

Output: `## 3. Identifiability check` with the discriminating
condition + listed confounders + missing-data plan.

### 4. Validation plan

Goal: pre-commit to how the user will know the result is real.

Ask:
- "What metric quantifies success?"
- "What baseline are you beating?"
- "What's the negative control — a setup where you EXPECT the metric
  to NOT improve, and that confirms your method isn't just noise?"

Output: `## 4. Validation plan` with metric, baseline, negative
control.

### 5. Risk register

Goal: list 3-5 specific things that would kill the design.

Ask:
- "What could go wrong with the data?"
- "What could go wrong with the model assumptions?"
- "What could go wrong with how you interpret the result?"
- "What's the most likely reason a reviewer would reject this study
  as currently designed?"

For each risk, ask: "What would early-warning of this risk look
like? What would you do?"

Output: `## 5. Risk register` with risks + early-warning + mitigation
per row.

## Output: `.research/design_brief.md`

Use the template at `references/design_brief_template.md` (sibling
file in this skill). Fill the 5 sections with the user's answers
verbatim. At the top, include metadata:

```markdown
---
project: <from project_manifest.yml or asked at start>
last_updated: <ISO date>
stage: design
status: draft     # draft | reviewed | locked
---
```

If the file already exists, **update don't replace**: keep human-edited
sections intact, only fill blanks unless the user explicitly says
"regenerate from scratch".

## Token-saving behavior

- Don't repeat the user's answers back at length — quote in the
  written brief, summarize one sentence in the conversation.
- Don't dump the whole template into the chat — just write the file
  and report what sections were filled.
- Skip segments the user can't answer; record `_TODO_` and move on.
  The point is not to complete every section in one session; it's to
  surface the gaps.

## Output format for the user

After saving the brief, print:

```
[research-design-helper]
  Wrote: .research/design_brief.md
  Sections completed: 4 / 5 (Risk register marked _TODO_ — circle back)
  Strongest spot: Identifiability check — clear discrimination via
                  negative control.
  Weakest spot: Validation plan — baseline not yet specified.
  Suggested next: refine the validation baseline, then re-run this
                  skill with "regenerate from scratch" to lock the
                  brief.
```

## What NOT to do

- **Do NOT invent the research question.** If the user is vague,
  surface the vagueness; do not fill it in for them.
- **Do NOT propose model architectures or technologies.** That's
  Stage 4 implementation work, owned by the user with help from
  `codex-delegate` for boilerplate. This skill stops at the spec.
- **Do NOT write to `.paper/`** — that's `paper-memory-builder`.
- **Do NOT touch `.research/project_manifest.yml`** — that's
  `research-context-compressor`. The two are complementary; the
  manifest captures STATE, the brief captures DESIGN INTENT.
- **Do NOT skip segments silently.** If a segment is blank, the
  brief must say `_TODO_` so future sessions (or the orienter) can
  flag it.

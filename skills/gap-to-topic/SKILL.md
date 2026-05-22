---
name: gap-to-topic
description: Turn a research area into a go/no-go decision dossier for ONE candidate thesis/proposal topic — a 3-gate verdict (is the gap open? is it a contribution? is it feasible?) with the evidence laid out so the researcher can verify it. Use when the user asks "is this gap worth pursuing", "help me pick a thesis topic", "is this idea already taken", "find me a defensible research gap", "vet this research idea before I commit", or "should I do this". NOT a literature review (use `literature-triage-matrix` for a comparison matrix) and NOT a study design (use `research-design-helper` once a topic is chosen). Produces a `.research/topic_dossier.md` plus a `.bib` and a `.gaps.yml`.
compatibility: Pure agentskills.io-spec skill. Domain-agnostic; works alongside Zotero/Obsidian/NotebookLM workflows but requires none of them.
---

# gap-to-topic

Choosing a thesis or proposal topic is not "do a literature review." It is a
decision under uncertainty: *given everything already known, what should I do
next, and why is it defensible?* This skill produces the document that
decision actually needs — a **3-gate decision dossier** for one (or a few)
candidate breakthrough points.

It deliberately stops short of the verdict. It assembles the evidence for
three gates and hands the final *"is this worth doing"* call back to the
researcher and their advisor — where it belongs.

## When to use

Trigger phrases:

- "Is this research gap worth pursuing?"
- "Help me pick a thesis / proposal topic."
- "Is this idea already taken? / has someone done this?"
- "Find me a defensible research gap in <area>."
- "Vet this research idea before I commit."
- "Should I do this? / should I commit to this?"

Not for:

- A comparison matrix over a known paper set — that's `literature-triage-matrix`.
- Designing the study once a topic is chosen — that's `research-design-helper`
  (gap-to-topic decides *which* topic; research-design-helper designs *how*).
- A narrative literature review — that's a writing task.
- Building manuscript claim memory — that's `paper-memory-builder`.

## What it produces

`.research/topic_dossier.md` — a fixed 5-section document (§0–§4):

| § | Section | Answers |
|---|---|---|
| §0 | Candidate breakthrough point(s) | what topic, typed **A** (a method-limitation opening) or **B** (an unoccupied-application opening) |
| §1 | Gate ① — **Open?** | is the gap genuinely unoccupied — backed by a complete, verifiable reference list |
| §2 | Gate ② — **A contribution?** | dead-end history + contribution type (problem-solving vs incremental) |
| §3 | Gate ③ — **Feasible?** | can the data / resources be obtained in time and budget |
| §4 | Handed back to the human | the dossier states explicitly that the *"worth it"* verdict is the researcher's + advisor's |

Plus two machine-readable companions: `<dossier>.bib` (the §1 reference
list as BibTeX) and `<dossier>.gaps.yml` (structured gaps + open questions).

The go/no-go test is a **3-gate AND** — a candidate that fails ANY gate is a
no-go. The dossier is a thinking tool, not a polished report.

## Inputs

In priority order:

1. A research area or a candidate idea, stated by the user in conversation.
2. `.research/literature_matrix.md` if it exists — prior-art context.
3. `.research/claims.yml` if it exists — only when the user is *also*
   drafting a manuscript; its `status: gap` claims cross-link to §2.
4. The user's free-text answers during the §0 and §3 conversational steps.

This skill orchestrates other research-hub capabilities as tools:
`search --adversarial` (§1 recall), `cite --format bibtex` (§1 `.bib`),
and `literature-triage-matrix` (§0/§1 prior art). `paper gaps` is used
only when a relevant ingested cluster already exists — at topic-selection
time it usually does not, so `literature-triage-matrix` is the default.

## Workflow

Run §0–§4 in order. Each section has a fixed contract; do not skip a gate.

### §0 — Candidate breakthrough point(s)

Socratic, like `research-design-helper`. Help the user articulate 1–N
candidates. Do **not** invent the topic. For each, classify the type:

- **Type A — method-limitation opening:** an existing method *cannot* do X
  ("traditional ABM cannot give agent profiles via text").
- **Type B — unoccupied-application opening:** no one has applied a
  capability to a domain ("no one has used LLMs for X").

A multi-gap candidate is decomposed into its constituent gaps; every later
gate runs per gap.

### §1 — Gate ① — Open?

Incomplete recall is the dominant failure mode: a missed paper makes a gap
look open when it is not. So this gate is **adversarial**:

1. Run `research-hub search --adversarial` on the gap — it searches several
   query phrasings and reports a recall-confidence verdict. If `--adversarial`
   is unavailable (older CLI), run several query phrasings by hand and record
   the reduced recall confidence in the dossier.
2. Emit the **complete reference list** (real DOIs / arXiv IDs) as the
   `.bib` companion via `cite --format bibtex` — this is the trust artifact;
   the researcher must be able to verify "open" themselves.
3. Record the recall-confidence verdict as a **headline**, not a footnote.

A gap is never declared "open" on the basis of "absent from my corpus" —
absence in a corpus is not absence in the literature.

### §2 — Gate ② — A contribution?

Two parts — see the references for the full method:

- **Dead-end history** (`references/dead-end-history.md`): find the
  "tried-but-unsolvable" history. A gap can be open because the field gave
  up on it (a dead end), not because no one tried.
- **Contribution typing** (`references/contribution-typing.md`): classify
  the candidate as *problem-solving* or *incremental*. This is a descriptive
  lens, not a quality verdict — `incremental` is not "not worth doing."

### §3 — Gate ③ — Feasible?

Front-loaded by design: the researcher must know feasibility *before*
building the research framework, before spending money and running
experiments. Socratically establish data / resource accessibility — is the
data public? what does it cost? how long to obtain? — and record a verdict.

### §4 — Handed back to the human

The dossier ends by stating explicitly: it has assembled the three
gate-verdicts; whether the gap is *worth doing* is the researcher's and
advisor's call. The skill never makes that call.

## Honesty rules

- **Never decide "worth it."** §4 is a hard boundary.
- **Quote verification:** every evidence quote in §1/§2 must be confirmed to
  exist in the cited source; an unverified quote is dropped, not downgraded.
- **Absence is not proof:** every "open" verdict carries the recall caveat.
- **Screening-grade, not systematic:** the dossier says so in §4.
- **No fabricated identifiers:** every DOI / arXiv ID must resolve.

## References

- `references/dossier-template.md` — the blank §0–§4 dossier + companion-file schemas.
- `references/dead-end-history.md` — §2 dead-end detection method.
- `references/contribution-typing.md` — §2 contribution-type classification.

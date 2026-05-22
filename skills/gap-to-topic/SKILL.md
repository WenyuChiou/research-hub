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

`.research/topic_dossier.md` — a **reader-first summary report**: it must
read top-to-bottom in Word with no decoding — no codes (`G1`/`G2` stay only
in `.gaps.yml`), no decorative glyphs, plain-language verdicts ("Do not
pursue — as stated" / "Worth pursuing — only if its open conditions hold" /
"Worth pursuing"), tool mechanics kept in Appendix A.

| Section | What it covers |
|---|---|
| Bottom line | the answer up front — one plain-language paragraph per candidate plus a **Decision scorecard** table (candidates × the 3 gates + verdict) |
| What's in this deliverable | an index of the bundle — every file and what information it carries |
| The candidates | 1–N candidate topics in a roster table, each given a readable name + a plain "why it could be a gap" phrase |
| Gate 1 — Is the gap still open? | the literature funnel + classification, closest prior work, recall confidence |
| Gate 2 — Would it be a real contribution? | dead-end history + new-capability-vs-extension |
| Gate 3 — Is it feasible? | can the data / resources be obtained in time and budget |
| The decision is yours | the dossier states explicitly the *"worth it"* verdict is the researcher's + advisor's; upgrade/kill test per conditional candidate |
| Appendix A | how the dossier was produced (pipeline, recall mechanics) |

(SKILL.md §0–§4 below are the agent's internal workflow steps; they map to
the reader-facing sections above — §0 → The candidates, §1 → Gate 1, etc.)

Plus two machine-readable companions: `<dossier>.bib` (the Gate 1 reference
list as BibTeX) and `<dossier>.gaps.yml` (structured candidates + verdicts +
open questions — keeps the machine ids and enum tokens).

The go/no-go test is a **3-gate AND** — a candidate that fails ANY gate is a
no-go. The dossier is a thinking tool, not a polished report.

## Inputs

In priority order:

1. A research area or a candidate idea, stated by the user in conversation.
2. `.research/literature_matrix.md` — produced in §1 step 2, or reused
   (appended to) if an earlier run already wrote one.
3. `.research/claims.yml` if it exists — only when the user is *also*
   drafting a manuscript; its `status: gap` claims cross-link to §2.
4. The user's free-text answers during the §0 and §3 conversational steps.

This skill orchestrates other research-hub capabilities as tools:
`search --adversarial --screen --json` (§1 step 1 — recall, the fit-check
BM25 relevance gate, and the metadata the `.bib` is built from) and
`literature-triage-matrix` (§1 step 2 — turns the on-topic search results
into the prior-art comparison matrix). `paper gaps`
is used only when a relevant ingested cluster already exists — at
topic-selection time it usually does not, so the
`search` → `literature-triage-matrix` path is the default. Note:
`cite --format bibtex` is **not** used for the §1 `.bib` — it resolves
identifiers only against an already-ingested Zotero library, and at
topic-selection time the candidate papers are not ingested (see §1 step 3).

## Workflow

Run §0–§4 in order. Each section has a fixed contract; do not skip a gate.

### §0 — Candidate breakthrough point(s)

Socratic, like `research-design-helper`. Help the user articulate 1–N
candidates. Do **not** invent the topic. For each candidate:

- **Give it a short, readable name** — it becomes the candidate's heading
  in the dossier ("The candidates" section). The `G1` / `G2` id is only a
  machine tag for the `.gaps.yml` companion; it must never be the reader's
  primary label.
- **Classify the opening type**, and write it in plain words in the dossier:
  - **Type A — method-limitation opening:** an existing method *cannot* do X
    ("traditional ABM cannot give agent profiles via text").
  - **Type B — unoccupied-application opening:** no one has applied a
    capability to a domain ("no one has used LLMs for X").

A multi-gap candidate is decomposed into its constituent gaps; every later
gate runs per gap.

### §1 — Gate ① — Open?

Incomplete recall is the dominant failure mode: a missed paper makes a gap
look open when it is not. So this gate is **adversarial**:

1. Run `research-hub search --adversarial --screen --json` on the gap. It
   searches several query phrasings, reports a recall-confidence verdict,
   and applies the fit-check BM25 relevance gate. With `--screen --json` the
   output is an object `{screening_summary, results}`: `results` is the
   per-paper list (title, DOI / arXiv ID, year, authors, venue, plus a
   `relevance` field — `score` / `kept` / `tier` / `reason`), and
   `screening_summary`
   gives the retrieved / kept / screened-out counts. `--screen` never drops
   a paper — it tags relevance, so recall stays auditable. If `--adversarial`
   or `--screen` is unavailable (older CLI), run several query phrasings by
   hand and record the reduced recall confidence in the dossier.
2. From `results`, take the **on-topic** papers — those the relevance gate
   tagged `kept: true` — and feed them to `literature-triage-matrix` (as
   its input #0, a Markdown list of titles + DOIs / arXiv IDs) to produce
   `.research/literature_matrix.md`: the structured prior-art comparison
   (per paper — method, main claim, evidence, limitation, relevance).
   Papers tagged `kept: false` are off-topic noise — keep them out of the
   matrix, the `.bib` and the openness reasoning. This matrix is a **real
   workflow output** — it is what the openness judgement in step 4 and the
   §2 gates read, not an assumed pre-existing input. If a
   `literature_matrix.md` from an earlier run exists, `literature-triage-matrix`
   appends to it; if either skill is unavailable, reason directly over the
   `results` and record the reduced structure in the dossier.
3. Build the **complete reference list** (real DOIs / arXiv IDs) as the
   `.bib` companion **from the on-topic `results` metadata** (the same
   `kept: true` set as step 2) — this is the trust artifact; the researcher
   must be able to verify "open" themselves. Do **not** use
   `cite --format bibtex` here: `cite` resolves identifiers only against an
   already-ingested Zotero library, and at topic-selection time the
   candidate papers are not ingested. Every entry must carry a resolvable
   DOI or arXiv ID; drop any paper whose identifier did not resolve (an
   unverifiable reference is not a trust artifact).
4. Record the recall-confidence verdict as a **headline**, not a footnote,
   and report the `screening_summary` counts (retrieved vs on-topic) so the
   reader sees how much of the corpus was off-topic noise. Reason the
   per-gap openness over the step-2 matrix.

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

- `references/dossier-template.md` — the blank reader-first dossier + companion-file schemas.
- `references/dead-end-history.md` — §2 dead-end detection method.
- `references/contribution-typing.md` — §2 contribution-type classification.

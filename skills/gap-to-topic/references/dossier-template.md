# Reference — the topic-decision dossier (blank template)

> The shape `gap-to-topic` emits to `.research/topic_dossier.md`. Each `>`
> italic note is that section's contract — what it must contain. The dossier
> is a thinking tool: surface uncertainty, do not polish it away.
>
> **Reader-first rules** — the dossier is written for a researcher (a
> graduate student and their advisor) deciding a thesis or proposal topic.
> It must read as a plain summary report, top-to-bottom, with no decoding:
> - **No codes in the document.** Candidates are named in plain words; the
>   machine ids (`G1`, `G2`, …) live only in the `.gaps.yml` companion.
> - **No decorative symbols.** No `✓ ✗ ~` glyphs, no `·` separators.
> - **Plain verdicts.** Never "no-go / go" jargon — say "Do not pursue —
>   as stated", "Worth pursuing — only if its open conditions hold",
>   "Worth pursuing".
> - **Lead with the answer**; keep tool / pipeline mechanics in Appendix A.
> - Formal enum tokens (`partially-occupied`, `borderline`, …) belong in
>   `.gaps.yml`, not the prose — gloss them in plain words.
> - The dossier is **English by default**. A translated mirror is produced
>   only on request, in a sibling-language folder.

---

# Topic Decision Dossier — <topic area>

## Bottom line

> *One framing sentence (what was evaluated), then one short paragraph per
> candidate — name it, give its plain-language outcome, and the reason in a
> sentence or two. Each paragraph must name at least one concrete piece of
> evidence. Then the Decision scorecard, then the one key caveat.*

<One sentence: N candidate topics were evaluated for <area>.>

**<Candidate 1 name>** — <plain outcome>. <One or two plain sentences; name
a concrete piece of evidence.>

**<Candidate 2 name>** — <plain outcome>. <…with a concrete piece of
evidence named.>

### Decision scorecard

> *Each gate is stated as a claim and rated 1–5: 5 = strongly agree the
> claim holds, 3 = mixed or qualified, 1 = strongly disagree. A topic is
> worth pursuing only if every gate rates 3 or higher. A gate after a gate
> that already failed reads "Not assessed". No glyphs — the cell is
> `N/5 label — short description`.*

Rating: 5 = strongly agree, 4 = agree, 3 = neutral, 2 = disagree,
1 = strongly disagree. A topic is worth pursuing only if every gate is 3 or
higher.

| Candidate | Gate 1 — "the gap is still open" | Gate 2 — "it would be a real contribution" | Gate 3 — "it is feasible within reach" | Verdict |
|---|---|---|---|---|
| 1. <name> | <N/5 label — short description> | <N/5 label — … or "Not assessed"> | <N/5 label — … or "Not assessed"> | **<Do not pursue — as stated / Worth pursuing — only if its open conditions hold / Worth pursuing>** |
| 2. <name> | … | … | … | **…** |

| Field | Value |
|---|---|
| Area | <the research area> |
| Compiled | <YYYY-MM-DD> |
| Verdict grade | Screening-grade — assembles evidence; does NOT decide worth |

> *This dossier is a thinking tool, not a polished report. It runs each
> candidate through a 3-gate test — open AND a contribution AND feasible. A
> candidate that fails any gate should not be pursued as stated. The "is it
> worth doing" call is handed back to the researcher and advisor.*

## What's in this deliverable

> *An index of the bundle — every file and what information it carries — so
> a reader knows the whole pack from this one document, then a file tree of
> the layout. A default (English-only) dossier lists a flat bundle; a
> translated deliverable shows the sibling-language folders.*

| File | What it is | What it gives you |
|---|---|---|
| `topic_dossier.md` / `.docx` | This document — the topic-decision summary | The verdict on each candidate and the evidence behind it |
| `topic_dossier.bib` | The reference list, as BibTeX | Every cited paper with a resolvable DOI / arXiv ID — lets you verify "open" yourself |
| `literature_matrix.md` | The paper-by-paper comparison table | How each retrieved paper compares — method, claim, evidence type, limitation |
| `topic_dossier.gaps.yml` | Machine-readable export | Structured data for a downstream tool or a later pass; not needed for reading |

```
<deliverable-folder>/
├── topic_dossier.md / .docx
├── topic_dossier.bib
├── literature_matrix.md
└── topic_dossier.gaps.yml
```

## The candidates

> *1–N candidates, articulated WITH the researcher (Socratic — never
> invented). The roster table names each and says, in plain words, why it
> could be a gap — each "why" cell leads with one of two plain tags:
> "No one has tried this" (a capability not yet applied to a domain) or
> "Current methods fall short" (an existing method has a blocking limit).
> Then a one-sentence statement per candidate. Each candidate also has a
> machine id (`G1`, `G2`, …) — that id goes ONLY into `.gaps.yml`.*

| # | Candidate topic | Why it could be a gap |
|---|---|---|
| 1 | <readable name> | <"No one has tried this" / "Current methods fall short"> — <plain rationale> |
| 2 | <readable name> | <…> |

1. **<name>** — <one-sentence statement of the candidate>.
2. **<name>** — <…>

## Gate 1 — Is the gap still open?

> *The verdict is in the Decision scorecard; this section is the evidence
> behind it, in three blocks.*

**Literature collected.** The Gate 1 search funnel:

| Stage | Count |
|---|---|
| Retrieved (adversarial query phrasings) | <N unique papers> |
| Returned for relevance screening | <M> |
| Kept on-topic by the relevance gate | <K> |
| Selected into the prior-art corpus | <P> |

Classification of the prior-art corpus (full per-paper detail in
`literature_matrix.md`):

| By evidence type | By candidate |
|---|---|
| <e.g. 6 primary studies, 2 reviews, 1 survey, 1 perspective, 1 caution paper, 2 close analogues> | <e.g. 9 bear on Candidate 1, 4 on Candidate 2> |

**Closest prior work, and how solid it is.** <One conclusion sentence, then
a few bullets — the key papers per candidate, each with an inline
evidence-type tag (primary study, review, survey, perspective, caution
paper, close analogue, conference abstract, preprint, data artifact), and a
plain note on how solid the occupancy signal is. Full list in the `.bib`.>

- **Candidate 1:** <key papers, tagged> — <how solid the signal is>.
- **Candidate 2:** <closest analogues, tagged> — <how thin the direct
  evidence is>.

**Recall confidence.** <One plain sentence — e.g. "Medium: one search
backend was unavailable, so a missed paper is possible; re-check before
relying on an 'open' verdict.">

## Gate 2 — Would it be a real contribution?

> *The scorecard carries the verdict; here is the reasoning, per assessed
> candidate, in four parts. A candidate that failed Gate 1 is not assessed.*

For each assessed candidate:

- **What it would contribute.** <One explicit claim — what the finished
  research would add: a modelling method, a validated behavioural
  representation, a dataset or benchmark, an empirical finding, or a
  decision-support result. Not "applies X to Y" — the actual addition.>
- **Has the field tried this and hit a wall?** <Plain answer. If a caution
  or post-mortem paper exists, summarise the *kind* of risk it raises —
  construct validity, ethics, representativeness, interpretability — not
  just "go read it".>
- **A new capability, or an extension of existing work?** <Plain answer +
  one-sentence justification. A descriptive lens, not a quality judgment;
  an extension can be well worth doing.>
- **Minimum validation sketch.** <What would distinguish a real
  contribution from a plausible-looking result: the behaviour target, a
  baseline or comparator, a held-out test, and the main failure mode the
  study must survive.>

## Gate 3 — Is it feasible?

> *The scorecard carries the verdict; here is the detail, per assessed
> candidate, in five parts. Front-loaded — feasibility must be known BEFORE
> the research framework is built. A candidate that failed an earlier gate
> is not assessed.*

For each assessed candidate:

- **What it needs.** <Data / resources — public? cost? lead time?>
- **Design feasibility.** <Beyond data availability: can the baselines /
  comparators actually be run; privacy or consent constraints on the data;
  reproducibility when outputs depend on an external API model.>
- **Scale outline.** <A rough size / time / cost band — enough for the
  reader to picture the project, not a precise estimate.>
- **The binding constraint.** <The one item that decides the timeline.>
- **Proposal-feasible vs dissertation-feasible.** <State both: what a
  proposal needs to clear, and whether a full dissertation or paper can
  realistically be completed — for a student the effort boundary is the
  decision.>

## The decision is yours

> *The dossier stops here. It has assembled the three gate verdicts;
> whether a gap is WORTH doing is the researcher's and advisor's call.
> Frame each surviving candidate consistently as a CONDITIONAL
> RECOMMENDATION pending named checks — do not mix "evidence, not a
> verdict" with "worth pursuing". For each, give an upgrade / kill test
> written as concrete artifacts or results, and for a failed candidate one
> explicit salvage-path line.*

The three gates above are assembled evidence. A topic is worth pursuing
only if all three pass — open AND a contribution AND feasible. **Whether
<Candidate N> is worth pursuing is your and your advisor's decision**, and
for any candidate that cleared the gates it is a *conditional
recommendation* — worth pursuing once the checks below are met.

<Per candidate: the plain outcome, then the conditions to resolve.>

**Upgrade / kill test — <conditional candidate>.** It is **worth pursuing**
once <each open condition expressed as a concrete artifact or result — e.g.
"a held-out validation result against baseline X", not "credibly answer">.
It is **not worth pursuing as stated** if <the concrete finding that would
fail a gate>.

**Salvage path — <failed candidate>.** <One line: the narrower slice worth
a fresh look, and what specifically to re-search.>

---

## Appendix A — How this dossier was produced

> *A method note, not a tool log — enough for a researcher to judge how far
> to trust the dossier and what must be re-run. Downplay internal command
> names; state search scope, inclusion criteria, and dates; separate the
> automated steps from agent / researcher judgement.*

| Item | Detail |
|---|---|
| Search scope | <what was searched: query phrasings, fields, year range, the backends used and any unavailable> |
| Inclusion criteria | <how the prior-art corpus was selected from the screened set — what made a paper in or out> |
| Automated vs judgement | <which steps were automated — search, relevance screening — and which were agent / researcher judgement — corpus selection, evidence tagging, the gate verdicts> |
| Recall confidence | <the headline confidence and why; what to re-run for a tighter verdict> |
| Run details | <date; tool version; pipeline as a one-line trace if useful> |

---

## Schema reference — `topic_dossier.gaps.yml` (NOT emitted in the dossier)

> The `.gaps.yml` companion is machine-readable and is **not** part of the
> human dossier above. It keeps the machine ids (`G1`, `G2`) and the formal
> enum tokens. Its shape:

```yaml
dossier: <topic area>
generated: "YYYY-MM-DD"
gaps:
  - id: G1
    name: "<readable candidate name>"
    statement: "<candidate>"
    type: A            # A = method-limitation | B = unoccupied-application
    open: open         # open | partially-occupied | occupied
    dead_end_status: genuinely-open
    contribution_type: problem-solving
    feasibility: feasible
    linked_claim: null  # claims.yml C-id, only if a manuscript draft exists
open_questions:
  - id: Q1
    text: "<question the evidence could not settle>"
```

The `.bib` companion is the Gate 1 reference list as BibTeX — built from the
on-topic `search --adversarial --screen --json` results (NOT from
`cite --format bibtex`, which resolves only already-ingested Zotero items —
see SKILL.md §1 step 3). Every entry must have a resolvable DOI or arXiv ID.

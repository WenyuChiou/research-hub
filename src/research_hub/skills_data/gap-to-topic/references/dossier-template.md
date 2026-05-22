# Reference — the topic-decision dossier (blank template)

> The shape `gap-to-topic` emits to `.research/topic_dossier.md`. Each `>`
> italic note is that section's contract — what it must contain. The dossier
> is a thinking tool: surface uncertainty, do not polish it away.
>
> **Reader-first rules** — the dossier must read as a plain summary report a
> researcher understands top-to-bottom in Word, with no decoding:
> - **No codes in the document.** Candidates are named in plain words; the
>   machine ids (`G1`, `G2`, …) live only in the `.gaps.yml` companion,
>   never in the dossier.
> - **No decorative symbols.** No `✓ ✗ ~` glyphs, no `·` separators —
>   plain words, plain numbering, commas and "and".
> - **Plain verdicts.** Never "no-go / go" jargon — say "Do not pursue —
>   as stated", "Worth pursuing — only if its open conditions hold",
>   "Worth pursuing".
> - **Lead with the answer**, state each gate verdict in plain language
>   before the evidence, keep tool / pipeline mechanics in Appendix A.
> - Formal enum tokens (`partially-occupied`, `borderline`, …) belong in
>   `.gaps.yml`, not the prose — gloss them in plain words.

---

# Topic Decision Dossier — <topic area>

## Bottom line

> *One framing sentence (what was evaluated), then one short paragraph per
> candidate — name it, give its plain-language outcome and the reason in a
> sentence or two. Then the Decision scorecard, then the single most
> important caveat. A reader must get the whole answer here.*

<One sentence: N candidate topics were evaluated for <area>.>

**<Candidate 1 name>** — <plain outcome>. <One or two plain sentences: why
this outcome.>

**<Candidate 2 name>** — <plain outcome>. <…>

### Decision scorecard

> *Candidates against the 3 gates, plus the verdict. Plain words only — no
> glyphs. A gate a candidate was not assessed on (it already failed an
> earlier gate) reads "Not assessed".*

| Candidate | Gate 1 — Open? | Gate 2 — A contribution? | Gate 3 — Feasible? | Verdict |
|---|---|---|---|---|
| 1. <name> | <Open / Occupied / Partially occupied + confidence> | <A contribution / Borderline / Not assessed> | <Feasible / Feasible with effort / Blocked / Not assessed> | **<Do not pursue — as stated / Worth pursuing — only if its open conditions hold / Worth pursuing>** |
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

> *An index of the bundle — every file and what information it carries, so
> a reader knows the whole pack from this one document.*

| File | What it is | What it gives you |
|---|---|---|
| `topic_dossier.md` / `.docx` | This document — the topic-decision summary | The verdict on each candidate and the evidence behind it |
| `topic_dossier.bib` | The reference list, as BibTeX | Every cited paper with a resolvable DOI / arXiv ID — lets you verify "open" yourself |
| `literature_matrix.md` | The paper-by-paper comparison table | How each retrieved paper compares — method, claim, evidence type, limitation |
| `topic_dossier.gaps.yml` | Machine-readable export | Structured data for a downstream tool or a later pass; not needed for reading |

## The candidates

> *1–N candidates, articulated WITH the researcher (Socratic — never
> invented). The roster table names each and says, in plain words, why it
> could be a gap; then a one-sentence statement per candidate. Each
> candidate also has a machine id (`G1`, `G2`, …) — that id goes ONLY into
> `.gaps.yml`, never into this document.*

| # | Candidate topic | Why it could be a gap |
|---|---|---|
| 1 | <readable name> | <plain phrase — e.g. "a capability no one has applied to this domain" or "a limit of existing methods"> |
| 2 | <readable name> | <…> |

1. **<name>** — <one-sentence statement of the candidate>.
2. **<name>** — <…>

## Gate 1 — Is the gap still open?

> *The verdict is in the Decision scorecard; this section is the evidence
> behind it. Show the search funnel and the prior-art classification, the
> closest prior work (each work tagged by evidence type), an evidence-mix
> summary, and a one-sentence recall-confidence headline. Tool mechanics go
> in Appendix A. "Absent from my corpus" is never proof of "open".*

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

**Closest prior work.** <The papers that bear on whether each gap is filled
— readable prose, each tagged by evidence type (primary study, review,
survey, perspective, caution paper, close analogue, conference abstract,
preprint, data artifact). Full list in the `.bib`.>

**Evidence mix.** <One or two sentences: how solid the occupancy signal is
— e.g. an "occupied" verdict resting mostly on conference abstracts is
weaker than one resting on primary studies.>

**Recall confidence.** <One plain sentence — e.g. "Medium: one search
backend was unavailable, so a missed paper is possible; re-check before
relying on an 'open' verdict.">

## Gate 2 — Would it be a real contribution?

> *The scorecard carries the verdict; here is the reasoning. Per assessed
> candidate, two plain-language questions. (1) Has the field already tried
> this and hit a wall? — a gap can be open because the field gave up.
> (2) Would this be a new capability, or an extension of existing work? —
> a descriptive lens, NOT a quality judgment; an extension can be well
> worth doing. A candidate that failed Gate 1 is not assessed here.*

- **<candidate> — has the field hit a wall here?** <plain answer +
  evidence; cite the paper(s).>
- **<candidate> — new capability or extension?** <plain answer +
  one-sentence justification.>

## Gate 3 — Is it feasible?

> *The scorecard carries the verdict; here is the data/resource detail.
> Front-loaded: feasibility must be known BEFORE the research framework is
> built. Per assessed candidate, in plain words: what is needed, is it
> public, what does it cost, how long to obtain — and the binding
> constraint. A candidate that failed an earlier gate is not assessed.*

- **<candidate> — what it needs:** <data / resources — public? cost? lead
  time?>
- **<candidate> — the binding constraint:** <the one item that decides the
  timeline.>

## The decision is yours

> *State explicitly that the dossier stops here. It has assembled the three
> gate verdicts; whether a gap is WORTH doing is the researcher's and
> advisor's call. Per candidate, name the outcome in plain words and the
> conditions the human must resolve before committing. For each candidate
> that is "worth pursuing only if its conditions hold", give an explicit
> upgrade / kill test — the finding that would make it a clear go, and the
> finding that would make it not worth pursuing.*

The three gates above are assembled evidence, not a verdict. A topic is
worth pursuing only if all three pass — open AND a contribution AND
feasible; if any gate fails, do not pursue it as stated. **Whether
<Candidate N> is worth pursuing is your and your advisor's decision.**
<Per-candidate: the plain-language outcome, and the conditions to resolve
first.>

**Upgrade / kill test — <conditional candidate>.** It becomes clearly
**worth pursuing** if <the findings that resolve every open condition
favourably>. It is **not worth pursuing as stated** if <the finding that
would fail any gate — e.g. the recall re-run surfaces a paper already
occupying the gap, or the binding resource proves unobtainable>.

---

## Appendix A — How this dossier was produced

> *All tool / pipeline / API mechanics live here, out of the reader's way.*

| Item | Detail |
|---|---|
| Pipeline | research-hub `search --adversarial --screen --json` → `literature-triage-matrix` → gap-to-topic gates |
| Recall mechanics | <N query phrasings, M unique papers; which backends ran; any rate-limited / unavailable and the effect on recall confidence. The `--screen` relevance gate: retrieved / on-topic / screened-out counts.> |
| Tool / version | <research-hub plugin version, run date, caveats — e.g. set `SEMANTIC_SCHOLAR_API_KEY` for tighter recall> |

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

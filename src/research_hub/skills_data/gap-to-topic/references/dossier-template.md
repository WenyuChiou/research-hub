# Reference — the topic-decision dossier (blank template)

> The shape `gap-to-topic` emits to `.research/topic_dossier.md`. Each `>`
> italic note is that section's contract — what it must contain. The dossier
> is a thinking tool: surface uncertainty, do not polish it away.
>
> **Reader-first rules** (the dossier is for a researcher, not for the
> pipeline): lead with the answer; name every candidate in plain words; state
> each gate verdict in plain language *before* the evidence; keep all tool /
> API / pipeline mechanics out of the body — they live in Appendix A. Formal
> enum tokens (`partially-occupied`, `borderline`, …) belong in the
> `.gaps.yml` companion, not the prose — gloss them in the body.

---

# Topic Decision Dossier — <topic area>

## Bottom line

> *2–4 sentences, plain language, no jargon. What was evaluated, the verdict
> for each named candidate (go / no-go / conditional), and the single most
> important caveat. A reader must get the answer here without reading on.*

<e.g. "Two candidate topics were evaluated. **<Candidate 1 name>** is a
no-go — the gap is already taken. **<Candidate 2 name>** is a conditional
go — it is open and feasible, but rests on a medium-confidence search and
one published caution. Whether to pursue it is your and your advisor's
call.">

| Field | Value |
|---|---|
| Area | <the research area> |
| Compiled | <YYYY-MM-DD> |
| Verdict grade | Screening-grade — assembles evidence; does NOT decide worth |

> *This dossier is a thinking tool, not a polished report. It runs each
> candidate through a 3-gate test — open AND a contribution AND feasible. A
> candidate that fails any gate is a no-go. The "is it worth doing" call is
> handed back to the researcher and advisor.*

## The candidates

> *1–N candidates, articulated WITH the researcher (Socratic — never
> invented). Each gets a short readable NAME as its heading. State its
> opening type in plain words: a method-limitation opening (an existing
> method cannot do X) or an unoccupied-application opening (no one has
> applied a capability to a domain). The machine id (`G1`, `G2`, …) is
> noted once, parenthetically — it is a tag for the `.gaps.yml` companion,
> not the reader's label.*

### Candidate 1 — "<readable name>"

<one-sentence statement of the candidate>. This is an
<unoccupied-application opening | method-limitation opening>. *(Machine id:
`G1`.)*

### Candidate 2 — "<readable name>"

<...>

## Gate 1 — Is the gap still open?

> *Verdict FIRST, per candidate, in plain words. Then the evidence: the
> closest prior work, and a one-sentence recall-confidence headline (how
> much to trust "open"). The complete reference list is the `.bib`
> companion; the structured comparison is `literature_matrix.md`. How the
> search was run belongs in Appendix A, not here. "Absent from my corpus" is
> never proof of "open".*

- **Candidate 1 — <plain verdict>.** <e.g. "Occupied — the gap is already
  taken." one-sentence why.>
- **Candidate 2 — <plain verdict>.** <e.g. "Open, with medium confidence.">

**Closest prior work:** <the papers that bear on whether each gap is filled
— readable prose, real citations; full list in the `.bib`.>

**Recall confidence:** <one plain sentence — e.g. "Medium: one search
backend was unavailable, so a missed paper is possible; re-check before
relying on an 'open' verdict.">

## Gate 2 — Would it be a real contribution?

> *Per candidate, two plain-language questions. (1) Has the field already
> tried this and hit a wall? — a gap can be open because the field gave up.
> (2) Would this be a new capability, or an extension of existing work? —
> a descriptive lens, NOT a quality judgment; an extension can be well worth
> doing. Gloss any verdict in plain words; the formal token goes to
> `.gaps.yml`. A candidate that already failed Gate 1 is not assessed here.*

- **Candidate <n> — has the field hit a wall here?** <plain answer +
  evidence; cite the paper(s).>
- **Candidate <n> — new capability or extension?** <plain answer +
  one-sentence justification.>

## Gate 3 — Is it feasible?

> *Front-loaded: feasibility must be known BEFORE the research framework is
> built, before money is spent. Per candidate, in plain words: what data /
> resources are needed, are they public, what do they cost, how long to
> obtain. End with a plain verdict (feasible / feasible with effort /
> blocked). A candidate that failed an earlier gate is not assessed.*

- **Candidate <n> — what it needs:** <data / resources — public? cost? lead
  time?>
- **Candidate <n> — feasibility:** <plain verdict + the binding constraint.>

## The decision is yours

> *State explicitly that the dossier stops here. It has assembled the three
> gate verdicts; whether a gap is WORTH doing is the researcher's and
> advisor's call. List, per candidate, the gate outcomes and any conditions
> the human must resolve before committing.*

The three gates above are assembled evidence, not a verdict. A go requires
all three to pass (open AND a contribution AND feasible); any gate failing
is a no-go. **Whether <Candidate N> is worth pursuing is your and your
advisor's decision.** <Per-candidate: the gate outcomes, and the conditions
to resolve first.>

---

## Appendix A — How this dossier was produced

> *All tool / pipeline / API mechanics live here, out of the reader's way.*

- **Pipeline:** research-hub `search --adversarial --json` →
  `literature-triage-matrix` → gap-to-topic gates.
- **Recall mechanics:** <N query phrasings searched, M unique papers;
  which backends ran; any that were rate-limited / unavailable and the
  effect on recall confidence.>
- **Tool / version context:** <research-hub plugin version, run date, any
  caveats — e.g. set `SEMANTIC_SCHOLAR_API_KEY` for tighter recall.>

## Appendix B — Companion files

### `<dossier>.bib`

The Gate 1 reference list as BibTeX — the trust artifact that lets the
researcher verify "open" independently. Built from the
`search --adversarial --json` metadata (NOT from `cite --format bibtex`,
which resolves only already-ingested Zotero items — see SKILL.md §1
step 3). Every entry must have a resolvable DOI or arXiv ID.

### `<dossier>.gaps.yml`

Structured export of the candidates + their gate verdicts + open questions,
so a later pass (or a downstream skill) can list every candidate and its
standing. This file keeps the machine ids and the formal enum tokens.

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

# Reference — the topic-decision dossier (blank template)

> The shape `gap-to-topic` emits to `.research/topic_dossier.md`. Each `>`
> italic note is that section's contract — what it must contain. The dossier
> is a thinking tool: surface uncertainty, do not polish it away.
>
> **Reader-first rules** (the dossier is for a researcher, not for the
> pipeline): lead with the answer; name every candidate in plain words; put
> the gate verdicts in the **Decision scorecard** table so the whole 3-gate
> test is scannable at a glance; keep all tool / API / pipeline mechanics out
> of the body — they live in Appendix A. Formal enum tokens
> (`partially-occupied`, `borderline`, …) belong in the `.gaps.yml`
> companion, not the prose — gloss them in the body.

---

# Topic Decision Dossier — <topic area>

## Bottom line

> *2–4 sentences of plain-language prose — what was evaluated and the
> verdict for each named candidate — followed by the Decision scorecard
> table. A reader must get the whole answer here without reading on.*

<e.g. "Two candidate topics were evaluated. **<Candidate 1 name>** is a
no-go — the gap is already taken. **<Candidate 2 name>** is a conditional
go — open and feasible, but it rests on a medium-confidence search and one
published caution. Whether to pursue it is your and your advisor's call.">

### Decision scorecard

> *Candidates × the 3 gates + the verdict. Cell convention: `✓` = passes,
> `✗` = fails, `~` = borderline / qualified, `—` = not assessed (a
> candidate that already failed an earlier gate). Each cell pairs the glyph
> with one plain word. The Verdict column: No-go / Conditional go / Go.*

| Candidate | Gate 1 · Open? | Gate 2 · A contribution? | Gate 3 · Feasible? | Verdict |
|---|---|---|---|---|
| 1 · <name> | <✓/✗/~ + word> | <✓/~/— + word> | <✓/~/✗/— + word> | **<No-go / Conditional go / Go>** |
| 2 · <name> | … | … | … | **…** |

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
> invented). List them in the roster table, then give a one-sentence
> statement per candidate. Each candidate has a short readable name; the
> machine id (`G1`, `G2`, …) is a tag for the `.gaps.yml` companion, not
> the reader's label. Opening type: a method-limitation opening (an
> existing method cannot do X) or an unoccupied-application opening (no one
> has applied a capability to a domain).*

| # | Candidate | Opening type | id |
|---|---|---|---|
| 1 | <readable name> | <unoccupied-application / method-limitation> opening | `G1` |
| 2 | <readable name> | … | `G2` |

**1 · <name>** — <one-sentence statement of the candidate>.

**2 · <name>** — <…>

## Gate 1 — Is the gap still open?

> *The verdict is in the Decision scorecard; this section is the EVIDENCE
> behind it. Give the closest prior work (readable prose, real citations —
> full list in the `.bib`), and a one-sentence recall-confidence headline
> (how much to trust "open"). How the search was run belongs in Appendix A.
> "Absent from my corpus" is never proof of "open".*
>
> *Tag each cited work by evidence type — primary study / review / close
> analogue / caution paper / conference abstract / preprint / data
> artifact — and end with a one-sentence evidence-mix summary. The reader
> must see how solid the occupancy signal is without opening
> `literature_matrix.md`: an "occupied" verdict resting mostly on
> conference abstracts is weaker than one resting on primary studies.*

**Closest prior work:** <the papers that bear on whether each gap is filled
— readable prose, each tagged by evidence type, e.g. "Smith 2024 (primary
study)", "Jones 2026 (conference abstract)". Full list in the `.bib`,
structured comparison in `literature_matrix.md`.>

**Evidence mix:** <one sentence — e.g. "Of the 9 papers on Candidate 1:
4 primary studies, 1 review, 3 conference abstracts, 1 data artifact — the
occupancy signal is clear but partly early-stage.">

**Recall confidence:** <one plain sentence — e.g. "Medium: one search
backend was unavailable, so a missed paper is possible; re-check before
relying on an 'open' verdict.">

## Gate 2 — Would it be a real contribution?

> *The scorecard carries the verdict; here is the reasoning. Per assessed
> candidate, two plain-language questions. (1) Has the field already tried
> this and hit a wall? — a gap can be open because the field gave up.
> (2) Would this be a new capability, or an extension of existing work? —
> a descriptive lens, NOT a quality judgment; an extension can be well worth
> doing. A candidate that failed Gate 1 is not assessed here.*

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
> advisor's call. Per candidate, name the outcome and the conditions the
> human must resolve before committing. For each conditional-go candidate,
> give an explicit **upgrade / kill test** — the finding that would make it
> a clear go, and the finding that would make it a no-go — so the threshold
> logic lives in the dossier, not left for the advisor to supply.*

The three gates above are assembled evidence, not a verdict. A go requires
all three to pass (open AND a contribution AND feasible); any gate failing
is a no-go. **Whether <Candidate N> is worth pursuing is your and your
advisor's decision.** <Per-candidate: the outcome, and the conditions to
resolve first.>

**Upgrade / kill test — <conditional-go candidate>.** It becomes a clear
**go** if <the findings that would resolve every open condition favourably>.
It becomes a **no-go** if <the finding that would fail any gate — e.g. the
recall re-run surfaces a paper already occupying the gap, or the binding
resource proves unobtainable within scope>.

---

## Appendix A — How this dossier was produced

> *All tool / pipeline / API mechanics live here, out of the reader's way.*

| Item | Detail |
|---|---|
| Pipeline | research-hub `search --adversarial --json` → `literature-triage-matrix` → gap-to-topic gates |
| Recall mechanics | <N query phrasings, M unique papers; which backends ran; any rate-limited / unavailable and the effect on recall confidence> |
| Tool / version | <research-hub plugin version, run date, caveats — e.g. set `SEMANTIC_SCHOLAR_API_KEY` for tighter recall> |

## Appendix B — Companion files

| File | What it is |
|---|---|
| `<dossier>.bib` | The Gate 1 reference list as BibTeX — the trust artifact that lets the researcher verify "open" independently. Built from the `search --adversarial --json` metadata (NOT from `cite --format bibtex`, which resolves only already-ingested Zotero items — see SKILL.md §1 step 3). Every entry must have a resolvable DOI or arXiv ID. |
| `<dossier>.gaps.yml` | Structured export of the candidates + gate verdicts + open questions, so a later pass (or a downstream skill) can list every candidate and its standing. Keeps the machine ids and the formal enum tokens. Schema below. |
| `literature_matrix.md` | The structured prior-art comparison (`literature-triage-matrix` output): one row per paper — method, claim, evidence, limitation, relevance. |

```yaml
# <dossier>.gaps.yml
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

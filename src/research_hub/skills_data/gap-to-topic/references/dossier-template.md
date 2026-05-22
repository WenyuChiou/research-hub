# Reference — the §0–§4 topic-decision dossier (blank template)

> The shape `gap-to-topic` emits to `.research/topic_dossier.md`. Each `>`
> italic note is the section's contract — what it must contain. The dossier
> is a thinking tool: surface uncertainty, do not polish it away.

---

# Topic Decision Dossier — <topic area>

| Field | Value |
|---|---|
| Area | <the research area> |
| Compiled | <YYYY-MM-DD> |
| Pipeline | research-hub: `search --adversarial --json` → `literature-triage-matrix` → gap-to-topic gates |
| Verdict grade | Screening-grade — assembles evidence; does NOT decide worth |

## §0 — Candidate breakthrough point(s)

> *1–N candidates, articulated WITH the researcher (Socratic — never
> invented). Each typed: A = method-limitation opening, B = unoccupied-
> application opening. A multi-gap candidate is decomposed into gap_ids.*

- **[G1]** <one-sentence candidate> — **Type A / B**
- ...

## §1 — Gate ① — Open?

> *Is the gap genuinely unoccupied? Backed by a COMPLETE, verifiable
> reference list (real DOIs/arXiv IDs — see the `.bib` companion) and an
> adversarial-recall verdict. "Absent from my corpus" is not evidence of
> "open". The recall verdict is a headline, not a footnote.*

- **Recall verdict:** <high / medium / low> — <N query phrasings searched,
  M unique papers; from `search --adversarial --json`>
- **Closest prior work:** <papers that bear on whether the gap is filled>
- **Per-gap openness:** [G1] open / partially-occupied / occupied — ...

## §2 — Gate ② — A contribution?

> *Two parts. Dead-end history: is the gap open because the field gave up
> (a dead end), per `references/dead-end-history.md`? Contribution type:
> problem-solving vs incremental, per `references/contribution-typing.md` —
> a descriptive lens, NOT a quality verdict.*

- **[G1] dead-end status:** genuinely-open / dead-end-stale /
  dead-end-fundamental / partially-attempted — <evidence + quotes>
- **[G1] contribution type:** problem-solving / incremental / borderline —
  <justification citing evidence>

## §3 — Gate ③ — Feasible?

> *Front-loaded: feasibility must be known BEFORE building the research
> framework, before spending money and running experiments. Establish data
> / resource accessibility Socratically — public? cost? time to obtain?*

- **[G1] data / resources:** <what is needed> — <public? cost? lead time?>
- **[G1] feasibility verdict:** feasible / feasible-with-effort / blocked

## §4 — Handed back to the human

> *State explicitly that the dossier stops here. It has assembled the three
> gate-verdicts; whether the gap is WORTH doing is the researcher's and
> advisor's call.*

The three gates above are assembled evidence, not a verdict. **Whether
[G1] is worth pursuing is your and your advisor's decision.** A go
requires all three gates to pass (open AND a contribution AND feasible);
any gate failing is a no-go.

---

## Companion files

### `<dossier>.bib`

The §1 reference list as BibTeX — the trust artifact that lets the
researcher verify "open" independently. Built from the
`search --adversarial --json` metadata (NOT from `cite --format bibtex`,
which resolves only already-ingested Zotero items — see SKILL.md §1
step 3). Every entry must have a resolvable DOI or arXiv ID.

### `<dossier>.gaps.yml`

Structured export of §0 gaps + their gate verdicts + open questions, so a
later pass can list every candidate and its standing.

```yaml
dossier: <topic area>
generated: "YYYY-MM-DD"
gaps:
  - id: G1
    statement: "<candidate>"
    type: A            # A | B
    open: open         # open | partially-occupied | occupied
    dead_end_status: genuinely-open
    contribution_type: problem-solving
    feasibility: feasible
    linked_claim: null  # claims.yml C-id, only if a manuscript draft exists
open_questions:
  - id: Q1
    text: "<question the evidence could not settle>"
```

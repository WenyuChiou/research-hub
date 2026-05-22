# Reference — Dead-end history detection (gap-to-topic §2)

> Method reference for the `gap-to-topic` skill, §2 Gate ② — finding the
> "tried-but-unsolvable" history that distinguishes a real opening from a
> gap the field abandoned.

## 1. Purpose

Gate ② of the dossier asks *"is this a contribution?"* The first thing that
disqualifies a candidate gap is that it is **not actually open** — people
*tried* it and it did not work. This component finds that
**tried-but-unsolvable history** so a researcher does not commit to a gap
the field already abandoned.

It produces evidence for §2 and the §4 human verdict. It does **not** decide
"abandon this gap."

## 2. Why this is hard

A gap with no *successful* paper looks, on a normal search, identical to a
gap nobody tried. The distinguishing evidence — failed attempts — is the
hardest to retrieve (publication bias; failures hidden in *Limitations*
sections; failure is a *pattern*, not one document). So this component needs
its own retrieval discipline, separate from §1.

## 3. Input contract

| Input | Source | Shape |
|---|---|---|
| candidate gaps | gap-to-topic §0 | list of `{gap_id, statement, type: A|B}` |
| `literature_matrix` | the `literature-triage-matrix` skill → `.research/literature_matrix.md` | table: `citation, year, method, data, claim, limitation, relevance` |
| corpus | gap-to-topic §1 adversarial search | papers with retrievable abstracts + DOIs |

If `literature_matrix` is absent the component still runs on the §1 corpus
alone, at reduced confidence (recorded in the recall caveat).

## 4. Failure signals

| # | Signal | Source |
|---|---|---|
| S1 | Explicit negative-result language — "fails to", "does not generalise", "negative results", "rethinking", "when X does not work" | Titles / abstracts |
| S2 | Limitation / future-work admissions — "we were unable to", "remains an open challenge" | Limitations / Future-work sections of on-topic papers |
| S3 | Survey verdict — "despite many attempts, X remains unsolved" | Review / survey papers (highest-value: aggregates the field's verdict) |
| S5 | Temporal abandonment — papers cluster in years Y1–Y2, then activity stops | Temporal distribution of the corpus |

(Signal "S4 — citation-graph: cited but never successfully extended" is
**deferred** — see Open Question Q1. It needs a citation-graph API not
established as available; it is NOT a peer of S1–S3/S5.)

**S1 false-positive filter (required).** Failure-term language is most often
*motivational framing* — "X fails, therefore we propose Y" — not a dead-end
verdict. Rule: an S1/S2 hit counts as dead-end evidence **only if** the
failure is predicated of the **gap topic itself as a standing verdict**
(retrospective, survey, or post-mortem). If the same paper then proposes a
fix for that failure, the paper is an **attempt**, not a verdict — classify
it under §6 as an attempt and follow its outcome; do not count its intro
sentence as "the field gave up."

**S5 disambiguation (required).** Activity stopping can mean *solved*, not
*abandoned*. S5 counts as a dead-end signal **only if** S1/S2/S3 are also
present for the same gap. Temporal silence alone is never a failure signal.

## 5. Retrieval strategy + control flow

Three passes, **all always run** (no pass short-circuits another); the final
status is derived from the **union** of evidence:

1. **Failure-term queries** — gap topic × failure vocabulary (`limitations`,
   `negative result`, `fails`, `open problem`, `remains unsolved`,
   `intractable`).
2. **Survey sweep** — explicitly retrieve review / survey papers on the gap.
3. **Limitations read** — for the closest on-topic papers, read their
   *Limitations* / *Future-work* sections.

**Aggregation.** Any S1/S2/S3 evidence for a gap prevents `genuinely-open`
(minimum `partially-attempted`); a survey that explicitly engaged the
problem (S3) does so on its own. **S5 (temporal abandonment) never enters
the evidence union on its own** — per §4 it counts only when an S1/S2/S3 hit
is co-present for the same gap; an isolated S5 hit is discarded, not folded
into the union.

## 6. Classification

Per candidate gap, emit exactly one `dead_end_status`:

| Status | Rule |
|---|---|
| `genuinely-open` | No S1/S2/S3 evidence found, no survey engaged the problem. Always carries the recall caveat (§7). |
| `dead-end-fundamental` | Failure language attributes the failure to **the problem itself** (intractable / theoretical barrier / "no known approach") AND ≥2 papers or a survey concur. |
| `dead-end-stale` | Requires **both**: (a) failure language attributes the blocker to a **specific tool / method / resource** (not the problem), AND (b) that tool/method has a **documented successor in the retrieved corpus** that plausibly removes the blocker. (a) without (b) → `partially-attempted`, not stale. |
| `partially-attempted` | Attempts exist but evidence is mixed / inconclusive, or (a)-without-(b). Needs a human read. |

**Crux — `stale` vs `fundamental`.** `dead-end-stale` is the *opportunity*
case (Wenyu's type-A example: "traditional ABM cannot give agent profiles
via text" — abandoned because the *old tool* could not, reopenable by LLMs).
The two-part rule (a)+(b) is what stops every dead end from being optimistically
relabelled "stale": stale must name the *tool* as the blocker AND name a real
successor. If the successor is not in the corpus, it is not stale — it is
`partially-attempted` and the human decides.

## 7. Output schema

```yaml
dead_end_analysis:
  - gap_id: G1
    dead_end_status: dead-end-stale
    evidence:
      - paper: "<citation>"
        signal: S2
        quote: "<the failure sentence, verbatim>"
        quote_verified: true        # see §9
    revivable_by: "<dead-end-stale ONLY: a specific, real technology named
                    in the retrieved corpus that removes the blocker.
                    MUST be null for every other status, and null for
                    stale if no such technology was retrieved>"
    recall_caveat:
      failure_queries_run: 6
      corpora_searched: [arxiv, openalex, crossref]
      survey_papers_found: 2
```

`recall_caveat` is a **structured object**, never free text. `revivable_by`
must cite a real, corpus-present technology — never a hypothesised one; if
none was retrieved it is `null`.

## 8. How it renders in the dossier

The researcher does not see raw YAML. In §2 of the dossier each gap shows:
a one-line `dead_end_status` with a plain-language gloss, the verbatim
evidence quotes with citations, and — for `genuinely-open` — the recall
caveat stated as a sentence ("6 failure-term queries across 3 corpora found
no prior attempts; this is screening-grade, not proof"). `dead-end-stale`
additionally shows `revivable_by` as the opportunity line.

## 9. Honesty boundary + enforcement

- **Quote verification (required implementation step).** For every
  `evidence.quote`, the implementation MUST retrieve the source paper and
  confirm the sentence exists (fuzzy match, threshold set at implementation).
  If it cannot confirm, the evidence entry is **dropped**, not kept at lower
  confidence. `quote_verified` records the result; an unverified quote never
  ships. A rule without this step is not an honesty boundary.
- **Reports, does not decide.** Output is evidence for the §4 human verdict.
- **Absence is not proof.** `genuinely-open` always carries the structured
  recall caveat — the Segment-2 recall problem applies here too.

## 10. Multi-gap candidates

A candidate may span gaps (e.g. "LLM-based ABM for compound hazards"). §0
decomposes such a candidate into its constituent `gap_id`s; this component
runs **per gap_id**. The dossier then shows the per-gap statuses side by
side and flags divergence (e.g. one gap `genuinely-open`, another
`dead-end-fundamental`) for the human — it does not collapse them to a
single verdict.

## 11. Open questions — with v1 defaults

- **Q1 (S4 citation graph).** v1 default: **deferred** — ship S1–S3 + S5.
  Revisit if a citation-graph API is confirmed available and ≥10 real runs
  show S1–S3/S5 missing real dead ends.
- **Q2 (`stale` vs `fundamental` split).** v1 default: **keep the split** —
  the (a)+(b) rule in §6 makes it decidable, and `stale` is the highest-value
  output. Collapse only if ≥20 real runs show the rule is not reliably
  applicable.
- **Q3 (recall stopping condition).** v1 default: tie the failure-query
  budget to the §1 adversarial-search saturation signal (stop when a new
  query adds no new papers); hard cap 8 queries.

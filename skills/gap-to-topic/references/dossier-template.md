# Reference — the topic-decision dossier (blank template)

> The shape `gap-to-topic` emits to `.research/topic_dossier.md`. Each `>`
> italic note is that section's contract — what it must contain. The
> dossier is a **research-grade decision memo**: first page enables a
> decision; the body supports verification; the appendices support a re-run.
>
> **Reader-first rules** — the dossier is for a graduate student and their
> advisor. It must read top-to-bottom in Word with no decoding:
> - **No machine codes in the document.** `G1` / `G2` ids live only in
>   `.gaps.yml`.
> - **No decorative symbols.** No `✓ ✗ ~` glyphs, no `·` separators.
> - **Plain verdicts.** "Not supported as stated" /
>   "Conditional candidate — evidence still needed" / "Evidence assembled — human decision pending".
> - **Decision-first.** Page 1 is the executive summary; the body holds the
>   small set of decision-relevant tables; everything else (file list,
>   search details, automated-vs-judgement) belongs in an appendix.
> - English by default; a translated mirror goes in a sibling-language folder.

---

# Topic Decision Dossier — <topic area>

## 1. Executive Decision Summary

| Field | Value |
|---|---|
| Area | <the research area> |
| Compiled | <YYYY-MM-DD> |
| Verdict grade | Screening-grade — assembles evidence; does NOT decide worth |
| Search confidence | <high / medium / low — one phrase why> |

<One framing sentence: "N candidate topics were evaluated for <area>." Zero or
multiple justified options are valid; do not fabricate a portfolio.>

> *Verdict cards — one small 2-column table per candidate. Header row
> reads `Candidate N | <readable name>` (rendered as the card title);
> data rows are `Verdict | <plain phrase>` (the generator colour-codes
> this cell) and `Reason | <one or two sentences>`.*

| Candidate 1 | <readable name> |
|---|---|
| **Verdict** | <Not supported as stated / Conditional candidate — evidence still needed / Evidence assembled — human decision pending> |
| **Reason** | <one or two plain sentences naming a concrete piece of evidence> |

| Candidate 2 | <readable name> |
|---|---|
| **Verdict** | <…> |
| **Reason** | <…> |

**Key uncertainty.** <One line — the dominant caveat the reader must keep
in mind: recall confidence, a caution paper, or a dataset constraint.>

## 2. Candidate Definitions

> *Plain prose, no roster table. Per candidate: name + a one-sentence
> statement, then a plain "why it could be a gap" line that leads with one
> of two hypotheses — "Application coverage unresolved" (no equivalent located
> within the declared search scope) or "Specific method limitation" (an existing
> method has a source-supported limit). State local coverage / unresolved / narrow
> candidate / unsupported novelty separately. Neither label proves novelty.*

State whether the proposal improves an existing method/design or proposes a new
concept/mechanism; either route is legitimate and no paper must explicitly name
the gap. Separate sourced premises, inferences and untested expected benefits.
An unmeasured effect belongs in the research question, not in verified findings
or an automatic infeasibility verdict.

**Candidate 1 — <readable name>.** <One-sentence statement of the
candidate.> *Why it could be a gap:* <"Application coverage unresolved" /
"Specific method limitation"> — <one-sentence rationale>.

**Candidate 2 — <readable name>.** <…>

## 3. Decision Scorecards

> *Per candidate, one small 3-column table — Gate / Score / Rationale —
> with the three gates plus a Verdict row. The Likert scale: 5 = strongly
> agree, 4 = agree, 3 = neutral, 2 = disagree, 1 = strongly disagree. A
> neutral 3/5 or any unassessed gate leaves a decision unresolved. Scores are
> aids, never an automatic go/worth rule; each gate needs claim-level evidence
> and explicit uncertainty. Unknown is unassessed/null, never an invented zero.
> Hard blockers cannot be averaged away or compensated by other scores.
> The researcher and advisor decide worth. The Verdict
> row's Score cell and any "Not assessed" cells are colour-coded by the generator.*

**Candidate 1 — <readable name>**

| Gate | Score | Rationale |
|---|---|---|
| Gate 1 — Gap still open | <N/5 label> | <brief why> |
| Gate 2 — Real contribution | <N/5 label or "Not assessed"> | <brief why or "failed Gate 1"> |
| Gate 3 — Feasible | <N/5 label or "Not assessed"> | <brief why or "failed Gate 1"> |
| **Verdict** | **<plain verdict phrase>** | <overall one-liner> |

**Candidate 2 — <readable name>**

| Gate | Score | Rationale |
|---|---|---|
| Gate 1 — Gap still open | <…> | <…> |
| Gate 2 — Real contribution | <…> | <…> |
| Gate 3 — Feasible | <…> | <…> |
| **Verdict** | **<…>** | <…> |

## 4. Evidence Base

> *Three sub-blocks: the search funnel, the prior-art classification, and
> the closest prior work per candidate. The closest-prior-work bullets
> carry inline evidence-type tags (primary study, review, survey,
> perspective, caution paper, close analogue, conference abstract,
> preprint, data artifact). Full per-paper detail is in
> `literature_matrix.md`; do not duplicate it here.*

**Search funnel.** Use unknown for unavailable/truncated counts or failed paths;
do not turn paywalls, timeouts or HTTP 429 into zero results.

| Stage | Count |
|---|---|
| Retrieved (adversarial query phrasings) | <N unique papers> |
| Returned for relevance screening | <M> |
| Kept on-topic by the relevance gate | <K> |
| Selected into the prior-art corpus | <P> |

**Prior-art classification of the <P>-paper corpus.**

| By evidence type | By candidate |
|---|---|
| <e.g. 6 primary studies, 2 reviews, 1 survey, 1 perspective, 1 caution paper, 2 close analogues> | <e.g. 9 bear on Candidate 1, 4 on Candidate 2> |

**Closest prior work.**

- **Candidate 1:** <key papers, each tagged inline by evidence type> —
  <how solid the occupancy signal is>.
- **Candidate 2:** <closest analogues, each tagged> — <how thin the direct
  evidence is>.

## 5. Gate-by-Gate Assessment

> *Each gate uses the same five-field skeleton. The Score line is the
> Likert from the scorecard. Evidence summarises the corpus reading (the
> corpus itself lives in §4). Interpretation says what the score means;
> Risk names the dominant uncertainty; Action needed says what to do next.*

### Gate 1 — Gap still open

- **Score:** <N/5 label, per candidate>.
- **Evidence:** <one paragraph summarising §4's closest-prior-work read
  per candidate>.
- **Interpretation:** <what the score means — "occupied", "open", "lean
  open", etc., glossed in plain words>.
- **Risk:** <the dominant openness uncertainty — typically recall
  confidence and which backend was missing>.
- **Action needed:** <re-run the search with the missing backend; specific
  query refinements if any>.

### Gate 2 — Real contribution

- **Score:** <N/5 label or "Not assessed", per candidate>.
- **Evidence:** <what the field has already tried; any caution paper —
  named, with its content summarised>.
- **Interpretation:** <what the candidate would contribute, in one
  explicit claim — a method, a validated representation, a dataset, an
  empirical finding, or a decision-support result; the informative observation,
  derivation or comparison that can answer it and the claim it cannot establish;
  also the
  new-capability-vs-extension call>.
- **Risk:** <the kind of risk a caution paper raises: construct validity /
  ethics / representativeness / interpretability>.
- **Action needed:** <the minimum validation sketch — behaviour target,
  baseline or comparator, held-out test, the main failure mode the study
  must survive>.

### Gate 3 — Feasible

- **Score:** <N/5 label or "Not assessed", per candidate>.
- **Evidence:** <what data / resources are needed; the design-feasibility
  picture — can the baselines run, privacy / consent constraints,
  reproducibility when outputs depend on an API model; actual required variables,
  granularity, applicability, quality and access; an informative baseline and
  validation path; a minimum execution envelope and scale outline
  with a rough size / time / cost band>.
- **Interpretation:** <the binding constraint — the one item that decides
  the timeline; the proposal-vs-dissertation split>.
- **Risk:** <privacy / consent or API-model reproducibility, whichever
  binds harder>.
- **Action needed:** <identify a reusable dataset, or plan a
  primary-collection schedule; distinguish a missing enabling prerequisite from
  the study's unmeasured outcome. Revise a material mismatch, park critical
  unknowns with a bounded check, or reject only on supported negative evidence>.

## 6. Risks and Upgrade / Kill Tests

> *First a per-candidate list of the named risks; then, per conditional
> candidate, an operational upgrade / kill test (every condition written
> as a concrete artifact or result, not "credibly answer" prose); then,
> per failed candidate, a one-line salvage path.*

**Named risks.**

- **Construct-validity risk** — <how it manifests in this dossier — e.g.
  a caution paper raising whether LLM-generated behaviour faithfully
  represents real human decisions or only looks plausible>.
- **Dataset-constraint risk** — <the binding behavioural / domain dataset
  question for the conditional candidate>.
- **Novelty risk** — <borderline novelty if a weaker realised form
  already exists>.
- **Reproducibility risk** — <e.g. LLM outputs depend on an external API
  model that can change; the design must pin model versions and archive
  prompts and outputs>.

**Upgrade / kill test — <conditional candidate>.** Evidence needed before
the researcher and advisor decide whether to commit:
1. <a bounded closest-work and contrary/dead-end search with executed paths,
   relevance decisions, source/version locators, overlap and remaining difference;
   a zero-result search is never proof of complete recall or novelty>;
2. <a concrete pilot artifact — e.g. "a held-out validation result in
   which the candidate's method predicts the target at least as well as
   baseline X">;
3. <a concrete data check — e.g. "a reusable dataset is identified or a
   primary-collection schedule that fits the project timeline is in
   hand">.
Record the specific finding that defeats or narrows the candidate; failed access,
HTTP 429, truncation or unknown publication versions remain unresolved, not a
scientific failure or proof of openness. Retain counterevidence with conditions.

**Salvage path — <failed candidate>.** <One line — the narrower slice
worth a fresh look, and what specifically to re-search.>

## 7. Recommended Next Steps

> *Describe the actual options, tradeoffs and unresolved prerequisites. Zero or
> multiple justified directions are valid; do not force a rejected broad topic
> and a conditional narrower topic. Keep other useful candidates when one fails.
> Withdraw unsupported novelty without automatically deleting a useful proposal.
> For each next action say whether to revise a substantive mismatch, park an
> enabling unknown with a bounded check, or reject on supported negative evidence.
> Do not start detailed design or experiments from this report.*

<Actual disposition(s), reasons, useful alternatives and bounded next checks.>

Use only applicable reason-to-check routes:
- Missing closest/contrary evidence: bounded targeted lookup with actual results.
- The claimed increment is already realized: withdraw novelty and reposition any
  remaining useful contribution; do not only rename the proposal.
- Material/variable/granularity mismatch: check suitable alternatives or request
  a user question/scope decision; do not silently change the target.
- Resource overrun: compare a value-preserving minimum version within confirmed
  limits, or park with the unresolved resource prerequisite.
- Critical access/permission unknown: a bounded check of actual availability;
  do not present it as a confirmed failure or available resource.

<User selection: the actual prior choice if clear, or the question needed to
choose. A sole eligible `go`/`conditional-go` is not an automatic user choice.>

---

## Appendix A. Search and Screening Protocol

> *A reproducibility log — enough for a researcher to judge how far to
> trust the dossier and to re-run the search.*

| Field | Value |
|---|---|
| Search date | <YYYY-MM-DD> |
| Databases searched | <crossref, OpenAlex, arXiv, Semantic Scholar — note any rate-limited / unavailable> |
| Query families | <the adversarial query phrasings and how they were generated> |
| Number retrieved | <N unique> |
| Deduplication rule | <how duplicates were handled> |
| Inclusion criteria | <what made a paper enter the prior-art corpus> |
| Exclusion criteria | <what made a paper exclude — tangential, off-domain, etc.> |
| Screening process | <automated relevance gate and manual judgement steps, distinguished> |
| Known limitations | <recall caveats, e.g. a backend unavailable> |
| Recall confidence | <headline confidence and what to re-run for a tighter verdict> |

## Appendix B. Deliverable File List

| File | What it is | What it gives you |
|---|---|---|
| `topic_dossier.md` / `.docx` | This document — the topic-decision summary | The conditional assessment and evidence for a human decision |
| `topic_dossier.bib` | The reference list, as BibTeX | Verified identity/version or stable collection locator, with unresolved identity disclosed |
| `literature_matrix.md` | The paper-by-paper comparison table | How each retrieved paper compares — method, claim, evidence type, limitation |
| `topic_dossier.gaps.yml` | Machine-readable export | Structured data for a downstream tool or a later pass; not needed for reading |

```
en/
├── topic_dossier.md / .docx
├── topic_dossier.bib
├── literature_matrix.md
└── topic_dossier.gaps.yml
```

(A translated mirror, if produced, lives in a sibling-language folder.)

---

## Schema reference — `topic_dossier.gaps.yml` (NOT emitted in the dossier)

> The `.gaps.yml` companion is machine-readable and is **not** part of the
> human dossier above. It keeps the machine ids (`G1`, `G2`) and the formal
> enum tokens. **Downstream consumer:** `research-design-helper` (Stage 3a)
> reads the user-selected `gaps[]` entry + `open_questions[]` to pre-fill its
> Socratic dialog.

```yaml
dossier: <topic area>
generated: "YYYY-MM-DD"
run_type: "<short prose, e.g. 'gap-to-topic re-test on screened search'>"
downstream_consumer: research-design-helper   # forward-compat hook; Stage 3a reads this
recall:
  tool: research-hub search --adversarial --screen --json
  query_phrasings: 6
  unique_papers: 435
  tool_confidence: medium       # high | medium | low
  dossier_confidence: medium    # high | medium | low
  screen:                       # the fit-check BM25 relevance gate (search --screen)
    gate: fit-check BM25 relevance gate (search --screen)
    retrieved: <int>
    kept: <int>
    screened_out: <int>
    tier: cold-start            # cold-start | <other-tier>
    note: "<short prose, e.g. why the tier was chosen>"
  note: "<backend caveat e.g. semantic-scholar rate-limited (HTTP 429)>"
pipeline:                       # 4-step provenance chain
  - research-hub search --adversarial --screen --json   # §1 step 1
  - literature-triage-matrix -> literature_matrix.md     # §1 step 2 (on-topic kept:true)
  - .bib from on-topic search --json results             # §1 step 3
  - gap-to-topic gates §1-§4
gaps:
  - id: G1
    name: "<readable candidate name>"
    statement: "<candidate>"
    type: A | B                 # A = method-limitation | B = unoccupied-application
    open: open                  # open | partially-occupied | occupied | partially-attempted
    open_confidence: medium     # only if open / partially-occupied — high | medium | low
    dead_end_status: genuinely-open    # not-assessed | genuinely-open | none |
                                       # partially-attempted | full-dead-end
    dead_end_evidence: >-       # paper-grounded prose; only when status != not-assessed
      "<one-line evidence pointer with author + year + DOI>"
    contribution_type: problem-solving   # not-assessed | problem-solving |
                                         # incremental | borderline
    borderline_reason: B1       # only if contribution_type == borderline; B1 | B2 | B3
    feasibility: feasible       # not-assessed | feasible | feasible-with-effort | not-feasible
    verdict: go                 # go | conditional-go | no-go; assessment, not user selection
    verdict_reason: >-          # one-sentence summary the downstream consumer can quote
      "<short prose>"
    linked_claim: null          # claims.yml C-id, only if a manuscript draft exists
open_questions:
  - id: Q1
    text: "<question the evidence could not settle>"
```

**Refresh policy:** when the v0.3.10+ schema is intentionally extended,
the frozen handoff fixture at `tests/fixtures/topic_dossier_sample.gaps.yml`
must be updated in the same PR so the cross-skill integration test
stays meaningful.

The `.bib` companion is the Gate 1 reference list as BibTeX — built from
the on-topic `search --adversarial --screen --json` results (NOT from
`cite --format bibtex`, which resolves only already-ingested Zotero items
— see SKILL.md §1 step 3). Use verified DOI/arXiv IDs when available, or verified title/author/date and a
stable collection locator with acquisition provenance. Missing IDs remain
unresolved when identity cannot be established; they do not erase prior work.

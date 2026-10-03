---
name: gap-to-topic
description: Turn a research area into a go/no-go decision dossier for candidate thesis/proposal topics (zero or multiple justified options) — a 3-gate verdict (is the gap open? is it a contribution? is it feasible?) with the evidence laid out so the researcher can verify it. Use when the user asks "is this gap worth pursuing", "help me pick a thesis topic", "is this idea already taken", "find me a defensible research gap", "vet this research idea before I commit", or "should I do this". NOT a literature review (use `literature-triage-matrix` for a comparison matrix) and NOT a study design (use `research-design-helper` once a topic is chosen). Produces a `.research/topic_dossier.md`, a `.research/topic_dossier.docx` (Word, colour-coded), a `.bib`, and a `.gaps.yml`.
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
  (gap-to-topic assembles options for the researcher to choose; research-design-helper designs *how* after that choice).
- A narrative literature review — that's a writing task.
- Building manuscript claim memory — that's `paper-memory-builder`.

## What it produces

`.research/topic_dossier.md` and `.research/topic_dossier.docx` — a
**research-grade decision memo** in Markdown and as a colour-coded Word
document: first page enables a decision; the body supports verification; the
appendices support a re-run. Reads top-to-bottom in Word with no decoding —
no codes (`G1`/`G2` stay only in `.gaps.yml`), no decorative glyphs,
plain-language verdicts, decision-relevant tables in the body and reference /
log tables in the appendices. Verdict cells are colour-coded in the .docx
(light red / yellow / green / grey by verdict phrase, bilingual en + zh-TW).

| Section | What it covers |
|---|---|
| 1. Executive Decision Summary | metadata box; one framing sentence; **per-candidate verdict cards** (small 2-column tables, generator colour-codes the verdict cell); a one-line key uncertainty |
| 2. Candidate Definitions | per candidate, name + one-sentence statement + a plain "why it could be a gap" tag ("Application coverage unresolved" / "Specific method limitation") |
| 3. Decision Scorecards | per candidate, a small 3-column table (Gate / Score / Rationale) with the three gates rated 1–5 (Likert) plus a Verdict row; cells colour-coded by the generator |
| 4. Evidence Base | the search funnel, the prior-art classification, and the closest prior work per candidate with inline evidence-type tags |
| 5. Gate-by-Gate Assessment | each gate uses a fixed five-field skeleton: Score / Evidence / Interpretation / Risk / Action needed |
| 6. Risks and Upgrade / Kill Tests | named risks (construct validity, dataset, novelty, reproducibility); operational upgrade / kill test per conditional candidate; salvage path per failed candidate |
| 7. Recommended Next Steps | actual options and tradeoffs, reason-specific bounded next checks, and pending or explicit user choice |
| Appendix A. Search and Screening Protocol | a reproducibility log — search date, databases, query families, retrieved, dedup, inclusion / exclusion, screening, known limitations, recall confidence |
| Appendix B. Deliverable File List | the file index and the file tree |

(SKILL.md §0–§4 below are the agent's internal workflow steps; they map to
the reader-facing sections above — §0 → §2 Candidate Definitions, §1 → §3
Decision Scorecards + §4 Evidence Base + §5 Gate 1, etc.)

Plus two machine-readable companions: `<dossier>.bib` (the Gate 1 reference
list as BibTeX) and `<dossier>.gaps.yml` (structured candidates + verdicts +
open questions — keeps the machine ids and enum tokens).

When a version-bound materials/resource record is useful, optionally add
`candidate_version` to the relevant candidates and a separate
`<dossier>.direction-review.json`. This is an opt-in offline check, not a new
requirement for natural-language ideation or the ordinary dossier workflow.

The three gates organize the assessment; a supported hard failure cannot be
compensated by another score. Unassessed prerequisites remain unresolved, not a
scientific failure or automatic go. The dossier supports the human decision.

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

## Shared research contract

Use `../research-hub/references/research-protocol.md` for the user's original
constraints, information-needs/query map, closest prior work and contrary/dead-end
searches, and bounded completion. Use `../research-hub/references/source-claim-audit.md`
for actual evidence levels and version-bound source passages. Missing Hub runtime
blocks its commands/writes, not available native discovery. Preserve explicit
population/geography/date boundaries; suggested filters are not user decisions.
If these shared files are absent in a standalone install, retain these rules
and disclose any unassessed load-bearing evidence rather than implying novelty.

## Workflow

Run §0–§4 in order. Each section has a fixed contract; do not skip a gate.

### §0 — Candidate breakthrough point(s)

Socratic, like `research-design-helper`. Help the user articulate candidates
within the stated objective; zero or multiple justified options are valid. Keep
improving an existing method/design and proposing a new concept/mechanism as
equally valid routes, without a quota. A paper need not explicitly name a gap.
Separate sourced premises, inferences and proposed benefits; an unmeasured effect
is a research question, not automatic infeasibility. Retain useful replication,
validation, exploratory or simple-method options. Do **not** invent the user's
objective or constraints. For each candidate:

- **Give it a short, readable name** — it becomes the candidate's heading
  in the dossier ("The candidates" section). The `G1` / `G2` id is only a
  machine tag for the `.gaps.yml` companion; it must never be the reader's
  primary label.
- **Classify the opening type**, and write it in plain words in the dossier:
  - **Type A — method-limitation opening:** an existing method *cannot* do X
    ("traditional ABM cannot give agent profiles via text").
  - **Type B — unoccupied-application opening:** no equivalent application has been located within the declared search scope
    ("application coverage unresolved for X"). This is an openness hypothesis,
    not a literature-wide absence claim; compare closest work before narrowing it.

A multi-gap candidate is decomposed into its constituent gaps; every later
gate runs per gap.

### §1 — Gate ① — Open?

Incomplete recall is the dominant failure mode: a missed paper makes a gap
look open when it is not. So this gate is **adversarial**:

1. Map every material information need to a distinct search family and record
   planned vs executed status. Use available native tools or, when appropriate,
   run `research-hub search --adversarial --screen --json` on the gap. It
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
2. Screen candidates against the preserved scope. In CLI mode, inspect
   `results` and the relevance gate's `kept`/`reason`; in native mode, record
   actual inclusion/exclusion decisions and reasons without inventing CLI
   fields. Feed the **on-topic** works to `literature-triage-matrix` (as
   its input #0, a Markdown list of titles + DOIs / arXiv IDs) to produce
   `.research/literature_matrix.md`: the structured prior-art comparison
   (per paper — method, main claim, evidence, limitation, relevance).
   Relevance scores are screening aids, not scientific verdicts. Retain
   screened-out candidates and reasons in the log; check decision-relevant
   closest/contrary/boundary evidence before excluding it. This matrix is a **real
   workflow output** — it is what the openness judgement in step 4 and the
   §2 gates read, not an assumed pre-existing input. If a
   `literature_matrix.md` from an earlier run exists, `literature-triage-matrix`
   appends to it; if either skill is unavailable, reason directly over the
   observed candidates and record the reduced structure in the dossier.
3. Build the **reference list for the assessed scope** as the `.bib`
   companion from verified on-topic candidate metadata (CLI `results` or
   actual native observations) — this is the trust artifact; the researcher
   must be able to verify "open" themselves. Do **not** use
   `cite --format bibtex` here: `cite` resolves identifiers only against an
   already-ingested Zotero library, and at topic-selection time the
   candidate papers are not ingested. Verify supplied DOI/arXiv IDs when
   available. A missing identifier does
   not make a work nonexistent: qualitative, historical or archival sources
   can use verified title/author/date, stable collection/catalog locator and
   acquisition provenance. Unresolved identity remains explicitly unresolved;
   never drop inconvenient prior work merely because it has no DOI.
4. Record recall limits as a **headline**, not a footnote. In CLI mode,
   report available `screening_summary` counts; in native mode, report
   observed counts and tool references, leaving inaccessible payloads or
   backend totals unknown. Do not infer recall confidence from counts alone. Reason the
   per-gap openness over the step-2 matrix, comparing the closest works by
   question, population/system, method and outcome. Search failures, truncation
   or unknown native payloads are not zero-result proof of openness.

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

Both parts must also explain significance and decision relevance: who benefits,
what changes if the contribution succeeds, and why the closest alternative does
not already resolve the problem. Compare plausible alternatives, boundary
conditions, and upgrade/kill tests. A newly combined method alone is not proof
of a meaningful contribution; retained dead-end evidence may overturn optimism.

### §3 — Gate ③ — Feasible?

Front-loaded by design: the researcher must know feasibility *before*
building the research framework, before spending money and running
experiments. Socratically establish data / resource accessibility — is the
data public? what does it cost? how long to obtain? — and record a verdict.
Include data access/quality, skills/compute, time and cost, ethics/consent and
applicable approvals, execution/analysis validation, and a feasible fallback.
Do not treat unconfirmed access or permissions as available. Check actual
materials/variables, temporal or spatial granularity, applicability and quality;
a successful download is not sufficient. Specify the minimum study and a
simpler/closest baseline with an informative validation path within confirmed
resources. A missing enabling prerequisite is unknown, not a zero score or
supported failure; record a bounded next check. Hard blockers cannot be averaged
away or compensated by value. Revise substantive mismatches, park critical
unknowns, and reject only with supported negative evidence. Preserve a useful
alternative when another candidate fails, and do not silently change scope.
Use applicable reason-specific checks: missing closest/contrary evidence needs
a bounded targeted lookup; an already-realized increment needs repositioning;
a material/granularity mismatch needs suitable alternatives or a user scope
decision; a resource overrun needs a value-preserving minimum version or parking;
unconfirmed critical access needs a bounded access/permission check.

#### Optional version-bound offline check

Use `research-hub paper direction-check --dossier <dossier>.gaps.yml --review
<dossier>.direction-review.json --source-root <local-root> --json` when the caller
wants to check supplied candidate/source bindings and combined planned estimates.
It reads only the explicit local inputs, without reading Hub configuration,
calling a model/network, writing files or starting the next stage. The exact
contract is in `docs/direction-review-contract.md` in the research-hub repository;
`references/dossier-template.md` summarizes the optional companion.

- Bind each reviewed candidate with its ID, positive-integer `candidate_version`
  and canonical hash of the complete candidate. Preserve old review records when
  revising; a version or content change requires a fresh review. Never assume
  a missing legacy version is 1. Old dossiers still work in the ordinary flow.
- Record all seven kinds: `data`, `tool`, `model`, `license`, `cost`, `premise`
  and `validation-path`. Each may have multiple named checks. Distinguish
  `supported`, `contradicted`, `unknown` and `not-applicable`; supply evidence
  references for the first two, a bounded next check for unknowns and an
  applicability reason for not-applicable. Theory need not invent data/models.
- Bind evidence to actual local bytes, a concrete locator, actual material level
  and recorded publication version. Preserve existing context provenance;
  a local note is not the original full paper. An explicit `unknown` publication
  version remains unresolved metadata even if its byte hash is current.
- Declare the combined candidate scope, required resource units, components,
  estimate evidence and capacities/decision references. Add separate demands;
  count a shared component once only with explicit scope and `sharing_basis`.
  Missing sharing basis, demand or capacity leaves the relevant result unknown.
  Units stay separate; unknown is not zero. The checker cannot find omitted work.
- Read `record_status`, `binding_status`, `prerequisites` and
  `resource_estimates` together. Exit 0 means a structurally valid/current report
  completed, including reports with unknown/contradicted assessments or estimates
  over budget. It does not establish semantic support, actual runtime budget,
  scientific feasibility, human selection or execution permission.

Carry unresolved and stale items into the human discussion. If supplied totals
exceed capacity, compare a minimum version that still answers the question or
park it; do not silently change the goal, remove necessary baselines or increase
the budget. An optional check never replaces the three gates or user choice.

### §4 — Handed back to the human

The dossier ends by stating explicitly: it has assembled the three
gate-verdicts; whether the gap is *worth doing* is the researcher's and
advisor's call. The skill never makes that call. Explain actual options,
tradeoffs and reason-specific next checks without forcing a rejected/conditional
pair. An eligible `go` or `conditional-go` is an assessment, not a user choice,
even for a sole candidate. Use an actual prior selection if clear; otherwise ask
which direction to design before handing it to `research-design-helper`.
Do not invent approval or start design/experiments from a next-step suggestion.

### §4.5 — Generate .docx

After `.research/topic_dossier.md` is written, run the bundled generator to
produce the matching Word deliverable:

```bash
# From the dossier's output directory (e.g. .research/ or en/)
node /path/to/skills/gap-to-topic/scripts/dossier_to_docx.js topic_dossier [--no-toc]
```

Prerequisite: `npm install -g docx` (or `cd scripts && npm install docx` for a
local install). See `scripts/README.md` for full invocation details and the
zh-TW case.

The script produces `topic_dossier.docx` alongside the `.md`. It colour-codes
verdict cells (light red / yellow / green / grey), auto-selects font
(Microsoft JhengHei for zh-TW filenames, Arial otherwise), skips Markdown
separator rows, and inserts a TOC + page break after the first table (suppress
with `--no-toc`).

## Honesty rules

- **Never decide "worth it."** §4 is a hard boundary.
- **Quote verification:** every evidence quote in §1/§2 must be confirmed to
  exist in the cited source; an unverified quote is dropped, not downgraded.
- **Absence is not proof:** every "open" verdict carries the recall caveat.
- **Screening-grade, not systematic:** the dossier says so in §4.
- **No fabricated identifiers:** verify supplied DOI/arXiv IDs; identifier-free
  sources need explicitly verified bibliographic/acquisition provenance.

## References

- `references/dossier-template.md` — the blank reader-first dossier + companion-file schemas.
- `references/dead-end-history.md` — §2 dead-end detection method.
- `references/contribution-typing.md` — §2 contribution-type classification.

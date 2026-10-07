---
project: ""
last_updated: ""
stage: design
status: draft        # draft | reviewed | locked
source: ""           # optional — Stage 2 provenance, e.g. `topic_dossier.gaps.yml#G2`
gap_verdict: ""      # optional — frozen snapshot of <verdict> + first 60 chars of verdict_reason
placeholder_segments: []   # optional — list of segment numbers whose content is test-fit / dogfood placeholder,
                           #            NOT real Socratic dialog output. Example: [2, 3, 4] means segments 2-4
                           #            were filled by AI-generated stubs for testing the wire, not by the
                           #            researcher's actual answers. Downstream tools should refuse to gate
                           #            real research on a brief with non-empty placeholder_segments.
---

# Design brief

Keep the researcher's answers verbatim and preserve existing human edits. Use
`_TODO: <reason>_` for unresolved answers and `not-applicable: <reason>` for
genuinely inapplicable fields. No empirical, hypothesis, causal, predictive or
LLM design is required.

## 1. Research question

**Sharpened RQ** (one sentence, answerable in the relevant field):
_TODO_

**Falsification condition** (if applicable; otherwise evidence or argument
that would challenge or revise the proposed answer):
_TODO_

**Claim and time boundary** (future observation, contemporaneous difference,
mechanism, description or other claim; population, setting and period):
_TODO_

**Prospective information boundary** (where relevant: decision time,
information available then versus later, necessary outcome and observation horizon):
_TODO_

**Smallest answerable version** (question still answerable within confirmed
available resources and a justified timeline; scope reductions chosen by the user):
_TODO_

**Explicit nonclaims** (what this version cannot establish):
_TODO_

**Necessary materials and essential comparisons** (what cannot be removed
without losing the question; availability, confirmed resource limits,
remaining unknowns and bounded next checks):
_TODO_

## 2. Expected mechanism

**Causal chain or argument** (as appropriate to the claim):
_TODO: State the proposed mechanism or reasoning; explain inapplicable causal fields._

**Most uncertain step**:
_TODO_

**First step you'd bet breaks**:
_TODO_

## 3. Identifiability check

**Discriminating condition** (what experiment / data / counterfactual /
proof / interpretive evidence distinguishes the proposed answer from alternatives):
_TODO_

**Confounders or competing explanations to address**:
- _TODO_

**Missing-material plan** (if current evidence cannot discriminate, what
minimum extra material is needed, whether it is obtainable and the next check):
_TODO_

**Design-specific inference limits** (where applicable: two observation
occasions support bounded change rather than a full trajectory; vignette responses
do not alone establish observed behavior, future outcomes or real-world mechanisms):
_TODO_

## 4. Validation plan

**Success metric or assessment criterion**:
_TODO_

**Baseline or relevant comparison** (or reason it is not applicable):
_TODO_

**Matched-information comparison conditions** (candidate and comparator's
available variables, information time, data splits and planned resources;
disclose and correct asymmetry for a capability comparison. Retain extra
information only when its value is explicitly the research question):
_TODO_

**Minimum worthwhile gain** (improvement or uncertainty reduction sufficient
to change knowledge or a decision; justified quantitative threshold or qualitative
criterion. If unresolved, leave TODO; no default percentage or significance rule):
_TODO_

**Added cost and value** (incremental resources and why the worthwhile gain
would justify them; mark unconfirmed estimates and next checks):
_TODO_

**Negative control or other check** (where applicable: an expected non-gain
and the alternative explanation it tests; otherwise explain the limitation):
_TODO_

## 5. Risk register

| # | Risk | Early-warning signal | Mitigation |
|---|---|---|---|
| 1 | _TODO_ | _TODO_ | _TODO_ |
| 2 | _TODO_ | _TODO_ | _TODO_ |
| 3 | _TODO_ | _TODO_ | _TODO_ |

## Notes

**Optional direction-review provenance and limitations** (when supplied:
selected candidate ID/version, reviewed candidate-content hash and review path;
binding status or not checked, unresolved assessments and resource limits.
Missing versions stay unknown. Preserve earlier review limitations on refresh):
_TODO or not-applicable: no direction review supplied_

Record source-byte or candidate changes requiring recheck; a valid record is
not scientific approval, and within-estimate is not verified runtime spending.
Do not use these notes as a substitute for the user's choice or answers.

(Free-form. Add any other constraints, deadlines or dependencies the segments
above don't capture.)

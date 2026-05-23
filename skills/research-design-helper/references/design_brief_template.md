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

## 1. Research question

**Sharpened RQ** (one sentence, falsifiable):
_TODO_

**Falsification condition** (what would you observe if FALSE):
_TODO_

**Smallest answerable version** (1-week prototype scope):
_TODO_

## 2. Expected mechanism

**Causal chain**:
_TODO: A causes B because of C; B then affects D through E._

**Most uncertain step**:
_TODO_

**First step you'd bet breaks**:
_TODO_

## 3. Identifiability check

**Discriminating condition** (what experiment / data / counterfactual
distinguishes RQ-true from RQ-false):
_TODO_

**Confounders to rule out**:
- _TODO_

**Missing-data plan** (if current data can't discriminate, what's
the minimum extra data needed):
_TODO_

## 4. Validation plan

**Success metric**:
_TODO_

**Baseline being beaten**:
_TODO_

**Negative control** (a setup where you EXPECT the metric to NOT
improve, confirming the method isn't just noise):
_TODO_

## 5. Risk register

| # | Risk | Early-warning signal | Mitigation |
|---|---|---|---|
| 1 | _TODO_ | _TODO_ | _TODO_ |
| 2 | _TODO_ | _TODO_ | _TODO_ |
| 3 | _TODO_ | _TODO_ | _TODO_ |

## Notes

(Free-form. Add any constraints, deadlines, dependencies the segments
above don't capture.)

# `.paper/revision_history.yml` — schema and rules

## Why this file exists

`.paper/claims.yml` and `.paper/figures.yml` are point-in-time
snapshots of the manuscript's claim layer. After 3-6 revision rounds
(reviewer 1 round 1, advisor comments round 1, reviewer 2 round 1,
revision-and-resubmit, etc.) you lose the history of what changed
when. `revision_history.yml` is the audit trail.

## Schema

```yaml
revisions:
  - round: <int, 1-indexed, monotonically increasing>
    date: "<YYYY-MM-DD>"
    trigger: "<one line: what triggered this round>"
    changed_claims: ["<C-id>", ...]      # IDs from claims.yml; [] if fresh draft
    changed_figures: ["<Fig-id>", ...]   # IDs from figures.yml; [] if no figure change
    summary: "<one paragraph: substantive changes in this round>"
    # Optional fields:
    reviewer: "<Reviewer 2 round 1 / Advisor / Self-edit / Copyediting>"
    sections_touched: ["Methods 2.3", "Results 3.1", "Fig 3 caption"]
```

### Required fields per revision entry

- `round` — integer, starts at 1, increments by 1 per revision round.
- `date` — ISO 8601 date.
- `trigger` — one short line. Examples: `"Initial draft v1"`,
  `"Reviewer 2 round 1: calibration window critique"`,
  `"Advisor comments before submission"`.
- `summary` — one paragraph in plain prose describing the
  substantive changes. Not a diff; a human-readable digest.

### Optional fields

- `changed_claims` / `changed_figures` — IDs from `claims.yml` /
  `figures.yml`. `[]` is valid for the first round (everything is
  new) or rounds that only touch prose (no claim/figure changes).
- `reviewer` — categorize source of comments.
- `sections_touched` — which manuscript sections / figure captions
  saw edits.

## Rules

### Append, never overwrite

Past rounds are the audit trail. Each new round is a new list entry.
Editing or deleting a past entry should require an explicit
`# manually edited 2026-MM-DD by <name> because <reason>` comment
right above the change.

### Round numbering is paper-scoped, not journal-scoped

If you submit to journal A, get rejected, then submit to journal B —
keep numbering continuous across journals. The history reflects the
manuscript's life, not the submission outcome.

### When to create vs append

- **Create the file** the first time `paper-memory-builder` runs on
  this manuscript. Round 1 = initial draft.
- **Append a new round** every time the trigger is "we are reacting
  to feedback" — reviewer comments, advisor comments, copyediting
  back from the journal.
- **Don't append** for routine paper-memory-builder reruns where you
  only refresh `claims.yml` from a slightly tweaked manuscript.
  Save those for actual revision rounds.

### Sync with `claims.yml` / `figures.yml`

When `revision_history.yml` references a claim ID like `C4`, that ID
must exist in `claims.yml` (current snapshot). If you delete a claim
in a later round, keep the historical reference and add a status
field `dropped` to the corresponding entry in `claims.yml`. Don't
silently delete IDs.

## Example: 3-round revision

```yaml
revisions:
  - round: 1
    date: "2026-04-15"
    trigger: "Initial draft v1"
    changed_claims: []
    changed_figures: []
    summary: "First complete draft. 9 claims, 8 main figures."
  - round: 2
    date: "2026-05-02"
    trigger: "Advisor comments before submission"
    changed_claims: ["C2", "C7"]
    changed_figures: ["Fig5"]
    reviewer: "Advisor"
    sections_touched: ["Introduction", "Discussion 5.2", "Fig 5 caption"]
    summary: "Sharpened C2 to specify the calibration window. Removed C7 (advisor said it was implicit in C5). Reworked Fig 5 caption to match prose."
  - round: 3
    date: "2026-06-18"
    trigger: "Reviewer 2 round 1: pushback on ABM-CAT calibration window"
    changed_claims: ["C1", "C4"]
    changed_figures: ["Fig3"]
    reviewer: "Reviewer 2 round 1"
    sections_touched: ["Methods 2.3", "Results 3.1", "Supplementary S3"]
    summary: "Added robustness check Fig S3 covering 1990-2024 window per Reviewer 2 R1. Softened C4 wording from 'demonstrates' to 'is consistent with'. Updated C1 RMSE number to reflect re-fit on extended window."
```

## What this enables

Once `revision_history.yml` exists, `academic-writing-skills` can
answer questions like:
- "What changed since the last submission?"
- "Did I address Reviewer 2 round 1's calibration concern?"
- "Which figures have been touched in the last 2 rounds?"
without re-reading the entire manuscript history.

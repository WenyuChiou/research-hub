# `.paper/` YAML schemas

Schemas for the two main outputs of `paper-memory-builder`. The third file (`revision_history.yml`) has its own dedicated schema doc at `revision_history_schema.md` because of the append-only audit-trail rules.

## `.paper/claims.yml`

```yaml
claims:
  - id: C1
    text: "Coupled ABM-CAT reduces flood-impact RMSE by 22%."
    evidence_artifacts:
      - "outputs/E2/calibration.csv"
      - "outputs/E2/figure3.png"
    figure_or_table: ["Fig3"]
    status: "draft"          # draft | supported | rejected | gap
    risk: "Reviewer R2 may push back on calibration window."
    sentence_in_manuscript: "...we observe a 22% reduction in RMSE..."

  - id: C5
    text: "Subsidy treatment narrows the post-disaster housing-cost gap between renter and owner cohorts."
    evidence_artifacts: []
    figure_or_table: []
    status: "gap"
    gap_reason: "Claim appears in the manuscript intro but no experiment output backs it yet; flag for reviewer-response cycle."
```

**Required per claim:** `id`, `text`, `status`.

**Required when `status: gap`:** `gap_reason` (non-empty string).

**Numbering:** `C1, C2, ...` contiguous. If you regenerate, preserve human-assigned IDs — claim numbers are referenced by other tooling (`academic-writing-skills` pulls them by id).

### Anti-leakage rule (binding)

A claim with empty or absent `evidence_artifacts` MUST have
`status: gap` and a one-line `gap_reason`. Never emit such a claim as
`status: draft` or `status: supported` — that would leak an
unsupported claim into the downstream writing/audit pipeline as if it
were backed by evidence.

The valid `status` transitions are:

- `gap` → `draft` once evidence is identified (move `gap_reason` to
  `risk` if the evidence is preliminary; clear it if solid).
- `draft` → `supported` once the evidence is confirmed and the claim
  text is final.
- any → `rejected` if the claim is dropped from the manuscript (keep
  the row for audit trail; do not delete).

This contract is enforced by `scripts/check_claims_schema.py` (CI) and
the JSON Schema at `references/claims.schema.json`. If you edit
`.paper/claims.yml` by hand, run `python scripts/check_claims_schema.py
<path-to-claims.yml>` before committing.

## `.paper/figures.yml`

```yaml
figures:
  - id: "Fig1"
    file: "outputs/figures/Fig1_study_area.png"
    panels: ["a) site map", "b) gauge locations"]
    key_numbers: ["12 gauges", "1985-2024 record length"]
    supports_claims: []
    caption_in_manuscript: "Figure 1. Study area..."
```

**Required per figure:** `id`, `file`, `supports_claims` (may be `[]`).

## See also

- `revision_history_schema.md` — schema + append-only rules for `revision_history.yml`.

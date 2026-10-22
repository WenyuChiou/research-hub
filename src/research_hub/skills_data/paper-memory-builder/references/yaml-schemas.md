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

**IDs:** Use `C` followed by digits (for example `C1`, `C5`). Preserve existing IDs, including gaps in numbering; do not renumber on refresh — other tooling references them. Preserve unknown fields at both root and claim level.

### Anti-leakage rule (binding)

An active claim with empty or absent `evidence_artifacts` MUST have
`status: gap` and a non-empty `gap_reason`. Never emit such a claim as
`status: draft` or `status: supported` — that would leak an
unsupported claim into the downstream writing/audit pipeline as if it
were backed by evidence.

`status: rejected` means editorial removal, not scientific contradiction.
It permits absent or empty `evidence_artifacts` without `gap_reason`.
A `gap` may have evidence pointers but always requires `gap_reason`;
pointers alone do not prove support or justify promotion.

```yaml
claims:
  - id: C7
    text: "Previously included claim removed for manuscript scope."
    status: rejected
  - id: C12
    text: "Claim with an unresolved evidence limitation."
    evidence_artifacts: ["outputs/preliminary.csv"]
    status: gap
    gap_reason: "Pointer exists, but support for this scope is unresolved."
```

The following are editorial workflow decisions, not automatic schema transitions:

- `gap` → `draft` once evidence is identified (move `gap_reason` to
  `risk` if the evidence is preliminary; clear it if solid).
- `draft` → `supported` once the evidence is confirmed and the claim
  text is final.
- any → `rejected` if the claim is dropped from the manuscript (keep
  the row and ID for audit trail; record the reason in revision history).

Contrary scientific evidence calls for human assessment, not automatic
`rejected` status. A refresh must not resurrect editorially removed claims.
`dropped` and unknown statuses are invalid: report validation diagnostics and
leave the original file unchanged, rather than coercing statuses or deleting
fields. The validator checks structure, not evidence existence or scientific
support; it does not implement the editorial transitions above.

The structural rules are enforced by `scripts/check_claims_schema.py` (CI) and
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

### `file:` sentinel values (v0.3.16+)

For figures that have NO separable source file on disk, `file:`
accepts these documented sentinel values instead of a real path:

| Sentinel | Use when |
|---|---|
| `embedded-in-manuscript` | Figure is embedded directly inside the `.docx` / `.tex` / Word manuscript with no separable source file (typical for Word-based research workflows where figures are pasted or rendered inline). |
| `embedded-in-supporting-information` | Same as above, but for figures in the SI / Appendix manuscript file. |
| `embedded-in-presentation` | Figure originates in a `.pptx` deck (some workflows author in PowerPoint and export to manuscript). |

Downstream consumers (`academic-writing-skills` figure-text consistency
checks, future figure-archive tooling) treat sentinel values as
"present in manuscript, no separable artifact to verify
independently." This is a documented limitation, NOT a permanent
solution — a future paper-memory-builder version may add a
pre-processing step that extracts embedded figures to a
`.paper/figures/` subdir, at which point the sentinel becomes a real
path. Until then, the sentinel is the honest representation.

Example:

```yaml
figures:
  - id: "Fig2"
    file: "embedded-in-manuscript"
    panels: ["(a) baseline", "(b) intervention"]
    key_numbers: ["10-year simulation", "50 runs"]
    supports_claims: ["C1", "C4"]
    caption_in_manuscript: >-
      Figure 2. Yearly adaptation trajectories ...
```

## See also

- `revision_history_schema.md` — schema + append-only rules for `revision_history.yml`.

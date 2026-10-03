# Offline direction-review contract

`paper direction-check` validates caller-supplied records, candidate/source byte
bindings and arithmetic over supplied resource estimates. It does not assess
scientific support, novelty, actual runtime spending or human choice, and does
not authorize execution. `supported` is a supplied assessment, not a conclusion
produced by this checker.

This is optional. `paper gaps`, natural-language ideation, its writer/context
snapshot, the existing gap verdict/feasibility enums and ResearchEvidencePacket
v1 keep their existing contracts. An ordinary legacy dossier need not acquire a
review file or candidate versions. When passed to this checker, a referenced
candidate without a positive-integer version is explicitly noncurrent.

## Invocation and exit status

```bash
research-hub paper direction-check \
  --dossier topic_dossier.gaps.yml \
  --review topic_dossier.direction-review.json \
  --source-root /explicit/local/evidence-root \
  --json
```

`python -m research_hub` is the equivalent module entry point. All three paths
are required. `--json` selects a machine-readable report; without it stdout is a
short human-readable summary. No Hub configuration is read, no model or network
is called, no input/output files are written or repaired, and no next stage is
started. The caller decides whether and where to retain stdout.
`--audit-output`, available on some other commands, is unsupported here; argparse
rejects it before an audit directory can be written (usage error, exit 2).

| Exit | Meaning |
|---|---|
| `0` | A structurally valid report with current candidate/source byte bindings completed. Unknown or contradicted prerequisites and unknown or over-budget estimates can still be present. |
| `2` | Invalid input/contract or a valid record with at least one noncurrent binding. Invalid CLI arguments also use argparse's error exit. |

Never treat exit 0 as research approval, readiness, a recorded user selection or
budget approval. Read `record_status`, `binding_status`, `prerequisites` and
`resource_estimates`, and retain all limitations. In particular, a sole `go`
candidate is not a user choice.

## Dossier and candidate identity

The dossier is a UTF-8 YAML mapping with a `gaps` array. Each candidate must be a
mapping with a unique nonempty string `id`. The checker does not revalidate the
ordinary dossier's scientific verdicts or impose a new ideation schema.

The optional `gaps[].candidate_version` is a positive integer, not a boolean.
It is needed only for a current checker binding. Missing, null, noninteger or
nonpositive versions yield `missing-candidate-version` for referenced candidates;
they are never silently treated as 1. Retain legacy fixtures/reading paths.

Each reviewed candidate is identified by this exact object shape:

```json
{
  "candidate_id": "G1",
  "candidate_version": 1,
  "candidate_sha256": "<64 lowercase hexadecimal characters>"
}
```

That shape illustration contains a placeholder and is not runnable. Calculate
the hash from the **entire current candidate mapping**, including `id`, version,
statement and any other candidate fields. The Python implementation is
`research_hub.direction_review.candidate_sha256(candidate)`:

```python
hashlib.sha256(json.dumps(
    candidate, ensure_ascii=False, sort_keys=True,
    separators=(",", ":"), allow_nan=False,
).encode("utf-8")).hexdigest()
```

Values must be JSON-compatible; object keys must be strings, floats finite, and
nesting at most 50 levels under this validator. Strings and keys must contain
Unicode scalar values; escaped lone surrogates are rejected before output.
YAML aliases (including merge aliases) are not supported by this optional
checker, preventing a small alias graph from expanding into unbounded work.
Expanded validation/serialization visits at most 100,000 values. Normal
JSON/YAML candidate numbers retain the canonical hash behavior shown above;
resource decimal-token parsing does not change those candidate hashes.
No Unicode normalization or
semantic equivalence is inferred. YAML formatting/key order alone does not
change the parsed candidate hash; list order and candidate text changes do.
Do not hash the whole YAML file for `candidate_sha256`.

The full dossier and review receive separate raw-byte SHA-256 receipts in the
report. Changing G2 or dossier formatting changes that receipt but does not by
itself stale unchanged G1. Changing G1's version **or any candidate content**
stales the old G1 review, even if the author forgot to increment its version.
Preserve the old record, reassess applicability and author a new version-bound
review rather than updating a hash and assuming the old assessment still holds.

## Review JSON: exact field shapes

The review is UTF-8 JSON. Every object below requires exactly the named fields;
extra or missing fields are errors. An optional value means the field is still
present with `null` or an allowed empty array. All textual values described as
nonempty must contain a non-whitespace character; matching uses the exact
supplied strings. SHA-256 values are 64 lowercase hexadecimal characters.
Duplicate JSON/YAML object keys and duplicate IDs in their respective namespaces
are rejected. Numeric amounts accept finite nonnegative integers/floats or
`null`; booleans, negative values, NaN and infinity are rejected.

### Root

| Field | Shape and constraints |
|---|---|
| `format` | Exactly `"research-direction-review/1.0"`. |
| `candidate_refs` | Nonempty array of candidate-reference objects above, unique by `candidate_id`. This explicitly defines the reviewed combination, not selected/approved research. |
| `evidence` | Array of evidence objects below; may be empty when no check or estimate requires evidence. |
| `checks` | Array of prerequisite objects below, covering all seven kinds for every reviewed candidate. |
| `resources` | Object with exactly `requirements`, `components`, `capacities`, each an array of the shapes below. |

Every nested `candidate_ref` or member of `candidate_refs` in a component must
match an object in the root `candidate_refs` exactly. Referencing a candidate
outside this explicit scope, or supplying a different hash/version internally,
is a contract error. Other dossier candidates are not silently included.

### Evidence

| Field | Shape and constraints |
|---|---|
| `id` | Unique nonempty string within `evidence`. |
| `path` | Nonempty local path relative to `--source-root`, using `/` separators. |
| `sha256` | SHA-256 of the actual raw file bytes, not normalized/decoded text. |
| `locator` | Nonempty description of the concrete supporting location, such as a section/table/line range. The checker requires text but does not interpret or verify the location. |
| `evidence_level` | Nonempty description of the material actually read, e.g. `local-note`, `abstract`, `full-text`, `data-dictionary` or `decision-record`. This is descriptive metadata, not an enum or quality score. |
| `publication_version` | Nonempty recorded version, e.g. a known revision identifier; use `"unknown"` when unresolved. It is recorded, never verified by the checker. |

Unknown publication version does not become verified because bytes match.
`publication_version_status` in the output is `unknown` when the stripped,
case-insensitive value is `unknown`, otherwise `recorded-not-verified`. Both can
coexist with `status: current`; a consumer must retain this publication limit.

When using an existing `paper gaps` context, preserve its `note_locator`,
`note_sha256` and source observations in that original companion. The review's
`path`/`sha256` identify the actual referenced local note bytes, while `locator`
and `evidence_level` describe what was really read. Do not add unsupported
context fields to this strict object or relabel a note/summary as original full
text. A hash of a context snapshot binds only that snapshot, not unavailable
original papers. The checker neither imports nor rewrites PR144 context records.

Evidence paths reject absolute/drive paths, backslashes, colons, empty path
segments, `.` and `..`. Symlinks, junctions and reparse-point evidence components
are rejected; the source root and its ancestors are checked for links too.
Evidence must resolve to a file within the explicit root. Sources are read as
bytes, with a 64 MiB limit per source. The supplied dossier/review files are read
as UTF-8 with a 4 MiB limit each. This is local binding validation, not source
authenticity verification or a guarantee against concurrent filesystem changes.

### Prerequisite checks

| Field | Shape and constraints |
|---|---|
| `check_id` | Unique nonempty string across all checks. Use distinct IDs for distinct conditions. |
| `candidate_ref` | One exact root candidate-reference object. |
| `kind` | One of `data`, `tool`, `model`, `license`, `cost`, `premise`, `validation-path`. |
| `statement` | Nonempty description of the named condition. |
| `status` | `supported`, `contradicted`, `unknown` or `not-applicable`. |
| `evidence_refs` | Array of distinct existing evidence IDs; nonempty for `supported` and `contradicted`. |
| `reason` | Nonempty explanation; for `not-applicable`, state why the condition does not apply. |
| `next_check` | Nonempty text or null; nonempty text is required for `unknown` and should describe a bounded next check. |

Every kind needs at least one check per reviewed candidate; a kind can contain
multiple checks (e.g. several datasets, licenses or premises). Omission is not
not-applicable. Theoretical work may legitimately record data/model conditions
as not-applicable with a reason, without inventing an empirical/LLM requirement.

Supported/contradicted checks need resolvable evidence with concrete locators
and matching bytes for a current binding. If a source changes or is unavailable,
the supplied assessment remains in the report and `binding_status` is noncurrent.
Do not read the preserved assessment as newly verified support. The checker does
not judge whether a reason is scientifically sound, a next check is informative
or a passage actually supports the statement.

### Resource requirements

Each row has exactly:

| Field | Shape and constraints |
|---|---|
| `candidate_ref` | One exact root candidate-reference object; at most one requirements row per candidate. |
| `units` | Array of distinct nonempty unit strings, or null when the required resource dimensions are unknown. `[]` is allowed only when all that candidate's cost checks are `not-applicable`. |

Omitted rows are treated like null scope and reported in
`unknown_requirement_candidate_ids`. Such scope uncertainty makes every
computed demand unknown. Declare the complete required units; the checker cannot
discover unrecorded work or verify that a caller supplied a complete plan.

### Resource components

| Field | Shape and constraints |
|---|---|
| `component_id` | Unique nonempty string within components. |
| `candidate_refs` | Nonempty array of distinct, exact root candidate-reference objects to which this component applies. |
| `unit` | Nonempty unit string. It must be declared in each applicable candidate's known requirements. |
| `amount` | Finite nonnegative number or null for an unknown estimate. |
| `estimate_basis` | Nonempty explanation of the estimate, including its uncertainty. |
| `evidence_refs` | Array of distinct existing evidence IDs; nonempty whenever `amount` is a number (including zero). |
| `sharing_basis` | Nonempty explanation or null. A component applying to multiple candidates needs a stated sharing basis to contribute a resolved estimate. |

One component is summed once, even if it applies to several candidates, only
when explicit scope and sharing basis permit it. If shared work has no basis,
its ID appears in `unresolved_component_ids` and the dimension's demand/status
is unknown. Similar names or separate component IDs are never deduplicated.
The checker requires the supplied sharing explanation, but does not establish
that work is scientifically or operationally shareable.

### Capacities

| Field | Shape and constraints |
|---|---|
| `unit` | Unique nonempty unit string within capacities. |
| `amount` | Finite nonnegative number or null. |
| `decision_ref` | Nonempty reference to the actual capacity source or user/project decision. This is a recorded string, not a dereferenced/verified grant or spending authorization. |

No unit conversion or currency exchange occurs. Use consistent labels; `USD`,
`person-weeks` and `GPU-hours` remain separate dimensions. Capacity alone is not
a complete demand record. A missing capacity, null amount, missing component for
an applicable candidate/unit or missing sharing basis yields `unknown`, not zero.

For example, separate 7 and 8 person-week components with capacity 10 give
demand 15 and `exceeds-estimate`. An explicit shared component of 3 plus separate
4 and 5 gives 12, still over capacity. Removing the second candidate's estimate
does not turn the first candidate's 7 into a within-budget combined plan.

Arithmetic has explicit decimal semantics. The file reader preserves JSON
decimal tokens with `Decimal`; sums use enough precision for every aligned digit
and carry, and comparisons use exact decimals rather than an epsilon. Thus
`0.1 + 0.2` equals capacity `0.3`, while `10000000000000000.0 + 1` exceeds
capacity `10000000000000000`. Longer fractional tokens also retain their digits.
For direct Python API calls, native floats mean their shortest decimal spelling;
use `Decimal` when the caller needs to preserve a more precise decimal value.

Numeric coefficient-digit count plus absolute decimal exponent is capped at
4,096 before aggregation, avoiding pathological precision/exponent work.
Booleans, negative/non-finite quantities, and quantities/totals outside the
existing finite binary64 magnitude range are rejected; no tolerance hides an
overrun. Fractional totals may be `Decimal` in the Python result. Serialize with
`research_hub.direction_review.dumps_direction_json(result)` as the CLI does;
it writes exact JSON **number** tokens without converting them to binary floats
or quoted strings. Consumers needing exact decimal arithmetic should also parse
those tokens with a decimal-aware JSON reader.

Per-unit results are `within-estimate` when known demand is at most known
capacity, `exceeds-estimate` when larger, otherwise `unknown`. Overall resource
status is `exceeds-estimate` if any dimension exceeds, otherwise `unknown` if
any scope/dimension is unknown, otherwise `within-estimate` when totals exist,
or `not-applicable` when no dimensions exist and all scopes are explicitly known.
Even an overall exceeds result can coexist with unknown dimensions; inspect all
totals. `runtime_budget_verification` always remains `not-performed`.

## Report JSON

A valid record returns these fields:

| Field | Shape and meaning |
|---|---|
| `format` | `research-direction-check/1.0`. |
| `record_status` | `valid`; structural validation completed. |
| `binding_status` | `current` only if every listed candidate and evidence binding is current; otherwise `not-current`. Even unused evidence entries are checked. |
| `candidate_bindings` | Array of `{candidate_id, status}`; statuses are `current`, `missing-candidate`, `missing-candidate-version`, `stale-candidate`. |
| `evidence_bindings` | Array of `{evidence_id, status, expected_sha256, actual_sha256, locator, locator_verification, evidence_level, publication_version, publication_version_status}`. `actual_sha256` is null when no hash was read; `locator_verification` is always `not-performed`. |
| `prerequisites` | Copies of the supplied `checks`, including unchanged supplied status, reason and next check. |
| `resource_estimates` | `{status, totals, unknown_requirement_candidate_ids, requirements, components, capacities, runtime_budget_verification}` plus conditional `arithmetic_status` described below. The three resource input arrays are preserved unchanged, including estimate/sharing bases, evidence references and capacity decision references. |
| `semantic_assessment` | Always `not-performed`. |
| `human_selection` | Always `outside-checker`; no `selected_id` is produced. |
| `execution_authorized` | Always `false`. |
| `limitations` | String array explaining byte-binding and estimate/selection limits. |
| `input_receipts` | `{dossier_sha256, review_sha256}`, raw-byte hashes added by the file-reading API/CLI. |

Each `resource_estimates.totals` row contains `unit`, `demand` (number/null),
`capacity` (number/null), `status`, `missing_candidate_ids` and
`unresolved_component_ids`. Units and these ID arrays are sorted. Missing
candidate IDs refer to declared candidate/unit demands without a component;
unresolved component IDs refer to null amounts or missing sharing basis.

If **any** candidate/source binding is noncurrent, the resource status and every
total's status become `unknown`; their original arithmetic result is retained
as `arithmetic_status`. Numeric diagnostic demand/capacity values may remain,
but must not be consumed as a current feasibility result. The tool does not
automatically replace a stale record or modify a supplied prerequisite status.

The Python pure validator is
`validate_direction_review(dossier, review, source_root)`; the local reader is
`check_direction_review(dossier_path, review_path, source_root)`. Only the latter
adds raw input receipts. Neither produces an external action or authorization.

On a contract error, the CLI emits `{format, record_status: "invalid", error,
semantic_assessment: "not-performed", human_selection: "outside-checker",
execution_authorized: false}`. Binding/prerequisite/resource data and receipts
are absent from that invalid report; the tool reports a bounded error code
rather than echoing source contents or a traceback. Argparse usage errors happen
before the report handler and are not this JSON shape.

## Binding failures and contract errors

Evidence binding statuses are:

| Status | Meaning |
|---|---|
| `current` / `changed` | Raw bytes match / differ from supplied SHA-256. |
| `invalid-path` | Unsafe relative path form. |
| `linked-path` | A source component is a symlink/junction/reparse point. |
| `not-file` | The source exists but is not a file. |
| `unavailable` / `unreadable` | A path is missing / another read or resolution error occurred. |
| `source-too-large` | Source exceeds 64 MiB. |

These are noncurrent bindings in a structurally valid report, not new
`contradicted` scientific assessments. Invalid source roots instead produce
`source-root-linked`, `source-root-not-directory` or `source-root-unavailable`.

Other contract error codes are grouped below. Each aborts structural validation;
the code identifies the failed requirement, not a scientific disposition.

| Area | Error codes |
|---|---|
| Input/parsing | `input-unreadable`, `input-too-large`, `input-malformed`, `input-nesting-limit`, `input-node-limit`, `yaml-alias-not-supported`, `duplicate-object-key`, `non-string-object-key`, `non-scalar-unicode`, `non-json-value`, `non-finite-value`, `numeric-precision-limit` |
| Root/dossier | `review-shape`, `unsupported-review-format`, `dossier-object-required`, `dossier-gaps-required`, `dossier-candidate-invalid`, `duplicate-dossier-candidate` |
| Candidate references | `candidate-refs-required`, `candidate-scope-empty`, `candidate-ref-shape`, `candidate-id-invalid`, `candidate-version-invalid`, `candidate-hash-invalid`, `duplicate-candidate-ref`, `candidate-ref-not-in-review` |
| Evidence records | `evidence-list-required`, `evidence-shape`, `duplicate-or-invalid-evidence-id`, `evidence-hash-invalid`, `evidence-description-required`, `evidence-refs-invalid`, `evidence-ref-missing` |
| Prerequisites | `checks-list-required`, `check-shape`, `duplicate-or-invalid-check-id`, `check-kind-invalid`, `check-status-invalid`, `check-description-required`, `next-check-invalid`, `unknown-requires-next-check`, `missing-prerequisite-category` |
| Resource requirements | `resources-shape`, `requirements-list-required`, `resource-requirement-shape`, `duplicate-resource-requirement`, `required-units-invalid`, `applicable-cost-requires-units` |
| Components | `components-list-required`, `resource-component-shape`, `duplicate-or-invalid-component-id`, `resource-estimate-invalid`, `component-scope-required`, `component-scope-invalid`, `component-unit-not-declared`, `sharing-basis-invalid`, `resource-total-overflow` |
| Capacities | `capacities-list-required`, `capacity-shape`, `capacity-invalid`, `capacity-decision-ref-required` |

## Minimal complete example: unresolved, with no claimed evidence

This example is a minimal checker input, not a completed scientific dossier.
It deliberately supplies seven unknown assessments, no evidence claims and no
resource estimate. The candidate hash is real for the exact YAML candidate
below; changing any candidate content requires recalculation and reassessment.
No source hashes or scientific support are invented.

Save this as `topic_dossier.gaps.yml`:

```yaml
gaps:
  - id: G1
    candidate_version: 1
    name: Illustrative unresolved direction
    statement: Determine whether the proposed question can be answered.
    feasibility: not-assessed
    verdict: conditional-go
```

Save the following as `topic_dossier.direction-review.json`. All seven checks
explicitly bind that same complete candidate. The unknown checks are authoring
placeholders for bounded follow-up, not evidence that these conditions hold.

```json
{
  "format": "research-direction-review/1.0",
  "candidate_refs": [
    {"candidate_id": "G1", "candidate_version": 1, "candidate_sha256": "9f33414479329474ea6cd8155b54af8afa4a9a7f173182bb518581fde9599e94"}
  ],
  "evidence": [],
  "checks": [
    {
      "check_id": "G1-data", "candidate_ref": {"candidate_id": "G1", "candidate_version": 1, "candidate_sha256": "9f33414479329474ea6cd8155b54af8afa4a9a7f173182bb518581fde9599e94"},
      "kind": "data", "statement": "Required materials and granularity are identified.",
      "status": "unknown", "evidence_refs": [], "reason": "No material inventory has been supplied.",
      "next_check": "List the variables needed for this question and inspect one proposed source dictionary."
    },
    {
      "check_id": "G1-tool", "candidate_ref": {"candidate_id": "G1", "candidate_version": 1, "candidate_sha256": "9f33414479329474ea6cd8155b54af8afa4a9a7f173182bb518581fde9599e94"},
      "kind": "tool", "statement": "Necessary tools are identified.",
      "status": "unknown", "evidence_refs": [], "reason": "No tool requirements have been supplied.",
      "next_check": "List tools needed for the proposed minimum analysis and check their availability."
    },
    {
      "check_id": "G1-model", "candidate_ref": {"candidate_id": "G1", "candidate_version": 1, "candidate_sha256": "9f33414479329474ea6cd8155b54af8afa4a9a7f173182bb518581fde9599e94"},
      "kind": "model", "statement": "Any required model is identified.",
      "status": "unknown", "evidence_refs": [], "reason": "Whether a model is needed is unresolved.",
      "next_check": "Determine whether the minimum analysis requires a model and document why."
    },
    {
      "check_id": "G1-license", "candidate_ref": {"candidate_id": "G1", "candidate_version": 1, "candidate_sha256": "9f33414479329474ea6cd8155b54af8afa4a9a7f173182bb518581fde9599e94"},
      "kind": "license", "statement": "Required use permissions are known.",
      "status": "unknown", "evidence_refs": [], "reason": "No applicable permission record has been supplied.",
      "next_check": "Inspect the terms for the proposed material and planned use."
    },
    {
      "check_id": "G1-cost", "candidate_ref": {"candidate_id": "G1", "candidate_version": 1, "candidate_sha256": "9f33414479329474ea6cd8155b54af8afa4a9a7f173182bb518581fde9599e94"},
      "kind": "cost", "statement": "Necessary resource dimensions and estimates are known.",
      "status": "unknown", "evidence_refs": [], "reason": "No effort or compute estimate has been supplied.",
      "next_check": "List minimum-work resource dimensions and obtain an estimate for each."
    },
    {
      "check_id": "G1-premise", "candidate_ref": {"candidate_id": "G1", "candidate_version": 1, "candidate_sha256": "9f33414479329474ea6cd8155b54af8afa4a9a7f173182bb518581fde9599e94"},
      "kind": "premise", "statement": "The load-bearing premise has been checked.",
      "status": "unknown", "evidence_refs": [], "reason": "No premise evidence has been supplied.",
      "next_check": "State one load-bearing premise and inspect its closest supporting and contrary source."
    },
    {
      "check_id": "G1-validation", "candidate_ref": {"candidate_id": "G1", "candidate_version": 1, "candidate_sha256": "9f33414479329474ea6cd8155b54af8afa4a9a7f173182bb518581fde9599e94"},
      "kind": "validation-path", "statement": "An informative validation path is specified.",
      "status": "unknown", "evidence_refs": [], "reason": "No validation design has been supplied.",
      "next_check": "Describe a minimum informative comparison and what its result cannot establish."
    }
  ],
  "resources": {
    "requirements": [
      {"candidate_ref": {"candidate_id": "G1", "candidate_version": 1, "candidate_sha256": "9f33414479329474ea6cd8155b54af8afa4a9a7f173182bb518581fde9599e94"}, "units": null}
    ],
    "components": [],
    "capacities": []
  }
}
```

Run the command above with `--source-root .` from an existing nonlinked local
directory containing the two files. Since no evidence is claimed, it reads no
evidence file. Expected: exit 0, `record_status: valid`, `binding_status: current`,
seven preserved unknown prerequisites, `resource_estimates.status: unknown`,
empty totals and `unknown_requirement_candidate_ids: ["G1"]`. Semantic assessment
and runtime budget verification remain not performed, human selection remains
outside the checker, and execution is not authorized.

# Native research protocol v1

Use this proportionately: a quick paper lookup needs a short checklist; a
substantive review needs a compact research plan and final coverage record.
This is a shared instruction contract, not another search engine or autonomous
ledger. Keep the host's native search, reading, citation chaining, and reasoning
choices. Research Hub search/audit/source-fetch adapters remain optional.

## Preserve the actual question

1. Retain the user's objective and original constraints verbatim in the plan.
   Separate accepted decisions, unresolved material questions, and suggestions.
   Ask only about unresolved choices that change retrieval or interpretation.
2. Assign an ID to each material information need. Map each to concepts and
   synonyms, distinct search families, sources/tool paths, and screening rules.
   Rephrasing one query is not coverage of a second need. Mark queries as
   `planned`, `executed`, or `unavailable`, with actual tool/attempt references.
3. Preserve population, geography, period, method, outcome, and document-type
   boundaries. Unrestricted geography stays unrestricted. An explicit region
   is preserved without asking again; a suggested region is not a filter.
   Methodological comparators outside the target population require a transfer
   rationale and never substitute for missing topical evidence. No universal
   recent-year window, minimum paper count, backend list, or citation direction
   is implied.
4. Include topical, closest-prior-work, and contrary/boundary search paths when
   material to the user's decision. Keep screening reasons and failed attempts.
   Do not invent opposition when a contrary search finds none.

A useful compact plan is:

| Need ID / decision | User constraint / open choice | Concepts | Search family / native tool | Inclusion / exclusion | Status / observation |
|---|---|---|---|---|---|
| N1 / explain mechanism | no regional restriction | terms and synonyms | topical search | mechanism evidence | planned; no result yet |
| N2 / feasible measurement | target data available | instrument and validation terms | methods comparator | transfer rationale required | planned; no result yet |

## Select literature by contribution

Distinguish roles rather than equating fame, age, citation count, or recency:

- **Topic-core**: contribution, need IDs, decision relevance, omission effect,
  and plausible substitutes explain why this work carries the review's load
- **Closest prior work**: compare question, population/system, method, and
  outcome; identify the specific overlap and remaining difference
- **Historical classic**: record external recognition evidence when that role
  matters; an old famous but irrelevant work is not automatically topic-core
- **Method comparator / contrary / boundary**: retain applicability conditions,
  population and measurement differences, and limitations

A recent relevant paper can be both core and closest without being classic.
A method-only paper cannot fill a topical evidence gap. Opposing findings are
preserved with their conditions, not averaged into an unqualified consensus.
Use `gap-to-topic` for whether an evidenced gap warrants a meaningful, feasible
contribution; an absence in these search results is not proof of novelty.

## Bind findings and preserve versions

Read `source-claim-audit.md` before treating methods, findings, or limitations
as verified evidence. Screening from notes or abstracts is useful, but is not
full-text review. Preserve work/version and acquisition observations separately
from storage dedup. Do not collapse arXiv v1/v2, corrections, or retractions into
one current claim. Same DOI with conflicting title/year remains unresolved.

For native `papers` handoff, use the existing `source_records` list for append-only
observations: source/work/version IDs, acquisition and search references, actual
level/status, compared metadata, decision/revision references, and affected
claim IDs. Record corrections and include-to-exclude reversals with reason and
prior decision reference; mark dependent claims stale and re-review them.
Unknown versions remain unknown. Do not replace user notes or perform automatic
Zotero merges. Existing provenance merging preserves distinct observations and
exact replay; retained metadata does not establish independent verification.

## Bound completion honestly

Return a compact final record: covered and unresolved need IDs; executed paths
and observed backend/tool outcomes; screened works and assessed claims;
identity/version/access limits; contrary/boundary findings; remaining gaps;
marginal qualified yield when observable; and `continue`, `partial`, or
`bounded-complete` with rationale for the declared depth and resource bounds.

- Search success is separate from scientific coverage. Paper count, exhausted
  budget, command exit, valid source bundle, or valid packet cannot certify
  comprehensive review, novelty, adequate design, or publication readiness
- HTTP 429, timeout, paywall/login page, parse failure, truncation, and absent
  tool payload/count are failures or unknowns, never zero-result evidence
- A useful alternate source does not erase earlier failures or unmet needs
- Planned queries do not count as executed. Preserve visible native tool IDs
  and observations; do not invent hidden backend status or result counts
- Keep unassessed/unverifiable claims in the denominator. An empty denominator
  is `unavailable`, not 100%. A source/spot-check cap bounds work, not assertions
- `bounded-complete` means adequate for the explicitly declared scope with
  remaining limits disclosed. Unresolved load-bearing needs/claims require
  `partial` or continuation; superficial zero-yield rounds cannot close them

If Hub's executable is missing, do available native-only research and report
that Hub ingest/storage/NotebookLM actions are unavailable. Do not fabricate
CLI output, claim writes, or install credentials. Native research does not
itself authorize library/vault writes, costly experiments, or submission.

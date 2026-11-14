# Per-paper body summary

This is a native-host reading contract, not a new Hub task schema or semantic
validator. Use it across research domains without requiring Hub, a vault,
another account or an external model process. Reading permission does not
authorize uploads, paid calls, note updates or changing human review status.

## Read before summarizing

Preserve the user's topic, purpose, selected papers and requested depth. Verify
title/identifier and the version actually available. Distinguish a saved PDF or
publisher HTML body from an index record, abstract, search snippet or generated
summary. A source being saved does not mean it was read. Keep access failures
visible and use only permitted alternatives; never bypass an access restriction.

Read the introduction for motivation/objective, the relevant methods, results
and discussion/conclusion, and the limitations that support each important
statement. Inspect the actual table/figure, caption, supplement or correction
when the claim depends on it. A fixed first-two-pages window is not full-paper
review. State the pages/sections inspected and what remains unread. Do not call
partial body reading exhaustive full-paper review or abstract reading full text.

## Seven questions, with source support

Use these sections in readable prose; the names in parentheses are stable
semantic labels for an optional compatible handoff, not required user-authored
JSON. Keep them visible even when an answer is unknown.

1. **Why? (`why`)** The authors' motivation, problem and prior-work gap.
   Relevance to the user's project is a different judgment, not a substitute.
2. **What is the objective? (`objective`)** The question, hypothesis, tool,
   argument or comparison the authors set out to investigate.
3. **How? (`methods`)** Design, material/data, population/system, procedures,
   comparison and analysis as applicable. Describe qualitative, historical,
   theoretical and review methods on their own terms; do not invent sample sizes
   or force an experimental/statistical checklist onto every paper.
4. **What was found? (`findings`)** Actual observations, estimates, derived
   results or themes, not proposed benefits. Preserve denominators, units,
   study parts, conditions, uncertainty and comparison direction. A simulated
   scenario is not an observed intervention; model agents are not human subjects.
5. **What do the authors conclude? (`conclusions`)** Their interpretation and
   stated strength. Potential uses remain potential, not demonstrated outcomes.
6. **What should the reader retain? (`key_points`)** A short synthesis.
   Distinguish the authors' findings from the analyst's interpretation, transfer
   or recommendation. Do not quietly turn a body of mixed evidence into consensus.
7. **What is limited or unknown? (`limitations`)** Separate author-stated
   limitations, analyst scope cautions and checks not performed. Missing access
   or unreviewed supplements are unknown, not proof of absence or failure.

Attach a page, section, table/figure or other usable source locator to each
consequential statement. Quote only when needed, checking the exact passage.
Keep the work/version association and state whether the citation supports the
whole statement. Split a sentence if its supported result and analyst caution
need different statuses or evidence. For each item distinguish:

- `supported`: the reviewed source supports the stated claim at this scope;
  this is not a certification that the study or finding is scientifically true.
- `analyst_inference`: a reasoned synthesis/transfer, with its source premises
  and rationale; never relabel it as the author's result to fit an exporter.
- `unknown`: what cannot yet be established and why. It may cite a source that
  establishes the existence of unread material, without claiming that material
  has been reviewed. Do not fill missing facts with memory or a `[likely]` guess.

The source/reading footer retains title/identifier, version or explicit unknown,
the original versus derived material used, pages/sections and visual checks,
unread material, and access/correction-history limits. Preserve saved hashes
when available; do not fabricate captures, publication-version pins, timestamps,
provider/task receipts or human approval. Keep actual reading, generation and
destination states separate. An abstract-only partial summary uses the same
questions where useful but remains labeled abstract-only with its unresolved
body-level claims, not silently promoted because all seven headings are filled.

## Evidence and completion checks

Compare claims with their cited passages, not only with an abstract or an old
summary. Check meaningful counterexamples: calibration versus validation;
different denominators or subgroups; no significant difference versus
equivalence; association versus causation; observation versus model scenario;
and a result in one setting versus a universal conclusion. Apply only the checks
relevant to that study design. Retain contrary evidence and qualifiers.

Record the checked and unchecked statements against the total in scope. An
independent reader's bounded source-fidelity review is different from schema,
hash or exact-quote validation, and neither means the experiment was reproduced.
A true quote can be attached to a false conclusion; a filled-field checker
cannot decide entailment. Report unresolved load-bearing claims as partial.

Use observed time boundaries for source lookup/acquisition, reading, summary,
comparison and review when available. Separate newly acquired files from reused
files and new work identities from new versions. Report unmeasured time as
unknown; a warm single-paper pass is not a cold multi-paper performance test.

## Destination handoff

The useful result is the readable per-paper summary, not a demand for the user
to repair a schema. If a destination supports structured notes, preserve the
seven sections, source/version/reading footer, evidence links and three statuses.
If it does not, return or save the authorized readable artifact and disclose
the pending integration; do not silently drop inference/unknown or claim sync.
The current `paper-abstract-draft` path cannot receive a full-text summary merely
by relabeling it. Do not write to an existing vault or account without applicable
permission, overwrite human annotations, or claim an actual app import from a
synthetic roundtrip or a file export alone.


## Optional selected Hub handoff

Use this route only when the user has selected an existing Hub project/source
and authorized the relevant local writes. It connects an authored body summary
to the implemented Hub store and Markdown export; it does not search, extract,
run a model, verify scientific support, or grant destination permissions.
No Hub setup is required for the native readable summary above.

1. Check the installed Hub actually exposes `project native-summary-context`,
   `native-summary-import`, `native-summary-read` and `native-summary-export`.
   A package version or this skill being present does not prove availability.
   Read the [version-bound operation contract](https://github.com/WenyuChiou/research-hub/blob/e76e7ac40293592b17ba155e7f437b2f5742a7c5/docs/native-source-summary.md)
   before using it, and check that it matches the available implementation.
   If the commands or contract cannot be verified, return the readable summary
   and report Hub persistence as pending; do not silently install or upgrade.
2. Use the selected project, saved source database ID and explicitly selected
   evidence artifacts only. Obtain fresh `native-summary-context` and preserve
   its source identity, declared reading scope, revisions, hashes and selected
   Unicode ranges. Do not scan a library or treat saved bytes as fully read.
3. The agent prepares the seven-section authored envelope, not the researcher.
   Keep `supported`, `analyst_inference` and `unknown` with their reasons; bind
   quotations to the selected text and exact coordinates. Follow the contract's
   complete schema and limits, not an improvised JSON shape. Do not substitute
   `paper-abstract-draft` or change a claim's status to make an import pass.
4. Import only within authorized scope using `native-summary-import`, then
   check `native-summary-read` for the selected source. A conflict or validation
   failure is not a save: preserve the readable result, inspect the cause and
   refresh/reconcile before any retry rather than overwrite concurrent work.
   File-backed intake requires supported POSIX pinned reads; on unsupported
   platforms, report the limit without enabling BLOB storage or a path fallback.
5. When a Markdown transfer is requested, use `native-summary-export` only for
   that source. `current` permits prose; `missing`, `stale` or `unavailable` does
   not. Preserve all seven sections, source binding, support labels and
   `human_acceptance: pending` / `semantic_support: not_assessed`. Stdout or an
   authorized local file is a transfer artifact, not an Obsidian/Roam import,
   synchronization, or human acceptance. Do not upload private output without
   separate applicable authorization.

If any selected destination step is unavailable, deliver the useful readable
summary and name the pending step. Do not make the user rebuild JSON or copy
seven sections manually, and do not claim that prose delivery completed a save.

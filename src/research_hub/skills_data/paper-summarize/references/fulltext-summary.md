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

## Study-Type Summary Track

Route per-paper reading according to the nature of the work rather than forcing every source into an empirical lab-report mold:

- **Empirical Track (7-section contract)**: Experiments, observational studies, and quantitative, qualitative, or mixed empirical papers follow the seven-question contract below (`why`, `objective`, `methods`, `findings`, `conclusions`, `key_points`, `limitations`).
- **Theoretical / Conceptual / Formal / Historical Track**: Books, pure theory, formal proofs, conceptual frameworks, and historical scholarship use a five-part structure:
  1. **Core Thesis & Propositions** — central thesis, proposition, or theorem and the intellectual problem or debate it addresses.
  2. **Definitions, Concepts & Premises** — formal definitions, axioms, conceptual constructs, archival/textual corpus, and foundational premises.
  3. **Derivation, Argumentation & Mechanism** — proof strategy, logical derivation, theoretical mechanism, conceptual synthesis, or historical argument.
  4. **Scope Conditions, Assumptions & Conclusions** — boundary conditions, maintained assumptions, theoretical implications, and conclusions.
  5. **Counterexamples, Tensions & Legacy** — counterexamples, internal tensions, scholarly debates, limitations, and lasting legacy.

  Never fabricate sample sizes, empirical denominators, or experimental/statistical checklists for non-empirical works. If the user opts into the optional Hub `native-source-summary-v1` SQLite handoff, apply this deterministic slot mapping onto the seven storage fields (keeping `supported`, `analyst_inference`, and `unknown` intact):
  - `why` <- intellectual motivation and problem context from **(1) Core Thesis & Propositions**
  - `objective` <- central thesis/propositions and foundational definitions/premises from **(1) Core Thesis & Propositions** and **(2) Definitions, Concepts & Premises**
  - `methods` <- analytical/proof apparatus, axioms/corpus, and derivation or argumentation strategy from **(2) Definitions, Concepts & Premises** and **(3) Derivation, Argumentation & Mechanism** (explicitly marked non-empirical; no invented sample sizes)
  - `findings` <- proved propositions, derived mechanisms, or textual/conceptual results from **(3) Derivation, Argumentation & Mechanism**
  - `conclusions` <- scope-conditioned theoretical conclusions and implications from **(4) Scope Conditions, Assumptions & Conclusions**
  - `key_points` <- compact takeaway synthesis and legacy across **(1)–(5)**, keeping author claims separate from `analyst_inference`
  - `limitations` <- maintained assumptions, boundary conditions, counterexamples, and tensions from **(4) Scope Conditions, Assumptions & Conclusions** and **(5) Counterexamples, Tensions & Legacy**

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
   Read the [version-bound operation contract](https://github.com/WenyuChiou/research-hub/blob/38fa9128bf7c17652bd98ee3ebb37e494762d3a8/docs/native-source-summary.md)
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
   If `project native-summary-compose --help` confirms the optional preview
   command is installed, the agent can prepare only the seven sections in a
   private workspace-relative `sections.json`. Each item still has exactly
   `text`, `status`, `reason` and `evidence`. Each quote names its selected
   `artifact_id`; omit both `start`/`end` only for an exact unique literal quote.
   Save the original context result unchanged in a private `context.json`, then
   run `project native-summary-compose --root ROOT --project PROJECT
   --source-record-id DBID --context-path context.json --sections-path sections.json`.
   This emits compact import-ready JSON on stdout, without opening or writing
   the database. It does not automatically save a file or run import. With
   `--json`, inspect the wrapper's `binding: snapshot_only` and `envelope`.
   Default stdout is an authored envelope, not a saved or live-verified receipt.
   Keep output private; the agent handles authorized local file delivery, not
   manual researcher copy/paste. Do not redirect over either input file.
   Preview copies source identity, hashes, scope and revisions unchanged. It
   never refreshes a conflict. Ambiguous/missing quotes are rejected; inspect
   selected text and provide verified Unicode offsets or correct the draft,
   never pick the first occurrence or downgrade a status to pass. JSON input
   files are limited to 512 KiB for context and 256 KiB for sections, and the
   complete saved envelope must still fit 256 KiB. Preview does not establish
   current ownership, freshness or scientific support; import rechecks live
   bindings and compare-and-save revisions. If compose is absent or fails,
   retain the readable result. The agent may use the strict manual envelope
   contract when available, without shifting reconstruction to the researcher.
4. Import only within authorized scope using `native-summary-import`, then
   check `native-summary-read` for the selected source. A conflict or validation
   failure is not a save: preserve the readable result, inspect the cause and
   refresh/reconcile before any retry rather than overwrite concurrent work.
   File-backed intake and compose require supported pinned reads (POSIX or
   fixed-local-drive Windows). On unsupported platforms, report the limit
   without enabling BLOB storage or a path fallback.
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

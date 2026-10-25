# Restricted cited-paper abstract draft (backend candidate)

`paper-abstract-draft` is a Hub-owned **restricted adapter profile**, not a new
upstream skill or full execution of `paper-summarize`. It loads the existing
packaged public skill and two evidence references at commit
`f4fd94d6d2f815b37d967d7e0d861ef80c009929`, with exact file hashes recorded in each
request. It does not require copying skill files, configuring a bundle path,
installing an upstream skill, or loading ambient home-directory instructions.
Missing or changed packaged material fails closed.

## Actual stages

1. Select one registered `evidence` text artifact and one source record. The
   backend accepts `source_selection = {artifact_id, source_record_id, start,
   end}`. Offsets are **Python Unicode-character indices**, not UTF-8 bytes or
   JavaScript UTF-16 indices. A future reading UI must convert its selection.
   `.md`/`.txt` input is strict UTF-8 and at most 40,000 bytes, with no truncation.
   The operator declares the selected range an abstract; the reader does not
   verify that declaration or publication identity/version. PDFs are unsupported.
2. Read the selected bytes, check registration/source hashes, and load the exact
   packaged instruction material. Only the selected abstract and minimal source
   identity, chosen task instruction and this task's bounded revision enter the
   model/handoff payload. Unrelated project files/records never fall back into it.
3. In connected mode, the existing no-tool executor requests a bounded draft
   statement envelope. The skill's cluster CLI, retrieval, PDF reading, writes
   and approval stages are explicitly **not performed**. No CLI auto-detection,
   `summarize --apply`, hidden model retry or new provider is introduced. A
   prepared invocation manifest records actual transmitted prompt/source/skill
   hashes, not semantic success; retained transport events establish return/failure.
4. New tasks bind profile **v2** and prefer exactly `summary`, `findings`,
   `methodology`, `limitations`, each a list of at most six `{text, quote}`
   statements (sixteen total). Empty lists mean unknown. The backend finds a
   quote's **unique exact occurrence** within selected text and computes offsets;
   the model does not count characters. Absent or repeated/overlapping matches
   reject, with no fuzzy matching, Unicode/CRLF normalization or automatic retry.
   The legacy `{text, quote, start, end}` form remains strictly checked; supplied
   wrong offsets are never silently repaired. Arbitrary prose, unknown fields,
   missing bindings, changed sources and self-approval fields reject before
   candidate files exist.
5. Store owned new candidate files: `draft.md`, canonical `draft-response.json`,
   `raw-draft-response.json`, `selected-source.txt`, `binding-check.json`.
   Original sources are not edited. The receipt binds raw and canonical response
   hashes separately, records resolution-method counts and the coordinate frame
   `selected-text/python-unicode-codepoints`. Resolved rows retain `start/end`
   for source display and auditing; those are not original-file coordinates.
   Successful binding is **not entailment**: a fabricated causal explanation can
   cite a real quote, and a substring can omit negation. Semantic review stays
   pending. This receipt is a local binding check, **not** an independently
   completed `research-source-audit/1.0` assessment or publication verification.
6. Reuse existing local-human acceptance/revise/decline and current-hash delivery.
   Delivery is the existing local ZIP, not writing accepted notes into Zotero,
   Obsidian, or a new literature library. Source-aware human review is necessary;
   no independent semantic model/tool is silently called.

Handoff exports the same bounded material and an input hash; export is not
execution. `task import` accepts a `draft_response` envelope for this profile
instead of arbitrary `prose`/artifact paths. Host-produced text cannot create
trusted local execution or human-acceptance receipts.

## Local UI integration candidate

The separate VM UI increment is documented in
[workspace-abstract-draft-ui.md](workspace-abstract-draft-ui.md). It adds a bounded
existing-text preview and source-aware connected-draft path. The original backend
candidate remains independently frozen; the combined increment is not released.
No real model execution, semantic quality or browser/user acceptance is implied.

## Limits and deployment gate

- The original frozen commit is **backend/CLI foundation, not completed Hub UI
  integration**. Its generic TaskComposer did not offer this profile or source
  selection. The local UI increment uses a dedicated source-selection path;
  promotion still requires its integration review and browser validation. The UI
  must say “abstract draft; no tools/retrieval; human review pending” and return
  users to the selected source. Users must not be told to copy JSON/CLI commands
  to compensate for missing normal UI controls.
- The three instruction files total 17,901 UTF-8 bytes before source/input. No
  token/cost benefit, model-context fit or summary-quality gain is established.
  The adapter does not silently shorten them. Runtime diagnostics remain failures.
- Existing source-record identity is unverified; publication version is unknown.
  Local file hashes bind snapshots, not a publisher's authoritative version.
- Scope/hash checks are not filesystem CAS. Existing read/check/write races and
  host-runtime isolation limits are not newly solved by this profile.
- Raw model output is retained for diagnosis if format/binding fails. It is not
  a completed/accepted candidate, and no automatic retry is performed.
- Fake executors and synthetic human transports in tests exercise boundaries,
  never demonstrate actual model use, source quality or scientific approval.

Before promotion: independent source/diff review, wheel resource verification,
UI source-selection/label/return-path integration, and authorized real execution
plus independent source fidelity review. No prompt benchmark is substituted for
those gates.

## Profile revision compatibility

The existing upstream skill/reference versions stay fixed; v2 is a revision of
our restricted adapter contract only. Newly prepared tasks bind the v2 manifest,
so their input/action hashes change. Existing v1 task manifests are rechecked
against the explicitly supported v1 profile and retain their original generation
instructions and strict four-field response contract. They are not silently
migrated or relabeled v2. Unknown profile versions fail closed. Old accepted
artifacts/results are not rewritten. Unique-quote resolution removes a
model-counting obligation by construction; it is not evidence of better semantic
quality or a successful model run.

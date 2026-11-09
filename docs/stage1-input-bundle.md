# Private source preparation for Stage 1

Researchers can reuse explicitly selected, pending abstract drafts without
manually locating and matching each source and response file. The offline
preparer reuses the existing batch audit and source-selection verifier. It
does not search, call a model, mark a paper reviewed, or create a native Core
handoff.

## Use

Use the same explicit task-binding manifest described in
[workspace batch audit](workspace-batch-audit.md). It contains only the selected
project/source/task IDs, workspace roots, expected source and selection hashes,
and explicit unknown/blocked rows. No library-wide scan is performed.

```bash
python -m research_hub.workspace.stage1_inputs tasks.json new-private-bundle.zip
```

The destination is a new private ZIP file; its parent must already exist, and it must be
outside every selected workspace. Symlinks and overwrite attempts are refused.
The tool uses read-only, schema-checked SQLite handles and refuses active WAL,
SHM or journal databases. It does not checkpoint or migrate them.

Each successfully prepared row contains:

- The exact selected-source UTF-8 bytes and resolved draft-response JSON, with
  hashes and byte lengths. Quotes and offsets retain their selected-text Unicode
  codepoint coordinate frame from the existing source-bound draft contract.
- Project/source/task identifiers, task input/action/draft hashes, the original
  selection range and whole-source hash, title/locator and recorded reading scope.
- Explicit pending human acceptance, unassessed scientific acceptance and
  unverified provider execution. Publication identity and version remain unknown
  when that is what the original bounded source selection records.

This copies only the selected abstract, not the entire source artifact, private
instructions, raw provider response or unrelated project records. The bundle
contains source text, source-supplied metadata (possibly private locators) and
generated draft text: keep it private. Creating it is
not permission to upload or share it.

The archive manifest retains every requested row, including unavailable inputs.
`prepared` means the selected snapshot passed integrity checks at capture time.
It does not mean Stage 1 is complete or a paper is relevant or scientifically
accepted. Invalid/stale rows export no source or draft files. Each source is
verified independently, not as an atomic snapshot of several active projects.

Exit 0 means all requested rows were prepared. Exit 1 means the manifest records
unprepared, missing or blocked rows; inspect their diagnostic codes. Exit 2
means no verified bundle completed. All writes use one exclusive-created file
descriptor, and a renamed/replaced destination is refused before success. There
are no output child-path writes or automatic ZIP extraction. The manifest is
written last; an archive without manifest.json is incomplete. An interrupted
or unverified file is not removed or overwritten automatically; select a new
destination when retrying.
The console prints only counts and boundary flags, never source text or paths.

## Native Core handoff is a separate contract

This output is `ResearchHubStage1InputBundle` version 1, **not**
AutoResearchAgent `Stage1Handoff`. `native_core_handoff=false`,
`core_admission=not_assessed`, and `stage2_execution_authorized=false` are fixed.
It carries no fabricated eligibility, confirmed user scope, coverage approval
or scientific verdict. The original full source is not copied; its hash does
not by itself establish a publication version or source availability elsewhere.

The current external consumer requires its original native provenance manifest,
handoff and trusted hashes, same-run confirmed brief, and original claim/history,
screening, coverage and version-review closure. Its explicit current-Core route
accepts records 1.1/1.2; renaming this bundle cannot provide that evidence.
See the [version-pinned consumer contract](https://github.com/WenyuChiou/AutoResearchAgent/blob/42e32cf5cc913a36bcab78834957c0214f4d10dc/plugins/auto-research-agent/cli/stage2_workflow/import_stage1.py#L343).
There is no automatic external Core importer in this change.

## Pain point and acceptance boundary

- **Who:** researchers preparing existing source-bound Hub material for a
  subsequent literature workflow.
- **Current workflow:** export/check task metadata, find selected-text and
  response files separately, then manually preserve their identity and limits.
- **Friction/evidence:** locally examined real Hub abstract-task packets did not
  match the native Stage1Handoff contract. A byte-binding pass cannot fill missing
  Core history or a confirmed research brief. That mismatch is not a paper defect.
- **Steps removed:** matching and copying selected bytes, resolved claims and
  original task identities across an explicit batch.
- **New steps/costs:** one local ZIP file and optional downstream review;
  no new package, account, model call or cloud service. This does not eliminate
  native Core intake or necessary research decisions.
- **Non-users:** existing Hub reading/summary workflows remain unchanged. The
  batch audit remains available when only a content-free integrity report is needed.
- **Acceptance:** exact source/quote bytes and hashes survive export and repeat;
  stale, cross-project, malformed and unsafe-path inputs fail closed; original
  workspaces remain unchanged. Synthetic tests prove only these mechanics. Live
  model behavior, scientific value, complete Core admission and UI usability
  require separate evidence.

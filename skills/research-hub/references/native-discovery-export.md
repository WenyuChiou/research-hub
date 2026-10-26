# Optional native Stage1 observations export

Use after or during substantive native-agent literature discovery when a durable,
inspectable handoff helps the researcher resume. Search/read/reason with the host's
actual capabilities first; this export is not the research method or a replacement
for source assessment. Follow `research-protocol.md` and `source-claim-audit.md`.
No Zotero, Obsidian, NotebookLM, Hub installation or dedicated model account is
required for native research. This optional route writes only explicitly selected
local workspace files; it never uploads to integrations or starts Stage2.

## Produce a useful Stage1 result

Preserve the user's brief and relevant scope. Map each load-bearing need to topical,
closest-work and contrary/boundary queries as appropriate, inspect returned work,
follow useful citations and refine the next query from observed gaps. Explain why
a paper matters to a need; a title list is not a relevance assessment. Record
retrievable public bibliographic locators, exact versions where known, actual
reading scope and access limits. Prefer accessible authoritative material, but do
not silently impose open-access-only selection: important restricted work remains
a lead with its access/reading limits, never falsely marked fully read.

Codex and Claude Code are hosts, not guarantees of any particular tool. Inventory
search, deep-research (if present), reading, citation and skill capabilities by
actual visible availability. Use available alternatives within authorization;
record unavailable paths without inventing successful searches. Independent source
reading remains useful when its original query receipt is absent. Do not repeat a
search merely to fill a log or convert a bibliography into historical tool events.

Alongside the readable synthesis, the agent may emit a UTF-8 JSON file with format
`research-discovery-observations/1.0`. It describes caller-observed evidence, not
cryptographically authenticated execution. The bundled schema is
`research_hub/schemas/research-discovery-observations-1.0.json`; unsupported versions
and extra fields are rejected by the optional checker. Do not add these fields to
ResearchEvidencePacket v1 or the source-audit profile.

## Exact record shape

All listed fields are required; nullable values stay explicitly null. No inferred
backend counts, source-version equivalence, user choice or scientific-ready score.

| Object | Fields |
|---|---|
| Root | `format`, `run_id`, `project_id`, `brief`, `capabilities`, `needs`, `attempts`, `sources`, `completion` |
| Capability | `name`, `kind` (search/deep-research/read/citation/skill), `availability` (available/unavailable/unknown), `observation` |
| Need | unique `id`, `text`, `families` (query-family names), `status` (covered/unresolved/not-assessed) |
| Attempt | unique `id`, `need_ids`, `kind` (search/read), nullable `tool`, `input`, `status` (planned/declared/observed/unavailable), `outcome`, nullable `result_count`, nullable `receipt` |
| Receipt | nullable `reference` (visible tool/capture locator), nullable `material`; at least one non-null |
| Material | confined relative `path`, raw-byte lowercase hex `sha256` |
| Source | unique `id`, `work_id`, `title`, `locator`, `access` (public/restricted/unavailable/unknown), `need_ids`, `relevance`, nullable `version`, `reading_level` (metadata/abstract/excerpt/full-text/unavailable), nullable `reading_ref`, nullable `material`, `attempt_ids` |
| Completion | `status` (continue/partial/bounded-complete), `reason`, `residual_need_ids` |

Attempt outcome is success/empty/partial/timeout/denied/error/unknown. Planned,
declared or unavailable attempts must retain unknown outcome and null count.
Observed attempts require a named tool and an observation reference. That reference
is caller-supplied, not independently authenticated. Failed/unknown outcomes use
null count; an observed empty search uses zero, not timeout-as-zero. Read attempts
have no search result count. A declared available tool is not a used tool.

Abstract/excerpt/full-text reading requires a recorded reading reference, which
still does not prove that reading happened or that the material supports a claim.
`reading_level` describes what was actually assessed, not merely a downloaded file.
Sources may have no attempt IDs when independently supplied/read. Need/source IDs
join exactly, never by title/DOI heuristic. Unknown publication versions remain
null. Restricted access never becomes evidence that the paper does not exist.

All unresolved needs must remain in completion. Bounded-complete cannot contain
residual needs; a covered need requires a linked observed successful/empty attempt.
These are internal consistency checks, not proof that an empty search establishes
novelty or that all required needs were included. Preserve the declared research
bounds and scientific unknowns in the readable result. No fixed literature quota.

## Optional local check, save and replay

Probe the installed interface with `research-hub project discovery-check --help`.
If absent, retain the portable JSON/readable result and report this checker route
unavailable; do not invent output or require installation to continue research.
This first optional file-bound checker/save/replay implementation requires POSIX
directory-relative no-follow primitives; Windows is currently unavailable and
fails closed. Native discovery and portable JSON export remain usable on either
host/platform; existing Hub operations are unchanged. Do not claim Windows
end-to-end acceptance from this Linux path. When supported, with files already
in the explicit selected workspace root:

```bash
research-hub project discovery-check --root ./selected-workspace --project my-project --path native-observations.json --json
research-hub project discovery-save --root ./selected-workspace --project my-project --path native-observations.json --json
research-hub project discovery-replay --root ./selected-workspace --project my-project --artifact-id RETURNED_ARTIFACT_ID --json
```

`python -m research_hub` is equivalent. Check needs no initialized Hub project or
account configuration and writes nothing. Save requires an existing project with
the same exact ID; it writes a canonical JSON snapshot under `hub-discovery/`
and registers it using the existing artifact registry. Saving is an explicit local
write, not an implicit permission granted by research. No original file is replaced,
no entire source tree copied, and no task, approval, model, provider or Stage2 runs.
Same content/scope reuses the snapshot/artifact; changed content preserves history.

The report separates structure, referenced-byte binding, `caller_observed_attempts` versus declared/planned/unavailable
attempt counts, missing source material and unknown versions. `execution_verified`
is always false, `semantic_assessment` is not-performed, and execution is not
authorized. `binding: current` means supplied material references matched when
read, not that material exists for every source: inspect `material_reference_count`
and `unbound_source_material`. `material_reference_count` counts supplied
attempt/source material references, including stale or unknown bindings, not
unique files, native calls, or verified executions. Multiple operations can refer
to one captured tool-return file: 17 references to five files count as 17, not
17 captures. Inspect each `material_bindings` entry (kind, exact ID, status);
attempt receipt captures do not substitute for original source bytes. Sources
without their own material remain in `unbound_source_material`. Native reference-only evidence remains weaker than
replayable saved bytes but is not discarded. A file hash never authenticates a
native call, source origin, complete reading or semantic entailment.

Replay rechecks the exact registered snapshot and its selected material references.
Changed/missing references return stale/unknown, not zero results or scientific
failure. Check/replay return nonzero CLI status on invalid or noncurrent binding;
zero may still include unknown versions, unbound material and partial completion.
A `registration_incomplete` result means snapshot bytes were saved but DB
registration was not confirmed. Preserve that snapshot; explicit same-input save
can reconcile without repeating search or external actions. Do not delete unknown
outcomes or claim a filesystem+database transaction.

Bounds:4MiB profile/canonical snapshot,64MiB per selected material,128MiB total
material bytes,10000 entries per array. These are processing limits, not research
coverage quotas. Traversal, linked paths, internal `.research`/`.git` material,
duplicate keys, nonfinite JSON and unsupported formats are rejected. Preserve raw
receipt files only when appropriate to the user's scope; never include credentials
or unrelated private context. Concurrent external file edits remain detectable on
later replay, not preventable by a semantic validator.


## Agent-owned handoff to the visual workspace

Do not ask the researcher to author JSON, copy receipt IDs, or enter the same
literature again. After the native research run, the agent organizes its actual
observations and captured receipts into this profile using its available file
tools. Preserve unknown/missing observations; do not invent cross-links. This
export step is agent work, not an extra researcher form.

If an already available Hub interface and supported workspace are explicitly
selected, and the existing request authorizes local saving there, use the existing
MCP `workspace_project` operation `discovery-save` with that root, project_id,
and relative profile path. The CLI route above is an alternative, not a required
user task. Do not silently install Hub, create a project, start a server, change
accounts, or widen save scope. If required location/scope is missing, ask only
for that missing choice; native-only research remains valid.

On confirmed save, return the exact `view_path` with the research summary and
remaining uncertainties. Resolve it only against the already verified Hub server
origin (never invent a URL/port). Opening it selects the exact project and saved
artifact in Literature. The read-only Stage1 view shows needs, recorded progress,
source titles/IDs, relevance, versions/access/declared reading limits, and
unknown/stale material bindings. It is not live parallel-agent telemetry or
human acceptance. Attempts sharing one tool return remain separate references,
not separate authenticated calls.

An unavailable Hub or unsupported Windows file route must not block the native
research report or become a request for manual JSON. Preserve the portable output
and state that the visual handoff is unavailable. Windows-safe saved-file access
is not yet implemented by this slice. A successful POSIX handoff is not a claim
that Codex, Claude Code, Windows, or live providers have all been validated.

Returning researchers open the same exact result link; rechecking is read-only.
A new research request may create a new immutable snapshot, never overwrite old
evidence or imply renewed authorization. No Stage2 processing or provider writes
are triggered by opening, rechecking, or closing setup guidance.

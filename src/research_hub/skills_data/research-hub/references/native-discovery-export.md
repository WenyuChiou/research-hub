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
cryptographically authenticated execution. The schema is bundled with the loaded
skill at [`references/research-discovery-observations-1.0.json`](research-discovery-observations-1.0.json).
Resolve that path relative to the directory containing the loaded `SKILL.md`, even
when working in another project. The Hub package also keeps the canonical,
byte-identical copy at `research_hub/schemas/research-discovery-observations-1.0.json`.
The optional checker rejects unsupported versions and extra fields and checks
relationships that the schema alone cannot establish. Do not add these fields to
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

## Optional standalone reader (no Hub runtime)

The agent may render already selected observations with the loaded skill's
`scripts/render_native_reader.py`. It uses only Python's
standard library; no Hub installation, account, model, network or browser is
used. Do not ask the researcher to re-enter literature. The agent prepares the
presentation files from existing, authorized observations and supplied prose.
This helper does not replace the optional native checker above: check-only
checks rendering fields, exact references and generated links, not native
execution, material-byte binding, scientific entailment or reading authenticity.
The observations format and schema remain unchanged.

Locate the actual loaded `SKILL.md` through the host's supplied skill/resource
location, then resolve `scripts/render_native_reader.py` relative to that file's
directory. Use the resulting absolute local script path with an already available
Python interpreter. For URI-backed skills, obtain the accessible local path from
the host; `skill://` is not a shell pathname. Do not guess user/cache paths or
substitute a same-named project file or unrelated checkout.

Keep the working directory at the user's selected project so the input/output
arguments below remain project-relative. Replace `<resolved-reader-script>` with
that resolved path; the quotes also cover spaces in skill locations. If the loaded
skill has no accessible helper, or the host has no existing Python runtime,
retain the native report and state that this optional renderer is unavailable;
do not silently install Hub or ask the researcher to reconstruct the data.

```text
python "<resolved-reader-script>" --observations observations.json --content-en reader.en.json --content-zh-TW reader.zh-TW.json --bibliography verified-bibliography.json --check-only
python "<resolved-reader-script>" --observations observations.json --content-en reader.en.json --content-zh-TW reader.zh-TW.json --bibliography verified-bibliography.json --output-dir new-reader-output
```

Each language file is optional. A supplied file must declare that exact
language; an absent language produces no HTML and is recorded as missing.
Without language files, only JSON/BibTeX/manifest exports are generated.
The reader presents the research brief, recorded completion and needs first,
followed by a category/work index and the source literature. Categories
are only caller-provided presentation labels, not scientific classifications
or acceptance decisions. Versions are grouped by their recorded `work_id`
without collapsing their distinct source anchors. Delivery notes remain available
in a collapsed appendix. Fixed interface labels and enumerated statuses are
localized. Caller-supplied translations may accompany original observation text;
without a supplied translation, free-text observations are labeled as original
rather than silently translated. Missing per-source prose stays visibly not
supplied. The helper neither translates nor asserts semantic parity. Original
bibliographic titles remain unchanged. All five recorded reading levels (`metadata`, `abstract`, `excerpt`,
`full-text`, `unavailable`), access limits and partial/residual needs stay visible;
restricted and abstract-only leads are retained. Nothing decides inclusion or
turns a saved body into a reading attestation.

Presentation input is a view wrapper, not a second research-evidence schema:

```json
{
  "format": "native-reader-content/1.0",
  "language": "en",
  "delivery_notes": ["Supplied cohort counts, decision boundaries and unknowns; not inferred by the renderer."],
  "records": [{
    "source_id": "S1", "work_id": "W1", "version": null,
    "reading_level": "excerpt", "reading_ref": "saved-reading:S1",
    "category": {"label": "Supplied category", "reason": "Supplied reason"},
    "summary": "Supplied prose, not generated by this renderer.",
    "limitations": ["Supplied limitation"],
    "claims": [{
      "id": "C1", "text": "Supplied claim text",
      "reading_level": "excerpt", "reading_ref": "saved-reading:S1",
      "locator": "Supplied section/page/character locator"
    }]
  }]
}
```

Content format `native-reader-content/1.0` remains supported unchanged and
rejects an `observation_translations` overlay. Format
`native-reader-content/1.1` optionally accepts this overlay for sparse,
caller-supplied translations of existing observation text. It does not replace
or alter original observations, source identities, reading scopes, needs,
completion status, or recorded scientific status. No translation or scientific
assessment is generated by the renderer.

For example, the following is an illustrative 1.1 **fragment**; include the
mandatory outer `records` array as in the 1.0 example. Replace the placeholder
hash with the SHA-256 of the exact original `--observations` file bytes, including
any UTF-8 BOM and whitespace:

```json
{
  "format": "native-reader-content/1.1",
  "language": "zh-TW",
  "records": [],
  "observation_translations": {
    "observations_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "run_id": "example-run",
    "project_id": "example-project",
    "brief": "呼叫者提供的研究簡述翻譯",
    "completion_reason": "呼叫者提供的完成原因翻譯",
    "needs": [{"id": "N1", "text": "呼叫者提供的需求翻譯"}],
    "sources": [{"source_id": "S1", "work_id": "W1", "version": null,
                 "title": "呼叫者提供的標題翻譯", "relevance": "呼叫者提供的相關性翻譯"}]
  }
}
```

The overlay requires `observations_sha256`, `run_id`, and `project_id`; run
and project must match the observations. Its target language is the enclosing
content language, which must match the requested reader language. The `brief`, `completion_reason`, `needs`, and
`sources` fields are optional and may be sparse. Each need is identified by its
existing `id`, and each source by the exact existing `source_id`, `work_id`, and
nullable `version`. Duplicate need or source entries are invalid. A source
translation entry must supply at least one of `title` or `relevance`; those are
translated text, not changes to the recorded source. Supplied translations must
be nonempty text, not null. Original text and status remain visible. SHA-256 binds an overlay to exact input bytes, not to
the authenticity of that input or the correctness, completeness, or semantic
parity of the translation. Verify supplied translations before relying on them.

The optional root `delivery_notes` array contains plain supplied text, displayed
in a collapsed appendix after the literature. Use existing recorded cohort counts,
assessment limits and unknown totals when relevant; retain work-versus-version
distinctions and overlapping categories. Notes are not computed inclusion or
reading decisions, new summaries or translations. Missing notes/languages stay
missing. Shared machine-readable count text may be copied unchanged to both
language wrappers without claiming translation parity.

The first five record fields are mandatory and join exactly to an existing
observation source/work/nullable-version and its recorded reading scope/reference.
The remaining fields are optional; category may be null, summary may be null,
and absent limitations/claims are empty. Claim fields are mandatory when a claim
is supplied. Claim IDs must be unique within each language; a shared ID across
languages must retain the same source identity, scope and locator. A claim cannot
exceed the source's reading level. Abstract/excerpt/full-text claims need a
non-null supplied locator. These checks bind presentation references; they do
not establish that the claim is supported. No referenced material is opened.

Optional bibliography input uses `format: native-reader-bibliography/1.0` or
`native-reader-bibliography/1.1` and a `records` array. Each record requires
`source_id`, `work_id`, `version`,
the unchanged source `title`, and `verification_ref` exactly equal to that
source's recorded locator or non-null reading reference. Optional fields are
`authors` (list or null), `year` (integer or null), `venue`, `doi`, and `url`
(text or null). In both versions, a supplied DOI must be nonempty text with no
disallowed control characters and must match the DOI syntax check, which also
rejects whitespace. The agent supplies only already verified metadata; the
renderer does not independently verify it. Unknown fields are omitted from BibTeX, never
inferred from a URL, title or summary. Missing bibliography yields an empty BibTeX
export. Every supplied bibliography record is retained regardless of access or
reading level. Source/work/version joins, rather than titles, produce stable
distinct anchors and BibTeX keys, including separate versions of one work.
Reader bibliography sections show the supplied authors (as display names), year,
venue, DOI and URL for each version, with missing fields marked as not supplied.
The BibTeX export contains supplied version records, not necessarily complete
citations; unknown fields can be absent. Check each citation and the imported
author formatting before reuse; no external import or acceptance is attested.

Version 1.0 continues to protect each supplied author display name as a literal
BibTeX author, but the literal-brace serialization change described below also
applies to it. Version 1.1 optionally accepts
`author_kinds` on each record: an array parallel to the supplied `authors`
array, with exactly the same length and only `person` or `literal` entries.
If `author_kinds` is present, `authors` must be an array (including an empty
array if both arrays are empty); `author_kinds: null` is invalid. When
`author_kinds` is omitted, the literal behavior is retained. This illustrative
record fragment explicitly distinguishes a person from an organization; it does
not infer classifications:

```json
{
  "authors": ["Alice Smith", "Research Organization"],
  "author_kinds": ["person", "literal"]
}
```

`literal` keeps individual protective braces; `person` emits the escaped supplied name without
those braces. The renderer does not infer person versus organization or split a
name into given and family components. A `person` value containing a standalone
BibTeX `and` author delimiter (case-insensitive, at whitespace boundaries) is
rejected: provide separate author entries or choose `literal` where appropriate.
Explicit `person` names containing either `{` or `}` are rejected, even when
the braces are balanced. Person names may contain at most two commas, and each
comma-separated component must contain at least one character that is neither
whitespace nor a hyphen; separator-only components such as `-` are unsupported.
Hyphenated names with actual text remain accepted. These are bounded syntax
checks, not name or identity verification. The caller is
responsible for providing valid BibTeX person-name syntax and checking the
imported result; the renderer does not verify the meaning or identity of a name.

Version 1.1 protects each supplied title word (Unicode letter/digit/underscore
runs) with a BibTeX case-preserving group; punctuation and whitespace remain
outside word groups. Literal-brace escape macros are isolated in their own
balanced groups, preventing them from consuming adjoining protected words in
Pandoc. This preserves supplied case without guessing which words are proper
names, while letting importers derive short titles at colons. It also
prevents ordinary sentence-case normalization; it does not infer preferred
citation-style capitalization. Version 1.0 title serialization is unchanged.
This protects supplied case, not source accuracy or compatibility with every
citation style. Imported short titles remain consumer-derived, not supplied
bibliographic metadata. Pandoc 3.1.11.1 still omits literal brace glyphs encoded
by these macros, as it does for 1.0; case protection does not promise an exact
round trip of every literal character.

For BibTeX text fields (including titles, names and venues), literal input
braces are serialized as the balanced TeX macros `\textbraceleft{}` and
`\textbraceright{}`; literal backslashes use `\textbackslash{}`. This also
changes the exported bytes for 1.0 text fields containing braces; 1.0 text
fields without braces retain their prior serialization. The JSON export preserves the
original supplied text. DOI and URL fields continue to use percent-encoding.
Synthetic BibTeX parser tests do not establish actual TeX rendering or
compatibility across citation styles. Inspect the imported and typeset result;
escaping alone is not a general guarantee of safe or correct output.

To make existing assessment/provenance sidecars and delivery instructions
discoverable, the agent may explicitly repeat `--attachment PATH` up to eight
times on either command above. Each selected file must be an ordinary single-link regular file, at most 4 MiB,
with an ASCII basename of letters, digits, dots, underscores or hyphens (starting
with a letter/digit) and a `.json`, `.md`, `.txt` or `.pdf` suffix (case-insensitive).
JSON, Markdown and text attachments must be UTF-8 without NUL. PDF attachments
are read and copied as opaque bytes; their validity, contents, language and
correspondence to a report are not verified. No PDF is generated, parsed,
translated or treated as evidence of full-text reading. PDF download links are
labeled as supplied attachments rather than verified matching-language reports. Generated-export names and case-insensitive
duplicate basenames are refused. No directory scan or automatic file selection
occurs. Attachment JSON is supporting text, not another validated evidence
schema. Copies retain their exact bytes, input/output hashes and a download link
in every supplied language reader; a missing required export link fails the
presentation check. The renderer does not interpret assessment statuses or
decide eligibility. Select only files authorized for this particular delivery;
local generation does not authorize publication of their contents.

Inputs are bounded to 4 MiB each, reject duplicate JSON keys/nonfinite values,
and must be ordinary unlinked files. Bibliographic HTTP(S) links are checked;
unsafe URL schemes are refused, and provenance references stay escaped text.
HTML and BibTeX text use the escaping described above; this does not establish
correct rendering or general safety. No scripts or remote assets are emitted.
Check-only writes nothing and does not create an output directory. Generation
requires a new output directory with an existing unlinked parent; existing
outputs, traversal and input/output overlap are refused. Each directory is a
new staged output set, incomplete until its final `manifest.json` is fully
written. If an input changes during the final recheck or generation is interrupted,
partial output files may already exist; retain the partial directory without
treating HTML file existence as completion; choose a new output set after reconciliation.

A parsed `status: complete` manifest and matching input and output hashes
establish only present artifact consistency; they do not establish that the
invocation succeeded or that `fsync` ensured durability. Record a successful
zero exit and the `status: generated` response, including its
`manifest_sha256`, separately from artifact checks. A failed or unknown
invocation outcome remains unconfirmed even if the files match. Preserve that
directory; retry using the same verified unchanged inputs in a fresh output
directory.

Outputs are `reader.en.html` and/or `reader.zh-TW.html` only for supplied
languages, `references.bib`, `native-reader.json` (original observations plus
separate presentation inputs and any selected attachment identities), selected
supporting files, and a deterministic manifest of input/output
hashes. Check local fragment/export links and manifest hashes before handing
over the exact HTML paths. Generated readers are local artifacts, not permission
to publish or upload source material. PDF generation and actual browser, assistive
technology, layout, human reading and scientific acceptance remain unverified
by the synthetic parser tests.

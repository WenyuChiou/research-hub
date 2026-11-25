---
name: research-hub
description: Operate research-hub workflows pairing your AI host's native search/reading with Zotero status checks, Obsidian cluster notes, NotebookLM briefs, and local Hub source tracking. Use when the user asks to find and organize papers, save native research to Hub, ingest PDFs, upload to NotebookLM, generate briefs, inspect clusters, or maintain a research vault. NOT for auditing or cleaning up an existing Zotero library — that's `zotero-library-curator` (read-only audit) plus `zotero-skills` (for CRUD).
---

# research-hub

research-hub is your local Stage 1–2 research workspace connecting **host-native AI discovery & reading** (Claude Code, Codex, Gemini CLI, etc.) with **Zotero**, **Obsidian**, and **NotebookLM**. Host-native research remains useful without Hub or any integration account; choose a destination before its setup or write steps.

## Runtime contract (do this first)

This skill pairs your active AI host's native capabilities with the `research-hub` runtime. Your host handles multi-round search, browsing, citation chaining, and evidence reasoning with its own native tools; `research-hub` handles deterministic ingest/storage, Zotero status tracking, Obsidian cluster organization, NotebookLM bundles, local dashboard/workspace views, and MCP/REST tools.

For native-only research, skip Hub-specific describe, doctor and setup checks; inventory host-native capabilities and follow the shared research contract below. Before running a selected Hub CLI workflow, check that interface:

```bash
research-hub describe --json
```

For Hub-only metadata, inspect `research-hub project record --help` for the installed batch interface. Use `research-hub doctor` only when setup is relevant and uncertain for a selected integration/vault workflow; missing integration credentials do not block the local metadata route in step 3.

If `research-hub` is **not found**, this executor cannot invoke that CLI route. This can happen after a skill-only install or with a different environment/PATH; it does not prove the product or another supported MCP/native interface is absent. Continue available host-native search, reading, citation chaining and evidence reasoning within the user's scope, and inventory any other supported interface before claiming overall unavailability (see [cli-workflows.md](references/cli-workflows.md) for optional setup commands).

Do **not** invent or simulate `research-hub` output if the CLI is missing. Missing CLI routes never block native-only research, comparison, topic vetting, or project/paper memory work. Default language policy: answer the user in their language, and write durable research notes, metadata, and citations in English unless asked otherwise.

## Shared research contract

Read `references/research-protocol.md` before substantive discovery and `references/source-claim-audit.md` before source-supported synthesis. Preserve the user's exact scope; map material needs to actual search paths; distinguish core/closest/classic/contrary roles; and report unresolved evidence and bounded completion. Neither a successful search nor a valid ingest certifies coverage, novelty or scientific sufficiency. Use optional source-audit sidecars only when local binding checks help; strict ResearchEvidencePacket v1 stays unchanged. For an optional portable Stage1 observation handoff and local byte-check/save, read `references/native-discovery-export.md`; native research stays useful without Hub persistence, and no Stage2 or external write is implied.

## Agent preflight protocol

For AI hosts such as Claude Code, Codex, Gemini CLI, Cursor, OpenClaw, Hermes, or generic API clients, use this sequence unless the user gives a narrower command:

1. Inventory the actual host-native search, deep-research (if present), reading, citation and relevant skill capabilities using the Stage 1 procedure in `references/research-protocol.md`. Record used versus untested/unavailable paths. Do not infer availability from the host name. For native-only research, skip Hub-specific preflight and Hub-only steps 3–7 unless a Hub operation is selected. For a selected Hub operation, check the available installed interface separately:

   ```bash
   research-hub describe --json
   ```

   Inspect `research-hub project record --help` for a Hub-only metadata save; reserve doctor/setup and credential checks for selected integration workflows.

2. If the host has native research tools and the user wants multi-round discovery, use those tools for search, browsing, citation chaining, and evidence reasoning. Follow the shared needs-to-query map and record visible tool outcomes; planned queries and unavailable payloads do not count as executed searches or zero results. For native-only research, default to readable inline bibliographic records with title, authors and year when known, source identity and locator, publication version or unknown, actual reading level and access limits. Honor the user's explicitly requested output format over this default; distinguish assessed claims from leads and unverified claims. Preserve the source and claim audit boundaries in `references/research-protocol.md` and `references/source-claim-audit.md`; do not invent missing evidence or receipts. Native-only research does not inherently require JSON or the Hub CLI.

   Prepare `papers` JSON only for a selected Hub ingest or an explicit request for that structured handoff, using the shape in `docs/papers_input_schema.md` with optional `provenance` and `source_records`. The separate `research-discovery-observations/1.0` export remains optional. Do not pass a `ResearchEvidencePacket` directly as papers input; it is a separate evidence-validation contract. This path needs neither a second agent nor a dedicated deep-search API. The agent prepares structured handoffs; the researcher should not have to author JSON to use either route.

3. Before any real ingest or metadata save, choose the requested destination:

   **Native-only research**: deliver the requested readable research result; this needs no Hub installation, JSON, integration account or destination write. Do not turn search or summarization into a Hub setup prerequisite.

   **Hub-only metadata save**: use the existing, explicitly selected root and project. The agent prepares and safely quotes SOURCE_BATCH_JSON; never ask the researcher to handwrite JSON. It is an array of source data objects, not a `papers` wrapper or ResearchEvidencePacket. Each needs a stable batch_id, upstream id, title and locator; Hub owns the separate outer record ID. Do not run doctor or setup for a Hub-only metadata save. Inspect the installed batch flags before using these examples; placeholders are filled by the agent.

   ```bash
   research-hub project record --root SELECTED_ROOT --project selected-project --kind source --batch --dry-run --data SOURCE_BATCH_JSON
   research-hub project record --root SELECTED_ROOT --project selected-project --kind source --batch --apply --data SOURCE_BATCH_JSON
   ```

   First preview, inspect the plan, and retain the same batch/source IDs and data. A dry-run does not open the root or check live storage; an optional explicitly project-bound `--existing-records` snapshot is still not live storage evidence. Only run --apply after the user has authorized this selected local metadata write. Apply reads current storage and requires an already existing project. An exact replay can reuse existing Hub IDs; a conflict rolls the entire batch back. For an uncertain Hub result, use only the identical authorized batch, not per-row legacy writes or newly invented IDs. This is not cross-batch bibliographic deduplication or a transaction across providers.

   Preserve reading_level/reading_scope, unknown versions, missing receipts and prior-batch matches. Do not promote abstract-snippet to abstract or full text. Keep identity_status=unverified and human_acceptance=pending; role candidates are not confirmed classifications. Do not turn relevance into a summary or generated prose into an original abstract. A metadata save does not verify the paper, summary, source version or actual reading; report registration and source-bound summary display remain separate existing operations. Report created/reused/conflict results honestly; Zotero, Obsidian and NotebookLM remain `not-performed`. See `docs/contracts/source-batch-handoff-preview.md`.

   **Optional external destinations**: use separate authorization and receipts for each selected destination. A Hub receipt is not a Zotero, Obsidian or NotebookLM receipt. Unattempted external writes stay `not-performed`; uncertain outcomes stay unknown and require reconciliation before retry. For a selected bibliographic ingest, inspect the configured vault and Zotero destination/collection with `research-hub doctor` only when relevant and uncertain. Its separate preview is:

   ```bash
   research-hub ingest --input ./handoff.json --cluster project-topic --dry-run
   ```

   `research-hub run --input PATH --dry-run` is also supported and leaves canonical notes, manifest, dedup index, labels, and pipeline output unchanged. Run real `ingest` or `run` only when the user has authorized those writes; host research alone does not authorize Zotero/library or vault changes.

4. Use CLI-managed literature discovery only as a headless CLI fallback when host-native search is absent or the researcher explicitly requests batch automation (see `research-hub auto` and `discover` in [cli-workflows.md](references/cli-workflows.md)):

   ```bash
   research-hub auto "TOPIC" --max-papers 3 --no-nlm
   ```

5. If NotebookLM is selected after your cluster input is ready, run its staged commands (login, bundle, upload, generate, download — each requires its own authorization and observed receipt):

   ```bash
   research-hub notebooklm bundle --cluster <slug>
   research-hub notebooklm upload --cluster <slug>
   research-hub notebooklm generate --cluster <slug> --type brief
   research-hub notebooklm download --cluster <slug>
   ```

6. For machine-readable automation, prefer `--json` flags when available, or use the MCP/REST surfaces exposed by `research-hub serve`.

## Pick The Right Entry Point

| User goal & setup | Primary host-native path |
|---|---|
| Literature search & reading only | Use host-native search/reading with [research-protocol.md](references/research-protocol.md); no Hub, JSON, or accounts needed |
| AI Host + Zotero + Obsidian + NotebookLM | **Host-native search/reading** → preview & `research-hub ingest --cluster <slug>` (sync Zotero & Obsidian) → `paper-summarize` → `notebooklm bundle/upload/generate/download` → `notebooklm-brief-verifier` |
| AI Host + Zotero + Obsidian | Host-native search/reading → `research-hub ingest` / `zotero backfill` → `paper-summarize` → `synthesize` |
| Local PDFs / files + Obsidian + NotebookLM | `research-hub import-folder <folder> --cluster <slug>` → `paper-summarize` → NotebookLM bundle/upload |
| Hub SQLite project only (no accounts) | Step 3 `project record --kind source --batch` (`--dry-run` then authorized `--apply`) + optional `native-summary-import` / `native-summary-export` |
| Headless batch CLI fallback (no host) | See [cli-workflows.md](references/cli-workflows.md) for `auto`, `discover`, `fit-check`, and maintenance commands |

Native-only research never requires Hub installation, `doctor`, integration accounts, or launching a dashboard. `research-hub dashboard --sample` and `research-hub serve --workspace` are optional inspection demos—sample data is never the user's research result.

## Core Workflows

### 1. Host-Native Search → Zotero & Obsidian Ingest

Have the host AI agent search and read accessible sources natively, prepare `papers` JSON when the user selects Hub persistence, preview with `--dry-run`, then run authorized ingest to update Zotero status and write Obsidian cluster notes:

```bash
research-hub ingest --input ./handoff.json --cluster project-topic --dry-run
research-hub ingest --input ./handoff.json --cluster project-topic
```

### 2. Per-Paper Summaries, Cluster Synthesis & NotebookLM Briefs

- **Single-paper body reading / 7-section summary:** use `paper-summarize` with host-native reading (`references/fulltext-summary.md`); in an authorized Hub SQLite project, optionally use `project native-summary-import` and `project native-summary-export` (emits generic Markdown to stdout).
- **Abstract-only note fill & synthesis:** use `paper-summarize` abstract-note mode or `research-hub synthesize --cluster project-topic`, then bundle/upload/generate with NotebookLM and audit with `notebooklm-brief-verifier`.
- **Compare & advance downstream:** pass verified clusters to `literature-triage-matrix` and `gap-to-topic`.

### 3. Secondary CLI, Maintenance & MCP Reference

See [cli-workflows.md](references/cli-workflows.md) for `auto`, `discover`/`fit-check`, `import-folder`, `crystal`, `memory`, `tidy`/`cleanup`, `research-hub install --platform {claude-code,codex,cursor,gemini}`, and STDIO MCP configuration (`research-hub serve`).

## Guardrails

- For a selected Hub CLI operation, verify runtime availability; installing `ai-research-skills` or copying `SKILL.md` does not install the Python CLI.
- Reserve `research-hub doctor` for selected, uncertain Hub integrations; native-only research needs no doctor run.
- Do not invent DOIs, citations, receipts, or paper metadata; keep unverified leads separate from source-assessed claims.
- Treat the Obsidian vault and Zotero library as user-owned data; preview writes and avoid overwriting notes or deleting clusters without reviewing cascade impact.

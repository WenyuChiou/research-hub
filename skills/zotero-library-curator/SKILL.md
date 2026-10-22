---
name: zotero-library-curator
description: Audit and curate a Zotero library — find duplicate DOIs, orphan items missing required tags, propose collection rebinds, identify bloated or under-used collections, generate tag hygiene reports, emit preview-only cleanup plans. Use when the user asks to "audit Zotero", "find duplicates", "tag hygiene report", "which collections are bloated or under-used", or "propose a Zotero cleanup plan". Defers all CRUD operations to the standalone `zotero-skills` skill or `research-hub zotero` CLI. Includes a backup-first reminder before any apply/CRUD handoff suggestion.
compatibility: Portable `SKILL.md` instructions for agentskills.io-style hosts. Depends on the standalone `zotero-skills` skill OR the `research-hub` CLI for actual Zotero connectivity. On Claude Code use the canonical marketplace plugin; on other hosts load skills/zotero-skills/SKILL.md from the resolved upstream checkout while retaining its scripts and references.
---

# zotero-library-curator

Sit one layer above the standalone `zotero-skills` skill. This skill
**reads** the Zotero library, runs **audit + hygiene checks**, and emits
**preview plans**. It does NOT perform the changes itself.

For any actual create / update / delete operation, defer to:

- The standalone **`zotero-skills`** skill (full CRUD, dual local/web API
  routing); or
- The **`research-hub zotero` CLI** (`backfill --tags --notes [--apply]`,
  etc., which is preview-first by default).

## Prerequisite check (do this first)

Reading the Zotero library requires a connection. The skill works in
two modes:

1. **Read-only audit / preview** — needs **either** `zotero-skills`
   (Zotero local API) **or** the `research-hub zotero` CLI to
   inspect items.
2. **Apply cleanup** — must defer to `zotero-skills` or
   `research-hub zotero ... --apply`.

Before running, verify at least one runtime is present. Loading a skill's
instructions alone does not establish Zotero connectivity.

```bash
research-hub doctor 2>/dev/null  # if research-hub CLI installed
```

For `zotero-skills`, use the host's plugin/skill discovery to resolve the
installed plugin root or upstream checkout. The canonical entry point is
`skills/zotero-skills/SKILL.md` relative to that root, **not** root-level
`SKILL.md`. Keep root-level `scripts/` and the skill's `references/`
available; a raw SKILL.md-only install is not a complete runtime.

If **neither** is available, stop and explain the available setup paths;
do not install anything merely because an audit was requested:

- **Claude Code:** use the canonical marketplace installation:

  ```bash
  claude plugin marketplace add WenyuChiou/ai-research-skills
  claude plugin install zotero-skills@ai-research-skills --scope user
  ```

- **Other hosts (including Hermes):** follow the host's supported loader
  against [the canonical upstream repository](https://github.com/WenyuChiou/zotero-skills).
  Load `skills/zotero-skills/SKILL.md` from the resolved checkout, retaining
  `scripts/` at the repository root and `references/` beside the skill.
  Do not clone the whole repository into a host's one-level skill directory
  and assume discovery, or use an obsolete root-level raw SKILL.md URL.
- **Or** use the `research-hub` CLI (`pip install research-hub-pipeline`).

After authorized setup, verify read-only connectivity: Zotero desktop's
local API on port 23119, or configured Zotero Web API read access. An audit
does not authorize writes, installing dependencies, changing credentials,
or granting persistent access. Never print API keys or inspect credential
files; if credential diagnosis is necessary, use the upstream
`credentials_status()` helper's presence/source labels only. Ask the user
to handle credential or permission changes. Re-run the audit only when a
read-capable runtime is available.

## When to use

Trigger phrases:

- "Audit my Zotero library."
- "Find duplicate DOIs in Zotero."
- "Find Zotero items missing required tags."
- "Propose a tag hygiene cleanup plan."
- "Generate a Zotero cleanup preview before I apply anything."
- "Which Zotero collections are bloated / under-used?"

Not for:

- Adding, editing, or deleting items — defer to `zotero-skills` skill.
- Backfilling tags/notes on items already in research-hub clusters —
  use `research-hub zotero backfill` (already preview-first).
- Cluster-level operations — use `research-hub clusters` commands.
- Searching the library for a specific paper — use `zotero-skills`
  search, not the curator.

## Inputs

In priority order:

1. **research-hub cluster registry** (`.research_hub/clusters.yaml`) —
   to know which Zotero collections belong to which research clusters.
2. **Zotero library state via local API** (fast, read-only) — list
   items, list collections, list tags. Use `zotero-skills` `READ
   Operations` patterns directly; don't reinvent.
3. **research-hub dedup index** (`.research_hub/dedup_index.json`) —
   precomputed DOI/title hash table; far cheaper than a fresh scan.
4. **Optional**: backfill report from `research-hub zotero backfill`
   (saved to `.research_hub/backfill-*.md`) — historical state of
   prior cleanups.

## Audit checks

Five checks: duplicate DOI scan, orphan-tag scan, cross-collection cluster mismatch, tag hygiene report, collection bloat / sparsity. Pick the relevant subset for each user request.

Full check details + suggested fixes for each: `references/audit-checks.md`.

## Output discipline

Always emit a **preview plan**, never apply. The report has 5 sections that map 1:1 onto the audit checks (skip a section if its check returned no findings) plus a "Suggested follow-ups" section listing concrete CLI commands for the user to run.

The "Suggested follow-ups" section MUST open with a one-line backup
reminder before any apply/CRUD handoff suggestion:

> **Back up first.** In Zotero desktop: File → Export Library → Zotero
> RDF. Any modifications via `zotero-skills` or `research-hub zotero
> ... --apply` are irreversible without this snapshot.

This is required because this skill is read-only but its output
typically feeds an apply step run by `zotero-skills`. Surfacing the
backup step at handoff prevents the most common data-loss class
(accidental tag mass-rename or collection move with no undo).

Full report template: `references/report-template.md`.

If the report has 0 issues, emit a single OK line and stop.

## Token-saving behavior

- Read the dedup index first; only hit the Zotero local API for items
  not in the index.
- Cap full-library scans at 100 items per audit run unless the user
  explicitly says "full library".
- Don't quote item titles back if a DOI / Zotero key is enough.
- Cache the report in `.research_hub/curator-<timestamp>.md` if the
  user asks "save this report".

## What NOT to do

- **Do NOT call any Zotero create / update / delete endpoint.** That's
  zotero-skills' or research-hub's job, with explicit user `--apply`.
- **Do NOT** rename tags directly — propose, then defer to manual
  review or `zotero-skills` batch update.
- **Do NOT** trash duplicate items automatically — propose, then defer
  to `research-hub zotero backfill --apply` or manual delete.
- **Do NOT** redocument the zotero-skills CRUD primitives — link to
  them. The whole point of this skill is to be the **layer above**.

## See also

- `references/audit-checks.md` — full details for each of the 5 audit checks
- `references/report-template.md` — full curation-report preview template

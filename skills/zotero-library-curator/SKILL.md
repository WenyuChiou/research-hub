---
name: zotero-library-curator
description: Audit and curate a Zotero library — find duplicate DOIs, orphan items missing required tags, propose collection rebinds, generate tag hygiene reports, emit preview-only cleanup plans. Use when the user asks to "audit Zotero", "find duplicates", "tag hygiene report", or "propose a Zotero cleanup plan". Defers all CRUD operations to the standalone `zotero-skills` skill or `research-hub zotero` CLI.
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

Before running, verify at least one is present:

```bash
research-hub --version 2>/dev/null  # if research-hub CLI installed
ls ~/.claude/skills/zotero-skills/SKILL.md 2>/dev/null  # if zotero-skills skill installed
```

If **neither** is available, the user installed only the marketplace
plugin without the CLI and without the standalone `zotero-skills`
skill. Stop and tell them:

> This skill audits a Zotero library, which needs Zotero connectivity
> via one of:
>
> - The standalone `zotero-skills` skill (handles Zotero local API):
>   `git clone https://github.com/WenyuChiou/zotero-skills ~/.claude/skills/zotero-skills`
> - **Or** the `research-hub` CLI: `pip install research-hub-pipeline`
>
> Either path needs Zotero configured (local API on port 23119, or
> Zotero Web API key). Once one is set up, re-run your audit request.

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

For each request, pick the relevant subset:

### Duplicate DOI scan

- Group items by normalized DOI.
- Report any DOI with > 1 Zotero item.
- For each duplicate group, suggest which item to keep (the one with
  more notes / tags / attachments) and which to merge or trash.

### Orphan-tag scan

For each item in a research-hub cluster:

- Required tags (post v0.61): `research-hub`, `cluster/<slug>`,
  optionally `category/<arxiv-cat>`, `type/<doc-type>`, `src/<backend>`.
- Report items missing `research-hub` or `cluster/<slug>`.
- Suggested fix: `research-hub zotero backfill --tags`.

### Cross-collection cluster mismatch

- For each item, compare `cluster/<slug>` tag vs Zotero collection
  membership.
- Report items whose tag and collection disagree.
- Suggested fix: `research-hub clusters rebind --emit` then
  `--apply`.

### Tag hygiene report

- Top 50 most-used tags + count.
- Tags used < 3 times (potential typos).
- Tags that look like near-duplicates (e.g. `agent-based-modelling` vs
  `agent-based-modeling`).
- Suggested fix: human review + manual rename via Zotero desktop or
  `zotero-skills` batch update.

### Collection bloat / sparsity

- Collections with > 200 items (consider splitting).
- Collections with < 3 items (consider merging or deleting).
- Empty collections.

## Output discipline

Always emit a **preview plan**, never apply. Structure:

```
## Zotero curation report (read-only)

**Library**: <library_id>  ·  **Items audited**: <N>

### Duplicate DOIs (<count>)
- 10.1234/abcd: 2 items (KEEP item ABC123, MERGE/TRASH XYZ456)
- ...

### Items missing required tags (<count>)
- KEY1: missing [research-hub, cluster/foo]
- ...

### Cluster/collection mismatches (<count>)
- KEY7: tagged cluster/foo but in collection bar
- ...

### Tag hygiene
- Near-duplicate tag candidates: agent-based-modeling (47) vs agent-based-modelling (3)
- Tags used once: ['hopf', 'sufficient', ...] (potential typos)

### Collection bloat
- "survey" collection has 237 items — consider splitting
- "benchmarking" has 8 items — consider merging

### Suggested follow-ups
1. Run `research-hub zotero backfill --tags --notes` to fix the 12 missing-tag items
2. Run `research-hub clusters rebind --emit` to review the 3 mismatches
3. Manually rename the 2 tag near-duplicates in Zotero desktop
4. Defer the bloat/sparsity questions to a human review session
```

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

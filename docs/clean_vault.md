# Clean Vault at Scale

A practical playbook for keeping an Obsidian vault usable when it holds 1,000+ research papers. Written for Research Hub v0.3.0 but the ideas apply to any large research vault.

---

## The core principle

**`raw/` is storage. `hub/` is the map. You navigate via the map, never the storage.**

Obsidian's graph view and file explorer stop being useful around ~500 notes. Instead of fighting it, treat `raw/<cluster>/*.md` as an inert data layer that you query via dataview blocks inside `hub/clusters/<slug>.md` pages. You open a hub page, filter by reading status, click into one or two papers, done. You never scroll `raw/` looking for something.

---

## Five settings that matter

### 1. Hide `raw/` and other storage dirs from the graph view

Edit `.obsidian/graph.json` (or use the graph view settings panel). Add hidden filters:

```
-path:raw/ -path:hub/clusters/archive/
```

The graph view then only renders `hub/` hub pages and concept/theory pages. Instead of a supernova of 1,063 dots you see 30–60 meaningful nodes — cluster hubs linked to theory pages linked to a handful of seed papers. Each node is clickable to dig deeper.

### 2. Excluded files in the quick-switcher

Obsidian Settings → Files & Links → Excluded files → add `raw/`.

You can still `[[wikilink]]` into raw notes and search them with `Ctrl+Shift+F`, but they stop cluttering the quick-switcher (`Ctrl+O`) and the left-hand file tree gets scoped to hub pages and theories.

### 3. Obsidian's `userIgnoreFilters` in `.obsidian/app.json`

Research Hub v0.3.0 auto-populates this key during install with sensible defaults. Verify it includes:

```json
{
  "userIgnoreFilters": [
    "pytest-cache-files-",
    "__pycache__/",
    ".research_hub/",
    "pdfs/"
  ]
}
```

This stops the indexer from descending into non-vault directories that share the vault root.

### 4. Set a default folder for new notes

Files & Links → Default location for new notes → `inbox/` (create this folder if it does not exist).

Any note you create by hand goes to `inbox/`, not to the root of `raw/`. The pipeline still writes to `raw/<cluster>/`. A weekly triage pulls `inbox/` notes into the right cluster.

### 5. Turn off "Detect all file extensions"

Files & Links → Detect all file extensions → off. Then Obsidian only indexes `.md` and ignores stray `.json`, `.py`, `.log`, `.tmp` files that sometimes end up next to your notes.

---

## The reading status workflow

Every note written by Research Hub v0.3.0 gets `status: unread` in its YAML frontmatter. The progression is:

```
unread      just ingested, not looked at
skimming    read the abstract + first figure
deep-read   read cover to cover, took notes
cited       actively referenced in your current paper
archived    confirmed not relevant — kept for history, hidden from default views
```

You advance status by hand (or via a simple Obsidian template). Hub pages filter on status so you only see what matters right now.

### A ready-to-paste cluster hub page template

```markdown
---
type: cluster-hub
cluster: llm-behav-env-abm
---

# LLM Agents × Behavioral Science × Environmental Interaction

Short description of what this cluster is for and the research question it serves.

## Reading Queue (unread, top by citations)

```dataview
TABLE title, authors, year, citation-count
FROM "raw/llm-behav-env-abm"
WHERE status = "unread"
SORT citation-count DESC
LIMIT 10
```

## Deep-read (actively thinking about)

```dataview
TABLE title, authors, year
FROM "raw/llm-behav-env-abm"
WHERE status = "deep-read" OR status = "cited"
SORT year DESC
```

## Everything (including archived, by year)

```dataview
TABLE status, year, citation-count
FROM "raw/llm-behav-env-abm"
SORT year DESC, citation-count DESC
```
```

Open this file. See 10 unread papers. Read 2. Change their status to `skimming` or `deep-read`. Next week, 2 more. The queue shrinks visibly.

---

## Cluster sizing guideline

A cluster should hold roughly **30–80 papers**. Above ~100 the cluster itself becomes unusable and should be split. Below ~15 you probably are over-fragmenting — merge into a parent cluster.

If a cluster grows past 80, run:

```bash
research-hub clusters split <slug>
```

This scans the cluster's notes by tag and suggests 2–3 sub-clusters. You approve the split; the pipeline moves files and updates wikilinks.

(`research-hub clusters split` is planned for v0.4 — for v0.3.0 do it by hand: create the new cluster, move files, run `research-hub index` to rebuild the dedup cache.)

---

## Weekly review ritual (20 minutes)

1. Open `hub/index.md` — scan cluster sizes. Any over 80? Flag for split.
2. For each active cluster, open its hub page. Look at the Reading Queue block.
3. Pick 3–5 unread papers. Skim or deep-read. Update their `status:` field.
4. For papers you archived this week, move them out of the graph view (they are automatically hidden since status = archived is filtered).
5. Close Obsidian. Done.

Running this ritual weekly prevents the backlog from becoming the 1,063-note mess that v0.3.0 had to clean up.

---

## What NOT to do

- **Do not** flat-dump all papers into `raw/`. Always use a cluster sub-folder. An unclustered paper is an invisible paper.
- **Do not** navigate via the left-hand file tree in `raw/`. Use hub pages and dataview queries.
- **Do not** let `status` stay `unread` forever. A paper you will never read should be `archived`, not `unread`.
- **Do not** trust the graph view as a research map until you hide `raw/`. It is a pretty picture, not a thinking tool, when all 1,000 papers are visible.
- **Do not** manually add papers to hub pages. Let `build_hub.py` (run by `research-hub ingest` or a cron) regenerate them from frontmatter.

---

## Migrating an existing messy vault

If you already have a large flat `raw/` with hundreds of notes, the v0.3.0 migration is:

1. **Audit**: run `python scripts/audit_vault.py` (from the research-hub-audit workspace) to produce a report of YAML completeness and tag distribution.
2. **Propose clusters**: run `research-hub clusters propose --from-raw` to get a suggested list of clusters based on tag co-occurrence. Review and edit.
3. **Assign**: `research-hub clusters auto-assign --use-existing-yaml` moves each note into the best-matching cluster sub-folder and updates its frontmatter.
4. **Rebuild**: `research-hub index` then `research-hub build` regenerates the dedup index and hub pages.
5. **Verify**: open `hub/index.md` and spot-check 2–3 clusters.

Steps 2 and 3 are planned for v0.3.0 follow-up. For v0.3.0 base the migration is manual: create clusters via `research-hub clusters new`, move files by hand, run `research-hub index`.

---

## Summary

- Read notes from `hub/`, not `raw/`.
- Every note has `status:` — use it to filter.
- Cluster size 30–80; split when it grows.
- Run a 20-minute weekly review.
- Hide `raw/` from the graph view.
- Never add notes by hand to hub pages; let the pipeline regenerate.

These six rules keep a 5,000-paper vault usable. The v0.3.0 pipeline handles the mechanics; the discipline is yours.

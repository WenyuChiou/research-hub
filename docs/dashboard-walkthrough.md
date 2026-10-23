# Dashboard walkthrough

The dashboard is the fastest way to see one research cluster across Zotero, Obsidian, and NotebookLM without hopping between tools. It gives you one surface for inventory, briefings, health, and execution.

> Live mode matters when you want buttons to run the CLI for you. Static mode matters when you want a portable HTML snapshot you can open anywhere.

## What the dashboard is for

- Overview of cluster size, storage location, and recent additions.
- Library view of every paper note, with links out to Zotero, Obsidian, and NotebookLM.
- Briefings view for NotebookLM summaries and generated artifact links.
- Diagnostics for health warnings and drift.
- Manage for direct cluster actions, including NotebookLM and Obsidian maintenance.

## Static vs live mode

Static HTML:

```bash
research-hub dashboard
```

This renders a snapshot. Manage-tab buttons copy the exact CLI command.

Live HTTP dashboard:

```bash
research-hub serve --dashboard
```

Open `http://127.0.0.1:8765/`. In live mode, Manage-tab buttons execute immediately through the local server. If the server is not running, the same buttons fall back to clipboard-copy mode.

No extra setup is required for the v0.42-v0.44 NotebookLM actions beyond your existing `research-hub notebooklm login` session. Zotero actions keep using your existing configured credentials.

## The 5 tabs

### Overview

Use this when you want the big picture first:

- Treemap of papers per cluster.
- Storage map showing Zotero, Obsidian, and NotebookLM bindings.
- Recent additions feed.

### Library

Use this when you want the actual paper rows:

- Expand a cluster card to inspect paper notes.
- Use the search bar to filter titles, tags, and cluster names.
- Open links back into Zotero, Obsidian, or NotebookLM from each row.

#### Source & sync evidence / 來源與同步證據

Expand the bilingual **Source & sync evidence** disclosure on a paper row to see
its recorded DOI, Zotero key, Obsidian note path, and cluster. These values come
from the local note and dashboard grouping; a saved Zotero key is not a live
Zotero check. The display says **Remote sync: unknown** even when an identity is
found in the local NotebookLM cache.

The explanation distinguishes a missing, unreadable, or invalid cache from a
valid cache without an exact matching primary-source key. No match does not mean
that the source is absent remotely. Bundle-PDF and shard relationships are not
guessed from a DOI, filename, or title. Ambiguous matches remain unknown.
Blank, null, repeated, non-string, malformed YAML, or invalid UTF-8 identity fields stay
unknown rather than borrowing text from the next line. Invalid cache metadata
used by the dashboard is ignored for display with an explicit invalid reason;
the paper rows remain visible and cache bytes are not repaired or rewritten.
If unreadable note metadata prevents label counting, label counts are explicitly
unknown rather than hiding the cluster or claiming a zero count.

The cached payload version is **unknown** unless that exact uploaded-source key
also has a saved `source_versions` entry with `kind: pdf|text` and a SHA-256.
This optional field is read for compatibility with version-aware uploads; this
view neither creates it nor invents fingerprints for older caches. A recorded
fingerprint is historical, not a comparison with today's bytes or remote state.
The key and full hash are under a second **Technical identifiers** disclosure.

Read the reason and next step before acting. Opening, closing, and reopening the
disclosures performs no probe, upload, replacement, or deletion. This is the
native-vault **legacy Dashboard Library**, not the separate React Workspace
literature page. Existing dashboard collection/doctor behavior is unchanged;
the added evidence reader introduces no provider calls or additional files.

### Briefings

Use this when NotebookLM is part of the workflow:

- Preview downloaded brief text inline.
- Copy the full brief.
- Inspect the per-cluster NotebookLM artifacts tile.

### Diagnostics

Use this when the vault feels off:

- Check health badges for Zotero, Obsidian, and NotebookLM.
- Review drift alerts before running repair commands.

### Manage

Use this when you want action, not just inspection:

- Rename, merge, split, or re-bind clusters.
- Run the newer NotebookLM and Obsidian maintenance actions.

## Daily workflow

### Researcher

1. Open Diagnostics and clear obvious drift or health warnings.
2. Ingest new papers.
3. Open Manage for the target cluster.
4. Run `Bundle papers`, then `Upload to NotebookLM`.
5. Generate or download a brief.
6. Use `Ask NotebookLM` for one-off questions.

### Analyst

1. Use the search bar in Library to narrow to a topic.
2. Import or ingest new material.
3. Open Manage and run `Polish markdown` for note cleanup.
4. Run `Emit .base dashboard` to regenerate the Obsidian Bases view.

## v0.42 NotebookLM actions

### Bundle papers

Builds the NotebookLM upload bundle for a cluster. Use this before upload when the source set changed.

### Upload to NotebookLM

Sends the latest bundle into the bound notebook. The `Show browser window` checkbox switches from headless to visible mode for troubleshooting or manual inspection.

### Generate artifact

Triggers NotebookLM generation for one artifact type:

- `brief`
- `audio`
- `mind_map`
- `video`

Use this when you want NotebookLM to create a new output but you do not need to download it yet.

### Download brief

Pulls the latest briefing text into `.research_hub/artifacts/<slug>/brief-*.txt`, updates `nlm_cache.json`, and makes the result visible in Briefings.

### Ask NotebookLM

Runs `research-hub notebooklm ask` against the cluster notebook. Add a timeout if you want a shorter or longer wait than the default.

## v0.43 Obsidian actions

### Polish markdown

Runs the markdown normalizer for a cluster's notes. Leave `Apply` unchecked for a dry run.

### Emit .base dashboard

Generates `hub/<slug>/<slug>.base` for Obsidian Bases. Use `Overwrite existing` when you want to replace an older generated file.

## NotebookLM artifacts tile

Each Briefings card now includes a `NotebookLM artifacts` tile per cluster.

The table shows:

- Artifact kind.
- Download date.
- Character count.
- Open links.

Typical links:

- `open in NLM` opens the current NotebookLM notebook or generated artifact URL.
- `open .txt` opens the downloaded local artifact when a file exists.

If a cluster has no downloaded artifacts yet, the tile shows a `Download brief` button wired to the same Manage action.

## Troubleshooting

- If upload succeeds but the notebook does not reflect new sources, re-run upload with the visible browser option.
- If Briefings stays empty, generate a brief first and then download it.
- For NotebookLM session issues, see [notebooklm-troubleshooting.md](notebooklm-troubleshooting.md).

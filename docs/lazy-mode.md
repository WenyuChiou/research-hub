# Lazy mode — 4 commands you actually need

v0.46 added 3 new top-level commands that compress the most common research-hub workflows into one line each. Plus the existing `ask`. This page is the 1-page reference.

## The 4 commands

| Command | What it does | When to use |
|---|---|---|
| `research-hub auto "topic"` | Search + ingest + NotebookLM brief in one shot | "I want papers on X" |
| `research-hub ask "Q" --cluster X` | Ask an existing notebook a question | "What does my X cluster say about Y?" |
| `research-hub tidy` | Doctor autofix + dedup rebuild + bases refresh + cleanup preview | "My vault feels stale" |
| `research-hub cleanup --all --apply` | GC bundles + debug logs + old artifacts | "Disk is filling up" |

## `research-hub auto`

End-to-end pipeline.

```bash
research-hub auto "harness engineering for LLM agents"
```

Stages (visible in the live output):

```
[OK] cluster        harness-engineering-for-llm-agents (created)
[OK] search         8 results from arxiv,semantic_scholar (3.2s)
[OK] ingest         6 papers in raw/harness-engineering-for-llm-agents/
[OK] nlm.bundle     6 PDFs (24 MB)
[OK] nlm.upload     6 succeeded
[OK] nlm.generate   brief generation triggered
[OK] nlm.download   1,243 chars saved
Done in 47s.
```

Useful flags:

```bash
research-hub auto "topic" --max-papers 3        # smaller batch
research-hub auto "topic" --no-nlm              # skip NotebookLM (just Zotero + Obsidian)
research-hub auto "topic" --dry-run             # print plan, don't execute
research-hub auto "topic" --cluster existing-x  # reuse existing cluster instead of slugifying
```

## `research-hub ask`

```bash
research-hub ask --cluster llm-evaluation-harness \
    --question "What are the 3 main research threads?"
```

Routes to the cluster's previously-uploaded NotebookLM notebook. Saves answer to `.research_hub/artifacts/<slug>/ask-<UTC>.md`.

Default headless. Pass `--visible` to watch Chrome navigate. Default 120 s timeout; pass `--timeout 180` to extend.

## `research-hub tidy`

One-shot vault maintenance — runs 4 sub-steps non-fatally:

```bash
research-hub tidy
```

```
[OK] doctor    16 checks, 12 OK, 4 INFO, 0 WARN
[OK] dedup     767 DOIs, 1101 titles
[OK] bases     8 clusters refreshed
[OK] cleanup   would free 187 MB (8 stale bundles)  -- run `research-hub cleanup --all --apply` to apply
Done in 6s.
```

To also flush the cleanup preview:

```bash
research-hub tidy --apply-cleanup
```

## `research-hub cleanup`

GC accumulated files. Default is dry-run; pass `--apply` to actually delete.

```bash
research-hub cleanup --bundles --apply              # per-cluster, keep newest 2 bundle dirs
research-hub cleanup --debug-logs --older-than 30   # nlm-debug-*.jsonl older than 30d
research-hub cleanup --artifacts --keep 10          # per-cluster, keep newest 10 ask-/brief- files
research-hub cleanup --all --apply                  # all of the above, applied
```

Also still does the v0.45 wikilink dedup if you pass `--wikilinks`.

## Dashboard equivalent

Same 4 actions exist as Manage tab buttons in `serve --dashboard` (v0.44+):

```bash
research-hub serve --dashboard
# → http://127.0.0.1:8765/ → Manage tab
```

See [`docs/dashboard-walkthrough.md`](dashboard-walkthrough.md) for the full UI tour.

## Decision table

| Situation | Command |
|---|---|
| New topic to research | `research-hub auto "..."` |
| Want answer from existing notebook | `research-hub ask --cluster X --question "..."` |
| Vault feels cluttered | `research-hub tidy` |
| Disk space running low | `research-hub cleanup --all --apply` |
| Single paper to add | `research-hub add --doi <doi>` (longhand still works) |
| Manual control over each step | The longhand `clusters new` → `search` → `ingest` → `notebooklm bundle/upload/generate/download` chain |

## Compatibility

- All v0.42-v0.45 commands still work — the lazy commands are pure additions
- Zero new setup beyond v0.42's `notebooklm login` and Zotero credentials
- v0.46 release notes: [`CHANGELOG.md`](../CHANGELOG.md)

# Zotero Backfill

## When to run

Run this after `doctor` or `research-hub clusters audit` reports Obsidian/Zotero drift for a cluster.

## Prerequisites

- `research-hub` v0.74+ with `pipeline.write_papers_to_zotero(...)`
- A working Zotero API configuration
- A vault with `.research_hub/clusters.yaml` and bound `zotero_collection_key` values

## Step 1: Dry-run one cluster

```bash
python scripts/backfill_zotero.py --vault C:/Users/wenyu/knowledge-base --cluster survey --dry-run
```

## Step 2: Review the plan

Inspect:

- `<vault>/.research_hub/backfill/<cluster>/case_A_missing.json`
- `<vault>/.research_hub/backfill/<cluster>/case_B_skip.json`
- `<vault>/.research_hub/backfill/<cluster>/case_C_rebind.json`
- `<vault>/.research_hub/backfill/<cluster>/case_D_recreate.json`
- `<vault>/.research_hub/backfill/backfill_plan_<timestamp>.md`

## Step 3: Apply one cluster

```bash
python scripts/backfill_zotero.py --vault C:/Users/wenyu/knowledge-base --cluster survey --apply
```

## Step 4: Apply the rest

```bash
python scripts/backfill_zotero.py --vault C:/Users/wenyu/knowledge-base --all --apply
```

## Recovery

Before `--apply`, the script snapshots:

- `<vault>/papers_input.json.bak-<timestamp>` when `papers_input.json` exists
- `<vault>/.research_hub/clusters.yaml.bak-<timestamp>` when `clusters.yaml` exists

If you need to revert, restore those backup files and review the per-cluster backfill JSON files plus `manifest.jsonl` entries with `action=backfill_<case>`.

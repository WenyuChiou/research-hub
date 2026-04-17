# Upgrade Guide

This guide covers migration from older research-hub releases to v0.30. If you're upgrading from a release within the last few weeks, the path is usually `pip install -U research-hub-pipeline`. If you've been on a much older release, read the section that matches your starting version.

> **Backup first.** Before any upgrade that crosses a major version: copy your `~/.research_hub/` config dir AND your vault's `.research_hub/` dir somewhere safe. The vault `.md` files don't need backup (they're never destructively modified by upgrades).

---

## Quick path: upgrading from v0.28 or v0.29

```bash
pip install -U research-hub-pipeline
research-hub doctor
```

That's it. v0.30 only adds; nothing breaks. New since v0.29:

- `pipeline.py` Zotero collection routing now respects per-cluster `zotero_collection_key` (was ignored). If you bound a cluster to a specific Zotero collection but papers were going to your default collection, the next ingest will route correctly. **No manual fix needed** — existing papers stay where they are; only future ingests change.
- All MCP tools now reject path-traversal slugs (`../etc`). If you had any tooling that passed slug strings through unchecked, it'll now error with `ValidationError`. Fix: pass clean slugs.
- Dashboard now requires CSRF token + Origin check on `/api/exec`. Browsers handle this automatically when loading from `/`. Custom HTTP clients hitting `/api/exec` directly need to read `X-CSRF-Token` from the page meta tag and send it back.
- Config files now `chmod 600` (POSIX). If you have weird file ownership issues post-upgrade, `chmod 600 ~/.config/research-hub/config.json` manually.

---

## Upgrading from v0.20–v0.27

You're upgrading across the **anti-RAG crystals shift** (v0.28) and the **onboarding UX rework** (v0.29).

### Step 1 — install + run doctor

```bash
pip install -U research-hub-pipeline
research-hub doctor
```

If `doctor` reports `[XX] config: not found`, your config is in a legacy location. Run `research-hub init` to migrate; the wizard detects existing vaults and writes a fresh config without overwriting your data.

### Step 2 — new commands available

- `research-hub where` — quick "where's my stuff" status (<0.1s)
- `research-hub install --mcp` — auto-write Claude Desktop MCP config
- `research-hub crystal emit/apply/list/read/check` — pre-computed Q→A for clusters
- `research-hub clusters analyze --split-suggestion` — auto-suggest sub-topics for big clusters
- `research-hub serve --dashboard` — live HTTP dashboard with direct execution

### Step 3 — generate crystals (optional but recommended)

If you have a stable cluster you query often:

```bash
research-hub crystal emit --cluster <slug> > /tmp/prompt.md
# Feed prompt.md to Claude/GPT/Gemini, save the response as crystals.json
research-hub crystal apply --cluster <slug> --scored crystals.json
```

After this, AI agents querying your cluster get pre-written ~100-word answers (~30× token compression). See [docs/anti-rag.md](docs/anti-rag.md).

### Step 4 — refresh Obsidian graph colors

```bash
research-hub vault graph-colors --refresh
```

v0.27 added 14 graph color groups (5 cluster paths + 9 label tags). The refresh writes to `.obsidian/graph.json` non-destructively (preserves your other settings).

---

## Upgrading from v0.10–v0.19

You're crossing **all** the breaking-ish changes. The most important ones:

### Changes you may notice

| Change | Released in | Effect |
|---|---|---|
| `topic_cluster:` frontmatter as primary cluster membership | v0.20 | Older papers without this field still work via folder-name fallback |
| Labels canonicalized to 9 values | v0.21 | Old free-form labels still readable; `paper prune` migrates to canonical |
| Dedup index extended with title-norm key | v0.22 | Auto-rebuilt on first run; old DOI-only entries preserved |
| Vault layout: `raw/<cluster>/`, `hub/<cluster>/`, `topics/<cluster>/` | v0.20 | Old flat `raw/` still readable; new ingests use cluster subdirs |
| Config moves to `platformdirs` location | v0.18 | Old config auto-detected and migrated by `research-hub init` |
| MCP server (`research-hub-mcp` entry) | v0.15 | Optional dep `[mcp]`; install via `pip install research-hub-pipeline[mcp]` |

### Recommended migration sequence

```bash
# 1. Backup
cp -r ~/.research_hub ~/.research_hub.bak.v0.10
cp -r <your-vault>/.research_hub <your-vault>/.research_hub.bak.v0.10

# 2. Upgrade
pip install -U research-hub-pipeline

# 3. Run init in --reconfigure mode (interactive; preserves vault data)
research-hub init --reconfigure

# 4. Health check
research-hub doctor

# 5. Rebuild dedup index (DOIs + titles)
research-hub dedup rebuild

# 6. Refresh dashboard + graph
research-hub dashboard
research-hub vault graph-colors --refresh

# 7. (Optional) Generate crystals for your most-queried clusters
research-hub crystal emit --cluster <slug> > prompt.md
# ... feed to your AI, save as crystals.json
research-hub crystal apply --cluster <slug> --scored crystals.json
```

### What CAN break going from v0.10–v0.19 → v0.30

- **Custom scripts** that imported internal modules at the old paths. v0.30 split `cli.py` and `mcp_server.py` into packages. Public APIs preserved (`from research_hub.cli import main`, `from research_hub.mcp_server import main, mcp`), but if you imported internal helpers like `from research_hub.cli import _build_clusters_parser`, those moved. Update imports as needed.
- **Custom MCP tool wrappers** that didn't pass slug strings through validation will now hit `ValidationError` when called with non-slug-shaped input. Fix: clean the input or use `research_hub.security.validate_slug()` explicitly.
- **Direct edits to `.research_hub/clusters.yaml`** that used the old `collection_id` key (instead of `zotero_collection_key`) will be silently ignored. Re-run `research-hub clusters bind --slug X --zotero KEY` to set it via CLI.

### What CANNOT break

- Your `.md` paper notes — never destructively modified by upgrades
- Your Obsidian vault structure — research-hub writes alongside, never overwrites
- Your Zotero library — research-hub creates items, never deletes

---

## Upgrading from v0.1–v0.9

Treat as a fresh install. The schema differences are large and we don't guarantee data migration paths back this far.

```bash
# 1. Save your old vault somewhere safe
mv ~/knowledge-base ~/knowledge-base.v0.5

# 2. Fresh install
pip install -U research-hub-pipeline
research-hub init  # creates new vault

# 3. Re-import papers from Zotero one cluster at a time:
#    - in Zotero, list papers in a collection
#    - for each paper, get the DOI
#    - research-hub add <DOI> --cluster <new-slug>

# 4. Old vault remains read-only; you can browse it in Obsidian as a reference
```

If you have <50 papers, just re-ingest. If you have hundreds, contact via [issues](https://github.com/WenyuChiou/research-hub/issues) for a custom migration script.

---

## Rollback procedure

If a v0.30 upgrade goes wrong:

```bash
# 1. Pin to a known-good earlier version
pip install research-hub-pipeline==0.29.0

# 2. Restore the .research_hub config you backed up
cp -r ~/.research_hub.bak.v0.10 ~/.research_hub
cp -r <vault>/.research_hub.bak.v0.10 <vault>/.research_hub

# 3. Verify
research-hub doctor
```

Vault data (the `.md` files) doesn't need rollback — it's never destructively modified.

---

## Reporting upgrade problems

If something breaks: open an issue at https://github.com/WenyuChiou/research-hub/issues with:

1. Old version (`pip show research-hub-pipeline | grep Version` before the upgrade, or check `~/.research_hub/config.json` `__version__` field)
2. New version (`research-hub --version`)
3. The exact error message + traceback
4. Output of `research-hub doctor`
5. Output of `research-hub where`

We aim to keep upgrade paths working even across many minor versions; if yours doesn't, we want to fix it.

# Hidden File Formats — Schema Versions

> Status: **proposal** for the v0.91+ contract. Codifies G2 audit #9 from
> the v0.89.1 post-release scorecard. Third-party tools that parse
> research-hub state files should check `schema_version` and refuse to
> parse on a mismatch they don't understand.

research-hub writes several files outside the user-visible Obsidian
vault. Some of these are documented as parseable artifacts (e.g.
`manifest.jsonl` event log used by `vault rebuild-overviews` and
external auditors); others are internal caches that nonetheless leak
into people's tooling. This document inventories all 11 formats and
declares their current schema versions.

**Versioning policy** (v0.91+):

- New formats start at `schema_version: "1.0"`.
- Backward-compatible field additions: no schema bump.
- Field rename or removal: bump to `2.0`. New writers emit `2.0`;
  old readers see the bump and refuse to parse (or fall back).
- Old readers parsing a `1.0` file written by a future writer that
  forgot to bump: undefined behavior. Bump aggressively.

| File | Schema | Status | Bumped in | Reader behavior on missing field |
|---|---|---|---|---|
| `.research_hub/clusters.yaml` | `schema_version: "1.0"` | **versioned** | v0.91.0 W4 | Treated as `1.0` (implicit) |
| `.research_hub/dedup_index.json` | `schema_version: "1.0"` | **versioned** | v0.91.0 W4 | Treated as `1.0` (implicit) |
| `.research_hub/manifest.jsonl` | `_schema: 1` per line | **versioned** | v0.91.0 W4 | Treated as schema 0 (legacy) |
| `.research_hub/dashboard-summary.md` | none yet | unversioned | (tracked for v0.92) | n/a |
| `_HOME.md` | none | unversioned | (tracked for v0.92) | n/a |
| paper note frontmatter | none | unversioned | (tracked for v1.0) | n/a |
| `crystals/<slug>.md` | none | unversioned | (tracked for v0.95) | n/a |
| `<cluster>/.fit_check_accepted.json` | none | unversioned | (tracked for v0.92) | n/a |
| `<cluster>/.fit_check_rejected.json` | none | unversioned | (tracked for v0.92) | n/a |
| `.research_hub/nlm_cache.json` | none | unversioned | (tracked for v0.92) | n/a |
| `.research_hub/zotero_kept_collections.json` | none | unversioned | (tracked for v0.92) | n/a |
| `.research_hub/quotes/<slug>.md` | none | unversioned | (tracked for v0.95) | n/a |

## Versioned formats (parseable contract)

### `clusters.yaml` (top-level `schema_version: "1.0"`)

```yaml
schema_version: "1.0"
clusters:
  ml-flood-forecasting:
    name: "ML Flood Forecasting"
    zotero_collection_key: "ABC123"
    obsidian_subfolder: "raw/ml-flood-forecasting"
    notebooklm_notebook: "..."
    # ... cluster fields
```

Source: `src/research_hub/clusters.py:ClusterRegistry.save`.

### `dedup_index.json` (top-level `schema_version: "1.0"`)

```json
{
  "schema_version": "1.0",
  "doi_to_hits": { "<normalized-doi>": [<DedupHit>, ...] },
  "title_to_hits": { "<normalized-title>": [<DedupHit>, ...] }
}
```

Source: `src/research_hub/dedup.py:DedupIndex.save`.

### `manifest.jsonl` (per-line `_schema: 1`)

One JSON object per line. `_schema=1` is the v0.91+ marker; pre-v0.91
lines lack the field and are read as schema 0 (legacy). The field set
is otherwise stable since v0.6x:

```json
{"_schema": 1, "timestamp": "2026-05-15T...", "cluster": "...", "query": "...", "action": "new", "doi": "...", ...}
```

Source: `src/research_hub/manifest.py:ManifestEntry`.

## Unversioned formats (track for future bump)

These formats were in production before v0.91 and don't yet have a
documented schema. The reader code is the de-facto schema. They will
be bumped in subsequent v0.9x releases as outlined in the table above.

When bumping an unversioned format:

1. Add the schema field at the top level (JSON / YAML) or in the
   frontmatter (markdown).
2. Update the table above with the bump version.
3. Document the field set in this file.
4. Update any third-party parser docs that exist.

## CLI `--json` envelope (v0.91.0 W5)

Not a file format, but a parseable contract that agents depend on.
Every CLI subcommand invoked with `--json` emits an envelope of
fixed shape — agents can branch on `command` to know what's inside
`report`.

```json
{
  "schema_version": "1.0",
  "ok": true,
  "command": "auto",
  "version": "0.91.0",
  "report": { /* per-command shape */ }
}
```

| Field | Type | Stability |
|---|---|---|
| `schema_version` | `"1.0"` | envelope contract; bump = breaking |
| `ok` | `rc == 0` | stable; flips with exit code |
| `command` | str | stable; matches argparse subcommand name |
| `version` | `research_hub.__version__` | stable; tracks package version |
| `report` | varies | per-command shape; see G2 #8 follow-up for full standardization (tracked for v0.92) |

For now, the `report` payload mirrors the underlying Report
dataclass (or dict) returned by the command handler, run through
`_json_safe` to handle dataclasses / Path / nested types / datetime
/ bytes / Exception. **Until per-Report `schema_version` lands
(v0.92), agents should treat report-internal field names as
implementation details — use `command` to dispatch.**

Source: `src/research_hub/cli.py:_emit_cli_json`.

## See also

- v0.89.1 G2 audit summary: `~/.claude/plans/delegated-puzzling-umbrella.md`
- `research_hub.describe` capability manifest (v0.89.0 W-C) — agent-facing
  inventory of CLI subcommands, MCP tools, and env vars. Does NOT yet
  enumerate these file formats — tracked for v0.95 (G2 audit #5).

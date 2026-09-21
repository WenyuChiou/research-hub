# Stable Public API

> Status: **contract** as of v0.91.0; **the v1.x stability
> statement** as of v1.0.0. Codifies G2 audit #13 from the v0.89.1
> post-release scorecard. Anything documented here follows
> semantic-versioning guarantees; anything NOT here is internal and may
> change in any release without a deprecation cycle. The mechanical
> release gate — clean working tree, version-sync across all release
> files, and the FULL test suite (including e2e) on a fresh basetemp —
> precedes every `v*` tag (see [RELEASING.md](RELEASING.md)). Patch and
> minor releases ship on a rapid cadence behind that gate; there is no
> fixed multi-day RC-bake window.

research-hub has three public surfaces. Only the items listed below are
covered by the stability guarantee.

## 1. Python import surface

`research_hub.__all__` is the authoritative list:

```python
from research_hub import (
    __version__,
    # Structured exception hierarchy (since v0.89.0)
    ResearchHubError,
    MissingCredential,
    RequiresAuthRefresh,
    MissingExternalTool,
    UpstreamRateLimited,
    UpstreamUnavailable,
    # Capability manifest helpers (since v0.89.0)
    build_manifest,
    describe_manifest,
)
```

**Not public**, despite being importable:

- Any underscore module (`research_hub._deprecation`,
  `research_hub.search._rank`, …).
- Deep submodule imports (`research_hub.paper.set_labels`,
  `research_hub.dashboard.types`, …). Tests reach into these; that is a
  test-only convenience, not a contract. They may move or change
  signature in any release.
- `research_hub.cli` internals (`_emit_cli_json`, `_json_safe`,
  `_main_dispatch`). The CLI is public via its **subcommands**, not its
  Python functions.

If you need something from the internal tree as a stable API, open an
issue — we will promote it into `__all__` with a documented shape.

## 2. CLI subcommands

`research-hub describe --json` is the machine-readable source of truth
for the subcommand list. Every subcommand it reports with
`supports_json: true` emits the versioned envelope documented in
[`file-formats.md`](file-formats.md#cli---json-envelope-v0910-w5).

The subcommand **names** and their documented flags are stable. Help
text, internal flag defaults, and the per-command `report` payload
shape are NOT yet frozen (per-Report `schema_version` is tracked for
v0.92, G2 #8). Until then, branch on the envelope's `command` field.

## 3. MCP tools

The FastMCP server's tool **names** + input schemas are stable. The
full list is introspectable via `research-hub describe --json`
(`mcp_tools` key) or by starting the server. Tool consolidation
(merging overlapping `ask_cluster*` / `*_rebind` / `list_*` tools)
started in v0.91.0 with the deprecated aliases listed below.

## Deprecation policy

Implemented in `research_hub._deprecation`:

- `warn_deprecated(what, *, replacement, removed_in, stacklevel=2)`
  emits a standardized `DeprecationWarning`.
- `deprecated_callable(func, *, what, replacement, removed_in)` wraps a
  renamed callable so the old name keeps working but warns.

Rules:

1. A deprecation always emits `DeprecationWarning` naming the
   replacement and the removal version.
2. Deprecated surface is retained for the **remainder of the
   major**. Removal happens only at the next **major** bump, never
   inside a minor or patch.
3. Each deprecation gets a CHANGELOG entry under a `### Deprecated`
   heading (Keep-a-Changelog convention; tracked for v0.95-rc as part
   of the CHANGELOG-format rework, G4 #4).
4. The backwards-compat exception import paths
   (`research_hub.notebooklm.NotebookLMError`, etc.) noted as
   "deprecation TBD" in CHANGELOG v0.89.0 are hereby declared
   **supported aliases**, not deprecated — they re-export from
   `research_hub.errors` and inherit the new base. No removal planned.

### Deprecated (since v0.91.0 — retained through 1.x, removed no earlier than v2.0.0)

> Per standard semver, deprecated surface is **not** removed inside
> a major. The `removed_in` value was a placeholder `v1.0.0`; at
> the v1.0.0 freeze it is corrected to the next major (`v2.0.0`).
> Every alias below keeps working as a warning-emitting thin
> wrapper for the entire 1.x line.

| Old surface | Canonical replacement | removed_in |
| --- | --- | --- |
| `research-hub ask` | `research-hub notebooklm ask` | `v2.0.0` |
| `research-hub summarize` | `research-hub paper summarize` | `v2.0.0` |
| `research-hub cleanup` | `research-hub tidy` | `v2.0.0` |
| `research-hub label-bulk` | `research-hub paper bulk-relabel` | `v2.0.0` |
| MCP `ask_cluster_notebooklm` | MCP `ask_cluster(source="notebooklm")` | `v2.0.0` |
| MCP `read_briefing` | MCP `ask_cluster(source="notebooklm", mode="briefing")` | `v2.0.0` |
| MCP `brief_cluster` | MCP `ask_cluster(source="notebooklm", mode="brief")` | `v2.0.0` |
| MCP `propose_cluster_rebind` | MCP `cluster_rebind(action="propose")` | `v2.0.0` |
| MCP `apply_cluster_rebind` | MCP `cluster_rebind(action="apply")` | `v2.0.0` |
| MCP `list_orphan_papers` | MCP `cluster_rebind(action="list_orphans")` | `v2.0.0` |
| MCP `summarize_rebind_status` | MCP `cluster_rebind(action="status")` | `v2.0.0` |
| MCP `list_entities` | MCP `read_cluster_memory(kind="entities")` | `v2.0.0` |
| MCP `list_claims` | MCP `read_cluster_memory(kind="claims")` | `v2.0.0` |
| MCP `list_methods` | MCP `read_cluster_memory(kind="methods")` | `v2.0.0` |

## See also

- [`audit-output.md`](audit-output.md) — optional stable `--audit-output` CLI
  surface and version 1.0.0 attempt/event/artifact schema for search, enrich,
  verify, references and cited-by; default command outputs stay compatible.

- [`file-formats.md`](file-formats.md) — hidden file format schema versions
- [`authenticity.md`](authenticity.md) — the v1.0 no-fabricated-references guarantee + L0–L5 + quarantine triage
- [`RELEASING.md`](RELEASING.md) — the mechanical release-gate runbook (version-sync + full-suite gate before every tag)
- `research_hub.describe` — runtime capability manifest

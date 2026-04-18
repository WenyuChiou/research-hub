## v0.35.0 audit (2026-04-18)

**Theme:** Connector abstraction. Architecture-only release.

### Track A — Connector Protocol (Codex, committed `be41f16`)

5 files, +512 LOC, 8 tests. Real names verified before brief written:
- `notebooklm.upload.upload_cluster` (not `upload_to_notebooklm`)
- `notebooklm.upload.generate_artifact` (not `generate_briefing`)
- `notebooklm.upload.download_briefing_for_cluster`
- `notebooklm.bundle.bundle_cluster` returning `BundleReport(pdf_count, url_count, ...)` — no `source_count` attr; sum in adapter

Codex-Claude split:
- Brief: Claude (`.ai/codex_task_v035_connector.md`, 471 lines, full code embedded)
- Execution: Codex (`exec --full-auto`, ~5 min, no stalls this time)
- Verification + commit-message review + release: Claude

### Track B — Live verification

```python
>>> from research_hub.connectors import list_connectors, get_connector
>>> list_connectors()
['notebooklm', 'null']
>>> get_connector('notebooklm').name
'notebooklm'
>>> get_connector('null').check_auth(None)
True
```

Adapter calls real `notebooklm.bundle.bundle_cluster` under the hood — no shadow implementation.

### Test totals

```
1270 passed, 14 skipped, 2 xfailed, 1 xpassed in 75.36s
```

(+8 connector tests; +1 xpassed because v0.34 quality fixes unstuck a baseline test)

### Constraints honored

- 0 modifications to `notebooklm/*` (2,463 LOC)
- 0 modifications to 15 existing `notebooklm` import sites
- 0 CLI changes
- 0 MCP changes
- 0 workflows.py changes

### What's NOT in v0.35 (deferred)

- `--connector` CLI flag — lands when 2nd real connector exists (Notion? Logseq? Drive?)
- MCP `connector_*` tools — same gating
- Phase 2 structured memory layer — v0.36
- Vault restore (Task #124) + Zotero key encryption + search recall baselines — v0.37 housekeeping batch

### Sequence sanity

v0.30 (hardening) → v0.31 (Document abstraction = Codex Phase 1) → v0.32 (screenshot CLI + graphify redesign) → v0.33 (5 task wrappers = Codex Phase 3) → v0.34 (dashboard polish + persona tests) → v0.35 (connector abstraction = Codex critique #5).

Codex critique items now fully addressed:
- Phase 1: Document abstraction ✅ v0.31
- Phase 2: Structured memory ⏳ v0.36 (planning)
- Phase 3: Tool consolidation ✅ v0.33
- #5: NLM as optional connector ✅ v0.35

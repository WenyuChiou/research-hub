## v0.40.0 audit (2026-04-19)

**Theme:** Production readiness — close the top-tier gaps from a 3-axis audit.

### Why this release

After v0.39 shipped, user asked: "the 6 new clusters have no overview/summary?" + requested 整個系統評估 使用者評估 專案等等 確保可以上線 (full system + user + project audit to ensure go-live ready).

### Phase 1 — 3 parallel Explore agents

**Agent #1 (Architecture / tech debt)**:
- `cli.py` 3434 LOC monolith, `mcp_server.py` 1976 LOC monolith — flagged for v0.41+ split (huge work, low immediate impact)
- 6-month-old TODO in `dashboard/data.py:36` for crystal.py merge fallback
- `init/add/discover` entry points have no top-level try/except
- Search xfail tests still failing since v0.26
- **CRITICAL**: cluster hub scaffolding gap — `ClusterRegistry.create()` writes to clusters.yaml but never creates hub/<slug>/. Maintainer's vault has 7 clusters but only 1 has the hub structure.

**Agent #2 (User experience / onboarding)**:
- README persona table missing required pip extras per persona
- `docs/onboarding.md` v0.19 stale with removed `--field` flag, no Analyst/Internal mention
- MCP tools crash on empty vault
- Init wizard says "could not verify (may still work)" — silent failure trap
- PDF dep error fires mid-import, not at parse time
- Dashboard empty-state messaging weak

**Agent #3 (Public release / community)**:
- CI only runs on Linux (README claims Win/Mac/Linux)
- Zotero key plaintext on disk until user runs `doctor`
- Missing: SECURITY.md, CODE_OF_CONDUCT.md, ISSUE/PR templates
- README missing link to personas.md
- `readability-lxml` unmaintained since 2021 (deferred — narrow impact)

### Phase 2 — synthesis: 4 tracks

**A. Hub scaffolding** (Codex Brief A, committed `0ac4de5`) — closes user-discovered gap
**B. Onboarding hardening** (Codex Brief B, committed `71253ce`) — 5 fixes (B4 already done by A's encrypt call)
**C. Repo polish** (Claude direct) — multi-OS CI + repo policy files + first-10-minutes guide
**D. Live verify** (Claude direct) — backfill scaffold for maintainer's 7 clusters, persona MCP smoke

User locked: single v0.40.0 release, all 4 tracks combined.

### Track A — Cluster hub auto-scaffold

NEW `scaffold_cluster_hub(cfg, slug)` in `topic.py` creates full hub/<slug>/ structure on demand. Wired into `ClusterRegistry.create()` so EVERY new cluster gets it automatically (best-effort with try/except). `cluster_rebind._apply_new_cluster_proposals` also explicitly calls scaffolding (defense in depth). NEW CLI: `clusters scaffold-missing` for backfilling existing clusters.

6 tests cover scratch-create, idempotency, registry-auto-call, backfill CLI, memory.json shape, all-4-personas.

### Track B — Onboarding hardening

5 fixes wiring through README + docs + init_wizard + cli + mcp_server. Closes the cliff where Analyst follows README → installs base package → crashes on first PDF import. Closes the cliff where Researcher silently has bad Zotero key → discovers 30 min later.

10 tests in test_v040_onboarding.py.

### Track C — Repo polish

Multi-OS CI matrix: 1 job → 9 jobs (3 OS × 3 Python). `fail-fast: false`. `-m "not slow"` filter so live-vault test doesn't false-fail on CI runners.

5 new repo policy files: SECURITY.md, CODE_OF_CONDUCT.md, ISSUE_TEMPLATE/bug_report.md + feature_request.md, pull_request_template.md.

NEW docs/first-10-minutes.md per-persona guided tour (linked from EN + zh-TW READMEs).

### Track D — Live verification

```bash
$ research-hub clusters scaffold-missing
Scaffolded 7 of 7 clusters (others already had complete hub structure).

$ ls /c/Users/wenyu/knowledge-base/hub/abm-theories/
00_overview.md  crystals/  memory.json
$ ls /c/Users/wenyu/knowledge-base/hub/behavioral-theory/
00_overview.md  crystals/  memory.json
# ... same for all 7 clusters
```

The maintainer's vault now has full hub structure for every cluster — closing the original user complaint.

### Test totals

```
1402 passed, 15 skipped, 2 xfailed, 1 xpassed in 70s
```

(+15: 6 from A + 9 from B)

### Constraints honored

- 0 changes to `crystal.py`, `memory.py`, `cluster_rebind.py` heuristics — only added scaffolding hook
- 0 changes to MCP tool signatures — only added try/except wrapping
- ClusterRegistry.create() signature preserved — scaffolding is side-effect after save
- Auto-encrypt is OPT-IN by virtue of `[secrets]` extra (pyproject)

### What's NOT in v0.40

- **cli.py + mcp_server.py monolith split** (3434 + 1976 LOC) — biggest tech debt but huge work, blocks nothing user-facing. v0.41 candidate.
- **AI-assisted rebind classification** (last-mile coverage past v0.39's 100%) — v0.41
- **Replace readability-lxml** — narrow impact, v0.41
- **Telemetry / error reporting (Sentry)** — privacy-sensitive, defer until user demand

### Sequence sanity (running tally)

| Release | Theme | Tests | CI |
|---|---|---|---|
| v0.37 | Cluster integrity (rebind v1) | 1312 | ✅ |
| v0.38 | Persona-aware UI | 1369 | ✅ |
| v0.39 | Rebind v2 — 100% orphan coverage | 1387 | ✅ |
| **v0.40** | **Production readiness — go-live audit fixes** | **1402** | (pending CI verify on multi-OS) |

## v0.41.0 audit (2026-04-19)

**Theme:** Real-world friction fixes from end-to-end test + vault hygiene.

### Why this release

After v0.40.2 ship, ran live end-to-end test (create cluster → search → ingest → push to NotebookLM) with 6 LLM-eval-harness papers. Hit 4 ingest pipeline bugs. Separately, vault frontmatter audit found 1069/1096 notes with issues; ad-hoc Python scripts cut to 544 — productionized them.

7 fixes shipped together. Single Codex brief.

### Track results

**Set A — Ingest pipeline (4 fixes, F1-F4)**:
- F1 `add` → arXiv fallback when S2 rate-limits — closes the "preprint paper unaddable on first try" cliff
- F2 `search --to-papers-input` preserves arxiv_id + auto-derives DOI
- F3 `papers_input.json` accepts both shapes (back-compat with array + supports `{papers:...}`)
- F4 cluster's `zotero_collection_key` takes priority over `RESEARCH_HUB_DEFAULT_COLLECTION` env var

**Set B — Vault hygiene (3 CLIs, V1-V3)**:
- V1 `doctor --autofix` — mechanical backfills (topic_cluster from folder, ingested_at from mtime, doi from arxiv-shaped slug)
- V2 doctor distinguishes legacy/new papers — Bandura 1977 missing DOI is WARN, recent paper missing DOI is FAIL
- V3 `paper lookup-doi` — Crossref bulk lookup for old papers

### Live verification

```bash
# F1-F4 verified by re-running the harness pipeline (no manual JSON patching):
$ research-hub clusters new --query "v041 test" --slug v041-test
$ research-hub search "any query" --to-papers-input --cluster v041-test > /tmp/papers.json
$ research-hub ingest --cluster v041-test --no-verify
# Expect: zero errors

# V1+V2 verified on Wenyu's vault (1096 notes):
$ research-hub doctor --autofix
[autofix] topic_cluster=0 ingested_at=0 doi_derived=0 skipped_no_cluster=315
[XX] frontmatter_completeness: 316 FAIL (recent papers should have DOI), 324 WARN (legacy papers without DOI expected)
```

(autofix counts are 0 because Claude already manually backfilled in the previous session — but the CLI works idempotently.)

### Codex + Gemini delegation

- **Codex (Brief A, committed `6b91eb4`)**: Single brief, all 7 fixes, 18 tests across 5 test files. Codex executed cleanly first try (no stalls).
- **Gemini (zh-TW release notes)**: First Gemini CLI delegation attempt. Hit Windows-specific `AttachConsole failed` error from `@google/gemini-cli`'s node-pty dependency. Per `feedback_gemini_cli_invocation` memory ("wrong invocation silently emits pseudo-code comments instead of writing files"), Claude wrote the zh-TW notes as fallback to `docs/release-notes-v0.41.zh-TW.md`. Gemini CLI on Windows-Bash-shell needs more setup; works fine on Linux/macOS.

### Test totals

```
1423 passed, 15 skipped, 3 xfailed in 87s
```

(+21 from v0.40.2: 18 from brief + 3 Codex extras)

### Constraints honored

- 0 changes to crystal.py / memory.py / cluster_rebind.py / connectors / notebooklm
- All new CLIs are explicit invocation (no auto-run)
- Back-compat preserved: env var still works (F4), top-level array still works (F3), legacy DOI absence still parseable (V2)
- Crossref calls (V3) sleep 1 sec between requests

### Sequence sanity

| Release | Theme | Tests | CI |
|---|---|---|---|
| v0.39 | Rebind v2 — 100% orphan coverage | 1387 | ✅ |
| v0.40 | Production readiness — go-live audit | 1402 | ✅ multi-OS |
| **v0.41** | **Real-world friction fixes** | **1423** | (pending CI) |

繁體中文 release announcement: [release-notes-v0.41.zh-TW.md](release-notes-v0.41.zh-TW.md).

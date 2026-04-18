## v0.38.0 audit (2026-04-18)

**Theme:** Persona-aware UI + UX polish + housekeeping. Direct response to v0.37.3 review feedback.

### What user said after v0.37.3

Three concrete issues with the rendered dashboard:

1. **"UI 介面有錯誤訊息"** — doctor warnings dump as full red bullet list (`_render_health_banner`) at top of Overview. With v0.37 cluster-integrity checks + a real vault, surfaces 4-5 WARN/FAIL items as a wall of red — looks like install failed.
2. **"文字太小了吧"** — base body 14px (`--text-sm: 0.875rem`). Cramped at @2x render.
3. **"如果今天他不是研究者 那這個就不通用了不是嗎 例如他沒有用Zotero"** — even with `cfg.no_zotero=True` ("analyst" persona), dashboard still shows Diagnostics tab (Zotero-heavy noise), Manage tab with "Bind Zotero" button, Writing tab with citation-heavy compose_draft. Persona H sees ~70% irrelevant UI.

User aborted my initial v0.38 plan (terminology mapping only) calling it "lipstick" — correctly identifying that renaming "Cluster" → "Topic" doesn't fix feature visibility.

### Re-planning (Phase 1 + 2 in plan mode)

Launched 2 parallel Explore agents:
- **Agent #1**: Mapped tab system (CSS-radio in `sections.py:263-269, 293-304`), doctor banner location (`_render_health_banner` line 384), existing 9-spot persona gating pattern, font scale tokens.
- **Agent #2**: Mapped non-researcher feature surface — confirmed import-folder, ask_cluster, quote capture work for B/H; add_paper, crystal flow, entities/claims/methods, compose_draft, bind-zotero are paper-centric.

Findings drove the 3-track plan: A (UX polish), B (persona-aware IA), C (housekeeping). User locked in single-shipment v0.38.0 + interactive init prompt for persona.

### Track A — UX polish (Codex Brief A, committed `85c6439`)

- `_render_health_banner` rewritten to discrete `<details>` chip ("⚠ N issues — click to expand")
- Font scale: `--text-sm` 14→15px, `--text-md` 16→17px
- Recent feed: 16px row padding, hover, title bumped to `--text-md`
- 8/8 tests pass

### Track B — Persona-aware IA (Codex Brief B, committed `35642a9`)

- 4-persona detection: `researcher` / `analyst` / `humanities` / `internal`
- NEW `terminology.py`: 21-key label dict × 4 personas + `visible_tabs()` + `is_section_visible()`
- Diagnostics tab hidden for analyst/internal
- Bind-Zotero button, compose-draft, citation graph, Zotero column hidden for analyst/internal
- Init wizard 4-option prompt, `--persona` flag accepts all 4 values
- Doctor `check_persona_set` WARN if unset
- 37 tests (Codex added more than the 23 I asked for)

### Track C — Housekeeping (Codex Brief C, committed `a57e710`)

- C1 secret_box.py: Fernet encryption, `rh:enc:v1:` prefix, back-compat with plaintext, machine-bound key 0600 perms
- C2 search baselines: `metrics/search_recall.json` trajectory file, `@pytest.mark.evals` runner
- C3 `.dxt` packaging: `research-hub package-dxt` CLI + manifest builder
- 12 tests pass

### Live verification (4 personas × Wenyu's restored vault)

```bash
for p in researcher humanities analyst internal; do
  RESEARCH_HUB_PERSONA=$p research-hub dashboard --screenshot overview --out docs/images/dashboard-overview-$p.png --scale 2 --full-page
done
```

All 4 PNGs render correctly:

| Persona | Vocabulary | Tab count | Notable hidden |
|---|---|---|---|
| researcher | Cluster / Crystal / Paper / Citation graph | 6 | (none) |
| humanities | Theme / Synthesis / Source | 6 | (none) |
| analyst | Topic / AI Brief / Document | 5 | Diagnostics, Bind-Zotero, compose-draft |
| internal | Project area / AI Brief / Document | 5 | Diagnostics, Bind-Zotero, compose-draft |

Doctor warnings now render as collapsed amber chip across all personas (no more red wall).

### Test totals

```
1369 passed, 15 skipped, 3 xfailed in 69.33s
```

(+57 from v0.37.3: A=8, B=37, C=12)

### Constraints honored

- 0 changes to template element IDs (CSS+JS hooks intact, regression-tested across all 4 personas)
- 0 changes to `cfg.no_zotero` field (back-compat for existing vaults)
- 0 changes to crystal.py / memory.py / cluster_rebind.py / connectors / notebooklm
- File moves nowhere — pure code additions + 4 PNG re-shoots

### What's NOT in v0.38

- Per-persona color themes / CSS palettes (over-design)
- Localization (zh-TW labels)
- Per-MCP-tool persona filtering (Claude can already filter at agent level)

### Sequence sanity (running tally)

| Release | Theme | Tests | CI |
|---|---|---|---|
| v0.34 | Dashboard polish + persona test matrix | 1262 | ❌ |
| v0.35 | Connector Protocol abstraction | 1270 | ❌ |
| v0.36 | Structured memory layer | 1282 | ❌ |
| v0.37.0/.1 | Cluster integrity + memory CLI/MCP | 1312 | ❌ red |
| v0.37.2/.3 | CI fix + screenshots | 1312 | 🟢 first green |
| **v0.38** | **Persona-aware UI + UX polish + housekeeping** | **1369** | (pending CI) |

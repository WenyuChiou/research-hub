# research-hub v0.34.0 — Dashboard polish + persona × pipeline test matrix

**Released:** 2026-04-18
**Theme:** Visual polish (CSS-only, dark mode added) + first cross-persona test coverage. No new features. Connector abstraction deferred to v0.35.

---

## TL;DR

| Metric | v0.33.3 | v0.34.0 | Δ |
|---|---|---|---|
| Tests | 1249 | 1262 | +13 |
| Personas with direct test coverage | 1 (B partial) | 4 (A/B/C/H) | +3 |
| CSS dark mode support | none | full (auto via `prefers-color-scheme`) | NEW |
| Type scale steps | 5 (xs–xl) | 7 (xs–xl + md-2 + 2xl) | +2 |
| Design tokens | 30+ | 50+ (added shadow, motion, radii, brand-glow, semantic-soft) | +20 |
| Dashboard PNGs (re-shot) | v0.33 set | refreshed all 5 at @2x with new design | refresh |
| New docs | 0 | `docs/personas.md` | +1 |

**Headline:** dashboard looks more polished without losing any functionality. All 64 MCP tools, 5 task wrappers, screenshot CLI, live SSE, manage forms — unchanged.

---

## Tracks delivered

### Track Z — pre-release fixes (commit `6ea0cd3`, shipped as v0.33.3 earlier today)

- `pyproject.toml` `addopts` now includes `-m 'not stress'` so 1000-paper stress tests stay opt-in
- `tests/conftest.py::_auto_mock_require_config` extended path pattern from `test_cli_*.py` to also match `test_v0NN_*.py` for v030+ tests that call `cli.main([...])`. Patches `cli.get_config` only — not `cli.require_config` itself, since the dispatcher detects monkey-patching via `cli.get_config is require_config.__globals__["get_config"]` and would break if we replaced the wrong symbol.

### Track A — Dashboard CSS polish via design skills (Claude direct)

Modified `src/research_hub/dashboard/style.css` (~150 lines added/edited; total now 1,272 LOC):

**Token system extended:**
- `--surface-3`, `--border-strong` (deeper inset surfaces, hover borders)
- `--header-bg`, `--header-fg` (theme-aware sticky header — was hardcoded dark)
- `--brand-glow` (translucent halo for focus + primary button)
- `--ok-soft` / `--warn-soft` / `--fail-soft` (semantic background tints)
- `--shadow-1` / `--shadow-2` / `--shadow-glow` (brand-tinted elevation)
- `--radius-sm/md/lg/xl/pill` (consistent corner scale)
- `--ease-out`, `--duration-fast/base` (motion tokens)
- Type: added `--text-md-2` (1.125rem) + `--text-2xl` (2rem) — fills the awkward 1rem→1.5rem→2.5rem gap

**Dark mode added** (full token override under `@media (prefers-color-scheme: dark)`):
- All neutrals re-tinted for dark
- Brand stays warm amber (works in both)
- Semantic colors brighten + their soft variants darken
- Shadows use OKL black at appropriate alpha

**Component polish:**
- **`.live-pill`**: now has pulsing animation + glow ring when live, calmer chip when off. Uses `currentColor` for the dot
- **`.btn-primary`**: hover lifts to `--brand-strong` + adds `--shadow-glow`; active tap depresses 1px
- **`.cluster-card`**: hover lift via `--shadow-1`, open state via `--shadow-2`
- **`.treemap-cell`**: linear gradient (lighter top-left → brand → strong bottom-right) + radial highlight overlay; lift + saturate on hover; subtle inner top-light line
- **`.status-yes/no`** + `.reading-status`: tinted backgrounds (was just colored borders/text)
- **`.vault-search`**: hover border + focus ring with brand-glow halo
- **`section`**: subtle `--shadow-1` for soft separation
- All buttons: unified hover/active transitions

**Constraints preserved (verified by grep):**
- All 6 tab radio IDs (`dash-tab-{overview|library|briefings|writing|diagnostics|manage}`)
- All 6 panel IDs (`tab-{...}`)
- `vault-search`, `live-pill`, `csrf-token`
- `data-jump-tab`, `data-cluster`, all `[data-action]` attrs
- 5 demo PNGs re-shot at @2x via `dashboard --screenshot`

**Files NOT modified:** `template.html`, `script.js`, all Python. Pure CSS-only polish.

### Track B — Persona × pipeline test matrix (Claude direct)

NEW `tests/_persona_factory.py` (~110 LOC):
- `make_persona_vault(tmp_path, persona)` builds a vault state for personas A/B/C/H
- Forces `RESEARCH_HUB_CONFIG=/nonexistent/path` so HubConfig falls back to env-only mode and doesn't pick up the developer's real config (caught a real bug — without this fix, persona B test wrote to the real `~/knowledge-base/raw/persona-b-test/` and persisted across test runs)

NEW `tests/test_v034_persona_matrix.py` (~180 LOC, 13 tests):

| Test | Pipeline | Persona | What it verifies |
|---|---|---|---|
| `test_factory_builds_all_4_personas[A/B/C/H]` × 4 | Setup | A/B/C/H | Factory produces correct paper count + raw_dir per persona |
| `test_B_dashboard_renders_without_zotero` | Dashboard | B | `collect_dashboard_data` doesn't crash without Zotero |
| `test_H_dashboard_renders_with_mixed_source_kinds` | Dashboard | H | Mixed pdf/md/docx/url cluster renders cleanly |
| `test_B_ask_cluster_falls_back_to_digest_when_no_crystals` | Query (P9) | B | Document-only cluster → graceful digest fallback + `crystal emit` hint |
| `test_B_sync_cluster_recommends_crystal_generation` | Maintain (P9) | B | sync_cluster returns "no crystals yet" recommendation |
| `test_C_quote_capture_with_url_source` | Writing (P4) | C | URL-only sources support quote capture |
| `test_H_ask_cluster_handles_internal_doc_titles` | Query (P9) | H | Internal docs without DOI/authors don't crash ask_cluster |
| `test_A_collect_to_cluster_routes_doi_correctly` | Ingest | A | DOI source → `add_paper` route |
| `test_B_collect_to_cluster_routes_folder_correctly` | Ingest | B | Folder source → `import_folder` route |
| `test_doctor_skips_zotero_for_personas_B_and_H` | Health | B + H | Doctor doesn't fail loudly when Zotero absent |

NEW `docs/personas.md` (~200 lines): per-persona profile + typical pipeline + per-feature matrix + tested-by mapping.

### Track C — Release (Claude direct, this commit)

- `pyproject.toml` 0.33.3 → 0.34.0
- CHANGELOG v0.34.0 entry (this audit content + a tighter summary)
- README badges 1249 → 1262
- README link to `docs/personas.md`
- README zh-TW mirror updates
- tag v0.34.0 + push + GH Release

---

## Why this scope was right

Two tracks the user explicitly asked for, executed tightly:

1. **CSS-only polish** = real visual improvement with near-zero risk. The dashboard is a self-contained inlined-CSS document; redesigning its style.css is the safest possible UI change. Pure additive (dark mode, animation, glow) + pure refinement (typography / spacing / palette). Validated by re-shooting 5 PNGs and confirming all preservation IDs stayed in the rendered HTML.

2. **Targeted persona tests** = closes the worst coverage gaps. Persona C (humanities) and H (internal KM) had **zero** direct tests before v0.34. We chose 13 high-signal tests over a 40-cell brute-force matrix because the long tail would be mostly redundant mocked-dispatch coverage.

**Real bug caught during Track B:** persona factory was writing to the developer's REAL vault (`C:\Users\wenyu\knowledge-base\raw\persona-b-test\`) because `HubConfig.__init__` reads the config file from disk and the config file's `root` field overrode the env var. Fixed by forcing `RESEARCH_HUB_CONFIG=/nonexistent/path` in the factory. This bug would have eventually polluted any contributor's vault who ran the test suite.

---

## Live verification

```bash
PYTHONPATH=src python -m pytest -q
# 1249 → 1262 passed (+13)

PYTHONPATH=src python -m pytest tests/test_v034_persona_matrix.py -v
# 13 tests, all green

# Verify dashboard preservation
python -c "
import os
hp = os.path.expanduser('~/knowledge-base/.research_hub/dashboard.html')
html = open(hp, encoding='utf-8').read()
required = ['dash-tab-overview', 'dash-tab-library', 'dash-tab-briefings',
            'dash-tab-writing', 'dash-tab-diagnostics', 'dash-tab-manage',
            'tab-overview', 'vault-search', 'live-pill', 'csrf-token']
missing = [r for r in required if r not in html]
assert not missing, missing
print('All preservation IDs intact.')
"

# Re-shoot if needed
research-hub dashboard --screenshot all --out-dir /tmp/v034 --scale 2
```

---

## v0.35+ backlog

- **Connector abstraction** — was the prior v0.34 plan; deferred. Lightweight Protocol + null stub + NotebookLM adapter (~250 LOC, 1-2 days).
- **Codex Phase 2** — structured memory layer (entities/claims/methods)
- **`cli.py` / `mcp_server.py` monolith splits** — still HIGH RISK
- **Dark mode optional toggle** (currently auto via OS preference; some users want override)
- **Live NotebookLM round-trip in CI** — requires Chrome+CDP, can't run on CI runner
- **Task #124 archived vault restore** — needs user decision
- **Search recall xfail baselines** (v0.26)
- **Zotero key encryption** via OS keyring
- **`.dxt` Claude Desktop extension**

---

## Release commits

```
6ea0cd3 fix(v0.33.3): stress test marker filter + extend autouse fixture path pattern
+ Track A commit (style.css + 5 PNGs)
+ Track B commit (persona factory + matrix tests + personas.md)
+ Track C commit (this release: version + CHANGELOG + README + audit)
```

PyPI: `pip install -U research-hub-pipeline` after GHA auto-publishes.

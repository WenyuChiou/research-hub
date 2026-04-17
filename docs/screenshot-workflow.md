# Screenshot workflow

How to (re)generate the dashboard screenshots in `docs/images/` for README, audit reports, or other documentation.

## Quick re-shoot

```bash
# Pre-req: install Playwright + chromium
pip install 'research-hub-pipeline[playwright]'
playwright install chromium

# Re-shoot all 5 dashboard tabs at Retina-grade @2x:
research-hub dashboard --screenshot overview     --out docs/images/dashboard-overview.png         --scale 2
research-hub dashboard --screenshot library      --out docs/images/dashboard-library-subtopic.png --scale 2
research-hub dashboard --screenshot manage       --out docs/images/dashboard-manage-live.png      --scale 2
research-hub dashboard --screenshot briefings    --out docs/images/dashboard-crystals.png         --scale 2
research-hub dashboard --screenshot diagnostics  --out docs/images/dashboard-diagnostics.png      --scale 2
```

Each PNG comes out at **2880×1800** (1440×900 viewport × 2× device pixel ratio). GitHub auto-downscales for non-Retina displays; Retina/HiDPI users see crisp 2× pixels.

## Tabs available

| `--screenshot <tab>` | Renders |
|---|---|
| `overview` | Treemap, storage map, recent additions |
| `library` | Cluster cards with sub-topics, papers grouped by source kind |
| `manage` | CRUD forms (create cluster, label paper, etc.) with live execution |
| `briefings` | NotebookLM briefs + crystal answers |
| `writing` | Quotes, drafts, citations |
| `diagnostics` | Doctor checks, drift alerts, sync status |

`crystal` (singular) is a legacy alias for `briefings` since crystals render in that tab.

## Custom dimensions

```bash
# Bigger viewport (e.g. for poster prints)
research-hub dashboard --screenshot overview --out big.png \
    --viewport-width 1920 --viewport-height 1200 --scale 3
# Result: 5760×3600 native — print quality

# Smaller for inline blog images
research-hub dashboard --screenshot overview --out small.png \
    --viewport-width 1024 --viewport-height 768 --scale 1
# Result: 1024×768 native

# Capture entire scrolled page (for tabs with long content)
research-hub dashboard --screenshot library --out long.png --full-page
```

## Batch capture

```bash
research-hub dashboard --screenshot all --out-dir /tmp/all-tabs/ --scale 2
# Writes /tmp/all-tabs/dashboard-{overview,library,briefings,writing,diagnostics,manage}.png
```

## Obsidian Graph view (still manual)

Obsidian has no PNG export API. Workflow:

1. Open Obsidian (point at your research-hub vault)
2. Open Graph view (cmd/ctrl+G)
3. Wait for layout to settle (~5-10 seconds for the force-directed simulation)
4. Use OS screenshot tool — full-window capture preferred:
   - **macOS:** cmd+shift+4 then space then click window
   - **Windows:** Snipping Tool → window snip
   - **Linux:** `gnome-screenshot -w` or `flameshot gui`
5. Crop to graph area only
6. Save to `docs/images/obsidian-graph.png`

If you re-color the graph (`research-hub vault graph-colors --refresh`), screenshot AFTER the refresh so the colors match current label assignments.

## When to re-shoot

- Every release that changes any visible UI (style.css, template.html, or section rendering)
- After major data changes (e.g., demo cluster added/removed) so the Library tab matches what users will see
- If GitHub starts showing artifacts (file too small, blurry on Retina)

## Troubleshooting

**`PlaywrightNotInstalled`**
Run `pip install 'research-hub-pipeline[playwright]' && playwright install chromium`.

**Screenshot is just the overview tab even though I asked for "manage"**
The label-based tab click can fail silently if the dashboard template changes. Check the actual tab IDs:
```bash
grep -oE 'id="dash-tab-[a-z]+"' .research_hub/dashboard.html | sort -u
```
Then update `TAB_TARGETS` in `src/research_hub/dashboard/screenshot.py` if they've drifted.

**Headless chromium fails to launch on Linux**
You may need: `apt install libgbm1 libnss3 libgtk-3-0` then re-run `playwright install chromium`.

**Output PNG is too dark / has wrong colors**
The dashboard uses `prefers-color-scheme`. Headless Chromium defaults to light mode. To force dark mode, use the underlying Playwright API (not exposed via CLI) or temporarily flip the OS preference before running.

# README verification and historical evidence

This page preserves the bounded rehearsal and installation context referenced by the README. It is evidence for the dated runs described below, not a statement that every current installation or scientific workflow has been accepted.

## Cold-start fresh-venv install & three-integration E2E (2026-11-26)

Source branch `docs/workstation-onboarding-and-cold-e2e` (on top of `dda5a4e`, adding base `cryptography>=42.0.0,<47.0.0` so clean `pip install -e .` installs support encrypted local credential saving out of the box, plus aligning `README.md`, `README.zh-TW.md`, `docs/setup.md`, and `docs/workspace-guide*.md` with the v2 workstation):

- **Isolated fresh-venv installation & CLI onboarding (Windows 11, Python 3.14):** Installed into a brand-new virtual environment via plain `pip install -e .` (no optional extras); `pip check` exited `0` with `cryptography` active. Verified `research-hub init --vault ... --persona analyst --non-interactive --no-browser`, `research-hub clusters new`, `research-hub import-folder`, `scripts/library_snapshot.py` (`2` Markdown notes indexed read-only, `body_read: false`, `vault_written: false`), and `research-hub doctor --json`. Observed CLI limitation during the rehearsal: `research-hub ingest` still requires `RESEARCH_HUB_NO_ZOTERO=1` (or a cluster collection key) when `persona` is `analyst`.
- **Cold-start empty workspace & loopback three-integration browser E2E (`1440×900`, `0` console errors, `0` page errors, `0` HTTP ≥ 400 on the clean verification pass):**
  - Started from an empty workspace (`載入示範專案` -> inspected `review-demo` Goldberg limits), created blank-ID project `llm-agent-evaluation-simulation`, added 4 papers via `+ 新增文獻` (2 full-text, 2 abstract-only), curated categories and scoped `#` labels, tested Include/Exclude triage, `移出清單`/`復原文獻`, tag + year filtering, `閱讀`/`總表`/`矩陣` views, Quick Cite (`.bib`, `.ris`, `APA`), Evidence Blind-Spot Radar updates (`22%` -> `66%` robustness), Light/Dark themes, `Ctrl+K` Command Palette, and read-only Obsidian snapshot loading.
  - Verified all three connections & Sync Hub actions live in `⚙ 設定 → 連線與同步`: **Zotero** (`connected_local_and_web`, `rh:enc:v1:` Fernet-encrypted API key saved to `config.json`, `Dry-run` `3` new / `1` duplicate skipped -> confirmed write `3` items created -> idempotent `Dry-run` `0` new / `4` duplicates), **NotebookLM** (`authenticated` via imported storage state + `4`-source `.md`/`manifest.json` bundle), and **Obsidian** (`valid` read-only vault check + `4` `.md` notes and `.base` export confined to `.research/exports/`).
- **Bounded scope:** Zotero API reads/writes and NotebookLM session health probes were executed against an isolated local loopback HTTP harness and test state file rather than live third-party Zotero or Google accounts; no external cloud accounts were mutated.

## Workstation Light/Dark showcase & sync-hub captures (2026-11-26)

Source revision `b2ca1ad` (merging PR #309 on top of `45c5fcc`, adding HD brand emblems and status LEDs, Light/Dark/System themes, the 4-tab Settings Center, Connected Software Sync & Export Hub, 4-stage pipeline stepper, year/coverage analytics, Evidence Blind-Spot Radar, Literature × Theme/Evidence Synthesis Matrix, and `Ctrl+K` / `⌘K` Command Palette):

- Captured 10 bilingual Retina screenshots (`2880×1800` PNGs at `2×` scale from a `1440×900` Chromium viewport) on Windows 11 against an isolated `WorkspaceServer` on ephemeral port `8791` with **0 console errors**, **0 page errors**, and **0 HTTP ≥ 400 responses**:
  - `docs/images/workspace-ui.{en,zh-TW}.png`: offline `review-demo` teaching project in Light Mode with example `Foundations`/`Algorithms` curations and scoped `#domain:*`/`#method:*`/`#risk:*` labels; Goldberg (1991) retains its authentic demo limits (`Unverified`, `Coverage unknown`, `No summary saved`).
  - `docs/images/showcase-overview-radar.{en,zh-TW}.png`, `docs/images/showcase-dark-desk.{en,zh-TW}.png`, `docs/images/showcase-dark-matrix.{en,zh-TW}.png`, and `docs/images/showcase-settings-sync.{en,zh-TW}.png`: isolated 7-paper offline showcase fixture (`llm-decision-showcase`, using real public bibliographic metadata with illustrative reading-scope, screening, and claim records plus exercised local NotebookLM `.md` pack and Obsidian `.md + .base` exports inside a temporary directory).
- No private user files, external Zotero API writes, or live NotebookLM cloud sessions were used during capture; showcase fixtures illustrate UI capabilities rather than completed scientific reviews or live external provider acceptance.

## Redesigned workspace UI captures & cold-start E2E (2026-11-26)

Source revision `45c5fcc` (merging PRs #299–#304, covering the light-surface Reading Desk, Master Literature Table with category summary cards and Markdown/CSV export, collapsible Settings modal, compact `EN`/`中` toggle with `localStorage` persistence, append-only `source_curation` category/metadata editing, and 1-click **Load sample project**):

- Verified on Windows 11 with Python 3.14 from an installed source-built wheel (`research-hub-pipeline` built from `45c5fcc`) against a brand-new empty workspace directory.
- Exercised end-to-end in a real browser (`1440×900`): clicked **Load sample project**, opened `review-demo` Literature, edited categories (`Foundations`, `Algorithms`) and relevance notes via **Category & details**, verified **Master table** category summary strip and table rows, toggled `中` (`zh-TW`) and verified persistence across reload, created a fresh project with blank Project ID (auto-generated slug, zero HTML5 regex errors), and verified the empty-state **Add or search your first paper** CTA. Observed **0 console/page errors** and **0 HTTP ≥ 400 responses**.
- Captured fresh authentic bilingual screenshots (`docs/images/workspace-ui.en.png` and `docs/images/workspace-ui.zh-TW.png`, `1024×640` PNGs captured from a `1440×900` browser viewport) directly from the offline account-free `review-demo` teaching project (no user-private files or provider credentials).
- Cross-platform automated test matrix (`ubuntu-latest` Python 3.10–3.14, `macos-latest` Python 3.12, `windows-latest` Python 3.12, and installed-wheel Playwright browser checks) passed on `45c5fcc`.
- This is bounded UI and local-workspace engineering verification, not live provider verification, scientific validation, or a new PyPI release claim.

## Source demo first task (2026-11-07)

The README now pins merged source `1f0726a7e92a1231e633963f17236a2f5c1eab8f`
(tree `27febee56d7b32588e961cb70b6947ed1a9167ad`). This includes the launcher,
Unicode input, and task-bound working-summary fixes merged in PRs
[#250](https://github.com/WenyuChiou/research-hub/pull/250),
[#251](https://github.com/WenyuChiou/research-hub/pull/251), and
[#252](https://github.com/WenyuChiou/research-hub/pull/252). The previous README
pin predates those fixes. The historical guide and producer manifest retain
their own dated revisions.

On Linux with Python 3.12.14:

- The normal `python -m research_hub project demo --root PATH --json` command
  created two projects in separate new roots from the exact source checkout
  and from an already installed wheel. Existing dependency environments were
  reused; a clean dependency installation was **not** repeated.
- All 294 packaged files under `research_hub/` matched the pinned source and
  installed files byte for byte. The locally built wheel SHA-256 was
  `4ab2b123736404397077d45f5372f11d3895a1ef579686ae7f9d09637d3aad15`.
  This is a source-built wheel, **not** evidence about the published PyPI 1.2.0
  package or a new release.
- The unchanged installed CLI served a fresh teaching demo at
  `http://127.0.0.1:8765/app/` using `serve --workspace --root PATH --no-browser`.
  Actual Chromium interaction selected `review-demo`, opened Literature, and
  inspected the Goldberg source in English and Traditional Chinese. Both
  locales showed two seed references, DOI `10.1145/103162.103163`, unverified
  identity, unknown coverage, and no saved summary. Project switching and
  page reload returned to the same source data. The server was stopped with
  `Ctrl+C` after inspection.
- `summation-demo` has no source records, so its Literature list is empty. The
  first task now names `review-demo` rather than offering either project for
  the literature walkthrough. Neither demo supplies source text or summaries;
  example screening records do not mean a human has read or verified a source.

This is bounded first-run engineering verification, not a Windows/macOS
installation test, live provider run, full-text/scientific validation, or human
acceptance. No original-source links were opened and no research-provider
services were used. The historical README screenshots below the setup section remain dated;
this change does not claim the full visual redesign in issue
[#231](https://github.com/WenyuChiou/research-hub/issues/231) is complete.

<a id="current-source-and-environment-notes-2026-10-28"></a>

## Historical source and environment notes (2026-10-28)

The README source commands at that date identified `c1ab382e1bc4bfdb1d5df6a230d1ab4509a50d2a`. On Linux with Python 3.12.14, an initially clean isolated virtual environment completed `pip install -e .` after an interrupted installation was retried, passed `pip check`, and imported the module from a source tree matching that commit. CLI help ran, the demo created two teaching projects, and server and HTTP client subprocesses within one shell invocation returned HTTP 200 for `/app/`. This was not browser visual acceptance, Windows or macOS installation, or a provider/scientific workflow validation. An independent clean Linux Python 3.12.14 virtual environment installed the earlier `fe8a6b833febd5d6bb397f9924c2e379863bacee` source revision with `pip install -e .`, passed `pip check`, created the two demo projects, and returned HTTP 200 for `/app/`. This was not browser visual acceptance, a macOS or Windows installation, or a provider/scientific workflow validation. At the earlier source revision `14ddc07024f866a5a4f535f5e73185cc7ce69ea1`, a Linux Python 3.14 synthetic demo and same-process HTTP 200 were exercised with test guards and an older, unused NotebookLM dependency; this was not a clean installation or visual verification. At that same earlier revision, on one Windows Python 3.14 environment the source was fetched, CLI help and Chrome HTTPS worked, but demo creation encountered `os.link` / `WinError 5`. Its NTFS cause is unknown; this is not a claim that Windows is universally unsupported.

In a clean Linux Python 3.12 environment, the published PyPI 1.2.0 wheel installed and `pip check` passed, but `research-hub dashboard --sample` in a fresh HOME exited with `research-hub is not initialized`. Setting `RESEARCH_HUB_ROOT` to an existing directory under HOME allowed the sample to generate HTML; it did not open a browser without `--open`. The wheel did not expose the newer `project` command.

Workspace [PR #135](https://github.com/WenyuChiou/research-hub/pull/135) and writing adapter [PR #17](https://github.com/WenyuChiou/academic-writing-skills/pull/17) were merged. The original README also linked this [immutable capability-baseline version](https://github.com/WenyuChiou/research-hub/blob/c6ef19313ab69a85e041f4a86e4b9cb19229c138/docs/capability-baseline.md).

The last recorded NotebookLM authentication attempt failed and has not been reverified; see [troubleshooting](notebooklm-troubleshooting.md).

The older workspace preview pin `6381dfa7d474dd27cd4adb33f0f59ea8ec395150` is retained in the [historical capability baseline](capability-baseline.md) and [workspace guide](workspace-guide.md); its observations do not establish behavior of the newer source, and newer observations do not prove the older pin. The source version does not establish which features exist in a published wheel or in an AI host. See [workspace verification](workspace-verification.md) for earlier dated evidence.

## Native literature discovery rehearsal (English source)

### Stage 1

In a native AI agent that can read the research-hub skill and has public search/read tools, start with one request:

> Find literature on LLMs simulating human decisions.

The agent should choose a sensible initial scope, search/read available sources, and return a short list with original links, relevance, versions, and reading/access limits—not ask you to fill a research form or write JSON. Zotero, Obsidian, NotebookLM, and Hub storage are optional.

A real cloud-native rehearsal on 2026-10-26 returned three distinct starting points:
- [Aher et al. (2023)](https://proceedings.mlr.press/v202/aher23a.html): simulation of group behavior from existing experiments.
- [Park et al. (assessed 2024 preprint v1)](https://arxiv.org/abs/2411.10109v1): personalized agents grounded in human interviews; newer versions were not read in this rehearsal.
- [Gao et al. (2025)](https://doi.org/10.1073/pnas.2501660122): mismatched decision distributions as a validity check. The rehearsal read a DOI-matched public PDF mirror, not a successfully retrieved publisher PDF.

Then, if useful, say:

> Focus on economic decisions and compare the human baselines and evaluation methods.

Search snippets are not full-paper reading; human-like outputs are not evidence that human participants can be replaced. The agent retains unavailable sources and unresolved questions rather than inventing coverage.

**What was actually exercised:** one request → native search and original-text sections → a short, qualified result. This was a cloud-native run after directly reading the skill—not verification of Codex/Claude Code installation, automatic skill triggering, every host, Hub saving, or UI opening. No JSON, CLI, additional integration/provider account, or Stage 2 was required in that rehearsal.

For an optional visual handoff, the agent—not the researcher—can organize observations and use an already available, authorized Hub interface to save them. A confirmed save returns an exact saved-result link. The [saved-result contract](contracts/native-discovery-view.md) separates this path from native research: current secure file persistence/viewing is POSIX-only, Windows is not yet supported, and opening a result does not authenticate research or start provider writes.



## 原生文獻探索試跑（繁體中文原文）

### Stage 1

在能讀取 research-hub skill、且有公開搜尋／閱讀工具的原生 AI agent 中，可以先說一句：

> 幫我找 LLM 模擬人類決策的文獻。

Agent 應先採用合理範圍，搜尋與閱讀可取得來源，再回傳有原文連結、相關性、版本及閱讀／存取限制的短清單；不是要求你先填研究表單或寫 JSON。Zotero、Obsidian、NotebookLM 與 Hub 儲存都是選用。

2026-10-26 的真實雲端原生試跑得到三種不同起點：
- [Aher et al.（2023）](https://proceedings.mlr.press/v202/aher23a.html)：從既有實驗看群體行為模擬。
- [Park et al.（本輪核讀 2024 預印本 v1）](https://arxiv.org/abs/2411.10109v1)：從真人訪談看個人化代理；新版未在本輪閱讀。
- [Gao et al.（2025）](https://doi.org/10.1073/pnas.2501660122)：用不匹配的決策分布檢查模擬有效性。本輪讀取的是核對 DOI 的公開 PDF 鏡像，不是成功取得出版社 PDF。

需要續做時，再說：

> 聚焦經濟決策，幫我比較真人基準和評估方法。

搜尋摘要不等於全文閱讀，「像人」也不等於「可取代真人」。Agent 應保留取不到的來源與未決問題，不捏造覆蓋率。

**實際驗證範圍：**一句請求 → 原生搜尋與原文段落閱讀 → 有限制說明的短清單。這是直接讀取 skill 後的雲端原生實跑，不代表 Codex／Claude Code 安裝、技能自動觸發、所有宿主、Hub 儲存或 UI 開啟已驗收。本輪不需要 JSON、CLI、整合帳號或 Stage 2。

若另選視覺化交接，應由 agent 整理觀察、使用已可用且獲授權的 Hub 介面儲存，不讓研究者重複輸入。確認儲存後會回傳確切成果連結。[已儲存成果契約](contracts/native-discovery-view.md) 將此路徑與原生研究分開：目前安全檔案儲存／檢視僅支援 POSIX，Windows 尚未支援；開啟成果不驗證研究真實性，也不啟動外部服務寫入。

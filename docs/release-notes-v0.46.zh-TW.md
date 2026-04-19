# research-hub v0.46.0 — Lazy mode（一句話搞定）

**2026-04-19**

使用者反饋：「因為大家都很懶 我希望能夠在一些功能做到 打一句話搞定」。v0.46 把最常用的工作流濃縮成 4 個一行指令。

## 4 個 lazy 指令

`research-hub auto "topic"` — 一條指令搞定 search + ingest + NotebookLM brief 整套。

`research-hub ask "Q" --cluster X` — 對既有 notebook 問問題（v0.42 加的，這次 README 推到顯眼位置）。

`research-hub tidy` — vault 維護一條龍（doctor autofix + dedup rebuild + bases refresh + cleanup preview）。

`research-hub cleanup --all --apply` — GC 累積垃圾（bundles + debug logs + 舊 artifacts）。

## `research-hub auto` 細節

之前要打 7 個指令：

```
clusters new → search > papers.json → ingest → notebooklm bundle → upload → generate brief → download brief
```

現在一句：

```bash
research-hub auto "harness engineering for LLM agents"
```

實時輸出每個階段：

```
[OK] cluster        harness-engineering-for-llm-agents (created)
[OK] search         8 results from arxiv,semantic_scholar (3.2s)
[OK] ingest         6 papers in raw/harness-engineering-for-llm-agents/
[OK] nlm.bundle     6 PDFs (24 MB)
[OK] nlm.upload     6 succeeded
[OK] nlm.generate   brief generation triggered
[OK] nlm.download   1,243 chars saved
Done in 47s.
```

旗標：

- `--max-papers N`（預設 8）
- `--no-nlm`（跳過 NotebookLM 4 步，只做 Zotero + Obsidian）
- `--dry-run`（印出 plan 不執行）
- `--cluster X`（用既有 cluster slug，不重新 slugify topic）
- `--cluster-name "Display"`（覆寫顯示名稱）

任一階段失敗就停下來告訴你失敗在哪裡，從那一步可以手動接著跑。

## `research-hub cleanup` 變成真正的 GC

v0.45 為止 `cleanup` 只去重 hub 頁面的重複 wikilink，不碰真正會累積的東西：

- `.research_hub/bundles/` — 10+ 個 bundle 資料夾累積，每個 ~20 MB PDF 副本（你目前有 72 MB 的 stale bundle 等清）
- `.research_hub/nlm-debug-*.jsonl` — 每次 NotebookLM 操作都新增一筆
- `.research_hub/artifacts/<slug>/{ask-*.md, brief-*.txt}` — 每次 ask/brief 操作都新增

v0.46 變成真正的 GC：

```bash
research-hub cleanup --bundles --apply               # 每個 cluster 留最近 2 個 bundle
research-hub cleanup --debug-logs --older-than 30    # 30 天前的 debug log 全刪
research-hub cleanup --artifacts --keep 10           # 每個 cluster 留最近 10 個 ask/brief
research-hub cleanup --all --apply                   # 三個一起跑 + 真的刪
```

預設 dry-run（只印出會刪的清單跟總大小）。`--apply` 才真的刪。

舊的 wikilink 去重行為保留，加 `--wikilinks` 旗標叫得出來。

## `research-hub tidy` 一條龍維護

```bash
research-hub tidy
```

跑這 4 個 sub-step：

1. `doctor --autofix` — 機械式 frontmatter 補齊
2. `dedup rebuild --obsidian-only` — 重建 dedup index
3. `bases emit --force` 對每個 cluster — v0.43 Bases dashboard 重新產生
4. `cleanup --bundles --debug-logs --artifacts --dry-run` — preview 不真的刪

輸出：

```
[OK] doctor    16 checks, 12 OK, 4 INFO, 0 WARN
[OK] dedup     767 DOIs, 1101 titles
[OK] bases     8 clusters refreshed
[OK] cleanup   would free 187 MB (8 stale bundles)  -- run `research-hub cleanup --all --apply` to apply
Done in 6s.
```

`--apply-cleanup` 把 cleanup 也真的執行。

## `doctor` 修復 chrome 偵測

v0.45 為止 `doctor` 會說 `chrome: Not found`，即使你的 NotebookLM 完全運作正常。原因：v0.42 把 cdp_launcher 改成 patchright，但 doctor 還在用刪掉的 `cdp_launcher.find_chrome_binary` 走硬編碼路徑。

v0.46 改用 patchright probe（跟 NotebookLM 真實使用同一個機制）：

```
[OK] chrome: Available via patchright channel='chrome'
```

如果真的找不到 Chrome（例如沒裝），會顯示 `INFO` 等級訊息加安裝建議，**不再顯示嚇人的 `WARN`**。

## 統計

- 測試：1520 → **1553**（A1: 8、A2: 7、A3: 4、A4: 2 + 12 個原本就有的 doctor）
- LOC：~+550 程式 + ~150 文件
- 4 個新檔案：`src/research_hub/{auto, cleanup, tidy}.py` + `docs/lazy-mode.md`
- **零新設定**：所有新指令用既有的 NotebookLM session + 既有 Zotero credentials

## 設計決策

**為什麼 `tidy` 預設不真的清理？** 因為刪檔是破壞性操作。`tidy` 給你 preview，看完滿意再跑 `cleanup --all --apply` 或 `tidy --apply-cleanup`。

**為什麼 `auto` 預設包含 NotebookLM？** 因為這是核心使用情境。如果只想 ingest 不想推 NLM，加 `--no-nlm`。

**為什麼不直接整合 LLM API 來自動產生 crystals？** 因為 research-hub 從一開始就是 provider-agnostic——你用什麼 LLM 都行。整合特定 API 違反這個原則。

## 接下來（v0.47+ 候選）

- PDF embed 在 paper note（從 Zotero storage dir 自動拉路徑）
- `obsidian-cli` 整合（`tidy` 結束後自動 reload Obsidian vault）
- JSON Canvas 引用圖匯出
- Mega-cluster 拆分 helper（執行已產生好的 split-suggestion 報告）

## 碎念

這次嘗試把 code 工作交給 Gemini 做。結果 2 個 track 成功（`auto` + `cleanup`），第 3 個（`tidy`）跟 2 份 docs（`lazy-mode.md` + 這份 zh-TW 釋出筆記）都因為 `QUOTA_EXHAUSTED` fall back 給 Claude 自己寫。Gemini 的程式品質意外地不錯（雖然有些 import 路徑要修）——但 daily quota 還是個現實限制。

下次 batch 太多 Gemini code 任務之前，先看一下還剩多少 quota。

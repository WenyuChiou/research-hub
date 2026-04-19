# research-hub v0.44.0 — Dashboard UI 補齊 + README 走查

**2026-04-19**

v0.42 跟 v0.43 接連 ship，但 post-ship audit 抓到 dashboard UI **半套**：

- v0.42 把 `notebooklm-bundle/upload/generate/download` 加進 executor whitelist 但**沒寫 button**——後端認得這些指令，前端沒地方點
- v0.43 的 `ask` / `polish-markdown` / `bases-emit` **連 whitelist 都沒進**
- README 對 `serve --dashboard` 只有一行字，沒有走查、沒有截圖、沒有「按哪個按鈕做什麼」

v0.44 把這些洞補完。**零新設定**——所有新按鈕都用現有的 NotebookLM session（`notebooklm login` 一次）+ 現有 Zotero 認證。

---

## 新增 — Manage tab 7 個動作

每個 cluster 卡片上多了：

### NotebookLM 區塊（v0.42）
- 📦 **Bundle papers** — 收集所有 PDF 變成 NotebookLM-ready bundle
- ⬆️ **Upload to NotebookLM** — 把 bundle 推上去（可選 visible browser 模式）
- ✨ **Generate artifact** — 下拉選 brief / audio / mind_map / video
- ⬇️ **Download brief** — 抓最新 briefing 到 `.research_hub/artifacts/`
- ❓ **Ask** — 問問題（textarea + 可選 timeout）

### Obsidian 區塊（v0.42 + v0.43）
- ✨ **Polish markdown** — 升級論文筆記到 callout + block-ID（dry-run / apply toggle）
- 📊 **Emit .base dashboard** — 自動產生 cluster Bases dashboard（可選 force overwrite）

每個表單：
- Server mode (`serve --dashboard`)：直接執行、SSE 回傳結果
- Static mode (`dashboard`)：copy CLI command 到 clipboard

---

## 新增 — NotebookLM Library tile

每個 cluster 卡片旁邊多了一個 NotebookLM artifacts 小表格，讀 `nlm_cache.json::artifacts`，顯示已下載的 brief / audio / mind_map / video，附 deep-link 直接打開 NotebookLM 跟本地檔案。

如果還沒下載任何 artifact，顯示「⬇️ Download brief」一鍵按鈕。

---

## 新增 — `docs/dashboard-walkthrough.md`

完整 UI 走查：

1. **dashboard 是幹嘛用的** — Zotero / Obsidian / NotebookLM 三系統的 fusion view
2. **Static vs Live 模式差異**
3. **5 tab 逐個介紹** — Overview / Library / Briefings / Diagnostics / Manage
4. **Daily workflow 食譜**（按 persona 分）：
   - Researcher: 早上開 dashboard → 看 Diagnostics → ingest 新論文 → Manage tab → 上傳 NLM → 問問題
   - Analyst: 搜尋列 → ingest URL → polish-markdown → emit .base
5. **v0.42 動作詳解**（NotebookLM 7 個按鈕）
6. **v0.43 動作詳解**（Obsidian polish + Bases）
7. **NotebookLM artifact tile** 怎麼找 brief / audio
8. **Troubleshooting** — 連到 `notebooklm-troubleshooting.md`

README `serve --dashboard` 段落改寫成簡介 + 連到這份走查。

---

## 設計約束

| 規則 | 落實 |
|---|---|
| 零新設定 | 所有按鈕用現有 `notebooklm login` session + 現有 Zotero credentials |
| 不影響現有 button | rename / merge / split / bind-zotero / bind-nlm 全部維持原狀，新動作放在 `<details>` 區塊下 |
| Static mode 仍可用 | JS handler 對應每個新 action，沒有 server 也能 copy CLI |
| 測試 | 15+ 新 tests 涵蓋每個 builder 的所有分支 |

---

## 接下來（v0.44 ship 完）

直接做使用者本來的目標：**把 11 篇 harness cluster 推上 NotebookLM 完整跑一輪**。

```bash
# 在 dashboard Manage tab 直接點：
# 1. ✨ Generate artifact → brief    （新 11 篇全到位的 brief）
# 2. ⬇️ Download brief
# 3. ❓ Ask "What are the unresolved tensions across the 11 papers?"
# 4. 📊 Emit .base dashboard --force （reflect 新增的論文）
```

整個流程不需要打 CLI，全部在 `http://127.0.0.1:8765/` 上完成。

---

## 統計

- 測試：1492 → 1507+
- LOC：~+480 程式 + ~150 docs
- 檔案：`dashboard/{executor,manage_commands,sections}.py + script.js + README.md + new docs/dashboard-walkthrough.md + tests/test_v044_dashboard_actions.py`
- 沒有破壞性變更
- 安裝指令完全不變

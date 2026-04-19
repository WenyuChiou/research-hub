# research-hub v0.43.0 — kepano/obsidian-skills 整合 + 11 篇 NotebookLM 壓力測

**2026-04-19**

v0.42 雖然修好了 NotebookLM 上傳穩定性，但 [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills)（25.3k⭐, MIT, Obsidian CEO Steph Ango）整套 5 個 skills 我們只採用了 callouts + block-IDs 那一小塊。v0.43 把剩下的 4 個整合進來，順便用 11 篇論文壓力測 v0.42 的 NotebookLM 層。

---

## Track 1：v0.42 NotebookLM 11 篇壓力測

`llm-evaluation-harness` cluster 從 6 篇擴增到 11 篇——加了 5 篇新的 harness 論文（VeRO、AgentSPEX、TDAD、AEC-Bench、ALaRA）。

```
research-hub notebooklm bundle --cluster llm-evaluation-harness
research-hub notebooklm upload --cluster llm-evaluation-harness
→ 11 succeeded, 0 failed, 0 skipped
→ retry_count: 0
```

**v0.42 patchright + persistent context 在 11 篇規模下完全沒有 retry**——每篇都是第一次嘗試就上傳成功。

**雙軌交叉驗證**：同一個問題分別問 `research-hub notebooklm ask`（v0.42）和 `mcp__notebooklm__ask_question`（社群 5.9k⭐ MCP），兩邊回答都歸納出**相同 3 個研究 thread**（evaluation / memory / security）以及**相同的代表論文**（vla-eval+VeRO / M\* / SafeHarness）。v0.42 的 ask 跟參考實作行為一致。

完整驗證 log：[`docs/validation_v0.43.md`](docs/validation_v0.43.md)。

---

## Track 2：defuddle URL 萃取（替代 readability-lxml）

新模組 `src/research_hub/defuddle_extract.py`——subprocess wrap [defuddle CLI](https://github.com/kepano/defuddle)。`readability-lxml` 從 2021 年起無人維護，v0.40 audit 已標註安全風險，v0.43 換掉。

- `_extract_url`（importer.py）優先試 defuddle，未安裝就 fallback 到 readability-lxml
- 零破壞性變更：`[import]` extra 仍包 `readability-lxml`，v0.42 的安裝照常運作
- 可選安裝：`npm install -g defuddle-cli`
- CI 矩陣加上 `actions/setup-node@v4` 跟 `npm install -g defuddle-cli`（best-effort）

---

## Track 3：Obsidian Flavored Markdown 完整支援

`markdown_conventions.py`（v0.42 213 LOC → v0.43 ~330 LOC）新增四個 helpers：

- `wikilink(target, *, display, heading, block_id)` — `[[target]]` / `[[target|display]]` / `[[target#heading]]` / `[[target^block]]`
- `embed(target, *, size, page)` — `![[image|300]]` / `![[paper.pdf#page=3]]`
- `highlight(text)` — `==text==`
- `property_block(**fields)` — Obsidian property frontmatter

**Crystal Evidence 欄位** + **cluster paper list** 改走 `wikilink()` 統一格式。**論文筆記 frontmatter** (`make_raw_md`) 加了選擇性的 `zotero-pdf-path:`，這樣可以用 `![[{{zotero-pdf-path}}#page=1]]` 直接在筆記裡 embed PDF 頁面。

---

## Track 4：Obsidian Bases (`.base`) cluster dashboard 自動產生

新模組 `src/research_hub/obsidian_bases.py`——每個 cluster 自動產生 `.base` YAML 檔，包含 **4 views**：

1. **Papers** — 表格，依 `topic_cluster` 過濾，按年份 DESC 分組
2. **Crystals** — 卡片，依 `type=="crystal"` AND `cluster==<slug>` 過濾
3. **Open Questions** — 從 cluster overview 拉 open-questions
4. **Recent activity** — 依 `ingested_at` 排序，限 10 筆

加上兩個 formulas：`days_since_ingested`、`paper_count`。

**新指令**：`research-hub bases emit --cluster X [--stdout] [--force]`
**新 MCP tool**：`emit_cluster_base(cluster_slug)`，Claude Desktop 可呼叫
**自動產生**：`scaffold_cluster_hub` 現在會把 `<slug>.base` 跟 `00_overview.md` / `crystals/` / `memory.json` 一起寫入 hub dir。Idempotent，跑第二次不會覆蓋。

---

## v0.43 沒做（v0.44 候選）

- **obsidian-cli**：第 5 個 kepano skill。需要 Obsidian 桌面正在執行才能用，CI / 一般 user 環境沒法保證。延到 v0.44。
- **json-canvas** 引用圖匯出：純 JSON serializer，無外部 deps，但優先序低於 Bases。v0.44。
- **`cli.py` / `mcp_server.py` 單檔拆分**：原本的 v0.42 候選，繼續延後。
- **NLM audio / mind-map / video 下載**：v0.44+。

---

## 整體統計

- 測試：1458 → 1492+（Track 2: 8, Track 3: 15, Track 4: 11）
- LOC：~+550 新增、~5 修改
- 沒有破壞性變更（v0.42 安裝可直接升級）

CI 9 個多 OS job（Linux / macOS / Windows × Python 3.10/3.11/3.12）全綠才會 tag。

---

## 碎念

這次踩到一個重要的反思：v0.42 我自己讀 PleasePrompto/notebooklm-skill 的 source 然後重寫，沒有意識到該 repo 早就有現成的 Claude Code MCP（`mcp__notebooklm__*`）已經裝在系統上。同樣的，kepano/obsidian-skills 的 5 個 skill 一直沒裝起來，我只用文檔裡讀來的 callout 慣例做了一小塊。

**「Reinventing the wheel」是 LLM coding 最容易踩的坑——尤其是當你的工具列裡明明就有現成方案的時候**。v0.43 用「層層測試」這個紀律來修補：先裝起來、跨工具交叉驗證（research-hub vs mcp__notebooklm）、再用 obsidian-markdown skill 當 spec ground truth 比對我們的輸出。

下一輪 v0.44 會把剩下的 obsidian-cli + json-canvas 收掉，可能也評估 obsidian-mcp 加入 Claude Desktop（讓 obsidian 端也有 NotebookLM 那樣的雙軌驗證能力）。

持續節奏：ship → use → fix what hurts → don't reinvent if a battle-tested skill already exists.

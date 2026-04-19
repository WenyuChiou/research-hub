# research-hub v0.45.0 — NLM generate bug 修復 + v0.43 scaffolding 完成

**2026-04-19**

v0.44 ship 後跑 11 篇 harness cluster 的 NotebookLM push，抓到一個真實 bug：

```
$ research-hub notebooklm generate --cluster llm-evaluation-harness --type brief
NotebookLMError: Generation button not found: briefing
```

原因：`client.py::_trigger_and_wait` 在搜 studio panel 按鈕前沒先 dismiss NotebookLM 的 `cdk-overlay-backdrop-showing` overlay。v0.42 `ask.py` 已經修過這個問題，但 `generate` / `download_briefing` / `open_notebook_by_name` 都沒套。v0.45 補完。

## 修正 — NLM overlay dismissal

- 把 `_dismiss_overlay` 從 `ask.py` 抽到共用的 `notebooklm/browser.py::dismiss_overlay`
- `NotebookLMClient.open_notebook_by_name` 點 tile 後呼叫
- `_trigger_and_wait` 搜 studio panel 前呼叫
- `download_briefing` 讀 summary 前呼叫
- 4 個新 tests + `ask.py` 也改用共用 helper

## 新增 — `.base` 自動刷新

`research-hub ingest --cluster X` 跟 `research-hub topic build --cluster X` 結束時自動執行 `write_cluster_base(... force=True)`。失敗 non-fatal——只 log warning。填補 v0.43 留下的洞：之前新增論文後 dashboard 不會自動更新。

## 新增 — Crystal `See also` 走 `wikilink()`

純 refactor、byte-identical。集中化 wikilink 渲染。

## 新增 — `doctor` 偵測 defuddle CLI 缺失

`research-hub doctor` 多一行 `INFO`：缺 defuddle 提示 `npm install -g defuddle-cli`。**只偵測不自動安裝**。

## 統計

- 測試：1508 → **1520 pass**（+12）
- LOC：~+200

## 接下來

PDF embed 還沒做（v0.46 候選——需要先設計 Zotero storage dir 查找）。

接下來的工作：**README 全面檢視**——截圖更新、stale 數字更新、是否夠吸引人。

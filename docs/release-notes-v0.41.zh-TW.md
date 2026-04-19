# research-hub v0.41 — 真實使用發現的 7 個 friction 全修

> 一個 release，把實際走過一輪「建 cluster → 搜尋 → 收錄 → 推到 NotebookLM」抓到的所有粗糙點修完。

## 為什麼這個 release

v0.40 ship 之後，跑了一次完整 end-to-end 測試：建一個 `llm-evaluation-harness` cluster，搜尋 arXiv，挑 6 篇論文，全部推到 Obsidian + NotebookLM。理論上應該一氣呵成，實際上踩到 **4 個 ingest pipeline 的洞**。

同時間檢查舊 vault 的 frontmatter，發現 1069 / 1096 篇論文有欄位缺失。寫了兩個臨時 Python script 把問題從 1069 → 544，所以順便把這些 script 變成正式 CLI（**3 個 vault 衛生工具**）。

7 個 fix 全部塞進 v0.41，由 Codex 一個 brief 一次跑完。

## 修了什麼

### 🔧 Ingest pipeline（給新 user 第一次用就不會被卡）

| | 修法 | 影響 |
|---|---|---|
| **F1** | `add <doi>` 在 Semantic Scholar rate-limit 時自動 fallback 到 arXiv API | arXiv 論文以前被 429 直接擋掉，現在會走 arXiv 自己的 metadata API |
| **F2** | `search --to-papers-input` 保留 `arxiv_id` 並自動填 `doi` | 以前 arxiv ID 在序列化時被丟掉，使用者要手動補；現在 ingest 直接吃 |
| **F3** | `papers_input.json` 兩種格式都接受（top-level array 或 `{"papers":[...]}`） | search 的輸出格式 ≠ ingest 的輸入格式 → AttributeError；現在自動 normalize |
| **F4** | cluster 自己有 `zotero_collection_key` 時，不再強制 `RESEARCH_HUB_DEFAULT_COLLECTION` env var | 之前 cluster 已經綁好 Zotero collection 還是要設 env var，現在優先用 cluster 的 |

### 🧹 Vault hygiene（給有舊 vault 的 user）

| | 修法 | 用途 |
|---|---|---|
| **V1** | NEW `research-hub doctor --autofix` | 一鍵機械式回填：folder 推 `topic_cluster`、mtime 推 `ingested_at`、arXiv-shaped slug 推 `doi` |
| **V2** | doctor 區分 legacy 跟 new paper | 1977 年的 Bandura 論文沒 DOI 不該 FAIL，只該 WARN；新論文沒 DOI 才 FAIL |
| **V3** | NEW `research-hub paper lookup-doi <slug>` | 對舊論文用 Crossref 補 DOI（free API，可批次跑 `--cluster X --batch`） |

## 怎麼用（新 CLI 範例）

```bash
# Vault 衛生：一鍵把能機械式修的全修了
research-hub doctor --autofix

# 老論文 DOI 批次 lookup（一個 cluster 為單位）
research-hub paper lookup-doi --cluster behavioral-theory --batch
```

## 升級

```bash
pip install --upgrade research-hub-pipeline
```

無破壞性變更：舊的環境變數 `RESEARCH_HUB_DEFAULT_COLLECTION` 還是會被讀，舊的 `papers_input.json` 格式（top-level array）還是支援，舊 CLI 簽章不變。

## 反思

這次 release 的 7 個 fix **沒有一個是憑空想出來的**——4 個來自實際跑 ingest pipeline 撞牆，3 個來自看 doctor 報 1069 篇論文有問題開始 debug。

「把工具拿來用」是發現 friction 最有效的方式。v0.40 跑過一輪 multi-OS CI 才知道 Windows path 問題；v0.41 跑過一輪 ingest 才知道 search/ingest schema 對不上。

如果你也用 research-hub，**請告訴我你踩到的洞**——那是下一個 release 最有價值的 input。

---

完整 audit 報告：`docs/audit_v0.41.md`（待 release 時補）
英文 changelog：`CHANGELOG.md`

# `research-hub import-folder` — 本地檔案匯入

> v0.31.0 起提供。給 analyst persona 使用者用來處理一堆混合本地檔（沒有 DOI）。

`add` 指令適合學術論文（DOI / arXiv ID 查詢）。`import-folder` 是它的姐妹指令，用來處理其他類型 — 內部 PDF、市場報告、會議記錄、網頁存檔、Word 草稿。

## 什麼時候用

| 你手上有 | 用 |
|---|---|
| DOI 或 arXiv ID | `research-hub add 10.48550/arxiv.2310.06770 --cluster X` |
| 一個資料夾混合 PDF / DOCX / Markdown / TXT / URL | `research-hub import-folder ./folder --cluster X` |
| 已經收進 Zotero 的一堆條目 | （走 Zotero ingest 路徑 — `research-hub ingest`） |

## 快速開始

```bash
# 1. 安裝時加入 `import` 選項，以支援 PDF/DOCX/URL 提取器
pip install 'research-hub-pipeline[import]'

# 2. 建立一個 cluster（或讓 import-folder 自動建立）
research-hub clusters new --slug market-research --query "competitive intelligence Q2"

# 3. 走訪資料夾
research-hub import-folder ~/Downloads/q2-competitor-pdfs --cluster market-research

# 4. 驗證
research-hub status
research-hub where
```

第 3 步之後:
- 每個支援的檔案會變成一個 note 寫到 `<vault>/raw/market-research/<slug>.md`
- frontmatter 包含 `source_kind`、`topic_cluster`、`ingested_at`、`raw_path`（指回原始檔位置）
- body 包含前 5000 字元的預覽（限制 note 大小；完整內容留在 `raw_path`）
- dedup index 用內容 hash 更新，所以重跑會跳過已經匯入的檔

dashboard 的 Library tab 立刻會看到:

![匯入的文件在 Library tab](images/import-folder-result.png)

## 支援的檔案類型

| 副檔名 | source kind | 抽取器 | 選用相依 |
|---|---|---|---|
| `.pdf` | `pdf` | `pdfplumber` | 是 |
| `.md`、`.markdown` | `markdown` | 直接讀（去掉 frontmatter） | 否 |
| `.txt` | `txt` | 直接讀 | 否 |
| `.docx` | `docx` | `python-docx` | 是 |
| `.url` | `url` | `requests` + `readability-lxml` | 是 |

如果你沒裝 `[import]` extras，只有 `.md` 跟 `.txt` 能用；PDF/DOCX/URL 檔會丟出明確的錯誤訊息。

## CLI 參考

```
research-hub import-folder FOLDER --cluster SLUG [OPTIONS]

  FOLDER              來源資料夾路徑（遞迴遍歷）
  --cluster SLUG      目標 cluster（如果不存在則自動建立）
  --extensions LIST   以逗號分隔的副檔名（預設：pdf,md,txt,docx,url）
  --no-skip-existing  即使內容雜湊值與現有筆記相符，也重新匯入
  --use-graphify      執行 graphify CLI 以進行深度提取 + 社群式子主題
  --dry-run           顯示將匯入的內容，不進行任何寫入
```

## 範例

**輕量級預設（不使用 graphify）：**
```bash
research-hub import-folder ~/Downloads/competitor-pdfs --cluster comp-intel
# 輸出：
#   imported:  12
#   skipped:   2     （已在 dedup 索引中）
#   failed:    0
```

**僅特定副檔名：**
```bash
research-hub import-folder ./project --cluster X --extensions pdf,docx
```

**Dry-run（在實際寫入前預覽）：**
```bash
research-hub import-folder ./project --cluster X --dry-run
# 列出將會被匯入的內容，不對檔案系統進行任何變更
```

**重新匯入（更新內容）：**
```bash
research-hub import-folder ./project --cluster X --no-skip-existing
```

## 用 graphify 做深度抽取

graphify (https://github.com/safishamsi/graphify) 是另一個工具，能讀多模態內容（PDF、code、圖片、影片轉錄稿），用 Leiden community detection 建概念 graph。research-hub 可以把它當選用後端，用來做深度多模態抽取。

```bash
# graphify 要分開裝（很重，沒進 research-hub 相依）
pip install graphifyy && graphify install

# 匯入時加 --use-graphify
research-hub import-folder ./project --cluster X --use-graphify
```

`--use-graphify` 在預設流程之上會多做的事:
1. 輕量抽取完之後，跑一次 `graphify <folder>` 建概念 graph
2. 解析 `graphify-out/graph.json` 找 community（語意上相關的檔案群）
3. 根據每個 note 的 community 歸屬，加 `subtopics: [...]` frontmatter
4. 接著可以跑 `research-hub topic build --cluster X` 產生每個子主題的 landing page

如果沒裝 graphify，會回傳明確的錯誤訊息，告訴你裝的指令。

## 寫入的 frontmatter 長這樣

`.pdf` 檔的 note:

```yaml
---
title: "PDF 第一個標題或檔名"
slug: "pdf-first-heading-or-filename"
source_kind: pdf
ingested_at: "2026-04-17T04:30:00Z"
ingestion_source: import-folder
topic_cluster: market-research
labels: []
tags: []
raw_path: "/Users/you/Downloads/competitor-pdfs/something.pdf"
summary: "抽出的前 500 字元..."
---

# Body 預覽（前 5000 字元）
...
```

對照學術論文的 note（從 `research-hub add <DOI>` 來的）:

```yaml
---
title: "論文標題"
authors: "Smith, John; Doe, Jane"
year: 2024
journal: "Nature"
doi: "10.1234/xyz"
source_kind: paper
topic_cluster: market-research
labels: []
...
---
```

兩者都是 `Document` instance；Paper 只是多了一些欄位。

## 跟 research-hub 其他功能的整合

跑完 `import-folder` 之後:

| 指令 | 對匯入的 doc 有效嗎? |
|---|---|
| `research-hub status` | 有 — 列為 paper |
| `research-hub where` | 有 — 列入 note 總數 |
| `research-hub label SLUG --add core` | 有 — labels 對任何 Document 都有效 |
| `research-hub move SLUG --to OTHER-CLUSTER` | 有 — 在 cluster 之間搬移 |
| `research-hub crystal emit --cluster X` | 有 — crystal 對 paper + Document 混合內容都能跑 |
| `research-hub notebooklm bundle --cluster X` | 有 — bundle 走訪 `raw/<cluster>/`，不管 source_kind |
| `research-hub topic build --cluster X` | 有 — 子主題對匯入的 doc 也能用（搭配 `--use-graphify` 效果更好） |
| `research-hub clusters analyze --split-suggestion` | 部分 — 用 citation graph，非論文 doc 沒有 citation。會 fallback 到關鍵字 overlap。 |

## 疑難排解

**`ImportError: install 'research-hub-pipeline[import]' for local file ingest`**
你想匯入 PDF/DOCX/URL 但沒裝選用抽取器。執行:
```bash
pip install 'research-hub-pipeline[import]'
```

**`ERROR: --use-graphify requires graphify CLI`**
你帶了 `--use-graphify` 但 graphify 不在 PATH。安裝:
```bash
pip install graphifyy && graphify install
```

**匯入的 PDF 文字有奇怪的雜訊**
`pdfplumber` 是純文字抽取 — 不會做 OCR。如果你的 PDF 是掃描影像，文字抽取會是亂碼。解法:
- 先用 `ocrmypdf` 預處理，再重新匯入
- 用 `--use-graphify`（graphify 可以對多模態來源跑 Whisper / OCR）

**同一個檔被匯入兩次，兩個 note 都出現**
第二個被寫入是因為內容 hash 不一樣（例如兩次跑之間檔案被改過），或者你帶了 `--no-skip-existing`。清理:
```bash
research-hub remove <slug-of-duplicate>
```

**想匯入 1000+ 檔**
第一次會跑很久（PDF 抽取慢）。後續執行只處理新的或改過的檔（內容 hash dedup）。批次很大時，先用 `--dry-run` 確認範圍。

## 延伸閱讀

- [docs/anti-rag.zh-TW.md](anti-rag.zh-TW.md) — 說明為何 crystals 可處理匯入的檔案
- [docs/example-claude-mcp-flow.md](example-claude-mcp-flow.md) — Claude Desktop 如何驅動完整的 ingest → bundle → NotebookLM 流程
- [docs/notebooklm.md](notebooklm.md) — 設定 NotebookLM 來處理 bundle/upload/generate/download 鏈

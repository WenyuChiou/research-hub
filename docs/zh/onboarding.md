# 開始使用

`research-hub` 是一個為研究人員設計的本地優先（local-first）文獻工作流程，旨在提供從搜尋到分類（triage）到筆記（notes）的可重複路徑。它協助你跨學術後端（academic backends）進行搜尋，將論文組織成主題 cluster，並維護一個 ready to use 的 vault，用於 synthesis、fit-checking 及下游的 AI 工作流程。

## 誰應該使用它

- 一位正在建構 LLM agents、benchmark 或軟體工程工作流程的電腦科學研究人員。
- 一位關注蛋白質建模、臨床方法或快速發展的 preprints 的生醫領域博士生。
- 一位為活躍專案收集政策、經濟學或教育學文獻的社會科學博士後研究員。

## 首次安裝設定

安裝支援 MCP 的套件：

```bash
pip install research-hub-pipeline[mcp]
```

執行一個基本的健康檢查：

```bash
research-hub doctor
```

如果你是從零開始，請建立你的第一個 field-aware cluster：

```bash
research-hub init --field bio
```

你也可以完全以腳本化方式執行精靈（wizard）：

```bash
research-hub init --field cs --cluster llm-agents --name "LLM Agents" --query "LLM agent benchmark" --non-interactive
```

## 精靈（Wizard）做了什麼

Field-aware 的入門流程會建立一個 cluster 並立即以 field-appropriate 的後端啟動 `discover new`。

精靈會詢問：

- 一個 field，例如 `cs`、`bio`、`med`、`social` 或 `edu`
- 一個 cluster 的顯示名稱
- 一個 cluster 的 slug
- 一個搜尋查詢
- 一個可選的 cluster 定義

之後它會：

1. 在 `.research_hub/clusters.yaml` 中建立 cluster
2. 執行 `research-hub discover new ... --field <slug>`
3. 將 fit-check prompt 寫入 `.research_hub/discover/<cluster>/prompt.md`
4. 顯示繼續所需的下一條指令

## 流程範例

```bash
research-hub init --field cs
```

通常後續輸出的內容會引導你至：

1. 在 `.research_hub/discover/<cluster>/prompt.md` 中為 prompt 打分數
2. 將分數結果儲存為 `scored.json`
3. 執行 `research-hub discover continue --cluster <cluster> --scored scored.json --auto-threshold`
4. 執行 `research-hub ingest --cluster <cluster> --fit-check`
5. 執行 `research-hub topic scaffold --cluster <cluster>`

## 內建範例

你可以從一個內建的範例 cluster 開始，而不是從一個空白查詢開始。

列出它們：

```bash
research-hub examples list
```

檢視其中一個：

```bash
research-hub examples show cs_swe
```

將其中一個複製到你自己的 registry：

```bash
research-hub examples copy cs_swe --cluster my-se-agents
```

每個範例都包含：

- 一個標題和 slug
- 一個建議的 field
- 一個啟動查詢
- 一個 cluster 定義
- 建議的年份範圍
- 範例 DOI

## Doctor Field Check

`research-hub doctor` 現在包含每個 cluster 的 field 推斷（inference）流程。它會掃描筆記文字中的 venue 和 keyword 訊號，然後將推斷出的 field 與 cluster 的 seed keywords 進行比較。

這是一個警告訊號，而非硬性驗證器。不匹配通常表示以下情況之一：

- cluster 的查詢過於廣泛
- cluster 是使用錯誤的 field preset 建立的
- 筆記集已漂移到鄰近的學科

## 建議的後續步驟

- `research-hub topic scaffold --cluster <slug>` 以啟動 cluster 的概述
- `research-hub fit-check emit --cluster <slug> --candidates ...` 用於手動篩選工作流程
- `research-hub doctor` 以驗證設定、vault 健康狀況及 field 對齊情況
- `research-hub dashboard` 以取得一個生成的本地概述

## Field Reference

目前發行的版本包含 field presets，可將常見的研究領域對應到 backend 列表。涵蓋範圍包括：

| Field | 典型後端 (Typical backends) |
| --- | --- |
| `general` | OpenAlex, arXiv, Semantic Scholar, Crossref, DBLP |
| `cs` | OpenAlex, arXiv, Semantic Scholar, DBLP, Crossref |
| `bio` | OpenAlex, bioRxiv, Semantic Scholar, Crossref, PubMed |
| `med` | PubMed, OpenAlex, Semantic Scholar, Crossref |
| `social` | OpenAlex, Crossref, Semantic Scholar, RePEc, SSRN-style metadata sources where available |
| `econ` | RePEc, OpenAlex, Crossref, Semantic Scholar |
| `edu` | ERIC, OpenAlex, Crossref, Semantic Scholar |
| `physics` | arXiv, OpenAlex, Semantic Scholar, Crossref |
| `math` | arXiv, OpenAlex, Crossref, Semantic Scholar |
| `astro` | NASA ADS, arXiv, OpenAlex, Semantic Scholar |
| `chem` | ChemRxiv, OpenAlex, Crossref, Semantic Scholar |

請檢查 `research_hub.search.fallback.FIELD_PRESETS` 以了解你安裝版本所使用的確切 backend 順序。

## 相關文件

- [AI Integrations](ai-integrations.md)
- [CLI Reference](cli-reference.md)
- [NotebookLM](notebooklm.md)
- [Setup](setup.md)

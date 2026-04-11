# Research Hub

> 一句話跑完整條學術文獻流程：搜尋、儲存、摘要、上傳 — 在 Claude Code 裡由一個觸發指令完成。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-lightgrey.svg)](.github/workflows/ci.yml)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)]()

[English](README.md) | [繁體中文](README_zh-TW.md)

> ⚠️ **v0.2.1 alpha** — 這是一個公開分享的個人研究工具。預期會有粗糙的地方。NotebookLM 的 Chrome 上傳步驟目前仍然脆弱，可跳過不用。

---

## 為什麼要用 Research Hub？

市面上多數 Zotero ↔ Obsidian 工具做的都是「同步」兩個系統。Research Hub 不一樣：它把整條文獻蒐集流程當成單一動作一次跑完。

| 工具 | 範疇 | 定位 |
|---|---|---|
| obsidian-zotero-integration | 兩系統同步 | 同步導向 |
| ZotLit | 雙向同步 | 同步導向 |
| Paperpile | 雲端文獻庫 | 書目管理 |
| Zotfile | PDF 檔案整理 | 檔案歸檔 |
| **Research Hub** | **完整流程（搜尋 → 儲存 → 摘要 → 上傳）** | **工作流程導向** |

這是目前唯一把「論文搜尋 + Zotero 寫入 + Obsidian 筆記生成 + NotebookLM 上傳」整合在一句觸發指令後面的工具，也是唯一在流程裡內建 LLM 分類的工具。

---

## 完整流程

```
"幫我放到 Research Hub：<主題>"
    ↓
[1] 分類     (LLM 讀 title + abstract → 類別 + 子類別)
[2] 搜尋     (Semantic Scholar + arXiv + CrossRef + PubMed 平行查詢)
[3] 挑選     (顯示結果表格，使用者選)
[4] 儲存     (Zotero 項目 + Obsidian 筆記 + hub 頁面更新)
[5] 上傳     (可選 — NotebookLM 經由 Chrome 自動化)
[6] 建構     (重建 hub 索引 + Obsidian graph)
[7] 探索     (引用圖譜；提供相關論文加入選項)
```

每個步驟也可以獨立執行：找文獻、重寫筆記、整理 Zotero、同步 Obsidian、上傳 NotebookLM、追蹤閱讀狀態、找研究缺口、探索引用圖譜。

---

## 快速開始

```bash
# 1. Clone 專案
git clone https://github.com/WenyuChiou/research-hub
cd research-hub

# 2. 安裝（editable 模式，含測試用 dev 套件）
pip install -e '.[dev]'

# 3. 複製範例設定
cp config.json.example config.json

# 4. 編輯 config.json — 至少要設定：
#    knowledge_base.root   → 你的 Obsidian vault 根目錄
#    zotero.library_id     → 從 https://www.zotero.org/settings/keys 取得
#    zotero.default_collection → 你在 Zotero 建好的 collection key

# 5. 驗證環境
python scripts/verify_setup.py
```

完整的步驟拆解與疑難排解，請看 [docs/setup.md](docs/setup.md)。

---

## 相依套件

必要：

| 元件 | 用途 |
|---|---|
| Python 3.10+ | 執行環境 |
| [Zotero Desktop](https://www.zotero.org/download/) | 本機文獻庫 + `localhost:23119` 的本地 API |
| [Zotero Web API key](https://www.zotero.org/settings/keys) | 經由 `pyzotero` 做寫入（建 item、加筆記） |
| [Obsidian](https://obsidian.md/) vault | 生成筆記與 hub 頁面的目的地 |
| [Claude Code](https://docs.claude.com/en/docs/claude-code) | 執行 skill 並協調整條流程 |
| [zotero-skills](https://github.com/WenyuChiou/zotero-skills) | 姐妹 skill — Zotero CRUD 基礎 |

可選：

| 元件 | 用途 |
|---|---|
| [NotebookLM](https://notebooklm.google.com/) | Step 5 的 source 上傳；需 Google 帳號 |
| Chrome + Claude in Chrome | 自動化 NotebookLM 上傳 |

Claude Code 用到的 MCP 連接器：

- `paper-search-mcp` — arXiv、Semantic Scholar、CrossRef、PubMed
- `Zotero MCP` — 唯讀檢視 Zotero 文獻庫
- `Desktop Commander` — 從 skill 內部寫檔案

---

## 專案結構

```
research-hub/
├── src/research_hub/       # 套件原始碼
│   ├── config.py           # 可攜式設定載入（env > config.json > 預設）
│   ├── pipeline.py         # run_pipeline() 主入口
│   ├── cli.py              # `research-hub` console script
│   ├── vault/              # Obsidian vault builder、categorizer、repair
│   └── zotero/             # 本地 + web API 客戶端，fetch / extract 工具
├── tests/                  # 42 個單元測試（pipeline、zotero、vault、config）
├── scripts/
│   └── verify_setup.py     # 安裝後的 sanity check
├── references/             # 分類定義、模板、Dataview queries
├── skills/
│   ├── knowledge-base/     # Claude Code skill 本體
│   └── zotero-skills/      # 姐妹 skill stub
├── docs/
│   ├── setup.md            # 首次安裝導覽
│   └── customization.md    # 套用到其他研究領域的調整方式
├── config.json.example     # 去識別化的 config 範本
├── .github/workflows/ci.yml
├── pyproject.toml
├── LICENSE                 # MIT
└── README.md
```

---

## 客製化

整條流程是領域無關的。預設設定瞄準洪災風險 + ABM 研究只是因為專案在那個情境下長出來，分類系統、Zotero collections、NotebookLM notebook 名稱都寫在 `config.json` 裡可以改。請參考 [docs/customization.md](docs/customization.md)，裡面有兩個完整範例：一個化學實驗室、一個經濟學問卷研究群。

---

## Roadmap

Phase 2（規劃中，未在這個 release 完成）：

- 以 local RAG 做 vault 內部的語意搜尋
- Incremental hub 重建（取代目前的全量重跑）
- Obsidian 筆記的重複偵測（現在只有 Zotero 側）
- Deterministic 分類稽核 log + rationale 紀錄
- Human-in-the-loop 的 `verified: false` 標籤，標記自動生成的段落

---

## 貢獻

歡迎貢獻。大改動請先開 issue 對齊範圍。開發流程、branch 命名、commit 慣例請看 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 授權

MIT — 請看 [LICENSE](LICENSE)。

---

## 致謝

本專案建立在 [Zotero](https://www.zotero.org/)、[Obsidian](https://obsidian.md/)、[Semantic Scholar](https://www.semanticscholar.org/)、[NotebookLM](https://notebooklm.google.com/) 和 [Claude Code](https://docs.claude.com/en/docs/claude-code) 的工作之上。論文搜尋工具鏈感謝社群維護的 [paper-search-mcp](https://github.com/openags/paper-search-mcp)。

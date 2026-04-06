# Research Hub — 學術文獻管理工作流程

> [English](README.md)

一鍵式學術研究知識管理工作流程。搜尋論文、存入 Zotero、建立 Obsidian 筆記、重建 Hub 索引、上傳至 NotebookLM — 全部透過一句觸發指令完成。

---

## 功能特色

### 一鍵式工作流程
- **單一觸發** — 說「幫我放到Research Hub」+ 主題，全流程自動執行
- **LLM 分類** — Claude 閱讀摘要後自動分類論文的類別與子類別
- **多來源搜尋** — Semantic Scholar、WebSearch、CrossRef、PubMed 平行查詢

### Zotero 整合
- **自動存檔含元數據** — 建立 Zotero 項目，含完整元數據、標籤、集合分類
- **子筆記** — 為每篇論文附加自動產生的摘要筆記
- **重複偵測** — 建立前自動檢查，防止重複
- **使用 [zotero-skills](https://github.com/WenyuChiou/zotero-skills)** 處理所有 CRUD 操作

### Obsidian 知識庫
- **結構化筆記** — 自動產生含 YAML frontmatter、摘要、主要發現、方法論的 `.md` 檔案
- **三層式 Hub** — 理論 → 主題 → 論文，可作為知識圖譜導覽
- **圖譜著色** — 在 Obsidian 圖譜視圖中依類別著色
- **Dataview 查詢** — 預建篩選、狀態追蹤、論文整合查詢

### NotebookLM 上傳
- **DOI 驗證** — 上傳前驗證每個 DOI，跳過付費牆內容
- **URL 優先順序** — 優先 arXiv > 預印本 > 開放取用 URL > DOI
- **Chrome 自動化** — 透過瀏覽器將來源上傳至對應筆記本

### 獨立操作
- 搜尋文獻、重寫筆記、整理 Zotero、同步 Obsidian、上傳 NotebookLM、閱讀狀態、研究缺口、引用圖譜 — 每項皆可獨立執行

---

## 安裝設定

### 前置需求

- **Python 3.10+**
- **pyzotero**: `pip install pyzotero`
- **Zotero 桌面版** 執行中（供本地 API 讀取）
- **[zotero-skills](https://github.com/WenyuChiou/zotero-skills)** 安裝於 `~/.claude/skills/`

### MCP 連接器

| 連接器 | 用途 |
|---|---|
| paper-search-mcp | 搜尋 arXiv、Semantic Scholar、PubMed、CrossRef |
| Zotero MCP | 讀取 Zotero 文獻庫（唯讀） |
| Desktop Commander | 執行 Python 腳本、寫入檔案 |
| Claude in Chrome | （選用）自動化 NotebookLM 上傳 |

### 設定

完整設定指南請參閱 `references/customization.md`，包含路徑、分類、筆記本及跨平台適配說明。

---

## 目錄結構

```
~/.claude/skills/knowledge-base/
├── SKILL.md              # AI 助理的核心工作流程指令
├── README.md             # English
├── README_zh-TW.md       # 繁體中文
└── references/
    ├── paper-template.md       # Obsidian 筆記模板
    ├── categories.md           # 分類系統、關鍵字、WIKI_MERGE
    ├── obsidian-conventions.md # Markdown 規範、YAML 模板
    ├── dataview-queries.md     # 預建 Dataview 查詢
    ├── customization.md        # 其他用戶設定指南
    └── setup-guide.md          # 首次 MCP 設定
```

---

## 非 Claude CLI 使用說明

| CLI | 如何載入 |
|---|---|
| **Claude Code** | 放入 `~/.claude/skills/` — 自動載入 |
| **Codex CLI** | 以 `-C` 傳入 `SKILL.md` 作為上下文 |
| **Gemini CLI** | 加入系統提示或專案上下文 |
| **Cursor / Windsurf** | 加入 `.cursor/rules` 或對應規則檔 |

---

## 授權

MIT
# research-hub

> Zotero + Obsidian + NotebookLM 三合一，專為 AI agent 打造。

[![PyPI](https://img.shields.io/pypi/v/research-hub-pipeline.svg)](https://pypi.org/project/research-hub-pipeline/)
[![Tests](https://img.shields.io/badge/tests-1113%20passing-brightgreen.svg)](docs/audit_v0.28.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

English → [README.md](README.md)

![Dashboard 總覽](docs/images/dashboard-overview.png)

---

## 這是什麼

一個 CLI + MCP server,同時做三件事:

1. **Ingest** — 一行指令把學術論文收進 Zotero(引用管理)+ Obsidian(結構化筆記)+ NotebookLM(AI 簡報)。
2. **Organize** — 論文自動分到 cluster、sub-topic,Obsidian graph 按 research label 上色。
3. **Serve** — 提供 52 個 MCP tools,讓 Claude Code / Codex / 任何相容 MCP 的 AI 可以直接驅動整個流程。

設計給每天都在用 AI agent 的 PhD 學生跟研究團隊,不想在六個分頁之間切來切去的人。

## 跟其他工具的差別

### 1. Crystals — 預先運算好的答案,不是 lazy retrieval (v0.28)

所有 RAG 系統(包括 Karpathy 的 "LLM wiki")都還是在查詢時才把資料拼湊起來。research-hub 的答案是:**儲存 AI 的推理結果,而不是原料**。

對每個 research cluster,你預先讓 AI 回答約 10 個標準問題(用 emit/apply 模式,你可以用任何 LLM),結果存成 crystal 檔案。之後 AI agent 再問「這個領域現在的 SOTA 是什麼?」時,它讀的是預先寫好的 100 字答案 — 而不是 20 篇論文的 abstract。

```bash
research-hub crystal emit --cluster llm-agents-software-engineering > prompt.md
# 把 prompt.md 給 Claude/GPT/Gemini 回答,存成 crystals.json
research-hub crystal apply --cluster llm-agents-software-engineering --scored crystals.json
```

每次 cluster 層級查詢的 token 成本:**~1 KB**(讀 crystal) vs ~30 KB(cluster digest)。**30 倍壓縮**,而且品質不會掉,因為品質在生成時就已經決定了。

[→ 為什麼這不是 RAG(中文版)](docs/anti-rag.zh-TW.md)

### 2. 即時互動 dashboard,可直接執行 (v0.27)

```bash
research-hub serve --dashboard
```

在 `http://127.0.0.1:8765/` 開一個 localhost HTTP dashboard。Manage tab 的每一個按鈕都是**直接執行** CLI 指令,不再只是 copy 到剪貼簿。Vault 有任何變動都透過 Server-Sent Events 推送到瀏覽器。沒開 server 時自動 fallback 到靜態 copy 模式。

![即時 dashboard](docs/images/dashboard-manage-live.png)

### 3. Obsidian graph 自動按 label 上色 (v0.27)

```bash
research-hub vault graph-colors --refresh
```

寫入 14 個顏色群組到 `.obsidian/graph.json`:5 個 cluster 路徑 + 9 個論文 label(`seed`、`core`、`method`、`benchmark`、`survey`、`application`、`tangential`、`deprecated`、`archived`)。每次 `research-hub dashboard` 都會自動刷新。打開 Obsidian Graph View — 你的 vault 是按「意義」視覺化,不是按檔案樹。

_(Obsidian graph 截圖待補 — 跑完 `research-hub vault graph-colors --refresh` 後按 `Ctrl+G` 截。)_

### 4. 分 sub-topic 的 Library + citation graph 自動分群 (v0.27)

很大的 cluster(331 篇論文?)不再是扁平清單。它會按 sub-topic 分組、每個可展開。如果你的 cluster 還沒有 sub-topic:

```bash
research-hub clusters analyze --cluster my-big-cluster --split-suggestion
```

用 Semantic Scholar citation graph + networkx community detection,建議 3-8 個有意義的 sub-topic。產出 markdown 報告,你 review 後再執行 `topic apply-assignments`。

![Library tab 分 sub-topic](docs/images/dashboard-library-subtopic.png)

---

## 安裝

```bash
pip install research-hub-pipeline
research-hub init              # 互動式設定
research-hub serve --dashboard # 自動開瀏覽器
```

Python 3.10+。**不需要 OpenAI/Anthropic API key** — research-hub 完全 provider-agnostic,所有 AI 生成都走 emit/apply 模式(你把 prompt 給自己的 AI)。

## 給 Claude Code / Claude Desktop 使用者

加到 `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "research-hub": {
      "command": "research-hub",
      "args": ["serve"]
    }
  }
}
```

然後跟 Claude 講話:

> 「Claude,把 arxiv 2310.06770 加到新的 cluster 叫 LLM-SE」
> 「Claude,幫 LLM-SE cluster 產 crystals」
> 「Claude,這個 cluster 在講什麼?」→ Claude 呼叫 `list_crystals` + `read_crystal` → 拿到預先寫好的 100 字答案

52 個 MCP tools 涵蓋:論文 ingest、cluster CRUD、labels、quotes、draft 組裝、citation graph、NotebookLM、crystal 生成、fit-check、autofill。

## 五行指令快速上手

```bash
# 1. 初始化 vault
research-hub init

# 2. Ingest 一篇論文
research-hub add 10.48550/arxiv.2310.06770 --cluster llm-agents

# 3. 開 live dashboard
research-hub serve --dashboard

# 4. 有幾篇論文後,產生 crystals
research-hub crystal emit --cluster llm-agents > prompt.md
# (把 prompt.md 給你的 AI 回答,存成 crystals.json)
research-hub crystal apply --cluster llm-agents --scored crystals.json

# 5. AI 查詢時直接讀 crystals,不用讀論文
# (透過 Claude Desktop MCP,或任何相容 MCP 的 client)
```

## 目前狀態

- **最新版本**: v0.28.0 (2026-04-15)
- **測試**: 1113 passing, 12 skipped, 5 xfail baselines(有紀錄的 search quality 問題)
- **平台**: Windows, macOS, Linux
- **Python**: 3.10+
- **相依**: `pyzotero`、`pyyaml`、`requests`、`rapidfuzz`、`networkx`、`platformdirs`(都是 pure-Python)
- **選用**: `playwright` extra(NotebookLM 瀏覽器自動化)

## 架構文件

- [Anti-RAG crystals(為什麼不用 RAG)](docs/anti-rag.md) — 英文完整版
- [Audit 報告](docs/) — `audit_v0.26.md`、`audit_v0.27.md`、`audit_v0.28.md`
- [NotebookLM 設定](docs/notebooklm.md) — CDP attach 流程 + 疑難排解
- [Papers input schema](docs/papers_input_schema.md) — ingest 管線參考

## 指令速查

| 階段 | 指令 | 用途 |
|---|---|---|
| **初始化** | `init` / `doctor` | 首次設定 + 健康檢查 |
| **搜尋** | `search` / `verify` / `discover new` | 多後端論文搜尋 + DOI 驗證 + AI 評分 |
| **收錄** | `add` / `ingest` | 單篇或批次收錄到 Zotero + Obsidian |
| **整理** | `clusters new/list/show/bind/merge/split/rename/delete` | Cluster CRUD |
| **主題** | `topic scaffold/propose/assign/build` | 從 `subtopics:` frontmatter 生成 sub-topic 筆記 |
| **標籤** | `label` / `find --label` / `paper prune` | 9 值 label 字典(seed/core/method...) |
| **Crystal** | `crystal emit/apply/list/read/check` | 預運算的標準 Q→A 答案 |
| **分析** | `clusters analyze --split-suggestion` | 大 cluster 的 citation graph 自動分群 |
| **同步** | `sync status` / `pipeline repair` | 偵測並修復 Zotero ↔ Obsidian 偏差 |
| **Dashboard** | `dashboard` / `serve --dashboard` / `vault graph-colors` | 靜態 HTML / live HTTP server / Obsidian graph 上色 |
| **NotebookLM** | `notebooklm bundle/upload/generate/download` | 瀏覽器自動化 NLM 流程(CDP attach) |
| **寫作** | `quote` / `compose-draft` / `cite` | 引言擷取、markdown 草稿組裝、BibTeX 匯出 |

## 兩種角色

| 角色 | 安裝 | 需要 Zotero? | 適合 |
|---|---|---|---|
| **研究者**(預設) | `pip install research-hub-pipeline[playwright]` | 是 | PhD 學生、學術文獻回顧 |
| **分析師** | `research-hub init --persona analyst` | 否 — 只用 Obsidian | 業界研究、白皮書、技術文件 |

兩種角色都有同樣的 dashboard、MCP server、crystal 系統。

## 給開發者

```bash
git clone https://github.com/WenyuChiou/research-hub.git
cd research-hub
pip install -e '.[dev,playwright]'
python -m pytest -q  # 1113 passing
```

PyPI 套件名稱: **research-hub-pipeline**
CLI 入口: **research-hub**

## License

MIT。見 [LICENSE](LICENSE)。

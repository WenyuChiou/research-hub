# research-hub

> **打一句話進去。Cluster + 論文 + AI 簡報出來。約 50 秒。**
> Zotero + Obsidian + NotebookLM 三合一,專為 AI agent 打造 — **不需要 OpenAI/Anthropic API key**。

[![PyPI](https://img.shields.io/pypi/v/research-hub-pipeline.svg)](https://pypi.org/project/research-hub-pipeline/)
[![Downloads](https://img.shields.io/pypi/dm/research-hub-pipeline.svg?color=blue)](https://pypi.org/project/research-hub-pipeline/)
[![GitHub stars](https://img.shields.io/github/stars/WenyuChiou/research-hub?style=social)](https://github.com/WenyuChiou/research-hub/stargazers)
[![Tests](https://img.shields.io/badge/tests-1569%20passing-brightgreen.svg)](docs/audit_v0.45.md)
[![MCP tools](https://img.shields.io/badge/MCP%20tools-83-blueviolet.svg)](docs/mcp-tools.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI: Linux · macOS · Windows](https://img.shields.io/badge/CI-Linux%20%C2%B7%20macOS%20%C2%B7%20Windows-blue)](.github/workflows/ci.yml)
[![last commit](https://img.shields.io/github/last-commit/WenyuChiou/research-hub.svg?color=orange)](https://github.com/WenyuChiou/research-hub/commits/master)
[![GitHub issues](https://img.shields.io/github/issues/WenyuChiou/research-hub.svg)](https://github.com/WenyuChiou/research-hub/issues)

English → [README.md](README.md)

---

## 📋 開始之前要有什麼

| 需要 | 為什麼 | 怎麼弄 |
|---|---|---|
| **Python 3.10+** | 整個套件 | `python --version` |
| **Obsidian**(免費) | research-hub 把筆記寫到 Obsidian 能渲染的 vault 裡 | [obsidian.md](https://obsidian.md) 下載 |
| **Google 帳號 + NotebookLM** | brief 是它生的 | 去 [notebooklm.google.com](https://notebooklm.google.com) 開通一次 |
| **Chrome** | patchright 用你本機 Chrome 跑(不用另外申請 API key) | 裝 Chrome — `init` 會自動偵測 |
| **Zotero 帳號 + API key**(researcher/humanities 才需要) | 跨裝置同步論文 + PDF | [zotero.org/settings/keys](https://www.zotero.org/settings/keys) |
| (可選)`claude` / `codex` / `gemini` CLI | 要 `auto --with-crystals` 全自動跑完 | 你已經在用哪個 AI CLI 就裝哪個 |

`research-hub init` 結尾會跑一次**首次執行就緒檢查**,缺哪個它會直接告訴你 — 不用把這張表背起來。

---

## ⚡ 安裝 + 第一次跑(60 秒)

```bash
pip install research-hub-pipeline[playwright,secrets]
research-hub init                                          # 互動式:選 persona + Zotero/NLM + 就緒檢查
research-hub notebooklm login                              # 一次性 Google 登入
research-hub auto "harness engineering for LLM agents"     # 完成 — 50 秒後拿到 8 篇論文 + 一份 brief
```

**想要從頭到尾全自動**(search → ingest → NLM brief → 預先運算的 AI 答案)?

```bash
research-hub auto "harness engineering" --with-crystals    # 自動 pipe 給 claude/codex/gemini CLI
```

**不確定要怎麼問?先 plan 再 act**(v0.50):

```bash
research-hub plan "我想學 harness engineering"
# 印出: 建議 topic、cluster、max_papers(看到 thesis/learn 字眼會自動調整),
# 警告 cluster 撞名,然後印出可以直接執行的 `auto` 指令。
```

用 Claude Desktop 時,只要說「Claude,幫我研究 X」,Claude 會先呼叫 `plan_research_workflow` 跟你確認計畫,再啟動 `auto_research_topic`。

如果支援的 LLM CLI 在你的 PATH 上,`--with-crystals` 會自動跑完 crystal 生成。沒有的話,prompt 會存到 `.research_hub/artifacts/<slug>/crystal-prompt.md`,結尾的 Next Steps 會明確告訴你要把哪個檔案貼到哪。

---

## 🎬 30 秒實測(真實 terminal 輸出,不是 mock-up)

下面是維護者在 Windows zh-TW 機器上跑 v0.49.5 驗證時,真的執行 `research-hub auto "LLM agents agent-based modeling social simulation" --with-crystals` 的輸出([`CHANGELOG.md`](CHANGELOG.md) v0.49.4 有完整紀錄):

```text
$ research-hub auto "LLM agents agent-based modeling social simulation" --with-crystals
[OK] cluster        created: llm-agents-agent-based-modeling-social
[OK] zotero.bind    created collection 9FHZCK4N for llm-agents-agent-based-modeling-social
[OK] search         8 results
[OK] ingest         8 papers in raw/llm-agents-agent-based-modeling-social/
[OK] nlm.bundle     7 PDFs (24 MB)
[OK] nlm.upload     8 succeeded
[OK] nlm.generate   brief generation triggered
[OK] nlm.download   1893 chars saved
[OK] crystals       10 crystals via claude

============================================================
Done in 187s. Cluster: llm-agents-agent-based-modeling-social
============================================================
  NotebookLM: https://notebooklm.google.com/notebook/99866b50-3b71-4d84-9e19-7682bbc85e2d
  Brief:      .research_hub/artifacts/.../brief-20260420T020640Z.txt

Next steps (copy-paste any of these):

  # 讀已快取的 SOTA 答案(~1 KB,不會打 LLM)
  research-hub crystal read --cluster llm-agents-agent-based-modeling-social \
                            --slug sota-and-open-problems

  # 對 NotebookLM 上傳的內容做臨時 Q&A
  research-hub ask llm-agents-agent-based-modeling-social "what's the main risk?"

  # 或直接跟裝了 research-hub MCP 的 Claude Desktop 講話:
  > "Claude, what's in my llm-agents-agent-based-modeling-social cluster?"
```

這一個指令幫你產出的東西:

| 產出物 | 位置 | 大小 |
|---|---|---|
| 8 篇 PDF | Zotero collection `9FHZCK4N`(自動建立) | 24 MB |
| 8 個 Obsidian 筆記(含 frontmatter) | `raw/llm-agents-agent-based-modeling-social/` | 8 × ~3 KB |
| NotebookLM notebook(含 8 個 source) | google.com/notebook/99866b50-... | — |
| AI brief(下載到本機) | `.research_hub/artifacts/.../brief-*.txt` | 1.9 KB |
| 10 個預先運算好的 Q→A crystal | `hub/llm-agents-agent-based-modeling-social/crystals/` | 10 × ~4 KB |

跑完這 187 秒之後,**之後每次對這 cluster 的問題都讀 cached crystal,不到 1 秒回答 — 不打 LLM、不消耗 API quota**。

**裝完之後三條路任你選:**

| 路徑 | 你做的事 | 背後跑的 |
|---|---|---|
| **🤖 跟 Claude 講話**(推薦) | 「Claude,幫我研究 harness engineering」 | Claude 透過 MCP 呼叫 `auto_research_topic(...)` — 一個工具呼叫 |
| **💻 一行 CLI** | `research-hub auto "topic"` | 同一個 orchestrator,直接呼叫 |
| **🖱 Dashboard 點按鈕** | `research-hub serve --dashboard` → Manage tab | 同樣的動作,改成按鈕驅動 |

三條路驅動的是**同一個** orchestrator。手在哪就用哪個。

---

## 🤖 跟 Claude 對話 — 30 秒設定

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

重啟 Claude Desktop。然後:

> **你:**「Claude,幫我找 5 篇 agent-based modeling 的論文,放到一個 notebook 裡。」
> **Claude:** *呼叫 `auto_research_topic(topic="agent-based modeling", max_papers=5)`* → 5 篇論文 + NotebookLM brief 連結 — 約 50 秒。

> **你:**「我的 llm-evaluation-harness cluster 現在 SOTA 是什麼?」
> **Claude:** *呼叫 `read_crystal("llm-evaluation-harness", "sota-and-open-problems")`* → 180 字預先寫好的答案,附引用。**讀取 ~1 KB,查詢時 0 篇 abstract 被重新讀取。**

**總共 81 個 MCP tools** — 完整參考: [`docs/mcp-tools.md`](docs/mcp-tools.md)。最大的幾個:

| Tool | 取代了什麼 |
|---|---|
| `auto_research_topic(topic)` | 7 步驟 CLI 流程(search → ingest → bundle → upload → generate → download) |
| `cleanup_garbage(everything=True)` | 手動 `du -sh .research_hub/bundles/*` + `rm -rf` |
| `tidy_vault()` | `doctor --autofix` + `dedup rebuild` + `bases emit --force` + cleanup preview |
| `ask_cluster_notebooklm(cluster, question)` | 開 NotebookLM 分頁、貼問題、複製答案 |
| `read_crystal(cluster, slot)` | 重新讀 20 篇 abstract 來回答同一個問題 |
| `list_claims(cluster, min_confidence)` | 翻 hub overview 希望 claim 在對的段落裡 |
| `add_paper(arxiv_id, cluster)` | 手動 Zotero add → 手動 Obsidian 筆記 → 手動 NotebookLM 上傳 |

---

## 📊 一張表看完所有功能

| 能力 | 指令(或 MCP tool) | 說明 |
|---|---|---|
| **Lazy mode** — 一句話進,brief 出 | `auto "topic"` / `auto_research_topic` | search → ingest → NLM brief,約 50 秒 |
| **Lazy maintenance** | `tidy` / `tidy_vault` | doctor + dedup + bases + cleanup preview |
| **GC 累積垃圾** | `cleanup --all --apply` / `cleanup_garbage` | bundles + debug logs + 過期 artifacts |
| **臨時 NLM Q&A** | `ask --cluster X "Q?"` / `ask_cluster_notebooklm` | 雙後端(NLM + crystal cache) |
| **預先運算 crystals** | `crystal emit / apply` | 每個 cluster 約 10 個標準 Q→A,每答案約 1 KB |
| **結構化 memory** | `memory emit / apply` + `list_entities/claims/methods` | 型別化 entity、有信心度的 claim、method taxonomy |
| **Live dashboard** | `serve --dashboard` | 6 個 tab、persona-aware、Manage tab 按鈕直接執行 CLI |
| **4 personas、1 套程式** | `RESEARCH_HUB_PERSONA=researcher\|humanities\|analyst\|internal` | 詞彙跟隱藏 tab 自動適配 |
| **100% orphan coverage** | `clusters rebind --emit` 然後 `--apply` | 8-heuristic 鏈、auto-create-from-folder 提案 |
| **健康檢查(12+ 項)** | `doctor` / `doctor --autofix` | 機械式 backfill、patchright Chrome 檢測 |
| **Multi-backend search** | `search "query"` | arXiv + Semantic Scholar(預設)+ Crossref DOI 查詢 |
| **Cluster autosplit** | `clusters analyze --split-suggestion` | networkx greedy modularity 跑在引用圖上 |
| **Obsidian Bases dashboard** | `bases emit` / `emit_cluster_base` | 每個 cluster 自動產出 `.base`(ingest 時自動更新) |
| **NotebookLM 上傳** | `notebooklm upload --cluster X` | patchright + persistent Chrome(無 API key、無 quota) |
| **引用圖** | `vault graph-colors` | networkx + Obsidian graph view 上色 |
| **本機檔案匯入** | `import-folder /path` | PDF / DOCX / MD / TXT / URL(analyst persona) |
| **通用網路搜尋**(v0.51) | `websearch "query"` / `web_search` | Tavily / Brave / Google CSE / DDG fallback(不用 key 也能跑) |
| **領域自動偵測**(v0.51) | `plan "intent"` → 建議 `--field` | bio/med 查詢自動挑 pubmed;cs 自動挑 arxiv+s2 |

[→ 完整 lazy-mode 指南](docs/lazy-mode.md) · [→ 所有指令](docs/dashboard-walkthrough.md) · [→ MCP 參考](docs/mcp-tools.md)

---

## 🖥 Dashboard 長什麼樣

`research-hub serve --dashboard` 會開 `http://127.0.0.1:8765/` — 六個 tab,跟 CLI 看到的是同一份資料。

| | |
|---|---|
| ![Overview](docs/images/dashboard-overview.png) | ![Library](docs/images/dashboard-library-subtopic.png) |
| **Overview** — treemap + storage map + 最近活動 + crystals 覆蓋率 | **Library** — cluster 鑽到 sub-topic + 每篇論文一列 |
| ![Briefings](docs/images/dashboard-crystals.png) | ![Diagnostics](docs/images/dashboard-diagnostics.png) |
| **Briefings** — NotebookLM brief 預覽 + artifact 連結 | **Diagnostics** — 健康狀態 + drift 警告(v0.48 已按 kind 分組) |
| ![Manage](docs/images/dashboard-manage-live.png) | ![Writing](docs/images/dashboard-writing.png) |
| **Manage** — 每個 CLI 動作都是按鈕(rename / merge / split / NLM upload / ask / polish-markdown / bases emit) | **Writing** — 引文採集 + 草稿合成 + BibTeX 匯出 |

[→ Dashboard 完整導覽](docs/dashboard-walkthrough.md) · [→ 4 個 persona 變體](docs/personas.md)

---

## 🧠 跟其他工具的差別

### 1. 預先運算好的答案,不是 lazy retrieval

所有 RAG 系統都還是在查詢時才把資料拼湊起來。research-hub 的答案是:**儲存 AI 的推理結果,而不是原料**。

對每個 cluster,你預先讓 AI(任何 LLM 都行)回答約 10 個標準問題,存成 **crystal**。之後 AI agent 再問「SOTA 是什麼?」時,讀的是預先寫好的段落(~1 KB),不是 20 篇 abstract(~30 KB)— **30× 壓縮**,品質不會在查詢時降級。底層的 **memory layer** 存放 crystal 引用的結構化內容:具型別的 entity、有信心度標記的 claim、method taxonomy。AI agent 用 `list_entities`、`list_claims(min_confidence="high")`、`list_methods` 查詢 — 結構化資料的結構化查詢,沒有 RAG。

維護者 vault 裡的範例 cluster: `hub/llm-evaluation-harness/` 有 10 crystals + 14 entities + 12 claims + 7 methods,全部產生過一次。你跑 `research-hub auto "harness engineering" --with-crystals` 之後,你的 vault 也會長這樣。[→ 為什麼這不是 RAG](docs/anti-rag.md)

### 2. 三個操作介面、一個 orchestrator

CLI、dashboard 按鈕、MCP tools 全部呼叫同一個 Python orchestrator。沒有「REST 模式」或「API 模式」會有不同行為。在 shell 能做的事,Claude 也能透過 MCP 做,反過來也是。

### 3. Provider-agnostic by design

**不需要 OpenAI / Anthropic API key**。所有 AI 生成都用 `emit` / `apply` 模式: `emit` 把獨立完整的 prompt 印到 stdout,你貼到自己選的 AI(Claude、GPT、Gemini、本機模型),`apply` 把 JSON 回應收進去。NotebookLM 用你自己已登入的 Chrome 跑瀏覽器自動化 — 沒有 quota、沒有按 token 計費。

---

## ⚖️ 跟其他工具比較

老實的並排比較。research-hub 不取代下面任何一個工具 — 它把它們縫起來,讓 AI agent 一次驅動全部。

| 你能做的事 | 只用 Zotero | 只用 NotebookLM | 通用 RAG(LangChain 等) | Obsidian-Zotero plugin | **research-hub** |
|---|---|---|---|---|---|
| 一個指令同時搜 arXiv + Semantic Scholar | ❌ | ❌ | DIY | ❌ | ✅ `auto "topic"` |
| 一次同步進 Zotero **+** Obsidian **+** NotebookLM | ❌ | ❌ | DIY | 部分(Z↔O 而已) | ✅ `auto` |
| 從你的論文集自動產 AI brief | ❌ | ✅(手動) | DIY | ❌ | ✅ 自動產 |
| 預先運算 Q→A 答案,AI 不用每次重新 RAG | ❌ | ❌ | ❌(RAG 每次重抓) | ❌ | ✅ crystals(~1 KB/答案) |
| 結構化 memory(entity + 有信心度的 claim + method) | ❌ | ❌ | unstructured chunks | ❌ | ✅ `list_entities/claims/methods` |
| AI agent 直接透過 MCP 控制 | ❌ | ❌ | DIY MCP server | ❌ | ✅ 81 個 MCP tool |
| Live HTML dashboard(含執行按鈕) | ❌ | ❌ | ❌ | ❌ | ✅ `serve --dashboard` |
| 自動 cluster + 偵測 drift + 自動 rebind orphan | ❌ | ❌ | ❌ | ❌ | ✅ `clusters rebind` |
| 每個 cluster 自動產 Obsidian Bases dashboard | ❌ | ❌ | ❌ | ❌ | ✅ `bases emit` |
| **AI 不需要 API key** | n/a | ✅ | ❌ | n/a | ✅ |
| **本機優先、你擁有 vault** | ✅(雲端同步) | ❌(Google) | 視情況 | ✅ | ✅ |
| 1000 次查詢成本 | n/a | quota 限額 | ~$5–50(按 token 收費) | n/a | **$0**(crystal 已快取) |

老實話: research-hub 的價值**只有在你已經用 Zotero / Obsidian / NotebookLM 三個裡面至少 2 個**、想要 AI 幫你 agentize 流程時才划算。如果你只用其中一個,單獨那個工具就夠了。

---

## 📦 安裝變體

```bash
# Researcher / Humanities(用 Zotero + NotebookLM)
pip install research-hub-pipeline[playwright,secrets]

# Analyst / Internal KM(不用 Zotero,匯入本機檔案)
pip install research-hub-pipeline[import,secrets]

# 開發用全套
pip install -e '.[dev,playwright,import,secrets,mcp]'
```

Python 3.10+。可選 `npm install -g defuddle-cli` 讓 URL 匯入更乾淨。

---

## 📚 文件

| | |
|---|---|
| [前 10 分鐘](docs/first-10-minutes.md) | 4 個 persona 各自的引導 |
| [Lazy-mode 參考](docs/lazy-mode.md) | 4 個一句話指令 |
| [Dashboard 完整導覽](docs/dashboard-walkthrough.md) | 每個 tab 配 persona 用法 |
| [MCP tools 參考](docs/mcp-tools.md) | 81 個 tool 分類 + 簽名 |
| [Personas](docs/personas.md) | 4 個 persona profile + 功能矩陣 |
| [Cluster integrity](docs/cluster-integrity.md) | 6 個 failure mode × 4 personas |
| [Anti-RAG / crystals](docs/anti-rag.md) | 為什麼預先運算贏 retrieval |
| [NotebookLM 設定](docs/notebooklm.md) + [疑難排解](docs/notebooklm-troubleshooting.md) | patchright + persistent Chrome(v0.42+) |
| [Import folder](docs/import-folder.md) | 本機 PDF/DOCX/MD/TXT/URL 匯入 |
| [Papers input schema](docs/papers_input_schema.md) | Ingestion pipeline 參考 |
| [升級指南](UPGRADE.md) | 從舊版本升上來 |
| [Audit 報告](docs/) | `audit_v0.26.md` … `audit_v0.45.md` |
| [CHANGELOG](CHANGELOG.md) | 每個版本的 release note |

---

## 🩺 疑難排解(第一次跑遇到的問題)

| 症狀 | 原因 | 解法 |
|---|---|---|
| `research-hub init` 印 `chrome WARN patchright cannot launch Chrome` | 沒裝 Chrome,或 patchright 找不到 | 從 chrome.com 裝 Chrome,再跑 `research-hub doctor` 重新偵測 |
| `research-hub notebooklm login` 開了瀏覽器但 Google 擋住登入 | Headless / 新裝置驗證 | 那是 patchright(真的 Chrome)— 在手機按「是的,是我」,然後正常登入 |
| `research-hub auto` 在 `search` 階段拿到 `0 papers` | 主題太窄,或 arXiv/SemSch 短暫斷線 | 加 `--max-papers 20` 或重新描述主題;兩個 backend 都會 fault-tolerant |
| `research-hub auto` 在 `nlm.upload` 階段炸「Generation button not found」 | NotebookLM UI 改了,或你沒登入 | 重跑 `research-hub notebooklm login`;持續發生請開 issue 附 `.research_hub/` 裡的 `nlm-debug-*.jsonl` |
| `auto --with-crystals` 顯示「no LLM CLI on PATH」 | `claude`、`codex`、`gemini` CLI 都沒裝 | 裝你慣用的 AI CLI;或手動跑 `crystal emit` → 貼到 AI → `crystal apply` |
| Claude Desktop 看不到 MCP server | `claude_desktop_config.json` 不在預期位置 | macOS: `~/Library/Application Support/Claude/claude_desktop_config.json` · Windows: `%APPDATA%\Claude\claude_desktop_config.json` · 改完要重啟 Claude Desktop |
| `init` 印 `zotero WARN` 但我不用 Zotero | 預設 persona 是 `researcher`,它預期要 Zotero | 重跑 `research-hub init --persona analyst`(或 `internal`)— 這兩個 persona 完全跳過 Zotero |

其他狀況: `research-hub doctor --autofix` 會修常見的機械問題,報告會告訴你哪個子系統有事。

---

## 🛠 狀態

- **最新**: v0.51.0(2026-04-20)— 通用 `websearch` backend(Tavily / Brave / Google CSE / DDG)+ planner 自動偵測領域,讓 bio/med 查詢挑 pubmed 而不是 arxiv。見 [`CHANGELOG.md`](CHANGELOG.md)。
- **測試**: fast suite 1569 passing(CI: Linux + Windows + macOS × Python 3.10/3.11/3.12 = 9 jobs)
- **MCP tools**: 83 個(v0.47 auto/cleanup/tidy;v0.49 擴充 `auto_research_topic`;v0.50 加 `plan_research_workflow`;v0.51 加 `web_search`)
- **End-to-end 實測通過**: v0.49.5 開始,完整 lazy-mode 流程 — `auto "topic" --with-crystals` → 搜尋 → 收論文 → NotebookLM brief → 預先運算 AI 答案 — 在 Windows zh-TW 機器配真實 `claude` CLI 上實測完整跑完。詳見 [`CHANGELOG.md`](CHANGELOG.md) v0.49.4 的 per-stage 結果表。
- **依賴**: `pyzotero`, `pyyaml`, `requests`, `rapidfuzz`, `networkx`, `platformdirs`(全部純 Python)
- **可選 extras**: `[playwright]` 給 NotebookLM、`[import]` 給本機檔案匯入、`[secrets]` 給 OS keyring

## 👩‍💻 開發者用

```bash
git clone https://github.com/WenyuChiou/research-hub.git
cd research-hub
pip install -e '.[dev,playwright]'
python -m pytest -q                     # 1569 passing
```

貢獻: [CONTRIBUTING.md](CONTRIBUTING.md)。安全性: [SECURITY.md](.github/SECURITY.md)。

PyPI 套件名: **research-hub-pipeline** · CLI 進入點: **research-hub**

## 授權

MIT。詳見 [LICENSE](LICENSE)。

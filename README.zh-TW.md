# research-hub

> **打一句話進去。Cluster + 論文 + AI 簡報出來。約 50 秒。**
> Zotero + Obsidian + NotebookLM 三合一,專為 AI agent 打造 — **不需要 OpenAI/Anthropic API key**。

![research-hub dashboard](docs/images/hero/dashboard-overview.png)

[![PyPI](https://img.shields.io/pypi/v/research-hub-pipeline.svg)](https://pypi.org/project/research-hub-pipeline/)
[![Tests](https://img.shields.io/badge/tests-1661%20passing-brightgreen.svg)](docs/audit_v0.45.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

English → [README.md](README.md)

📺 **[看 30 秒 dashboard 實測影片 →](docs/demo/dashboard-walkthrough.mp4)**

---

## 任何 AI host 都能用

只要你的 AI 會載 MCP tool、會跑 shell 指令、或會打 HTTP,它就能驅動 research-hub。

| 你的 AI | research-hub 怎麼接 |
|---|---|
| **Claude Desktop**(Anthropic 的桌面 app) | MCP stdio via `claude_desktop_config.json` |
| **Claude Code**(Anthropic 的 terminal / VS Code agent) | MCP stdio — 裝完 research-hub 後直接能用 |
| **Cursor · Continue.dev · Cline · Roo Code · VS Code Copilot** | 一樣的 MCP 設定,各自 host 有自己的 config 欄位 |
| **OpenClaw · 其他任何 MCP 相容 host** | MCP stdio |
| **ChatGPT · Claude.ai 網頁 · Gemini 網頁 · OpenAI Custom GPT** | REST JSON at `/api/v1/*`(bearer token + CORS) |
| **Codex CLI · Gemini CLI · GPT Code Interpreter · LangChain · AutoGen · CrewAI** | Shell subprocess — 每個指令都支援 `--json` 輸出 |
| **你自己寫的 Python script** | `from research_hub.auto import auto_pipeline`(任何函式都能 import) |

---

## 🤖 直接叫你的 AI 幫你裝

不想自己打指令?把下面這段複製到任何會幫你跑 shell 的 AI(Claude Desktop / Claude Code / Cursor / Continue / ChatGPT / Gemini)就好。它是個自給自足的安裝腳本,AI 會照步驟跑,需要你給東西時會停下來問你(Zotero key、vault 路徑、你用哪個 MCP host 等等)。

```text
請幫我從頭到尾安裝 research-hub。它是一個 Python 套件,把學術論文
pipe 進 Zotero + Obsidian + NotebookLM,並提供 MCP server。

依序做這些步驟。需要我互動的地方停下來問我,不要自己編:

1. 檢查: `python --version`。如果 < 3.10,叫我先升級再繼續。

2. 安裝: `pip install research-hub-pipeline[playwright,secrets]`

3. 跑 `research-hub init`。它會問問題,把問題轉給我,不要亂猜。
   persona 選項有 `researcher` / `humanities` / `analyst` / `internal`;
   問我哪個適合。如果我沒有 Zotero API key,停下來告訴我去
   https://www.zotero.org/settings/keys 拿。

4. 跑 `research-hub notebooklm login`。會開瀏覽器 — 告訴我完成 Google 登入。

5. 搞清楚我用哪個 AI host(通常就是你自己)。修改它的 MCP 設定,加入:
     { "mcpServers": { "research-hub": { "command": "research-hub", "args": ["serve"] } } }
   設定檔位置:
     - Claude Desktop (macOS):  ~/Library/Application Support/Claude/claude_desktop_config.json
     - Claude Desktop (Windows): %APPDATA%\Claude\claude_desktop_config.json
     - Cursor: Settings → MCP Servers
     - Continue.dev: ~/.continue/config.json
     - Cline / Roo: VS Code 設定裡 `cline.mcpServers`
   不確定的話問我我現在是透過哪個 host 跟你講話。

6. 跑 `research-hub install --platform claude-code`(或 `cursor` / `codex` /
   `gemini`,對應步驟 5 的 host)。這會把 skill 檔案複製到 host 的 skills 目錄,
   讓之後的 AI 對話知道怎麼正確用 research-hub 工具。

7. 叫我重啟 AI host。重啟後,問我要研究什麼主題當煙測,然後跑:
   `research-hub auto "主題" --with-crystals`
```

就這樣。AI 全部幫你處理,你只要回答它問你的問題就好。

---

## 或手動安裝(約 60 秒)

```bash
pip install research-hub-pipeline[playwright,secrets]
research-hub init                          # 互動式:選 persona + Zotero + 就緒檢查
research-hub notebooklm login              # 一次性 Google 登入
research-hub auto "你想研究的主題"          # 約 50 秒後拿到論文 + AI brief
```

`init` 結尾會跑一次**首次執行就緒檢查**,缺哪個(Obsidian vault、Chrome、Zotero key、LLM CLI)會直接告訴你。如果 `claude` / `codex` / `gemini` CLI 在 PATH 上,加 `--with-crystals` 讓 crystal 也自動生成:

```bash
research-hub auto "主題" --with-crystals
```

不確定要怎麼問?先 plan:

```bash
research-hub plan "我想學 harness engineering"
# 自動調 max_papers(看到「thesis / 深入」會調大)、偵測領域
# (bio/med/cs/…)、警告 cluster 撞名,印出可以直接執行的 `auto` 指令。
```

---

## 接到你的 AI host(30 秒,一次性設定)

不論 Claude Desktop / Cursor / Continue.dev / Cline / VS Code Copilot / OpenClaw,MCP 設定都是同樣格式。找到該 host 的 MCP config 檔案,加上:

```json
{ "mcpServers": { "research-hub": { "command": "research-hub", "args": ["serve"] } } }
```

重啟 host。然後直接用自然語言講話 — 下面用 Claude 當例子,對任何 MCP host 都一樣:

> **你:**「幫我找 5 篇 agent-based modeling 的論文放進 notebook」
> **AI:** *呼叫 `auto_research_topic(topic="agent-based modeling", max_papers=5)`* → 5 篇論文 + NotebookLM brief,約 50 秒。

> **你:**「我的 llm-evaluation-harness cluster 現在 SOTA 是什麼?」
> **AI:** *呼叫 `read_crystal("llm-evaluation-harness", "sota-and-open-problems")`* → 180 字預先寫好的答案,附引用。**讀 ~1 KB、0 篇 abstract 被重新讀取。**

**總共 83 個 MCP tools** — 完整參考: [`docs/mcp-tools.md`](docs/mcp-tools.md)。最重要的幾個:

| Tool | 取代了什麼 |
|---|---|
| `auto_research_topic(topic)` | 7 步驟 CLI 流程(search → ingest → bundle → upload → generate → download) |
| `plan_research_workflow(intent)` | 猜 max_papers / field / cluster slug |
| `ask_cluster_notebooklm(cluster, question)` | 開 NotebookLM、貼問題、複製答案 |
| `read_crystal(cluster, slot)` | 重讀 20 篇 abstract 回答同一個問題 |
| `web_search(query)` | 手動蒐集 blog/docs/news 連結 |
| `cleanup_garbage` + `tidy_vault` | `du -sh` + 手動 `rm -rf` + 手動跑 doctor |

**瀏覽器內的 AI**(ChatGPT、Claude.ai 網頁、Custom GPT)不能用 MCP — 改用 REST API:

```bash
curl -X POST http://127.0.0.1:8765/api/v1/plan \
     -H 'Content-Type: application/json' \
     -d '{"intent":"research harness engineering"}'
```

---

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

## 📓 在 Obsidian 裡長什麼樣

Dashboard 是一面;另一面才是你實際在用的:**Obsidian**。research-hub 收的每一篇論文都變成真正的 `.md` 筆記、含結構化 frontmatter,每個 cluster 還會自動產一個 **Bases** dashboard,你不離開 Obsidian 就能瀏覽。

| | |
|---|---|
| ![Cluster Bases dashboard](docs/images/obsidian-bases-dashboard.png) | ![單篇 paper 筆記 (Properties view)](docs/images/obsidian-paper-note.png) |
| **Cluster Bases dashboard** — 每個 cluster 自動產 `.base`(v0.43+)。可排序/可過濾的論文 database view,欄位從 frontmatter 自動建(name / title / year / status / verified / doi)。每次 `ingest` / `topic build` 自動刷新。 | **單篇 paper 筆記** — 每篇收進來的論文都有結構化 frontmatter(title / authors / year / journal / doi / zotero-key / collections / tags / ingested_at / topic_cluster / cluster_queries / verified / status)。可以 wikilink、可以被 Obsidian graph 收錄、可以全文搜尋。 |

Crystals(預先運算的 AI 答案)也是 Obsidian 原生筆記,放在 `hub/<cluster>/crystals/*.md`,完全可以 wikilink、graph view 看得到、可以透過 `read_crystal()` MCP tool 0 token 查詢。

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

- **最新**: v0.53.0(2026-04-20)— 多 AI skill pack: `research-hub install --platform claude-code` 現在會一起安裝 multi-AI orchestration skill,教 Claude 什麼時候把 crystal 產生 delegate 給 Codex、什麼時候把 CJK 內容 delegate 給 Gemini。見 [`CHANGELOG.md`](CHANGELOG.md)。
- **測試**: fast suite 1585 passing(CI: Linux + Windows + macOS × Python 3.10/3.11/3.12 = 9 jobs)
- **MCP tools**: 83 個(v0.47 auto/cleanup/tidy;v0.49 擴充 `auto_research_topic`;v0.50 加 `plan_research_workflow`;v0.51 加 `web_search`)
- **REST endpoints**: 12 個 at `/api/v1/*`,涵蓋 health/clusters/crystals/search/websearch/plan/ask/auto
- **內建 skills**: 2 個 — `research-hub`(核心 pipeline)+ `research-hub-multi-ai`(Claude + Codex + Gemini 分工 pattern)
- **End-to-end 實測通過**: v0.49.5 開始,完整 lazy-mode 流程 — `auto "topic" --with-crystals` → 搜尋 → 收論文 → NotebookLM brief → 預先運算 AI 答案 — 在 Windows zh-TW 機器配真實 `claude` CLI 上實測完整跑完。詳見 [`CHANGELOG.md`](CHANGELOG.md) v0.49.4 的 per-stage 結果表。
- **依賴**: `pyzotero`, `pyyaml`, `requests`, `rapidfuzz`, `networkx`, `platformdirs`(全部純 Python)
- **可選 extras**: `[playwright]` 給 NotebookLM、`[import]` 給本機檔案匯入、`[secrets]` 給 OS keyring

## 👩‍💻 開發者用

```bash
git clone https://github.com/WenyuChiou/research-hub.git
cd research-hub
pip install -e '.[dev,playwright]'
python -m pytest -q                     # 1585 passing
```

貢獻: [CONTRIBUTING.md](CONTRIBUTING.md)。安全性: [SECURITY.md](.github/SECURITY.md)。

PyPI 套件名: **research-hub-pipeline** · CLI 進入點: **research-hub**

## 授權

MIT。詳見 [LICENSE](LICENSE)。

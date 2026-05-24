# research-hub

> **把你的研究工具變成 AI 可以操作的工作區。**
> 你可以同時使用 Zotero、Obsidian、NotebookLM，也可以先從任意兩個工具開始。research-hub 提供 CLI、MCP server、REST API、Dashboard，讓 AI 助手能重複執行文獻搜尋、整理、摘要與維護流程。

![research-hub dashboard demo](docs/images/dashboard-walkthrough.gif)

[![PyPI](https://img.shields.io/pypi/v/research-hub-pipeline.svg)](https://pypi.org/project/research-hub-pipeline/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

[![Zotero](https://img.shields.io/badge/Zotero-CC2936?logo=zotero&logoColor=white)](https://www.zotero.org/)
[![Obsidian](https://img.shields.io/badge/Obsidian-7C3AED?logo=obsidian&logoColor=white)](https://obsidian.md/)
[![NotebookLM](https://img.shields.io/badge/NotebookLM-4285F4?logo=google&logoColor=white)](https://notebooklm.google.com/)

[English README](README.md) | [完整示範影片](docs/demo/dashboard-walkthrough.mp4)

---

## 這個專案解決什麼問題

Zotero、Obsidian、NotebookLM 都很有用，但它們各自處理不同段落：

- Zotero 管引用、metadata、PDF。
- Obsidian 管筆記、連結、知識整理。
- NotebookLM 把來源變成 AI 可以閱讀與詢問的 brief。

真正麻煩的是中間的交接。research-hub 把交接流程自動化，讓 AI agent 可以搜尋、匯入、標籤、摘要、修復、產生 brief、檢查 dashboard，而不是每一步都手動搬資料。

你不需要一開始就使用三個工具。

| 你現在使用的組合 | research-hub 先提供什麼 |
|---|---|
| Zotero + Obsidian | 文獻搜尋、Zotero metadata、Markdown 筆記、標籤、Obsidian Bases dashboard |
| Obsidian + NotebookLM | 本機 PDF/DOCX/MD/TXT 匯入、cluster dashboard、NotebookLM bundle/brief |
| Zotero + NotebookLM | Zotero-backed paper selection、namespaced tags、NotebookLM upload/generate/download |
| Zotero + Obsidian + NotebookLM | 完整流程：discover -> ingest -> organize -> brief -> answer -> maintain |
| 還沒有帳號 | sample dashboard 與本機 smoke test |

---

## 先從哪裡開始

先選摩擦最小的路徑。Zotero、NotebookLM、MCP、AI host skills 都可以之後再加。

| 目標 | 需要帳號 | 指令 |
|---|---|---|
| 只看 dashboard 預覽 | 不需要 | `pip install research-hub-pipeline` 後跑 `research-hub dashboard --sample` |
| 試用 demo vault | 不需要 | `pip install research-hub-pipeline` 後跑 `research-hub init --sample` |
| 先整理本機 PDF/DOCX/Markdown | Obsidian 可選 | `pip install "research-hub-pipeline[import,secrets]"` 後跑 `research-hub setup --persona analyst` |
| Zotero + Obsidian，不先碰 NotebookLM | Zotero | `pip install "research-hub-pipeline[secrets]"` 後跑 `research-hub setup --skip-login` |
| Zotero + Obsidian + NotebookLM 完整流程 | Zotero + Google | `pip install "research-hub-pipeline[playwright,secrets]"` 後跑 `research-hub setup` |
| 給 autonomous agent 啟動 | 既有 vault 或目標資料夾 | `python -m research_hub setup --autonomous --vault ./vault --persona agent` |

設定後先跑：

```bash
research-hub doctor
research-hub serve --dashboard
```

第一次真的匯入文獻時，建議先不要把 NotebookLM 放進流程，先確認 Zotero 與 Obsidian 正常：

```bash
research-hub auto "agent-based modeling" --max-papers 3 --no-nlm
```

等 NotebookLM 瀏覽器登入完成後，再跑完整 NotebookLM 流程：

```bash
research-hub notebooklm login --auto-detect
research-hub notebooklm bundle --cluster <slug>
research-hub notebooklm upload --cluster <slug>
research-hub notebooklm generate --cluster <slug> --type brief
research-hub notebooklm download --cluster <slug>
```

`research-hub setup` 結束時也會印出這些下一步。

## 首次設定檢查表

| 項目 | 什麼時候需要 | 怎麼處理 |
|---|---|---|
| Python 3.10+ | 一定需要 | 用同一個 Python 執行 `pip install research-hub-pipeline` |
| Zotero API key + library ID | 使用 Zotero 匯入文獻時 | 設定 `ZOTERO_API_KEY`、`ZOTERO_LIBRARY_ID`，再跑 `research-hub doctor` |
| Obsidian vault | 想產生 Markdown 筆記時 | `setup` 指到一個可以用 Obsidian 開啟的資料夾；內容仍是一般 Markdown |
| NotebookLM browser login | 使用 NotebookLM upload/generate/download 時 | 跑 `research-hub notebooklm login --auto-detect`；Google OAuth 仍需要人類在可見瀏覽器完成 |
| LLM CLI 關聯性判斷 | 預設 `research-hub auto` 流程 | 安裝 `claude`、`codex`、`gemini`、`opencode`、`aichat`、`cursor`，設定自訂 adapter，或加 `--no-fit-check` |
| AI host 整合 | Claude/Codex/Cursor/Gemini/OpenClaw 等 | Tool-calling host 用 MCP/REST；只有已驗證平台才用 `research-hub install --platform ...` |

Semantic Scholar 搜尋有內建節流。沒有 `SEMANTIC_SCHOLAR_API_KEY`
時會用較慢的匿名速度，因為公共流量共享容量；有 API key 時預設約
每秒一個 request，遇到 HTTP 429 會依 `Retry-After` 或 exponential
backoff 自動重試。若你的 key 有不同額度，再設定
`SEMANTIC_SCHOLAR_RPS`，一般使用者不需要調。

> **第一次跑 `auto` 前請看**：`auto` 預設會做 **fail-closed** 的關聯性判斷。若沒有支援的 LLM CLI，也沒有加 `--no-fit-check`，`auto` 會在搜尋**前**停下並給出修正指引，而不是默默產生空的 vault。
>
> **真實性閘門 (v0.95+)**：每篇文獻都必須能解析出真實識別碼（DOI / arXiv / PMID）並通過完整性與關聯性檢查，否則會被 **隔離（quarantine）並記錄原因**，不會寫進 vault。用 `research-hub quarantine list` 檢視被擋下的文獻。

---

## 連接 AI host

research-hub 有兩層 AI 整合方式：

| 層級 | 適合對象 | 目前狀態 |
|---|---|---|
| MCP / REST | Claude Desktop、Claude Code、Cursor、Continue.dev、Cline、Roo Code、VS Code Copilot、OpenClaw，以及其他能呼叫工具的 host | 通用；設定 MCP server 或呼叫 REST API |
| 已知 skill installer | Claude Code、Codex、Cursor、Gemini | 可用 `research-hub install --platform ...` 安裝 |
| 手動載入 `SKILL.md` | Hermes、OpenClaw、其他支援 skill/rules 目錄的 agent | 可手動複製 `skills/` 內的 skill；目前不是 release-verified installer target |

Claude Desktop、Cursor、Continue.dev、Cline、Roo Code、OpenClaw，或其他 MCP host 可以這樣連接：

```json
{ "mcpServers": { "research-hub": { "command": "research-hub", "args": ["serve"] } } }
```

下列平台有明確的預設 skills 目錄，因此可以直接安裝各平台用的 skill files：

```bash
research-hub install --platform claude-code
research-hub install --platform cursor
research-hub install --platform codex
research-hub install --platform gemini
```

OpenClaw、Hermes 和其他 agent 仍可透過 MCP/REST 使用 research-hub。若該 host 支援 `SKILL.md` 或 rules 目錄，請手動複製 `skills/` 內的對應目錄，或把相關 `SKILL.md` inline 到該 host 的指令中；`research-hub install --platform` 目前不驗證這些 host。

更多細節請看英文 README、[First 10 minutes](docs/first-10-minutes.md)、[MCP tools](docs/mcp-tools.md)、[AI integrations](docs/ai-integrations.md)。

## 授權

MIT. See [LICENSE](LICENSE).

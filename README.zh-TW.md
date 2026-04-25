# research-hub

> **把你的研究工具變成 AI 可以操作的工作區。**
> 你可以同時使用 Zotero、Obsidian、NotebookLM，也可以先從任意兩個工具開始。research-hub 提供 CLI、MCP server、REST API、Dashboard，讓 AI 助手能重複執行文獻搜尋、整理、摘要與維護流程。

[English README](README.md) | [完整示範影片](docs/demo/dashboard-walkthrough.mp4)

![research-hub dashboard demo](docs/images/dashboard-walkthrough.gif)

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

## 快速開始

### 不連帳號先預覽

```bash
pip install research-hub-pipeline
research-hub dashboard --sample
```

### Obsidian + 本機資料優先

```bash
pip install research-hub-pipeline[import,secrets]
research-hub setup --persona analyst
research-hub import-folder ./papers --cluster my-local-review
research-hub serve --dashboard
```

### Zotero + Obsidian + NotebookLM 完整流程

```bash
pip install research-hub-pipeline[playwright,secrets]
research-hub setup
research-hub auto "your research topic"
```

如果你暫時不想測 NotebookLM browser automation：

```bash
research-hub auto "your research topic" --no-nlm
```

---

## 連接 AI host

支援 Claude Desktop、Claude Code、Cursor、Continue.dev、Cline、Roo Code、OpenClaw，以及其他 MCP host：

```json
{ "mcpServers": { "research-hub": { "command": "research-hub", "args": ["serve"] } } }
```

也可以安裝各平台用的 skill files：

```bash
research-hub install --platform claude-code
research-hub install --platform cursor
research-hub install --platform codex
research-hub install --platform gemini
```

更多細節請看英文 README、[First 10 minutes](docs/first-10-minutes.md)、[MCP tools](docs/mcp-tools.md)、[AI integrations](docs/ai-integrations.md)。

## 授權

MIT. See [LICENSE](LICENSE).

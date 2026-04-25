# AI 整合指南 — 紙本搜尋與主題概覽

research-hub 的設計是模型無關（model-agnostic）的。任何能夠執行 shell 指令或呼叫 MCP 工具的 AI，都能驅動相同的 discovery → ingest → overview 工作流程。本指南展示了每個常見 AI 介面的確切路徑。

每個路徑的結束方式都相同：`research-hub topic digest --cluster X` 提供 AI 集群中的所有摘要（abstracts）；AI 讀取它們並撰寫 overview，NotebookLM 則作為最終的健全性檢查（"這個集群真的包含我說的內容嗎？"）。

---

## 共用工作流程

```
┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌────────────┐   ┌──────────────┐
│  discover   │ → │    enrich    │ → │    ingest    │ → │  overview  │ → │ NotebookLM   │
│ (尋找 DOI)  │   │ (完整中繼資料) │   │ (Zotero+vault│   │ (topic.md) │   │ (驗證 fit)   │
└─────────────┘   └──────────────┘   └──────────────┘   └────────────┘   └──────────────┘
```

1. **Discover** — 為一個主題尋找候選論文。如何執行取決於你的 AI 擁有什麼工具。
2. **Enrich** — 透過 OpenAlex/arXiv/Semantic Scholar 將候選者（DOI / arxiv_id / title）轉換為完整的 `SearchResult` 記錄。
3. **Ingest** — 將 enriquecido 的記錄傳送給 `research-hub ingest`，它會填充 Zotero + Obsidian + dedup 索引。
4. **Overview** — 執行 `research-hub topic digest` 來匯出 cluster 的摘要；AI 讀取它們並撰寫 `00_overview.md`。
5. **NotebookLM** — 將 cluster 的 PDF 上傳為一個 notebook，詢問 "這真的與 X 有關嗎？" — 這是真實性檢查。

---

## Claude Code (擁有 WebSearch)

Claude Code 是唯一能直接存取 `WebSearch` 的 AI。用它來進行 discovery；讓 research-hub 處理中繼資料解析。

```bash
# 1. Discover — Claude 使用其 WebSearch 工具尋找候選論文。
#    將 DOIs 或 arxiv IDs 收集到一個檔案中，每行一個：
cat > /tmp/candidates.txt <<EOF
10.48550/arXiv.2411.12345
10.48550/arXiv.2410.67890
2411.00000
Tight-Lipped Agents: A Study of LLM Reticence
EOF

# 2. Enrich — research-hub 針對每個候選者呼叫 OpenAlex/arXiv/Semantic Scholar
research-hub enrich - < /tmp/candidates.txt > /tmp/enriched.json

# 3. 建立一個 papers_input.json scaffold
research-hub enrich --to-papers-input --cluster my-topic - < /tmp/candidates.txt 
    > /tmp/papers_input.json
# Claude 然後透過閱讀每個候選摘要，填入 summary/key_findings/methodology/relevance 欄位。

# 4. Ingest
research-hub ingest --cluster my-topic --input /tmp/papers_input.json

# 5. Topic overview
research-hub topic scaffold --cluster my-topic
research-hub topic digest --cluster my-topic > /tmp/digest.md
# Claude 讀取 /tmp/digest.md 並直接透過 Edit 寫入
# <vault>/research_hub/hub/my-topic/00_overview.md。

# 6. NotebookLM verification
research-hub notebooklm bundle --cluster my-topic --download-pdfs
research-hub notebooklm upload --cluster my-topic
research-hub notebooklm generate --cluster my-topic --type brief
research-hub notebooklm download --cluster my-topic
# 閱讀 briefing — 如果它抱怨有離題的論文，請回到步驟 1。
```

**混合提示：** Claude Code 也可以呼叫下方的 MCP 工具，如果它運行時連接了 research-hub 的 MCP server。混合使用 WebSearch（用於 discovery）和 MCP `enrich_candidates`（用於中繼資料）是最穩健的路徑，因為每個步驟都使用了最強的工具。

---

## Claude Desktop / Cursor / Continue / 任何 MCP 客戶端

這些 AI 沒有 WebSearch，但它們可以直接呼叫 research-hub 的 MCP 工具。所有操作都通過工具呼叫進行；無需 shell。

在客戶端的設定中啟用 MCP（以 Claude Desktop 在 `~/.claude/claude_desktop_config.json` 為例）：

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

然後完全透過工具呼叫來驅動工作流程：

```
search_papers(
    query="LLM agent software engineering benchmark",
    year_from=2024,
    year_to=2025,
    min_citations=5,
    backends=["openalex", "arxiv"]
) -> list of papers with DOI, abstract, citation_count, year

# 如果使用者貼上他們已有的 DOI 列表：
enrich_candidates(candidates=["10.xxx/yyy", "2411.00000"]) -> full records

# ingest 之後：
get_topic_digest(cluster_slug="my-topic") -> {
    "papers": [...],
    "markdown": "<AI 讀取的完整文字摘要>"
}

# AI 撰寫 overview 內容，然後：
write_topic_overview(
    cluster_slug="my-topic",
    markdown="<AI 生成的 overview>",
    overwrite=False
)

read_topic_overview(cluster_slug="my-topic")
    -> 返回內容以便使用者驗證
```

**沒有 WebSearch 的路徑** — discovery 必須使用 `search_papers`。三個後端組成的備用鏈（fallback chain）提供了良好的 2024-2025 年數據涵蓋範圍。對於三個後端都找不到的 topic，使用者必須貼上 DOI 並使用 `enrich_candidates`。

---

## Codex CLI / Aider / 一般 shell

Shell 原生的 AI 直接執行 `research-hub`。不需要 MCP server。

```bash
# 1. 透過 CLI 進行 Discover (傳送 JSON)
research-hub search "LLM agent software engineering" 
    --year 2024-2025 
    --min-citations 5 
    --backend openalex,arxiv 
    --json > candidates.json

# 2. 提取 DOI 並 enrich (冪等操作 — 可安全地重新執行)
jq -r '.[].doi' candidates.json | research-hub enrich - > enriched.json

# 3. 建立 papers_input.json
research-hub search "LLM agent software engineering" 
    --year 2024-2025 
    --to-papers-input 
    --cluster my-topic 
    > papers_input.json
# AI 透過閱讀每個 paper 的 abstract 欄位，填入 summary/key_findings/methodology/relevance。

# 4. Ingest
research-hub ingest --cluster my-topic --input papers_input.json

# 5. Topic overview
research-hub topic scaffold --cluster my-topic
research-hub topic digest --cluster my-topic > digest.md
# AI 讀取 digest.md (透過 cat 或其自身的 Read)，將 overview 寫入
# <vault>/research_hub/hub/my-topic/00_overview.md

# 6. 傳送至 NotebookLM 進行驗證
research-hub notebooklm bundle --cluster my-topic --download-pdfs
research-hub notebooklm upload --cluster my-topic
```

**Codex 提示：** 使用 `codex exec --full-auto -C ~/vault "do steps 1-5 for cluster llm-agents"`，Codex 將執行整個鏈條。

---

## Gemini CLI

與 Codex CLI 相同 — shell 路徑。`research-hub` CLI 是模型無關的。

Gemini 特定注意事項：當要求 Gemini 填寫 papers_input.json 的摘要時，一次給它一小批 JSON（5-10 篇論文），而不是一次全部 25 篇。Gemini 的 JSON 輸出可靠性在長上下文（long contexts）中會下降。

---

## 何時使用哪個

| 你擁有 | 推薦路徑 |
|---|---|
| 一份 DOI 或 arxiv ID 列表 | `research-hub enrich - < candidates.txt` |
| 一個主題但沒有論文 | `research-hub search "..." --year 2024-2025 --json` |
| 一個現有的 cluster 但沒有 overview | `research-hub topic scaffold && research-hub topic digest` |
| 一個可能離題的 cluster | 打包並上傳到 NotebookLM，然後詢問 "這是關於 X 的嗎？" |
| 擁有 WebSearch 的 Claude Code | WebSearch 用於 discovery + `enrich` 用於中繼資料 |
| 其他任何情況 | 透過 CLI 或 MCP 的三後端 `search_papers` |

---

## 離線 / airgapped 模式

三個後端都需要網路。如果你離線：

- `research-hub search --backend ""` 會失敗 — backend 列表不能為空。
- 使用 `research-hub add --doi 10.xxx/yyy` 或 `add_paper` MCP 工具進行一次性添加。這兩個路徑都接受你已經信任的 DOI，無需搜索步驟。
- `research-hub topic digest` 和 `scaffold` 完全離線工作 — 它們只讀取 vault 檔案。

---

## 調查 discovery 品質

如果 NotebookLM 標記了離題的論文，那麼 discovery 步驟應負責任。檢查：

1. **詞彙 vs. 語義漂移** — Semantic Scholar 是詞彙學的，OpenAlex 使用概念。像 "harness engineering" 這樣的查詢在 Semantic Scholar 上會錯過 "agent benchmark for software engineering"，但在 OpenAlex 上可以找到。對於概念性查詢，優先使用 `--backend openalex,arxiv`。
2. **年份範圍過寬** — `--year 2020-2025` 會用過時的工作稀釋 2025 年的主題。對於新的研究領域，請縮窄到 `2024-2025`。
3. **引用閾值** — `--min-citations 10` 會移除大多數的 preprint。對於新的主題，請移除此選項。
4. **標題漂移** — 如果 `enrich_candidates` 返回的論文標題與你的輸入不同，模糊匹配閾值為 60。低於此閾值的標題將返回 `None`。盡可能提供 DOI 或 arxiv ID。

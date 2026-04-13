# CLI 參考

針對 research-hub v0.9.0 版本生成。35+ 個子指令，依工作流程階段分組。

## 設定 (Setup)

### `init`
互動式設定精靈。

```bash
research-hub init [--vault PATH] [--zotero-key KEY] [--zotero-library-id ID]
                  [--non-interactive] [--persona researcher|analyst]
```

| Flag | 說明 |
|---|---|
| `--vault PATH` | Vault 根目錄 (預設: ~/knowledge-base) |
| `--zotero-key KEY` | Zotero API 金鑰 (僅限 researcher persona) |
| `--zotero-library-id ID` | Zotero 圖書館 ID |
| `--non-interactive` | 跳過提示；透過 flag 提供值 |
| `--persona` | researcher (預設) 或 analyst (跳過 Zotero) |

範例：
```bash
research-hub init --persona analyst --vault ~/my-vault
```

### `doctor`
健康檢查 (設定檔, vault, Zotero, dedup, Chrome, NLM session)。

```bash
research-hub doctor
```

### `install`
安裝 AI 助理技能。

```bash
research-hub install --platform claude-code|codex|cursor|gemini
research-hub install --list
```

### `dashboard`
為 vault 生成個人化的 HTML dashboard。

```bash
research-hub dashboard [--open]
```

| Flag | 說明 |
|---|---|
| `--open` | 生成後在你的預設瀏覽器中開啟 dashboard |

Output: `<vault>/.research_hub/dashboard.html` — 單一獨立檔案，包含 stat cards、cluster table、status badges 和 NotebookLM 連結。離線可用。

## 搜尋與驗證 (Search & verification)

### `search`
查詢 Semantic Scholar。

```bash
research-hub search "QUERY" [--limit N] [--verify]
```

### `verify`
透過 DOI / arXiv ID / 模糊標題比對，檢查 paper 是否存在。

```bash
research-hub verify --doi 10.1234/x
research-hub verify --arxiv 2502.10978
research-hub verify --paper "Title" [--paper-year 2025] [--paper-author "Last"]
```

### `references`
列出給定 paper 引用的 paper (其參考文獻)。

```bash
research-hub references <doi-or-arxiv-id> [--limit 20] [--json]
```

### `cited-by`
列出引用給定 paper 的 paper。

```bash
research-hub cited-by <doi-or-arxiv-id> [--limit 20] [--json]
```

## 儲存與整理 (Save & organize)

### `add`
**一站式搜尋 → 儲存指令。**

```bash
research-hub add <doi-or-arxiv-id> [--cluster SLUG]
                                    [--no-zotero] [--no-verify]
```

### `ingest` / `run`
從 `papers_input.json` 執行完整 pipeline。

```bash
research-hub ingest [--cluster SLUG] [--no-verify]
research-hub run    [--cluster SLUG]
```

### `suggest`
Cluster + 相關 paper 建議。

```bash
research-hub suggest <doi-or-title> [--top 5] [--json]
```

### `find`
在 vault notes 中搜尋。

```bash
research-hub find "QUERY" [--cluster SLUG] [--status STATUS]
                          [--full] [--json]
```

### `mark`
更新閱讀狀態。

```bash
research-hub mark <slug> --status unread|reading|deep-read|cited
research-hub mark --cluster SLUG --status STATUS    # 批次處理
```

### `move`
在 clusters 間移動 paper。

```bash
research-hub move <slug> --to <cluster>
```

### `remove`
從 vault 中移除 paper。

```bash
research-hub remove <doi-or-slug> [--zotero] [--dry-run]
```

### `cite`
匯出引用。

```bash
research-hub cite <doi-or-slug> [--format bibtex|biblatex|ris|csljson] [--out FILE]
research-hub cite --cluster <slug> --format bibtex --out cluster.bib
```

## Cluster 管理 (Cluster management)

### `clusters list/show/new`

```bash
research-hub clusters list
research-hub clusters show <slug>
research-hub clusters new --query "topic" [--name "Display Name"]
```

### `clusters bind`
將 cluster 連結到 Zotero collection / Obsidian folder / NotebookLM notebook。

```bash
research-hub clusters bind <slug> [--zotero KEY] [--obsidian PATH] [--notebooklm "Name"]
```

### `clusters rename / delete / merge / split`

```bash
research-hub clusters rename <slug> --name "New Name"
research-hub clusters delete <slug> [--dry-run]
research-hub clusters merge <source> --into <target>
research-hub clusters split <source> --query "keywords" --new-name "Name"
```

## 維護 (Maintenance)

### `dedup`

```bash
research-hub dedup invalidate [--doi DOI] [--path PATH]
research-hub dedup rebuild [--obsidian-only]
```

### `index`
從 Zotero + Obsidian 重建 dedup_index.json。

```bash
research-hub index
```

### `status`
各 cluster 的閱讀進度。

```bash
research-hub status [--cluster SLUG]
```

### `sync`

```bash
research-hub sync status [--cluster SLUG]
research-hub sync reconcile --cluster SLUG [--dry-run] [--execute]
```

### `cleanup`
去重複化 hub page 的 wikilinks。

```bash
research-hub cleanup [--dry-run]
```

### `synthesize`
生成 cluster 綜合頁面。

```bash
research-hub synthesize [--cluster SLUG] [--graph-colors]
```

### `migrate-yaml`
修補舊版 notes 至目前的 YAML 規範。

```bash
research-hub migrate-yaml [--assign-cluster SLUG] [--folder PATH]
                          [--force] [--dry-run]
```

## NotebookLM

### `notebooklm login`

```bash
research-hub notebooklm login --cdp [--keep-open] [--timeout 300]
```

### `notebooklm bundle`

```bash
research-hub notebooklm bundle --cluster SLUG
```

### `notebooklm upload`

```bash
research-hub notebooklm upload --cluster SLUG [--dry-run] [--headless] [--visible]
```

### `notebooklm generate`

```bash
research-hub notebooklm generate --cluster SLUG --type brief|audio|mind-map|video|all
                                  [--headless] [--visible]
```

### `notebooklm download`
將生成的摘要拉回 vault 作為純文字。v0.9.0
支援 `--type brief`; audio/mind-map/video 下載將在
v0.9.1 中登場。

```bash
research-hub notebooklm download --cluster SLUG [--type brief] [--visible]
```

Output: `<vault>/.research_hub/artifacts/<cluster_slug>/brief-<UTC>.txt`
包含一個小標頭 (notebook 名稱, source URL, timestamp, 儲存的 briefing 標題)
接著是 briefing 主體。

### `notebooklm read-briefing`
列印 cluster 最近下載的 briefing。

```bash
research-hub notebooklm read-briefing --cluster SLUG
```

## AI 整合 (AI integration)

### `serve`
啟動 MCP stdio server 以供 Claude Desktop / Cursor / Claude.ai 使用。

```bash
research-hub serve
```

將此加入你的 Claude Desktop 設定檔：

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

已暴露 21 個 MCP 工具。請參閱 [docs/mcp-tools.md](mcp-tools.md) 取得完整清單。
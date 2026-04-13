# 快速入門

## 安裝

```bash
pip install research-hub-pipeline[mcp]
```

## 初始化

執行設定精靈：

```bash
research-hub init --vault ~/knowledge-base
```

或者，使用欄位導向的入門流程開始：

```bash
research-hub init --field cs
```

## 驗證

```bash
research-hub doctor
```

## 搜尋

```bash
research-hub search "LLM agent software engineering benchmark" --field cs
```

## 探索

```bash
research-hub discover new --cluster llm-agents --query "LLM agent software engineering benchmark" --field cs
```

然後評分產生的 fit-check prompt 並繼續：

```bash
research-hub discover continue --cluster llm-agents --scored scored.json --auto-threshold
```

## 匯入

```bash
research-hub ingest --cluster llm-agents --fit-check
```

## 後續步驟

- 使用 `research-hub topic scaffold --cluster <slug>` 建構主題筆記
- 使用 `research-hub examples list` 瀏覽套件範例
- 使用 `research-hub dashboard` 啟動本機儀表板

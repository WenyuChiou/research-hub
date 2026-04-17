# 為什麼 Crystals 不是 RAG

_v0.28.0 的架構說明。English → [anti-rag.md](anti-rag.md)。_

## 我們在反對什麼

每一個「給 AI 用的知識庫」系統 — 向量資料庫、Notion AI、Obsidian Copilot、Mem、Reflect，連 Karpathy 最近提出的「LLM wiki」也算 — 都犯了同一個架構病：

**當 AI 需要理解你的知識時，它仍然必須在查詢當下把相關資訊拼湊起來，再餵給模型做推理。**

表面上做法不太一樣：
- **粗 RAG：** 把所有東西做 embedding → 用距離搜尋 → 抓 top-K → 塞進 context。
- **精緻 RAG：** 加關鍵字、加分類器、做階層 chunk、做 re-ranking — 檢索變強，組裝邏輯沒變。
- **AI Wiki：** 預先生成有條理的 prose pages → AI 在查詢當下讀那些 pages。

這些都沒有改變核心結構：**儲存的單位是 input**，每次查詢時模型重新 synthesize。AI Wiki 只是變成更大、更整齊的一個 chunk，架構沒有換。
- 每次查詢都要付完整的 context 成本。
- 每次跑都會有 variance，因為 synthesis 是當下做的。
- 同一個問題答兩次，沒辦法重用前一次的工。

我研究使用者朋友的原話：

> 「他做的只是拉大查詢單位的資訊量以及加強檢索能力，就如同以往我們在做 RAG 一樣… 還是沒有解決『如果要讓 AI 理解我的資訊，仍然要先拼湊一堆相關資訊餵給模型』的問題，只是把拼湊的碎片給放大」

他完全說對了。我們需要不同維度的解法。

## 換一個維度：eager，不是 lazy

如果**儲存的單位變成「答案」，而不是「input」**呢？

具體來說：對任何一個研究 cluster，真正有用的問題其實不多。一個 PhD 學生在自己領域裡逛來逛去，大概只會問十種問題：

1. 這個領域在做什麼？
2. 為什麼現在很重要？
3. 有哪些主要的研究脈絡？
4. 專家在哪裡有不同意見？
5. 目前的 SOTA 是什麼？還有什麼沒解決？
6. 我剛入門，該先讀哪 5 篇？順序怎麼排？
7. 哪 10-20 個關鍵概念要先懂？
8. 這個領域怎麼評估自己的工作？
9. 新人最常踩什麼坑？
10. 有哪些相鄰領域要連接？

其他問題基本上都是這 10 個的延伸。而**這 10 個答案可以一次寫好、存成 markdown、之後直接讀回來。** 不用重讀 20 篇 abstract，不用 query-time fusion，**答案本身就是 artifact**。

我們把每一個答案叫做 **crystal**。每個 cluster 有最多 10 個 crystals，存在 `hub/<cluster>/crystals/<question-slug>.md`，三層詳細度：

- **TL;DR**（1 句話）
- **Gist**（約 100 字）
- **Full**（約 500-1000 字，內嵌 wiki-link 跟 evidence 表）

## 具體 before/after

**使用者問 Claude：「LLM 用在 software engineering 現在發展怎樣？」**

### v0.28 之前（lazy）

```
Claude → research-hub.get_topic_digest("llm-agents-software-engineering")
       ← 30 KB：20 篇論文的 abstract + frontmatter + overview，全部串在一起

Claude：[讀 30 KB，當下 synthesize 答案，回覆使用者]
```

每次有人問這個問題，Claude 都要重讀 30 KB、重新 synthesize。每次品質不太一樣。Token 成本隨 cluster 大小線性成長。

### v0.28 之後（eager）

```
Claude → research-hub.list_crystals("llm-agents-software-engineering")
       ← 1 KB：10 個 crystal (slug, question, tldr, confidence) tuples

Claude：[挑了 "what-is-this-field"]
Claude → research-hub.read_crystal(..., level="gist")
       ← 200 bytes：預先寫好的 100 字答案 + evidence

Claude：[直接回覆給使用者]
```

Claude 一共讀 1.2 KB。答案是一次寫好的，由同一等級的 model 寫的。Output deterministic。沒有 re-synthesis。

當 Claude 需要更詳細時：`level="full"` 回傳約 1000 字的答案，內嵌 wiki-links + evidence mapping。Claude 讀完後，可以選擇性地 drill 進特定論文。

## 這「不是」什麼

- **不是 embeddings。** research-hub 沒跑 sentence-transformers，沒維護 vector index。是呼叫端的 AI 用語意理解挑 crystal（它本來就是 LLM — 讀 10 個 TL;DR 挑一個對它來說是 trivial）。
- **不是 wiki。** Wiki 預先做的是「組織」。Crystals 預先做的是「答案」。Wiki page 還是要被讀 + synthesize 一次。Crystal answer 是直接 emit verbatim。
- **不是 essay / understanding.md。** 一個 cluster 寫一篇長文比 wiki 接近，但仍然是一個 chunk，呼叫端的 AI 還是要讀過 + 挑要的部分。Crystals 是有界、有槽位、有命名的 — 你知道裡面有什麼。
- **不是 auto-generated via API。** research-hub 自己從來不呼叫 LLM。Crystal 生成走 emit/apply pattern（跟 [autofill](../src/research_hub/autofill.py) 跟 [fit-check](../src/research_hub/fit_check.py) 一樣）：你拿到一個 prompt，餵給你選擇的任何 LLM，把回傳的 JSON 存起來，套用到磁碟上。完全 provider-agnostic。
- **不是論文 note 的取代品。** Crystals 處理 cluster 等級的常見問題。具體 drill-down（「SWE-agent 跟 OpenDevin 的差別在哪？」）還是 fall through 到直接讀論文。兩條路徑同時存在。

## 三個讓這套做法 work 的觀察

1. **Canonical questions 是 finite。** 觀察研究者問自己領域的問題很久，會驚訝其實 question SHAPE 沒幾種。約 10 個就涵蓋 90% 的查詢。所以「小且有界的 artifact 庫」就足以扛起大部分負載。

2. **呼叫端的 AI 自己會 routing。** LLM 完全有能力讀 10 個問題標題 + 一句 TL;DR，挑出最相關的。research-hub 不需要建 embedding layer 或 TF-IDF index。它只回傳 list；AI 自己挑。

3. **答案品質在生成時就決定了。** 用一個強的 LLM 把整個 cluster 讀過一次然後生成 crystal 時，那一刻就鎖定了那個品質。之後讀的時候每次都是同一段文字，沒有 variance，沒有「Claude 這次忘了 SOTA 是多少」這種事。

## Staleness（過期偵測）

Crystals 的 frontmatter 有 `based_on_papers: [...]` 欄位。當你新增 / 移除 cluster 裡的論文時，`research-hub crystal check --cluster X` 會算 delta ratio。如果 cluster 變動超過 10%，crystal 會被標記為 stale。Dashboard 會顯示 badge；drift detector 會發 alert。**你**自己決定什麼時候要重新生成（不會 auto-trigger，避免不必要的 LLM 花費）。

## Crystals 解決不了什麼

- **跨 cluster 的問題。** Crystals 是 per-cluster 的。「我整個 vault 對 agents 的累積知識是什麼？」跨多個 cluster — 這是 v0.29+ 才會處理。
- **意料外的 drill-down。** 如果使用者問的是 10 個 canonical slot 都涵蓋不到的具體問題，呼叫端的 AI 會 fall back 到直接讀論文。跟今天一樣。
- **使用者自訂的問題。** v0.28 把 10 個問題寫死。Custom questions 在 v0.29 才會有。
- **搜尋品質。** v0.26 留下的 5 個 xfail baseline（recall, rank stability, dedup merge, confidence calibration）跟這個是正交的問題。Crystals 降低 search 的呼叫頻率，但底層 ranker 沒被修。

## 生成流程

```
┌────────────────┐
│ 使用者：「幫    │
│ llm-agents     │
│ cluster        │
│ crystallize」  │
└────────┬───────┘
         │
         ▼
┌──────────────────┐      ┌────────────────────┐
│ Claude（或任何   │      │ research-hub       │
│ LLM）呼叫 MCP ───┼─────►│ emit_crystal_prompt│
│ emit_crystal_    │      │（讀 20 篇論文）    │
│ prompt()         │      └────────┬───────────┘
└──────────────────┘               │
                                   ▼
                          ┌────────────────────┐
                          │ 回傳 markdown      │
                          │ prompt（約 30 KB）：│
                          │ - cluster 定義     │
                          │ - 論文清單         │
                          │ - 10 個問題        │
                          │ - JSON schema      │
                          └────────┬───────────┘
                                   │
                     ┌─────────────┴─────────────┐
                     │ Claude 自己回答這個 prompt │
                     │（它就是 LLM）。產生 JSON   │
                     │ 包含 10 個 crystal 物件。  │
                     └─────────────┬─────────────┘
                                   │
                                   ▼
┌──────────────────┐      ┌────────────────────┐
│ Claude 呼叫 MCP  │      │ research-hub       │
│ apply_crystals() │─────►│ apply_crystals     │
│（帶上那個 JSON） │      │（寫 10 個 .md 到   │
└──────────────────┘      │  hub/...）         │
                          └─────────┬──────────┘
                                    │
                                    ▼
                          ┌─────────────────────┐
                          │ Crystals 已持久化   │
                          │ Dashboard 顯示      │
                          │ 10/10 crystals,     │
                          │ 0 stale             │
                          └─────────────────────┘
```

research-hub 內部零次 LLM API 呼叫。所有 synthesis 工作 Claude 做完；research-hub 只提供 prompt template + 把答案存起來。

## 查詢流程

```
┌───────────────────────┐
│ 使用者：「LLM-SE 的   │
│ SOTA 現在是什麼?」    │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐      ┌──────────────────┐
│ Claude                │      │ research-hub     │
│ list_clusters()       │─────►│ 回傳 5 個        │
│                       │◄─────│ clusters         │
└──────────┬────────────┘      └──────────────────┘
           │
           ▼
┌───────────────────────┐      ┌──────────────────┐
│ Claude 挑              │      │ research-hub     │
│ "llm-agents-software- │      │ 回傳 10 個       │
│  engineering"         │─────►│ crystal tuples   │
│ list_crystals(slug)   │◄─────│ (slug, q, tldr)  │
└──────────┬────────────┘      └──────────────────┘
           │
           ▼
┌───────────────────────┐      ┌──────────────────┐
│ Claude 挑             │      │ research-hub     │
│ "sota-and-open-       │      │ 回傳預先寫好的   │
│  problems"            │─────►│ ~100 字答案      │
│ read_crystal(...,     │◄─────│                  │
│  level="gist")        │      └──────────────────┘
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│ Claude 直接把那 100   │
│ 字答案回給使用者      │
│（可選擇加自己的       │
│  commentary）         │
└───────────────────────┘
```

**research-hub 每次查詢做的工：** 兩個小 function call，回傳約 1 KB 資料。沒有讀任何論文，沒有串接 abstract，沒有 re-synthesize。

## 誠實的限制

- **Crystal 品質取決於生成時用的 LLM。** 用弱 model 寫，crystal 就會很淺。用強 model 寫一次，之後每次查詢都受惠。
- **有些問題真的需要當下 synthesize。** 「SWE-agent 的 ACI 概念跟我剛加進來的那篇 Gemini 論文的 tool-use 模式有什麼關係？」— 這不是 canonical 問題，會 fall through 到直接讀論文。這沒問題。
- **Cluster 邊界很重要。** 如果你的「cluster」其實是三個不相關研究領域硬塞在一起，crystal 會生得很不連貫。先用 [`research-hub clusters analyze --split-suggestion`](../src/research_hub/analyze.py) 拆開。
- **沒有自動 refresh。** 在 20 篇論文的 cluster 加 1 篇，crystal 不會被標 stale。加 3 篇才會。你自己決定什麼時候 regenerate。

## 延伸閱讀

- [Karpathy 的 LLM Wiki post](https://karpathy.ai/)（我們在反對的那個）
- [Audit v0.28](audit_v0.28.md) — 對 llm-agents-software-engineering cluster 做 crystal live test 的 release 報告
- [`src/research_hub/crystal.py`](../src/research_hub/crystal.py) — 實作
- [`src/research_hub/autofill.py`](../src/research_hub/autofill.py) — 我們參考的 emit/apply pattern

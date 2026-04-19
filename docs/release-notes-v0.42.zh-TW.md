# research-hub v0.42.0 — NotebookLM 穩定性重寫 + ask 指令 + Obsidian callout 排版升級

**2026-04-19**

本次釋出直接回應真實使用者痛點：**「從 Obsidian 到 NotebookLM 總是很卡，很多次都沒有辦法把資料傳到 NotebookLM」**。v0.42 把 NLM 瀏覽器層整個換掉，並新增一個可以直接對著既有 notebook 提問的指令。

---

## 為什麼上傳常常失敗

我們做了一次完整的模組稽核，抓出 v0.41.x 在 `src/research_hub/notebooklm/` 下的七個具體失敗模式，依可能性排序：

1. **(致命) 缺少 anti-automation flag。** 舊版用 `--remote-debugging-port=9222` 啟動 Chrome，但沒有帶 `--disable-blink-features=AutomationControlled`。Google 的 NotebookLM 前端會偵測 `navigator.webdriver=true`，然後靜默拒絕上傳——這是最大元兇。
2. **(致命) 用 bundled Chromium，不是真的 Chrome。** 沒有設 `channel="chrome"`。NotebookLM（Gemini-backed 產品）對真 Chrome 的容忍度明顯高很多。
3. **(高) 用 standard playwright，不是 patchright。** patchright 是把 Playwright 的自動化指紋打掉的 fork，5.9k 星的 [PleasePrompto/notebooklm-skill](https://github.com/PleasePrompto/notebooklm-skill) 就是用它。
4. **(高) 沒有 retry logic。** 舊版 `upload.py` 抓到例外直接 `pass` 往下一篇——一次 transient 失敗 = 整篇論文丟掉。
5. **(中) 語系 fallback 只有 zh-TW/en/ja。** 帳號切到 zh-CN/ko/es/fr/de 時 aria-label 找不到，整批上傳失敗。
6. **(中) Dialog detach timeout 被吃掉。** 舊版 `client.py:256-260` 的 `try/except: pass` 讓下一次上傳對著殘留的對話框開跑。
7. **(低) 沒有 rate-limit 意識。** 每次上傳固定 sleep 2 秒，不管 HTTP 429 Retry-After。

---

## v0.42 做了什麼

### Track A — NotebookLM 瀏覽器層重寫

把整個 NLM 自動化層從 `playwright` + CDP-attach 換成 **patchright** + persistent Chrome context：

- **Anti-automation flag 補齊**：`--disable-blink-features=AutomationControlled` + `ignore_default_args=["--enable-automation"]`
- **改用真 Chrome**：`channel="chrome"`
- **Patchright stealth patches**：drop-in fork，import 路徑換掉就好
- **Cookie 注入 workaround**：Playwright bug #36139 的修補——cookies 寫到 `.research_hub/nlm_sessions/state.json`，每次啟動時 `add_cookies` 注入
- **Retry + 結構化 logging**：每篇論文最多重試三次，退避 1s → 3s → 9s；所有嘗試、失敗、重試都寫到 `.research_hub/nlm-debug-<UTC>.jsonl`
- **語系擴充**：加上 zh-CN、ko、es、fr、de 的 aria-label variants
- **Dialog close 硬化**：對話框沒關閉時丟 `NotebookLMError`，讓外層 retry 看得到、退避得動

瀏覽器打法的設計主要改編自 [PleasePrompto/notebooklm-skill](https://github.com/PleasePrompto/notebooklm-skill)（MIT）。我們沒有把他們的套件 vendor 進來，只是採用他們驗證過的 launch-args + auth-persistence + stable-polling 慣用法，並在原始碼、CHANGELOG、`docs/notebooklm.md` 標註出處。

相依性：`pip install research-hub-pipeline[playwright]` 現在裝 `patchright>=1.55`（原本是 `playwright>=1.40`）。使用者不用改安裝指令。

### Track B — 新指令 `research-hub notebooklm ask`

已經上傳好的 cluster，現在可以直接問問題：

```bash
research-hub notebooklm ask \
    --cluster llm-evaluation-harness \
    --question "Which paper proposes search over memory programs?"
```

- 從 `clusters.yaml` 讀 `notebooklm_notebook_url`
- 用 25–75ms/char 的 human-typing 節奏打字
- 答案用 3-read stability quorum 判斷「已完成」
- 偵測 `thinking-message` 期間自動暫停 polling
- 每題 120 秒 timeout
- 存到 `.research_hub/artifacts/<slug>/ask-<UTC>.md`（含問題標題 + latency）

MCP tool 叫 `ask_cluster_notebooklm(cluster, question)`，Claude Desktop 可以直接呼叫：

> 「Claude, 幫我問 llm-evaluation-harness 這個 notebook：『有沒有論文用 search-over-memory-programs 的方式？』」

### Track C — Obsidian callout + block ID 排版慣例

採用 [kepano/obsidian-skills/obsidian-markdown](https://github.com/kepano/obsidian-skills)（MIT，Obsidian CEO Steph Ango）的慣例：

- **論文筆記**：`## Summary` / `## Key Findings` / `## Methodology` / `## Relevance` 四個段落的內文會包成 `> [!abstract]` / `> [!success]` / `> [!info]` / `> [!note]` callout，並帶 `^summary` / `^findings` / `^methodology` / `^relevance` block ID。段落標題本身維持乾淨（沒有 inline block ID），所以所有舊有的 regex extractor 繼續正常運作。
- **Cluster overview 模板**：TL;DR → `> [!abstract]` (`^tldr`)；核心問題 → `> [!question]`；開放問題 → `> [!warning]`。
- **Crystal 模板**：TL;DR 包成 `> [!abstract]`，`from_markdown` 會 idempotently 解包。
- **新指令 `research-hub vault polish-markdown [--cluster X] [--apply]`**：掃描 vault 裡既有的論文筆記，把舊的純段落格式升級成 callout 格式。預設是 dry-run；跑第二次是 no-op（idempotent）。

### 什麼不在 v0.42

- **Obsidian Bases (`.base`) 自動產生**：價值很高但需要設計時間，v0.43 專門做一條。
- **JSON Canvas (`.canvas`) 引用圖匯出**：等 Bases 落地後。
- **`readability-lxml → defuddle` URL 萃取**：defuddle 是 NPM-only，不想為了這個加 Node 相依；v0.43 一併評估 trafilatura / newspaper3k。
- **`cli.py` / `mcp_server.py` 單檔拆分**：原本的 v0.42 候選，還沒有真實貢獻者撞牆，繼續延後。
- **NLM audio / mind-map / video 下載**：v0.43+。

---

## 驗收

```bash
# 把 CDP port 關掉，模擬使用者 Chrome 沒開 remote-debugging
research-hub notebooklm login
# 預期：看到真 Chrome 彈出，登入後自動關閉；state.json 寫入

research-hub notebooklm bundle --cluster v042-test
research-hub notebooklm upload --cluster v042-test
# 預期：所有論文都上傳，.research_hub/nlm-debug-*.jsonl 裡 retry_count=0
#       舊的「靜默跳過」模式不應該再出現

research-hub notebooklm ask --cluster v042-test \
    --question "What's the main claim of the most-cited paper?"
# 預期：約 60 秒內回答 2-3 句，存到 artifacts/

research-hub vault polish-markdown --cluster llm-evaluation-harness --dry-run
research-hub vault polish-markdown --cluster llm-evaluation-harness --apply
# 預期：dry-run 報告轉換清單，apply 實際寫入，第二次 apply 無變化
```

測試：`PYTHONPATH=src python -m pytest tests/test_v042_*.py -v` 期望 ~30 pass。全套 `PYTHONPATH=src python -m pytest -q -m "not slow"` 從 1423 提升到 ~1441。

CI 9 個多 OS job（Linux / macOS / Windows × Python 3.10/3.11/3.12）全綠。

---

## 碎念

v0.41.1 的 PEP 701 f-string 踩坑讓我們認真看待「Codex 用的是 3.12+ 語法預設」這件事，這次 brief 裡特別寫明「no PEP 701 f-strings」。

Gemini CLI 在 Windows 上的 AttachConsole / non-interactive shell 問題還沒解決——這次 zh-TW release notes 按照 `feedback_gemini_cli_invocation` 全域規則，Claude 直接寫。

下一輪 (v0.43) 主打 Obsidian Bases 自動產生 + JSON Canvas 匯出 + defuddle 替代品評估。持續的節奏：ship → use → fix what hurts。

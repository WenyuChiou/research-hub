# README verification and historical evidence

This page preserves the bounded rehearsal and installation context previously displayed on the README. It is evidence for the dated runs described below, not a statement that every current installation or scientific workflow has been accepted.

## Current source and environment notes (2026-10-28)

The README source commands identify `c1ab382e1bc4bfdb1d5df6a230d1ab4509a50d2a`. On Linux with Python 3.12.14, an initially clean isolated virtual environment completed `pip install -e .` after an interrupted installation was retried, passed `pip check`, and imported the module from a source tree matching that commit. CLI help ran, the demo created two teaching projects, and server and HTTP client subprocesses within one shell invocation returned HTTP 200 for `/app/`. This was not browser visual acceptance, Windows or macOS installation, or a provider/scientific workflow validation. An independent clean Linux Python 3.12.14 virtual environment installed the earlier `fe8a6b833febd5d6bb397f9924c2e379863bacee` source revision with `pip install -e .`, passed `pip check`, created the two demo projects, and returned HTTP 200 for `/app/`. This was not browser visual acceptance, a macOS or Windows installation, or a provider/scientific workflow validation. At the earlier source revision `14ddc07024f866a5a4f535f5e73185cc7ce69ea1`, a Linux Python 3.14 synthetic demo and same-process HTTP 200 were exercised with test guards and an older, unused NotebookLM dependency; this was not a clean installation or visual verification. At that same earlier revision, on one Windows Python 3.14 environment the source was fetched, CLI help and Chrome HTTPS worked, but demo creation encountered `os.link` / `WinError 5`. Its NTFS cause is unknown; this is not a claim that Windows is universally unsupported.

In a clean Linux Python 3.12 environment, the published PyPI 1.2.0 wheel installed and `pip check` passed, but `research-hub dashboard --sample` in a fresh HOME exited with `research-hub is not initialized`. Setting `RESEARCH_HUB_ROOT` to an existing directory under HOME allowed the sample to generate HTML; it did not open a browser without `--open`. The wheel did not expose the newer `project` command.

Workspace [PR #135](https://github.com/WenyuChiou/research-hub/pull/135) and writing adapter [PR #17](https://github.com/WenyuChiou/academic-writing-skills/pull/17) were merged. The original README also linked this [immutable capability-baseline version](https://github.com/WenyuChiou/research-hub/blob/c6ef19313ab69a85e041f4a86e4b9cb19229c138/docs/capability-baseline.md).

The last recorded NotebookLM authentication attempt failed and has not been reverified; see [troubleshooting](notebooklm-troubleshooting.md).

The older workspace preview pin `6381dfa7d474dd27cd4adb33f0f59ea8ec395150` is retained in the [historical capability baseline](capability-baseline.md) and [workspace guide](workspace-guide.md); its observations do not establish behavior of the newer source, and newer observations do not prove the older pin. The source version does not establish which features exist in a published wheel or in an AI host. See [workspace verification](workspace-verification.md) for earlier dated evidence.

## Native literature discovery rehearsal (English source)

### Stage 1

In a native AI agent that can read the research-hub skill and has public search/read tools, start with one request:

> Find literature on LLMs simulating human decisions.

The agent should choose a sensible initial scope, search/read available sources, and return a short list with original links, relevance, versions, and reading/access limits—not ask you to fill a research form or write JSON. Zotero, Obsidian, NotebookLM, and Hub storage are optional.

A real cloud-native rehearsal on 2026-10-26 returned three distinct starting points:
- [Aher et al. (2023)](https://proceedings.mlr.press/v202/aher23a.html): simulation of group behavior from existing experiments.
- [Park et al. (assessed 2024 preprint v1)](https://arxiv.org/abs/2411.10109v1): personalized agents grounded in human interviews; newer versions were not read in this rehearsal.
- [Gao et al. (2025)](https://doi.org/10.1073/pnas.2501660122): mismatched decision distributions as a validity check. The rehearsal read a DOI-matched public PDF mirror, not a successfully retrieved publisher PDF.

Then, if useful, say:

> Focus on economic decisions and compare the human baselines and evaluation methods.

Search snippets are not full-paper reading; human-like outputs are not evidence that human participants can be replaced. The agent retains unavailable sources and unresolved questions rather than inventing coverage.

**What was actually exercised:** one request → native search and original-text sections → a short, qualified result. This was a cloud-native run after directly reading the skill—not verification of Codex/Claude Code installation, automatic skill triggering, every host, Hub saving, or UI opening. No JSON, CLI, additional integration/provider account, or Stage 2 was required in that rehearsal.

For an optional visual handoff, the agent—not the researcher—can organize observations and use an already available, authorized Hub interface to save them. A confirmed save returns an exact saved-result link. The [saved-result contract](contracts/native-discovery-view.md) separates this path from native research: current secure file persistence/viewing is POSIX-only, Windows is not yet supported, and opening a result does not authenticate research or start provider writes.



## 原生文獻探索試跑（繁體中文原文）

### Stage 1

在能讀取 research-hub skill、且有公開搜尋／閱讀工具的原生 AI agent 中，可以先說一句：

> 幫我找 LLM 模擬人類決策的文獻。

Agent 應先採用合理範圍，搜尋與閱讀可取得來源，再回傳有原文連結、相關性、版本及閱讀／存取限制的短清單；不是要求你先填研究表單或寫 JSON。Zotero、Obsidian、NotebookLM 與 Hub 儲存都是選用。

2026-10-26 的真實雲端原生試跑得到三種不同起點：
- [Aher et al.（2023）](https://proceedings.mlr.press/v202/aher23a.html)：從既有實驗看群體行為模擬。
- [Park et al.（本輪核讀 2024 預印本 v1）](https://arxiv.org/abs/2411.10109v1)：從真人訪談看個人化代理；新版未在本輪閱讀。
- [Gao et al.（2025）](https://doi.org/10.1073/pnas.2501660122)：用不匹配的決策分布檢查模擬有效性。本輪讀取的是核對 DOI 的公開 PDF 鏡像，不是成功取得出版社 PDF。

需要續做時，再說：

> 聚焦經濟決策，幫我比較真人基準和評估方法。

搜尋摘要不等於全文閱讀，「像人」也不等於「可取代真人」。Agent 應保留取不到的來源與未決問題，不捏造覆蓋率。

**實際驗證範圍：**一句請求 → 原生搜尋與原文段落閱讀 → 有限制說明的短清單。這是直接讀取 skill 後的雲端原生實跑，不代表 Codex／Claude Code 安裝、技能自動觸發、所有宿主、Hub 儲存或 UI 開啟已驗收。本輪不需要 JSON、CLI、整合帳號或 Stage 2。

若另選視覺化交接，應由 agent 整理觀察、使用已可用且獲授權的 Hub 介面儲存，不讓研究者重複輸入。確認儲存後會回傳確切成果連結。[已儲存成果契約](contracts/native-discovery-view.md) 將此路徑與原生研究分開：目前安全檔案儲存／檢視僅支援 POSIX，Windows 尚未支援；開啟成果不驗證研究真實性，也不啟動外部服務寫入。

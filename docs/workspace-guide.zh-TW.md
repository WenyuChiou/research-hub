# 研究工作區指南

繁體中文 · [English](workspace-guide.md) · [README](../README.zh-TW.md) · [開發者架構](workspace-architecture.md)

工作區將研究問題連結至文獻、證據、檔案與稿件提案。你決定 AI 可以提出什麼建議，並在接受之前檢視結果。

## 預覽版狀態

本指南適用於**尚未發布的 `codex/researcher-workspace` 分支**。PyPI 上的 `1.2.0` 套件不含這些工作區指令。原始碼的版本文字無法單獨識別安裝狀態：既有安裝中繼資料仍可能顯示 `1.1.1`。請使用下方分支的可編輯安裝方式，並確認指令說明。

選用的寫作介接器也是預覽版：[academic-writing-skills PR #17](https://github.com/WenyuChiou/academic-writing-skills/pull/17)，commit `1b2ca75c0bd68d10a939edb4039525322fe2a837`，尚未合併或發布。它需要明確設定，不會成為 research-hub 的永久安裝相依項目。

## 先從免帳號示範開始

需要 Python 3.10+ 與 Git。請在預定放置程式碼的上層目錄執行：

```sh
git clone -b codex/researcher-workspace https://github.com/WenyuChiou/research-hub.git
cd research-hub
python -m pip install -e '.[mcp]'
research-hub project demo --help
research-hub project demo --root ./workspace-demo --json
research-hub serve --workspace --root ./workspace-demo
```

`workspace-demo` 必須是新建或空白目錄。示範會拒絕非空目錄；請另選位置，不要刪除自己的工作。開啟 [http://127.0.0.1:8765/app/](http://127.0.0.1:8765/app/)，結束後以 Ctrl+C 停止伺服器。

| 示範專案 | 檔案與用途 |
|---|---|
| `summation-demo` | `summation.py`、`analysis.json` 與 `manuscript.md`：可檢查輸入與結果的小型數值加總範例。 |
| `review-demo` | `references.json` 與 `manuscript.md`：包含篩選與證據紀錄的文獻回顧教學資料。 |

各專案檔案位於 `workspace-demo` 中同名的子目錄。測試資料標明為教學素材。建立示範不會執行 AI 模型、驗證科學發現、完成服務認證或接受稿件。

![使用本機示範紀錄的實際工作區介面。](images/workspace-ui.zh-TW.png)

## 六個頁面如何使用

| 頁面 | 從這裡開始 | 仍需由你負責 |
|---|---|---|
| 專案 | 設定目標，選擇 `empirical` 或 `review`。 | 決定研究問題與範圍。 |
| 文獻 | 搜尋 Crossref 中繼資料；記錄來源與篩選理由。 | 閱讀來源，確認身分與相關性。 |
| 證據 | 記錄主張，連結已登錄的來源。 | 確認每個來源是否支持該項具體主張。 |
| 設計與結果 | 記錄問題、方法、結果與限制；登錄分析檔。 | 在文字工作者之外，執行並驗證實際研究。 |
| 稿件 | 登錄檔案、綁定寫作狀態、準備提案並執行稽核。 | 處理科學問題並編輯原始文件。 |
| 審查與交付 | 檢視任務、決定是否接受提案，準備交付檔案。 | 針對確切版本作出接受與交付決定。 |

![研究生命週期概念圖，包含輸入變動後重新檢視的路徑。](images/workspace-lifecycle.zh-TW.png)

## 使用自己的專案

在 `research-hub` 程式碼目錄中，以 `./my-study` 作為工作區。該目錄可包含既有研究檔案。所有登錄檔案必須位於此根目錄內；符號連結與上層路徑跳脫會被拒絕。

```sh
research-hub project create study --root ./my-study --title "My study" --archetype empirical --goal "Assess the evidence for the research question" --json
research-hub project list --root ./my-study --json
```

文獻回顧請使用 `--archetype review`。專案 ID 使用小寫英文字母、數字與連字號。先在 `my-study` 中建立或放入自己的 `manuscript.md` 與 `analysis.csv`，再登錄：

```sh
research-hub project register --root ./my-study --project study --path manuscript.md --role main_manuscript --json
research-hub project register --root ./my-study --project study --path analysis.csv --role evidence --json
research-hub project record --root ./my-study --project study --kind question --data '{"text":"What does the analysis establish, and under which assumptions?"}' --json
research-hub project show --root ./my-study --project study --json
```

登錄使用 SHA256 雜湊值記錄檔案內容，不會搬移、改寫或在科學上驗證檔案。其他角色包括 `analysis`、`figure`、`table`、`supplement` 與 `reviewer_response`。稿件與審查回覆檔必須使用 `.docx`、`.tex` 或 `.md`。

紀錄類型包括 `question`、`source`、`claim`、`screening`、`analysis`、`outline` 與 `review`。來源紀錄需要 `title` 與 `locator`。新增主張連結或篩選決定時，請使用回傳的來源紀錄 ID。來源初始狀態為 `identity_status: unverified`；主張的支持程度未驗證，人工接受狀態待處理。新增紀錄不能自行宣告已驗證或已獲人工接受。明確建立的任務結果另有人工決定流程。

選用的即時中繼資料搜尋：

```sh
research-hub project search --root ./my-study --project study --query "research synthesis methods" --limit 3 --json
```

服務請求失敗時會回報功能降級。搜尋結果是文獻線索，不是主張正確的證據。既有 Zotero、Obsidian、NotebookLM 與檔案匯入設定，仍請參閱[安裝指南](setup.md)、[匯入指南](import-folder.zh-TW.md)及 [AI 主機指南](ai-host-support.md)。

<a id="writing-adapter-preview"></a>

## 驗證並連接公開寫作介接器

介接器提供既有公開的 `academic-writing-skills` 指令，以及僅供審查的 `paper-review` 指令，不含私人專案規則或預設科學領域。信任之前請先檢視原始碼：雜湊值證明套件完整性，不能證明發布者身分。

在 `research-hub` 程式碼目錄中，將固定版本的預覽版取得至新的同層目錄。停用 checkout 的換行轉換，才能保留清單涵蓋的原始位元組：

```sh
git clone -c core.autocrlf=false -b codex/writing-workspace-adapter https://github.com/WenyuChiou/academic-writing-skills.git ../academic-writing-adapter
git -C ../academic-writing-adapter checkout --detach 1b2ca75c0bd68d10a939edb4039525322fe2a837
python ../academic-writing-adapter/scripts/build_adapter_bundle.py --help
python ../academic-writing-adapter/scripts/build_adapter_bundle.py --root ../academic-writing-adapter --check
```

僅在結束碼為 `0` 且輸出 `"status": "PASS"` 後繼續。此指令檢查公開檔案集合、路徑、介面契約與雜湊值，不執行稽核程式。若需可攜式 ZIP，以 `--output ./academic-writing-adapter.zip` 取代 `--check`；目的檔案不得已存在。使用端應指向已檢查的目錄，或另行驗證過的解壓目錄，而不是 ZIP 檔。

在即將執行 research-hub 的終端設定目錄。PowerShell：

```powershell
$env:RESEARCH_HUB_WRITING_ADAPTER = (Resolve-Path ../academic-writing-adapter).Path
```

POSIX shell：

```sh
export RESEARCH_HUB_WRITING_ADAPTER="$(cd ../academic-writing-adapter && pwd)"
```

設定後請重新啟動已在執行的工作區伺服器，再綁定專案：

```sh
research-hub manuscript bind --root ./my-study --project study --json
research-hub manuscript state --root ./my-study --project study --json
research-hub manuscript audit --root ./my-study --project study --check state --json
```

綁定會使用已驗證的公開範本，初始化 `.research/projects/study/manuscript_state.json`，不代表接受稿件。尚未完成的專案可能合理地產生稽核問題。既有狀態會保留；問題或檔案變動時，綁定不會默默更新其權威資料。請在稿件狀態中明確處理回報的 `stale_alignment`，並登錄要使用的檔案版本，再建立下一項任務。

可用稽核包括 `state`、`consistency`、`prose`、`candidate`、`docx` 與 `regression`。`candidate` 須指定 `--candidate candidates/proposed-text.md`，使用工作區內含有確切候選文字的 UTF-8 檔案。`docx` 檢查已登錄 DOCX 的結構。稽核成功是機械檢查證據，不代表科學判斷通過或人工接受。

## 準備可攜式任務

![可攜式交接、連接文字工作者及明確人工審查的概念圖。](images/workspace-writing.zh-TW.png)

建立任務之前，先完成輸入登錄與狀態綁定。之後變更這些輸入，可能使任務失效。

```sh
research-hub task create --root ./my-study --project study --operation outline --mode handoff --instructions "Propose a section outline with evidence links and unresolved limitations." --json
research-hub task list --root ./my-study --project study --json
```

將回傳的任務 `id` 填入下方各處的 `TASK_ID`。支援操作為 `frame`、`outline`、`draft`、`review`、`revise`、`rebuttal`、`synthesize` 與 `audit`。

```sh
research-hub task handoff TASK_ID --root ./my-study --json
research-hub task show TASK_ID --root ./my-study --json
```

交接資料存於 `.research/tasks/TASK_ID/packet.json`。將資料包及你明確選定的來源交給 AI 主機。資料包含有路徑、雜湊值、紀錄與已設定的公開技能內容，不是檔案壓縮包。若未設定介接器，它會提醒接收者明確載入公開技能。匯出後狀態仍為 `awaiting_agent`，不會變成 `completed`。

要求對方提供文字、來源定位、未確定事項與修改建議。接收者必須保留來源檔案，也不能核准自己的輸出。後續可用獨立整理步驟將已蒐集證據結構化；JSON 格式本身不能證明證據品質。

### 匯入確切提案

在編輯器中建立以下格式的 `host-result.json`。將兩個雜湊值佔位文字換成實際的小寫 SHA256，並以主機回傳結果取代示例文字：

```json
{
  "input_hash": "COPY_INPUT_HASH_FROM_PACKET",
  "status": "completed",
  "prose": "The proposed outline and its evidence gaps go here.",
  "artifacts": [
    {"path": "candidates/draft-v2.docx", "sha256": "SHA256_OF_CANDIDATE_FILE"}
  ]
}
```

`input_hash` 必須符合資料包，不可自行詮釋後重算。純文字結果可用 `"artifacts": []`。若有 Word、LaTeX 或 Markdown 候選檔，請先用編輯器另存至 `my-study/candidates`，不得覆寫已登錄的輸入。雜湊值可這樣計算：

```sh
python -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('my-study/candidates/draft-v2.docx').read_bytes()).hexdigest())"
research-hub task import TASK_ID --root ./my-study --file ./host-result.json --json
```

`artifacts` 清單將確切候選檔登錄到結果中。不要事先把候選檔登錄為該任務的輸入。成功匯入後，任務進入 `awaiting_human`；結果中的 `completed` 是主機回報，不代表人工接受。輸入或候選檔雜湊不符時會被拒絕。

### 選用：連接 Codex 執行

先設定已驗證的介接器。PATH 中必須有相容且已登入的 Codex CLI。工作區會檢查必要的隔離旗標與停用功能；顯示可用不代表實際任務已成功。其本機狀態可能快取至伺服器重新啟動。

```sh
codex login status
research-hub task create --root ./my-study --project study --operation outline --mode connected --instructions "Propose an outline using only the supplied evidence." --json
research-hub task run TASK_ID --root ./my-study --json
```

將 `TASK_ID` 換成這項新任務的 ID。若尚未登入，請自行完成 `codex login` 並重新啟動伺服器。若 CLI 不相容，使用可攜式交接。連接執行會將選定文字傳送至 Codex，並可能消耗帳號的模型用量。

工作者不使用工具，只產生文字：不瀏覽網頁、不執行實驗，也不編輯來源文件。Word、PDF 與試算表等二進位檔案不會作為內容提供。如有需要，請在此工作者之外準備可檢查的文字摘錄。成功產生的文字另存為 Markdown 提案，等待人工審查。逾時、無效輸出、非預期工具活動與認證失敗，不算成功，也不會自動重試。

## 審查、接受與準備本機交付

檢視完整提案、引用來源、限制與確切候選檔後，由人工在互動終端執行：

```sh
research-hub task decide TASK_ID --root ./my-study --outcome accept --actor researcher --rationale "Reviewed the exact proposal, sources, and stated limitations" --json
```

CLI 會顯示候選內容完整的 `action_hash`，要求輸入該值以確認。標準輸入與錯誤輸出都必須連到終端。沒有 `--yes` 或代理核准憑證。`--actor` 記錄操作者自述姓名，不能驗證身分。其他決定為 `revise`、`decline` 與 `cancel`。要求修訂會將任務交回代理；由於輸入雜湊會變動，請重新匯出資料包。

接受只適用於這個提案版本。若要交付已接受任務的確切候選檔：

```sh
research-hub action prepare --root ./my-study --project study --task-ids TASK_ID --json
research-hub action show ACTION_ID --root ./my-study --json
research-hub action decide ACTION_ID --root ./my-study --outcome accept --actor researcher --rationale "Reviewed the selected files for local handoff" --json
research-hub action execute ACTION_ID --root ./my-study --json
```

將 `ACTION_ID` 換成準備好的動作 ID。交付核准同樣需要在互動終端輸入畫面顯示的確切雜湊。動作會在 `.research/deliveries/` 建立新的 ZIP，並記錄已驗證的收據。至少需要一個候選檔；只有文字的結果無法形成交付壓縮檔。這是**已接受提案的交接**，不等於稿件發布授權、期刊投稿或雲端上傳。

<a id="boundaries-and-recovery"></a>

## 邊界與復原

| 狀況 | 檢查與後續處理 |
|---|---|
| 已登錄檔案變動 | 執行 `manuscript impact`，登錄預定使用的版本，再建立新任務。舊接受紀錄不涵蓋新內容。 |
| 稿件權威資料變動 | 檢查稿件狀態與對齊警告，明確更新狀態；綁定會保留既有內容。 |
| 中斷任務仍顯示 `running` | 檢查保留輸出。僅在執行主機程序退出後使用 `task recover`；仍在執行的擁有者會阻止復原。 |
| 交付中斷 | 使用 `action reconcile` 驗證既有 ZIP。檔案缺失或變動時需要調查，不會盲目重做。 |
| NotebookLM 認證失敗 | 在新的可見登入與操作成功前，視為功能降級／未檢查。詳見 [NotebookLM 疑難排解](notebooklm-troubleshooting.md)。 |

```sh
research-hub manuscript impact --root ./my-study --project study --json
research-hub task recover TASK_ID --root ./my-study --json
research-hub action reconcile ACTION_ID --root ./my-study --json
```

僅執行符合已檢查狀態的指令。復原會將中斷任務移至 `blocked`，並標示結果未知；不會重新執行或接受保留文字。調查時請保留 `.research/tasks/TASK_ID/`。

SQLite 帳本參照既有工作流程 YAML 與公開稿件 JSON，不會自動推進工作流程的八個階段，也不會取代寫作技能的權威資料。影響報告以保守方式列出需要人工檢視的章節，不會理解並同步科學意義。

工作區核准涵蓋工作區提案任務與本機交付動作。既有 CLI、MCP、儀表板與雲端直接寫入工具，不會自動進入此核准流程。本機核准工作階段聲明操作者在場，不能確認共用電腦上的個人身分。確切邊界請參閱[開發者架構](workspace-architecture.md)。

<a id="verification"></a>

## 驗證與待完成檢查

**2026-09-08：預覽版證據；科學判斷驗收待完成。** 公開介接器 commit `1b2ca75c0bd68d10a939edb4039525322fe2a837` 的清單檢查通過。清單 SHA256 為 `9341d6a87a3f01a5f9d3c705e8f6f4bcd5fa88b4fa6d67ade70d81801b9726f6`。已執行離線契約、真實瀏覽器流程及兩項即時提案任務。[驗證報告](workspace-verification.md)分開列出通過、失敗、針對性修正與尚待確認的乾淨安裝。

兩項即時 Codex 任務已回傳待人工審閱的提案；這不表示完整科學工作流程或 NotebookLM 操作已成功。最近記錄的 NotebookLM 認證嘗試失敗，尚未重新驗證。示範資料與截圖僅呈現所展示的本機行為。

請在自己的安裝環境檢查 `research-hub project demo --help`，於空目錄執行示範，並以 `--check` 驗證選定介接器。連接任務前，先確認實際服務可用狀態。開發者應依[架構指南](workspace-architecture.md)及[實際操作檢查表](live-smoke.md)，記錄程式碼版本、確切指令、結果與剩餘限制。

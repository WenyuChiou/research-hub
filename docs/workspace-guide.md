# Research workspace guide

[繁體中文](workspace-guide.zh-TW.md) · [README](../README.md) · [Developer architecture](workspace-architecture.md)

The workspace connects a research question to literature, evidence, files, and manuscript proposals. You choose what an AI may propose and review the result before accepting it.

## Preview status

This guide describes the **unreleased `codex/researcher-workspace` branch**. The published PyPI `1.2.0` package does not contain these workspace commands. Source version text alone does not identify an installation: existing installed metadata may still report `1.1.1`. Use the editable branch checkout below and confirm its command help.

The optional writing adapter is also a preview: [academic-writing-skills PR #17](https://github.com/WenyuChiou/academic-writing-skills/pull/17), commit `1b2ca75c0bd68d10a939edb4039525322fe2a837`, is unmerged and unreleased. It is configured explicitly, not installed as a permanent research-hub dependency.

## Start with the account-free demo

Use Python 3.10+ and Git. Run these commands from the parent directory where you want the checkout:

```sh
git clone -b codex/researcher-workspace https://github.com/WenyuChiou/research-hub.git
cd research-hub
python -m pip install -e '.[mcp]'
research-hub project demo --help
research-hub project demo --root ./workspace-demo --json
research-hub serve --workspace --root ./workspace-demo
```

`workspace-demo` must be new or empty. The demo refuses an occupied directory; select another location instead of deleting your work. Open [http://127.0.0.1:8765/app/](http://127.0.0.1:8765/app/) and stop the server with Ctrl+C when finished.

| Demo project | Files and purpose |
|---|---|
| `summation-demo` | `summation.py`, `analysis.json`, and `manuscript.md`: a small numerical summation example with inspectable inputs and results. |
| `review-demo` | `references.json` and `manuscript.md`: a literature-review teaching fixture with screening and evidence records. |

Each project's files are under its matching directory inside `workspace-demo`. Fixtures are labeled teaching material. Creating them does not run an AI model, verify a scientific finding, authenticate a provider, or accept a manuscript.

![Actual workspace UI using local demonstration records.](images/workspace-ui.en.png)

## Navigate the six pages

| Page | Start here | What remains your responsibility |
|---|---|---|
| Project | Set a goal and choose `empirical` or `review`. | Decide the research question and scope. |
| Literature | Search Crossref metadata; record sources and screening reasons. | Read the source and verify its identity and relevance. |
| Evidence | Record claims and links to registered sources. | Check whether each source supports the exact claim. |
| Design & results | Record question, method, result, and limitation; register analysis files. | Execute and validate the actual research outside the prose worker. |
| Manuscript | Register files, bind writing state, prepare proposals, and run audits. | Resolve scientific issues and edit the original document. |
| Review & delivery | Inspect tasks, decide on proposals, and prepare accepted files for handoff. | Make acceptance and delivery decisions for the exact revision. |

![Concept diagram of the research lifecycle and return paths after changed inputs.](images/workspace-lifecycle.en.png)

## Bring your own project

From the `research-hub` checkout, choose `./my-study` as a workspace directory. It can contain existing research files. Every registered file must be inside that root; linked paths and parent traversal are rejected.

```sh
research-hub project create study --root ./my-study --title "My study" --archetype empirical --goal "Assess the evidence for the research question" --json
research-hub project list --root ./my-study --json
```

Use `--archetype review` for a literature review. Project IDs use lowercase letters, digits, and hyphens. Create or place your own `manuscript.md` and `analysis.csv` inside `my-study`, then register them:

```sh
research-hub project register --root ./my-study --project study --path manuscript.md --role main_manuscript --json
research-hub project register --root ./my-study --project study --path analysis.csv --role evidence --json
research-hub project record --root ./my-study --project study --kind question --data '{"text":"What does the analysis establish, and under which assumptions?"}' --json
research-hub project show --root ./my-study --project study --json
```

Registration records file bytes through a SHA256 hash. It does not relocate, rewrite, or scientifically validate the file. Other roles are `analysis`, `figure`, `table`, `supplement`, and `reviewer_response`. Manuscript and reviewer-response files must be `.docx`, `.tex`, or `.md`.

Record types include `question`, `source`, `claim`, `screening`, `analysis`, `outline`, and `review`. Source records require `title` and `locator`. Use the returned source record ID when adding claim links or screening decisions. Sources start with `identity_status: unverified`; claims start with unverified support and pending human acceptance. Adding a record cannot declare it verified or human-accepted. Explicit task results have a separate human decision path.

Optional live metadata search:

```sh
research-hub project search --root ./my-study --project study --query "research synthesis methods" --limit 3 --json
```

A failed provider request is reported as degraded. Search results are metadata leads, not evidence that a claim is correct. Existing Zotero, Obsidian, NotebookLM, and file-import setup remains in the [setup guide](setup.md), [import guide](import-folder.md), and [AI host guide](ai-host-support.md).

<a id="writing-adapter-preview"></a>

## Verify and connect the public writing adapter

The adapter supplies the existing public `academic-writing-skills` instructions and the review-only `paper-review` instructions. It includes no private project rules or scientific domain defaults. Review its source before trusting it: hashes establish bundle integrity, not publisher authenticity.

From the `research-hub` checkout, obtain the pinned preview in a new sibling directory. Disabling checkout line-ending conversion preserves the bytes covered by the manifest:

```sh
git clone -c core.autocrlf=false -b codex/writing-workspace-adapter https://github.com/WenyuChiou/academic-writing-skills.git ../academic-writing-adapter
git -C ../academic-writing-adapter checkout --detach 1b2ca75c0bd68d10a939edb4039525322fe2a837
python ../academic-writing-adapter/scripts/build_adapter_bundle.py --help
python ../academic-writing-adapter/scripts/build_adapter_bundle.py --root ../academic-writing-adapter --check
```

Continue only after exit code `0` and `"status": "PASS"`. The command verifies the public file closure, paths, contracts, and hashes without running audits. For an optional portable ZIP, use `--output ./academic-writing-adapter.zip` instead of `--check`; its destination must not already exist. Point the consumer at the checked directory or an independently verified extracted bundle, not a ZIP file.

Set the directory in the terminal that will run research-hub. In PowerShell:

```powershell
$env:RESEARCH_HUB_WRITING_ADAPTER = (Resolve-Path ../academic-writing-adapter).Path
```

In a POSIX shell:

```sh
export RESEARCH_HUB_WRITING_ADAPTER="$(cd ../academic-writing-adapter && pwd)"
```

Restart an already running workspace server after setting the variable. Then bind the project:

```sh
research-hub manuscript bind --root ./my-study --project study --json
research-hub manuscript state --root ./my-study --project study --json
research-hub manuscript audit --root ./my-study --project study --check state --json
```

Binding initializes `.research/projects/study/manuscript_state.json` from the verified public template. It does not accept the manuscript. An incomplete project can correctly produce audit findings. Existing state is preserved; binding does not silently refresh its authority when questions or files change. Resolve reported `stale_alignment` explicitly in the manuscript state and register intended file revisions before creating another task.

Available audit checks are `state`, `consistency`, `prose`, `candidate`, `docx`, and `regression`. For `candidate`, supply `--candidate candidates/proposed-text.md`, an exact UTF-8 text file inside the workspace. The `docx` check inspects registered DOCX structure. Audit success is mechanical evidence, not scientific or human acceptance.

## Prepare a portable task

![Concept diagram of portable handoff, connected prose execution, and explicit human review.](images/workspace-writing.en.png)

Finish recording inputs and binding state before creating a task. Later changes to these inputs can invalidate it.

```sh
research-hub task create --root ./my-study --project study --operation outline --mode handoff --instructions "Propose a section outline with evidence links and unresolved limitations." --json
research-hub task list --root ./my-study --project study --json
```

Copy the returned task `id` wherever `TASK_ID` appears below. Supported operations are `frame`, `outline`, `draft`, `review`, `revise`, `rebuttal`, `synthesize`, and `audit`.

```sh
research-hub task handoff TASK_ID --root ./my-study --json
research-hub task show TASK_ID --root ./my-study --json
```

The handoff is saved under `.research/tasks/TASK_ID/packet.json`. Give that packet and the deliberately selected source material to your AI host. The packet includes paths, hashes, records, and configured public skill material; it is not a file archive. Without an adapter it warns that the recipient must explicitly load the public skill. Export leaves status `awaiting_agent`, never `completed`.

Ask for prose, source locators, uncertainty, and proposed changes. The recipient must preserve source files and cannot approve its own output. A separate synthesis step may structure gathered evidence; JSON formatting alone does not establish evidence quality.

### Import the exact proposal

In your editor, create `host-result.json` with the following shape. Replace both hash placeholders with actual lowercase SHA256 values and replace the example prose with the host's result:

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

The `input_hash` must match the packet, not a manually recomputed interpretation. Use `"artifacts": []` for a prose-only result. For a Word, LaTeX, or Markdown candidate, first save the separate file inside `my-study/candidates` using your editor. Do not overwrite a registered input. Compute its hash, for example:

```sh
python -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('my-study/candidates/draft-v2.docx').read_bytes()).hexdigest())"
research-hub task import TASK_ID --root ./my-study --file ./host-result.json --json
```

The artifact list registers the exact candidate with the result. Do not pre-register that candidate as a task input. A successful result import moves the task to `awaiting_human`; the result's `completed` status is the host's report, not human acceptance. Mismatched input or candidate hashes are rejected.

### Optional connected Codex execution

Configure the verified adapter first. A compatible Codex CLI must be on PATH and authenticated. The workspace checks required isolation flags and disabled features; availability is not proof of a successful live task. Its local status may be cached until the server restarts.

```sh
codex login status
research-hub task create --root ./my-study --project study --operation outline --mode connected --instructions "Propose an outline using only the supplied evidence." --json
research-hub task run TASK_ID --root ./my-study --json
```

Replace `TASK_ID` with this new task's ID. If authentication is missing, complete `codex login` yourself and restart the server. If the CLI is incompatible, use portable handoff. Connected execution sends selected text to Codex and may consume your account's model usage.

The worker produces prose without tools: it does not browse, execute experiments, or edit source documents. Binary files such as Word, PDFs, and spreadsheets are not supplied as content. Prepare inspectable text excerpts outside this worker when needed. Successful prose is saved as a separate Markdown proposal and waits for human review. Timeouts, invalid output, unexpected tool activity, and authentication failures do not count as success or trigger automatic retries.

## Review, accept, and prepare a local delivery

Inspect the full proposal, cited sources, limitations, and exact candidate file. Then a human runs this in an interactive terminal:

```sh
research-hub task decide TASK_ID --root ./my-study --outcome accept --actor researcher --rationale "Reviewed the exact proposal, sources, and stated limitations" --json
```

The CLI displays the candidate's complete `action_hash` and requires typing it to confirm. Both input and error streams must be terminals. There is no `--yes` or agent approval proof. `--actor` records the operator's stated name; it does not authenticate identity. Other decisions are `revise`, `decline`, and `cancel`. Requesting revision returns the task to the agent; export a fresh packet because its input hash changes.

Acceptance applies to this proposal revision. To deliver exact candidate files from accepted tasks:

```sh
research-hub action prepare --root ./my-study --project study --task-ids TASK_ID --json
research-hub action show ACTION_ID --root ./my-study --json
research-hub action decide ACTION_ID --root ./my-study --outcome accept --actor researcher --rationale "Reviewed the selected files for local handoff" --json
research-hub action execute ACTION_ID --root ./my-study --json
```

Replace `ACTION_ID` with the prepared action's ID. Delivery approval also requires typing the exact displayed hash in an interactive terminal. The action creates a new ZIP under `.research/deliveries/` and records a verified receipt. At least one candidate file is required; prose-only results cannot form a delivery archive. This is an **accepted-proposal handoff**, not manuscript publication authorization, journal submission, or a cloud upload.

<a id="boundaries-and-recovery"></a>

## Boundaries and recovery

| Situation | Inspect and continue |
|---|---|
| Registered files changed | Run `manuscript impact`; register the intended revision and prepare a new task. Old acceptance does not cover new bytes. |
| Manuscript authority changed | Inspect manuscript state and alignment warnings. Update it explicitly; binding preserves existing state. |
| Interrupted task still says `running` | Inspect retained output. Use `task recover` only after the executor host exits; a live owner blocks recovery. |
| Delivery was interrupted | Use `action reconcile` to verify the existing ZIP. An absent or changed file requires investigation; no blind replay occurs. |
| NotebookLM authentication failed | Treat it as degraded/unchecked until a fresh visible login and operation succeeds. See [NotebookLM troubleshooting](notebooklm-troubleshooting.md). |

```sh
research-hub manuscript impact --root ./my-study --project study --json
research-hub task recover TASK_ID --root ./my-study --json
research-hub action reconcile ACTION_ID --root ./my-study --json
```

Run only the command matching the state you have inspected. Recovery moves an interrupted task to `blocked` with an unknown outcome; it does not rerun it or accept retained text. Preserve `.research/tasks/TASK_ID/` when investigating.

The SQLite ledger references the existing workflow YAML and public manuscript JSON. It does not automatically advance the workflow's eight stages or replace the writing skill's authority. Impact reporting conservatively lists sections that need human review; it does not understand and synchronize scientific meaning.

Workspace approval covers workspace proposal tasks and the local delivery action. Legacy direct-write CLI, MCP, dashboard, and cloud tools do not automatically enter that approval path. Local approval sessions assert operator presence; they do not establish user identity on a shared machine. See [developer architecture](workspace-architecture.md) for the precise boundaries.

<a id="verification"></a>

## Verification and remaining checks

**2026-09-08 — preview evidence; scientific acceptance pending.** The public adapter manifest check passed for commit `1b2ca75c0bd68d10a939edb4039525322fe2a837`. Its manifest SHA256 was `9341d6a87a3f01a5f9d3c705e8f6f4bcd5fa88b4fa6d67ade70d81801b9726f6`. Offline contracts, real browser flows and two live proposal tasks have been exercised. The [verification report](workspace-verification.md) separates passes, failures, targeted corrections and remaining clean-installation checks.

Two live Codex tasks returned proposals awaiting human review; this is not a claim that a complete scientific workflow or NotebookLM operation succeeded. The last recorded NotebookLM authentication attempt failed and was not reverified. Demo fixtures and screenshots establish only the illustrated local behavior.

For your installation, inspect `research-hub project demo --help`, run the demo in an empty directory, and verify the chosen adapter with `--check`. Inspect actual provider readiness before a connected task. Developers should record the checkout revision, exact commands, outcomes, and remaining limits using the [architecture guide](workspace-architecture.md) and [live smoke checklist](live-smoke.md).

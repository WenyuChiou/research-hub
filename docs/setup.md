# Setup Guide

Current setup path for research-hub v1.x. research-hub is not a
Claude-only skill: it is a Python CLI with MCP, REST, dashboard, and
portable `SKILL.md` instructions.

For a local workspace without accounts, start with the [capability baseline](capability-baseline.md).
A successful install or setup exit code does not certify every integration.

## 1. Install The CLI

```bash
pip install research-hub-pipeline
```

Choose extras only when you need them:

```bash
pip install "research-hub-pipeline[secrets]"
pip install "research-hub-pipeline[import,secrets]"
pip install "research-hub-pipeline[playwright,secrets]"
pip install "research-hub-pipeline[mcp]"
```

Use `[import]` for local PDF/DOCX/Markdown/TXT ingest, `[playwright]`
to install SDK Playwright plus EZProxy Patchright support, `[browser-auth]` for optional
browser-cookie import, `[secrets]` for encrypted local credentials, and `[mcp]`
for the FastMCP server. The base install does not declare FastMCP; install
`[mcp]` explicitly when using MCP. NotebookLM operations use the base
`notebooklm-py` dependency, not a supported consumer REST API. Browser binaries
and an authenticated session are separate prerequisites; installing an extra
does not prove login or connectivity. `login --auto-detect` delegates to the pinned SDK 0.8.5 Playwright flow
from the compatibility-named `[playwright]` extra. Install its Chromium browser
separately with `python -m playwright install chromium` before using that path.
See [NotebookLM architecture](notebooklm.md).

## 2. Pick A First Path

| You have | Recommended command |
|---|---|
| No accounts yet | `research-hub init --sample` or `research-hub dashboard --sample` |
| Zotero + Obsidian | `research-hub setup --skip-login` |
| Zotero + Obsidian + NotebookLM | `research-hub setup` |
| Local files, any persona | `research-hub init --persona researcher` (or `analyst`, `humanities`, `internal`); defer optional connections |
| Autonomous agent bootstrap | `python -m research_hub setup --autonomous --vault ./vault --persona agent` |

Then run:

```bash
research-hub doctor
```

`doctor` checks config, vault paths, Zotero credentials when required,
NotebookLM session state, and local workflow readiness. Read the individual
results: an existing session file is not proof of a working authenticated request,
and skipped, unknown, degraded, or failed checks are not ready. `setup` can
finish after partial installation/login failures; its exit status alone is not
a capability report. Do not run connector writes just to test setup.

Research Hub itself is optional; the research skills and source reading do
not require this pipeline. Zotero is an optional reference manager for saving
and organizing papers. Init can reuse saved settings or let you connect later.
Rerunning init reuses its saved vault and persona unless you explicitly override
them. If the existing configuration is unreadable or malformed, init stops
without overwriting it; check its permissions and JSON structure before retrying.
Init does not launch a browser to check readiness. Optional browser package
presence leaves browser launch and authentication unverified; login runs only
when explicitly selected, and `--no-browser` defers it.
To start with selected local Markdown/text files, without accounts:

```bash
research-hub import-folder ./papers --cluster my-reading --extensions md,txt
```

This writes local notes without Zotero; Obsidian is optional. PDF/DOCX extraction
needs `[import]` and `--extensions pdf,md,txt,docx`. URL imports can fetch remote
content. See [first-use paths](onboarding.md).

For a first Zotero-backed ingestion, configure its key and library ID and
inspect the vault and Zotero access results from `doctor` first. Then defer
NotebookLM with:

```bash
research-hub auto "agent-based modeling" --max-papers 3 --no-nlm
```

Then add NotebookLM only after the browser login succeeds:

```bash
research-hub notebooklm login --auto-detect
research-hub notebooklm bundle --cluster <slug>
research-hub notebooklm upload --cluster <slug>
research-hub notebooklm generate --cluster <slug> --type brief
research-hub notebooklm download --cluster <slug>
```

`setup` prints per-step outcomes and next actions. `passed` means only the
named command/probe reported success, not that every workflow is usable.
`failed`, `cancelled`, `skipped`, and `unknown` remain distinct. Interactive
init does not return its NotebookLM login result to setup, so that result is
reported as `unknown`, even if a skip flag was supplied to outer setup.
The existing ordinary setup exit code is preserved: zero can coexist with
install/login/sample failure. Read the outcomes, not just the exit code.
If init/install raises or is interrupted, setup attempts to print the stage
outcome and unrun steps, then re-raises the original exception (including
its exit code). A broken output stream cannot guarantee a visible summary.
A failed or unknown sample result does not open the dashboard; inspect any
partial writes before retrying. `--no-nlm` does not disable all network calls,
models, or writes. Dashboard command success is not browser/UI acceptance.

Autonomous JSON preserves all legacy fields and adds `ready_scope` and
`components` (`status`, `detail`, `next_step`). Legacy `ready` and its exit code
still check **required environment presence plus the Zotero read probe only**:
a missing/unwritable vault can coexist with `ready: true`. Inspect the vault
component separately. NLM state-file presence is not verified authentication;
CLI detection and installed skill paths are not successful invocation or host
discovery. These remain `unknown` for runtime usability. This report does not
provide a route-specific or whole-system readiness verdict.

### Optional saved observations in Workspace readiness

By default, autonomous setup only prints its report; it does not save a snapshot.
To opt in, choose an **existing local vault directory** that is also the root
selected by Workspace:

```bash
research-hub setup --autonomous --save-report --vault <workspace-root> --persona agent
```

This command can perform the existing Zotero read probe. It does not log in or
install tools. `--save-report` without `--autonomous` is rejected before setup.
It atomically replaces `.research_hub/setup-snapshot.json` under that root with
schema version 1, a UTC observation time, a source label, and six allowlisted
component statuses. It omits environment values, paths, raw errors and details.
No snapshot is copied from a different configured vault. Save failure is an
error, not success; the existing report/legacy readiness semantics still apply.

Workspace reads this small file without running setup or adding probes. Existing
Codex capability checks are separate and unchanged: the workspace endpoint
already calls `codex exec --help`, `codex features list`, and `codex login status`.
The new snapshot field adds no subprocess or network calls and does not alter
Codex/writing/approval behavior.

The UI labels the result **saved historical observations, not live verification**.
Current readiness remains unknown even for a recently saved pass. Its 24-hour
(86,400-second) age threshold is only a display policy to hide old observations,
not a credential/capability validity period; age is evaluated when the snapshot
is read. Missing, invalid, future-dated or older snapshots show unknown statuses.
Source/timestamp labels describe local file contents, not authenticated provenance.

Linked/reparse paths, escaped roots, nonregular or hardlinked input files, and
files above 8 KiB are rejected. This uses existing local workspace path checks
and atomic replacement; it does not claim race-proof confinement against another
process concurrently replacing ancestor directories. There is no automatic
refresh probe, retry, login button, new permission or route-readiness guarantee.

## 3. Connect An AI Host

### MCP / REST hosts

Claude Desktop, Claude Code, Cursor, Continue.dev, Cline, Roo Code,
VS Code Copilot, OpenClaw, and other MCP-capable hosts can attach the
same server:

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

Restart the host after editing its MCP config.

For browser-only or HTTP-capable assistants, start the local HTTP
surface:

```bash
research-hub serve --dashboard
```

Then call endpoints under `http://127.0.0.1:8765/api/v1/`.

### Installed skill files

The built-in installer currently targets hosts with known default skill
directories:

```bash
research-hub install --platform claude-code
research-hub install --platform codex
research-hub install --platform cursor
research-hub install --platform gemini
research-hub install --list
```

Hermes, OpenClaw, and other agents can still use the project through
MCP/REST. If the host supports `SKILL.md` or rules directories, copy
the relevant directories from `skills/` manually or inline the relevant
`SKILL.md` into that host's instructions. They are not release-verified
`research-hub install --platform` targets yet.

## 4. Required Credentials

Zotero-backed workflows need:

```bash
ZOTERO_API_KEY=...
ZOTERO_LIBRARY_ID=...
```

Optional search keys:

```bash
SEMANTIC_SCHOLAR_API_KEY=...
# Optional: only set this if your S2 key has a different quota.
SEMANTIC_SCHOLAR_RPS=1
TAVILY_API_KEY=...
BRAVE_API_KEY=...
```

research-hub paces Semantic Scholar calls by default: anonymous traffic
uses a slower delay, while API-key traffic defaults to about one request
per second and retries HTTP 429 with `Retry-After` / exponential
backoff. Keep `SEMANTIC_SCHOLAR_RPS` unset unless Semantic Scholar has
granted your key a quota other than the default.

NotebookLM upload requires a one-time browser login. The lowest-friction
path is:

```bash
research-hub notebooklm login --auto-detect
```

Google's auth flow is intentionally human-driven; headless agents can
prepare bundles and read downloaded briefs, but they cannot complete
the first NotebookLM login by themselves.

## 5. Smoke Tests

No-account preview:

```bash
research-hub dashboard --sample
research-hub init --sample
```

Machine-readable capability manifest:

```bash
research-hub describe --json
research-hub describe --filter skills --pretty
```

MCP server smoke:

```bash
research-hub serve
```

Dashboard/API smoke:

```bash
research-hub serve --dashboard
```

In another terminal:

```bash
curl http://127.0.0.1:8765/api/v1/health
```

## 6. Common Fixes

| Symptom | Fix |
|---|---|
| `research-hub` command not found | Reinstall with `pip install research-hub-pipeline` and check your PATH |
| AI host cannot see tools | Restart the host after adding MCP config |
| `research-hub install --platform openclaw` fails | Use MCP/REST or manual `SKILL.md` loading; OpenClaw is not a built-in installer target |
| `auto` stops before search | Install a supported LLM CLI or pass `--no-fit-check` |
| NotebookLM upload prompts for login | Run `research-hub notebooklm login --auto-detect` once in a browser-capable session |

## 7. Next Docs

- [First 10 minutes](first-10-minutes.md)
- [AI integrations](ai-integrations.md)
- [AI host support matrix](ai-host-support.md)
- [Live smoke checklist](live-smoke.md)
- [MCP tools](mcp-tools.md)
- [CLI reference](cli-reference.md)
- [NotebookLM](notebooklm.md)

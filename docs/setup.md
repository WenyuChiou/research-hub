# Setup Guide

Current setup path for research-hub v1.x. research-hub is not a
Claude-only skill: it is a Python CLI with MCP, REST, dashboard, and
portable `SKILL.md` instructions.

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
for NotebookLM browser automation, `[secrets]` for encrypted local
credentials, and `[mcp]` when your environment does not already include
FastMCP.

## 2. Pick A First Path

| You have | Recommended command |
|---|---|
| No accounts yet | `research-hub init --sample` or `research-hub dashboard --sample` |
| Zotero + Obsidian | `research-hub setup --skip-login` |
| Zotero + Obsidian + NotebookLM | `research-hub setup` |
| Local PDFs/reports only | `research-hub setup --persona analyst` |
| Autonomous agent bootstrap | `python -m research_hub setup --autonomous --vault ./vault --persona agent` |

Then run:

```bash
research-hub doctor
```

`doctor` checks config, vault paths, Zotero credentials when required,
NotebookLM session state, and local workflow readiness.

For a first real ingestion, keep the browser out of the path until the
local pieces are healthy:

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

`setup` prints the same next-step checklist after it finishes.

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

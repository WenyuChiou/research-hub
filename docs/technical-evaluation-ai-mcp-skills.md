# Technical Evaluation: AI, MCP, Skills, and Promotion Readiness

Date: 2026-04-25

Scope: evaluate research-hub as a public project that users can adopt with any two of Zotero, Obsidian, and NotebookLM, or all three. Focus areas: AI host integration, MCP tools, bundled skills, REST API, dashboard actions, security posture, testing, and promotion readiness.

## Executive Verdict

**Verdict: Promote as public beta, not as fully stable infrastructure.**

research-hub has enough real functionality to promote: 83 MCP tools, CLI parity tests, REST wrappers, dashboard actions, NotebookLM automation, persona-aware onboarding, packaged AI skills, and a local-first vault model. The strongest product message is now correct: users do not need all three tools; any two-tool combination can produce value.

The project still needs hardening before it should be marketed as "production-grade" or "turnkey for everyone." The main remaining risks are tool discoverability, inconsistent MCP response schemas, browser automation fragility, lack of end-to-end MCP client tests, and large monolithic modules that make future changes risky.

## Current Strengths

### 1. AI Host Coverage Is Broad

research-hub exposes three AI-operable surfaces:

- CLI: usable by Codex CLI, Gemini CLI, Claude Code, shell agents, and automation scripts.
- MCP: usable by Claude Desktop, Claude Code, Cursor, Continue.dev, Cline, Roo Code, OpenClaw, and other MCP hosts.
- REST: usable by browser-only or HTTP-capable assistants through `/api/v1/*`.

This is a strong distribution strategy because it avoids coupling the project to one model vendor.

### 2. MCP Tool Coverage Is Deep

The MCP server currently registers **83 tools**. They cover:

- discovery: `search_papers`, `web_search`, `discover_new`, `discover_continue`
- planning: `plan_research_workflow`
- ingest: `auto_research_topic`, `collect_to_cluster`, `add_paper`, `import_folder_tool`
- organization: clusters, labels, subtopics, rebind, fit-check, autofill
- knowledge artifacts: crystals, memory, topic notes, quotes, drafts
- NotebookLM: bundle, upload, generate, download, ask, brief
- maintenance: doctor, tidy, cleanup, dashboard, bases

This is materially useful for agents. It gives agents workflow-level tools, not only low-level CRUD.

### 3. Safety Is Better Than Average For A Local Tool

The codebase has explicit tests for:

- path traversal rejection
- slug validation
- identifier validation
- CSRF protection on dashboard action endpoints
- origin checking for dashboard actions
- process timeout killing for dashboard executor
- REST bearer-token enforcement when configured

This matters because the project invites AI agents to operate user-owned local files.

### 4. Tests Cover The Critical AI Surfaces

Targeted tests passed during this review:

```text
python -m pytest tests\test_skill_installer.py -q
9 passed

python -m pytest tests\test_consistency.py tests\test_mcp_server_comprehensive.py tests\test_v047_mcp_lazy.py tests\test_v050_planner.py tests\test_v052_rest_api.py -q
50 passed

python -m pytest tests\test_v030_security.py tests\test_onboarding_ux.py -q
52 passed, 2 skipped

python -m pytest tests\test_v052_rest_api.py -q
14 passed
```

Total targeted review coverage: **125 passed, 2 skipped**.

## Issues Found And Fixed In This Review

### Fixed: Packaged Skills Were Stale

Problem:

`research-hub install --platform ...` uses `src/research_hub/skills_data/*/SKILL.md` first. The public root skill files had been updated, but the packaged install sources still had old positioning and mojibake. Users installing skills would receive stale instructions.

Fix:

- Updated `src/research_hub/skills_data/knowledge-base/SKILL.md`.
- Updated `src/research_hub/skills_data/research-hub-multi-ai/SKILL.md`.
- Added regression coverage in `tests/test_skill_installer.py`.

Why it matters:

This directly affects Claude/Codex/Cursor/Gemini usage after installation.

### Fixed: Skill And Docs Used A Wrong NotebookLM Flag

Problem:

Several AI-facing docs used:

```bash
research-hub notebooklm generate --cluster my-topic --preset briefing
```

But the CLI uses:

```bash
research-hub notebooklm generate --cluster my-topic --type brief
```

Fix:

- Updated bundled skills and AI integration docs.
- Added regression coverage so `--preset` does not reappear in AI-facing installation docs.

Why it matters:

AI agents tend to execute skill commands literally. A wrong flag causes a failed workflow at the exact moment a new user is trying the project.

### Fixed: Version Drift Across Package And REST API

Problem:

- `pyproject.toml`: `0.64.2`
- `research_hub.__version__`: `0.60.0`
- REST `/api/v1/health`: `0.52.0`

Fix:

- Updated `research_hub.__version__` to `0.64.2`.
- Made REST `API_VERSION` derive from `research_hub.__version__`.
- Updated REST test expectation.

Why it matters:

Version mismatch makes bug reports and AI-agent diagnostics unreliable.

## Remaining Technical Risks

### P1: MCP Response Schemas Are Inconsistent

Severity: high for agent reliability.

Current tools return mixed shapes:

- `{"ok": false, "error": "..."}`
- `{"status": "error", "error": "..."}`
- `{"error": "..."}`
- successful lists directly, not wrapped
- strings for citation exports

This works for humans and some wrappers, but it is harder for LLM agents to reason about consistently. REST has adapter logic to normalize some cases, but MCP clients see the raw inconsistency.

Recommendation:

Introduce a common MCP envelope for new workflow tools:

```json
{
  "ok": true,
  "data": {},
  "warnings": [],
  "next_steps": []
}
```

For errors:

```json
{
  "ok": false,
  "error": {
    "code": "cluster_not_found",
    "message": "Cluster not found: x",
    "hint": "Run: research-hub clusters list"
  }
}
```

Do not break existing tools immediately. Add normalized v2 wrappers for the most common agent paths first: `plan`, `auto`, `ask`, `collect`, `brief`, `sync`, `tidy`.

### P1: MCP Tool Discoverability Is Overloaded

Severity: high for first-time AI users.

83 tools is powerful, but many host UIs and models struggle when tool lists are large. Some tools are low-level, some are workflow-level, and some duplicate CLI concepts.

Recommendation:

Add a small set of "front door" tools and bias skills/docs toward them:

- `plan_research_workflow`
- `auto_research_topic`
- `collect_to_cluster`
- `ask_cluster`
- `brief_cluster`
- `sync_cluster`
- `tidy_vault`
- `get_config_info`

Then mark low-level tools in docs as advanced/composable. If the MCP framework supports annotations or tags, group by `read`, `write`, `destructive`, `notebooklm`, `maintenance`.

### P1: No True MCP Client End-To-End Test

Severity: medium-high for public adoption.

Current tests call registered tool functions directly through helper wrappers. That is valuable, but it does not prove a real MCP stdio client can initialize the server, list tools, call a tool, and parse the response.

Recommendation:

Add one subprocess-based MCP smoke test that:

1. Starts `python -m research_hub.mcp_server`.
2. Performs MCP initialize.
3. Lists tools.
4. Calls a harmless read-only tool such as `plan_research_workflow` or `get_config_info`.
5. Shuts down cleanly.

This catches packaging, FastMCP transport, import-time warnings, and stdio protocol regressions that direct unit tests cannot catch.

### P2: Browser Automation Is A Fragile Dependency

Severity: medium.

NotebookLM upload/generate/download is useful, but it depends on Chrome, Google auth state, and NotebookLM UI stability. The code has graceful error handling and tests around wrappers, but public users will still hit environment-specific failures.

Recommendation:

Position NotebookLM automation as "optional browser automation" in all marketing. Keep `--no-nlm` and `dashboard --sample` as the first-run path. Add a specific `research-hub notebooklm doctor` command or `doctor` sub-section that reports:

- Chrome found/not found
- patchright installed/not installed
- session state exists/missing
- last NotebookLM operation timestamp
- likely next command

### P2: Large Monolithic MCP Server Raises Maintenance Cost

Severity: medium.

`src/research_hub/mcp_server.py` holds many unrelated tool implementations and registrations. This is easy to ship but hard to review. It increases the chance of accidental coupling and inconsistent error handling.

Recommendation:

Refactor gradually into modules:

- `mcp/search_tools.py`
- `mcp/cluster_tools.py`
- `mcp/notebooklm_tools.py`
- `mcp/crystal_tools.py`
- `mcp/maintenance_tools.py`
- `mcp/workflow_tools.py`

Keep one `mcp_server.py` registration entrypoint for compatibility.

### P2: REST API Versioning Is Now Fixed But Needs A Policy

Severity: medium.

REST `/api/v1/health` now reports package version. That fixes drift, but there is still no clear distinction between package version and API contract version.

Recommendation:

Return both:

```json
{
  "ok": true,
  "package_version": "0.64.2",
  "api_version": "v1"
}
```

This avoids implying that every package patch changes the REST contract.

### P2: Skill Quality Needs Real Evals, Not Only Static Tests

Severity: medium.

The skills are now clean and installable. However, no test validates whether an actual model uses them correctly. Static tests catch drift and bad commands, but not trigger quality or workflow quality.

Recommendation:

Create 6 skill eval prompts:

- "I use Zotero and Obsidian but not NotebookLM; find papers and make notes."
- "I only have PDFs and Obsidian; build a cluster and dashboard."
- "Use Gemini for Chinese summaries but keep citations in English."
- "I want to ask an existing cluster a question; avoid re-reading every paper."
- "Set up research-hub in Cursor."
- "Clean up my vault but do not delete anything yet."

Expected behavior should assert:

- starts with `plan` or `doctor` when appropriate
- uses `--no-nlm` for smoke tests
- does not assume all three tools are configured
- does not fabricate citations
- does not call destructive cleanup with `--apply` unless user asked

## Promotion Readiness Assessment

| Area | Rating | Rationale |
|---|---:|---|
| Product positioning | 8/10 | New README and GitHub About correctly communicate "any two, or all three." |
| CLI capability | 8/10 | Broad commands and tests; still complex for new users. |
| MCP capability | 7/10 | Deep coverage and strong workflow tools; too many tools and inconsistent schemas. |
| Skills | 7.5/10 | Fixed stale packaged skills and wrong commands; still needs model-run evals. |
| REST API | 7/10 | Useful for browser AIs, token auth tested; CORS and versioning policy need refinement. |
| Dashboard | 7.5/10 | Strong demo surface; action execution security has tests. |
| NotebookLM | 6.5/10 | Valuable differentiator but inherently fragile due to browser UI automation. |
| Security posture | 7.5/10 | Good local safety tests; needs continued review around external bind and REST exposure. |
| Maintainability | 6.5/10 | Large monolithic MCP/CLI files should be modularized over time. |
| Public beta readiness | 8/10 | Good enough to promote carefully, with clear beta/optional-automation framing. |

## Recommended Roadmap

### Immediate

- Add real MCP stdio smoke test.
- Add normalized response envelope for top workflow tools.
- Add skill eval prompts and static assertions.
- Keep `dashboard --sample` as the first public onboarding path.
- Document NotebookLM as optional, not required.

### Near Term

- Split MCP server by domain while preserving the same tool names.
- Add a `notebooklm doctor` diagnostic.
- Add docs page: "Which two-tool setup should I choose?"
- Add screenshots/gifs for the three two-tool paths.
- Add GitHub issue templates for bug report, integration request, and paper-source backend request.

### Later

- Add MCP tool annotations/tags if supported by the active FastMCP version.
- Add remote-safe mode for REST/dashboard with stricter CORS and token defaults.
- Add OpenTelemetry or structured logs for long-running `auto` jobs.
- Add a public demo vault repository or downloadable sample package.

## Claude Code Review Checklist

Ask Claude Code to verify:

- `research-hub install --platform <target>` copies `src/research_hub/skills_data/*`, not stale root-only files.
- `notebooklm generate` examples use `--type brief`, not `--preset briefing`.
- `research_hub.__version__`, `pyproject.toml`, and REST health are consistent.
- MCP tool count remains expected and all tools have typed params/docstrings.
- Direct MCP tests are not mistaken for real stdio integration tests.
- No destructive tool defaults to apply/delete without explicit user intent.
- README does not imply users need all three tools.
- NotebookLM automation is described as optional browser automation.

# AI Host Support Matrix

research-hub is host-agnostic at the workflow layer, but different AI
surfaces integrate through different mechanisms. Use this matrix to keep
README claims, installer targets, and release testing aligned.

## Support Levels

| Level | Meaning |
|---|---|
| Verified | Covered by automated tests and/or live smoke for this release. |
| Supported path | Expected to work through a stable public interface such as CLI, MCP, REST, or manual `SKILL.md` loading. |
| Manual | Requires copying `SKILL.md` or configuring host-specific rules by hand. |
| Not a target | Do not advertise as installed or verified. |

## Native research and ingest handoff

Codex and other capable hosts can use their own search, browsing, and
citation tools for multi-round discovery, source checking, and evidence
reasoning, then hand bibliographic records to `research-hub` as a JSON
`papers` payload. This does not require a second research agent or a
dedicated deep-search API. The CLI remains the deterministic ingest and
storage layer; scholarly search adapters are optional. A
`ResearchEvidencePacket` is a separate contract and is not a papers input.

Before a real `ingest` or `run` handoff, inspect the configured vault and
Zotero destination/collection, and proceed only when the user authorized
those writes. Host-native research does not itself authorize publication
or library writes. See [papers input schema](papers_input_schema.md) for
the explicit `--input PATH` handoff and preview behavior.

## Matrix

Connection columns describe available host paths; **Current position**
records research-hub integration validation. Host transport support alone
does not establish an end-to-end research-hub smoke.

| Host / surface | CLI | MCP | REST | `SKILL.md` installer | Manual `SKILL.md` | Current position |
|---|---:|---:|---:|---:|---:|---|
| Claude Code | Yes | Yes | Yes | Yes: `claude-code` | Yes | Verified core target. |
| Codex CLI | Yes | Yes (STDIO / Streamable HTTP) | Yes | Yes: `codex` | Yes | Verified CLI + skill target; MCP integration not release-verified. |
| Cursor | Partial | Yes | Yes | Yes: `cursor` | Yes | Installer writes skill files; MCP is the stronger tool path. |
| Gemini CLI | Yes | No | Yes | Yes: `gemini` | Yes | Verified CLI + skill target. |
| Claude Desktop | No | Yes | Yes | No | Manual via Claude ecosystem paths | Use MCP. Do not list as `install --platform`. |
| Continue.dev | No | Yes | Yes | No | Manual rules if available | Use MCP. |
| Cline | No | Yes | Yes | No | Manual rules if available | Use MCP. |
| Roo Code | No | Yes | Yes | No | Manual rules if available | Use MCP. |
| OpenClaw | Depends on host shell | Yes, if MCP is enabled | Yes | No | Yes, if it supports skills/rules directories | Structurally compatible through MCP/manual instructions; not release-verified as installer target. |
| Hermes | Depends on host shell | Unknown/host-dependent | Yes | No | Yes | Manual `SKILL.md` path only until a stable installer directory and live smoke exist. |
| Generic API client | No | No | Yes | No | Inline prompt only | Use REST endpoints. |
| R / RStudio | Shell-adjacent | No | Yes | No | Project instructions only | R is a research project context, not an AI host. |

### Codex MCP capability and validation

[OpenAI's MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
confirms that Codex CLI supports STDIO and Streamable HTTP servers.
research-hub's MCP entry point (`research-hub serve` or `research-hub-mcp`)
uses STDIO; Codex's HTTP capability does not imply that research-hub
provides an HTTP MCP endpoint.

CLI + skill remains the release-verified Codex route. Configure the server
in Codex using the linked OpenAI instructions, then follow the verification
steps in the [MCP host smoke checklist](live-smoke.md#4-mcp-host-smoke).
The checklist's JSON configuration example is for Claude-style hosts, not
Codex. Record the Codex host version and results before marking its
research-hub MCP integration verified.

## Built-In Skill Installer Targets

`research-hub install --platform` intentionally supports only hosts with
known default skill directories:

```bash
research-hub install --platform claude-code
research-hub install --platform codex
research-hub install --platform cursor
research-hub install --platform gemini
```

Do not add a new installer target until all of the following are true:

1. The host has a documented, stable skill/rules directory.
2. The directory works on Windows, macOS, and Linux or the platform
   limitation is documented.
3. A live smoke proves the host loads at least the core
   `research-hub/SKILL.md`.
4. `research-hub install --list` can reliably detect a complete install.
5. README, `docs/setup.md`, and this matrix are updated together.

## Runtime LLM CLI Adapters

The LLM CLI adapter registry is separate from the skill installer.
Runtime workflows can call:

- `claude`
- `codex`
- `gemini`
- `opencode`
- `aichat`
- `cursor`
- user-configured custom adapters

This affects fit-check, summaries, crystals, and autonomous bootstrap
readiness. It does not imply that every CLI has a `research-hub
install --platform` target.

## OpenClaw And Hermes Decision

OpenClaw and Hermes should remain outside built-in installer targets for
now. The supported story is:

- connect through MCP or REST when tool calls are needed;
- manually load `SKILL.md` when the host has a skill/rules mechanism;
- verify with `docs/live-smoke.md` before promoting either host to a
  release-verified installer target.

This is conservative but avoids overclaiming a host-specific install
path that has not been tested end to end.

## R Workflow Decision

R support should be framed as research-workspace support:

- `.R`, `.Rmd`, `.qmd`, `renv.lock`, data dictionaries, and experiment
  matrices can be captured in `.research/` manifests;
- AI hosts can reason over those files through CLI/MCP/REST workflows;
- research-hub is not currently an R package, RStudio add-in, or
  replacement for `renv`, `targets`, or Quarto.

Future R-specific work should be tracked separately from AI host support,
for example:

- `research-hub context audit` checks for `renv.lock`, `DESCRIPTION`,
  `_targets.R`, and Quarto project files;
- an R research skill that explains reproducibility and data-path
  conventions;
- optional examples for R/Quarto literature-review projects.

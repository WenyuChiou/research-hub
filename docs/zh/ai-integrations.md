<!-- ZH translation pending. English content below kept as a translation reference. -->

# AI Integrations

`research-hub` exposes an MCP server and several AI-facing workflows for searching literature, generating prompts, reading cluster state, and exporting research context.

## Install

```bash
pip install research-hub-pipeline[mcp]
```

## Start The MCP Server

```bash
research-hub serve
```

## Available Workflow Areas

- Search papers across multiple academic backends
- Run doctor checks and inspect local configuration
- Read cluster state and topic notes
- Use discover and fit-check prompts
- Browse bundled example clusters

## Recommended Pattern

1. Create or copy a cluster
2. Run `discover new`
3. Score the fit-check prompt with your preferred AI
4. Apply the scores with `discover continue`
5. Ingest accepted papers and build notes

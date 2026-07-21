# Repository wiki brief — research-hub

<!-- User-authored brief. OpenWiki reads this file for scope and priorities;
     it is not generated documentation and must never be rewritten by wiki
     init/update/chat runs. -->

## Audience

1. Coding agents (Claude Code, Codex CLI) orienting in this repository before
   making changes.
2. External users of the `research-hub` PyPI package — this is a public repo,
   so the wiki doubles as user-facing architecture documentation.

## Scope and priorities (in order)

1. **CLI module map.** `cli.py` dispatches to the split `cli_*` modules
   (citations, clusters, common, maintenance, notebooklm, paper, pipeline,
   search, summarize, vault, zotero). Document which subcommands live in which
   module and the canonical `python -m research_hub ...` invocation pattern
   (README's form; `PYTHONPATH=src` prefixing is the dev/pytest variant).
   This is the page agents need most.
2. **Ingest pipeline architecture.** Discovery → Zotero save (local API vs Web
   API boundary) → Obsidian note generation → hub index rebuild → NotebookLM
   upload. Package boundaries (`connectors/`, `api/`, `dashboard/`) matter more
   than per-function detail.
3. **Vault layout and maintenance flows.** What doctor / cleanup / dedup /
   cluster-rebind do, and which operations are destructive vs preview-only.
4. **Release flow.** Pointer to docs/RELEASING.md — do not duplicate it.
5. **Testing.** How to run the suite and where the main test seams are.

## Constraints

- Code is the source of truth. Where docs/ and src/ disagree, document src/
  behavior and flag the discrepancy explicitly.
- NEVER read or quote .env files, config.json (use config.json.example only),
  API keys, tokens, or credentials of any kind.
- Do not document the maintainer's personal vault contents, local paths, or
  paper collections — this wiki describes the tool, not anyone's library.
- Prefer linking to existing docs/ pages over restating them; the wiki is an
  orientation layer, not a docs/ replacement.
- Keep the wiki small: quickstart plus at most ~7 section pages. Depth over
  breadth; no stub pages.
- English only.

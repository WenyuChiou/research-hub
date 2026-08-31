# research-hub quickstart

research-hub (PyPI: `research-hub-pipeline`, v1.2.0, Python >= 3.10) is a CLI pipeline that turns Zotero, Obsidian, and NotebookLM into one AI-operable literature workspace. A single run discovers papers across academic search backends (arXiv, Semantic Scholar, CrossRef, OpenAlex, PubMed, and more under `src/research_hub/search/`), saves them into Zotero with hub-namespace tags, generates Obsidian paper notes, rebuilds the hub index, and optionally bundles and uploads the cluster to NotebookLM for brief generation. The same functionality is exposed four ways: the `research-hub` CLI (`research_hub.cli:main`), an MCP server (`research-hub-mcp` -> `research_hub.mcp_server:main`), a REST API (`src/research_hub/api/`), and a local dashboard (`src/research_hub/dashboard/`). Everything operates on a local-first vault the user owns; no OpenAI/Anthropic API key is required.

## Start here

- [CLI module map](./cli/modules.md) — which subcommands live in which `cli_*` module, and how `cli.py` dispatches to the split modules.
- [Ingest pipeline architecture](./architecture/ingest-pipeline.md) — discovery → Zotero save → Obsidian note generation → hub index rebuild → NotebookLM upload, and the package boundaries (`connectors/`, `api/`, `dashboard/`) along the way.
- [Vault maintenance](./operations/vault-maintenance.md) — vault layout plus doctor / cleanup / dedup / cluster-rebind flows, and which operations are destructive vs preview-only.
- [Release and testing](./operations/release-and-testing.md) — how to run the test suite, the main test seams, and a pointer to [docs/RELEASING.md](../docs/RELEASING.md) for the release flow.

## Repository layout

- `src/research_hub/` — the package (hatchling build, `packages = ["src/research_hub"]` in `pyproject.toml`). Key areas:
  - `cli.py` + `cli_*.py` — argparse entry point split into eleven modules (`cli_citations`, `cli_clusters`, `cli_common`, `cli_maintenance`, `cli_notebooklm`, `cli_paper`, `cli_pipeline`, `cli_search`, `cli_summarize`, `cli_vault`, `cli_zotero`); `cli.py` builds the parser tree (~170 subparser registrations) and imports the handlers.
  - `pipeline.py`, `auto.py`, `discover.py`, `dedup.py`, `verify.py` — the ingest pipeline core: candidate discovery, dedup against Zotero/Obsidian, DOI/arXiv verification, Zotero item creation, manifest logging.
  - `search/` — pluggable search backends plus fallback/ranking logic (`fallback.py`, `_rank.py`, `query_expansion.py`).
  - `zotero/` — Zotero client boundary (`client.py`, `fetch.py`): pyzotero-based reads/writes, duplicate checks, child notes.
  - `notebooklm/` — NotebookLM implementation: `auth.py`, `bundle.py`, `upload.py`, `ask.py`, `download.py` over `notebooklm-py`.
  - `connectors/` — the external-service seam: a `Connector` Protocol (bundle → upload → generate → download), `_notebooklm_adapter.py` providing the Protocol view over the existing NotebookLM code, and `null.py` for no-op runs.
  - `vault/` — Obsidian vault operations: `builder.py` (hub index), `cleanup.py`, `gc.py`, `repair.py`, `sync.py`, graph coloring, migrations.
  - `api/` — REST API helpers (`v1.py`, `jobs.py`) served alongside the dashboard.
  - `dashboard/` — HTML dashboard: `http_server.py`, `render.py`, `sections.py`, `data.py`, `executor.py` (action buttons), plus `template.html` / `script.js` / `style.css`.
  - `mcp_server.py`, `skill/` + `skills_data/`, `samples/` — MCP server, packaged AI-host skills, and sample-vault data (shipped in the wheel).
- `tests/` — pytest suite (`pytest.ini`: `testpaths = tests`, default run excludes `slow`/`stress` markers, 30 s per-test timeout).
- `docs/` — user-facing docs: [cli-reference.md](../docs/cli-reference.md), [setup.md](../docs/setup.md), [notebooklm.md](../docs/notebooklm.md), [mcp-tools.md](../docs/mcp-tools.md), [RELEASING.md](../docs/RELEASING.md), per-version audits.
- `skills/` — AI-host skill packages (gap-to-topic, literature-triage-matrix, paper-summarize, research-hub, zotero-library-curator, ...) mirrored into `src/research_hub/skills_data/` for wheel distribution.
- `config.json.example`, `constraints.txt`, `scripts/` — config template, reproducible-install constraints, dev scripts.

## Canonical invocation and configuration

The canonical CLI form is:

```bash
python -m research_hub <command> ...
```

`src/research_hub/__main__.py` delegates to `research_hub.cli:main`, so this is identical to the installed `research-hub` console script. Prefixing `PYTHONPATH=src` is the dev/pytest variant for running from a source checkout without installing.

Configuration is a JSON file modeled on `config.json.example` at the repo root: vault paths under `knowledge_base` (root/raw/hub/projects/logs), `clusters_file`, and a `zotero` block (library id/type, default collection, collection map). `src/research_hub/config.py` resolves it in order: the `RESEARCH_HUB_CONFIG` environment variable, then the platformdirs user config dir (`research-hub/config.json`), then legacy skill locations, then a repo-root `config.json`. Never commit a real `config.json`; secrets (Zotero API key, NotebookLM auth) stay out of the repo entirely.

Quick smoke test without any accounts:

```bash
pip install research-hub-pipeline
python -m research_hub dashboard --sample
```

## Backlog

Not yet covered by this wiki (read the source or `docs/` directly for now):

- Dashboard internals — section renderers, the action-button `executor.py`, drift/briefing views.
- The REST `api/` surface (`v1.py`, `jobs.py`) and how `serve` wires API + dashboard together.
- MCP server tool inventory (`mcp_server.py`; see [docs/mcp-tools.md](../docs/mcp-tools.md)).
- `skills/` packaging and the skill installer (`skill_installer.py`, `skills_data/`).
- Search-backend details beyond the pipeline's use of them (ranking, query expansion, region/field presets in `search/fallback.py`).
- Import/EZproxy paths for local PDFs and paywalled sources (`importer.py`, `ezproxy.py`).

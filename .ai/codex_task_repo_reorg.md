# Codex task: research-hub repo reorg to src/research_hub/

Pure refactor. No behavior changes. Use `git mv` for all moves. All existing pytest tests must still pass at the end.

## File mapping (exact)

```
hub_config.py        → src/research_hub/config.py
build_hub.py         → src/research_hub/vault/builder.py
categorize_graph.py  → src/research_hub/vault/categorize.py
fix_orphans.py       → src/research_hub/vault/repair.py
fetch_zotero.py      → src/research_hub/zotero/fetch.py
zotero_client.py     → src/research_hub/zotero/client.py
run_pipeline.py      → split into src/research_hub/pipeline.py (logic) + src/research_hub/cli.py (argparse main)
```

Create empty `__init__.py` in: `src/research_hub/`, `src/research_hub/zotero/`, `src/research_hub/vault/`.

## Import rewrites (update every internal import site)

- `from hub_config import X` → `from research_hub.config import X`
- `import hub_config` → `from research_hub import config as hub_config` (if used as module prefix) OR rewrite call sites
- `from zotero_client import ZoteroClient` → `from research_hub.zotero.client import ZoteroClient`
- `from fetch_zotero import X` → `from research_hub.zotero.fetch import X`
- `from build_hub import X` → `from research_hub.vault.builder import X`
- `from categorize_graph import X` → `from research_hub.vault.categorize import X`
- `from fix_orphans import X` → `from research_hub.vault.repair import X`

**Tests under `tests/`** use the same patterns. Also update any `monkeypatch.setattr("hub_config.X", ...)` style strings to the new dotted path (e.g. `"research_hub.config.X"`).

## pyproject.toml (create at repo root)

PEP 621, hatchling backend. Exact content:

```toml
[project]
name = "research-hub"
version = "0.2.0"
description = "Zotero → Obsidian → NotebookLM research pipeline"
authors = [{name = "WenyuChiou"}]
requires-python = ">=3.10"
dependencies = [
    "pyzotero>=1.5",
    "requests>=2.28",
]

[project.optional-dependencies]
dev = ["pytest>=7"]

[project.scripts]
research-hub = "research_hub.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/research_hub"]
```

Delete `requirements.txt` (its deps are now in pyproject.toml). Update README's install section to `pip install -e .`.

## src/research_hub/cli.py

Argparse entry point with subcommands. Extract argparse logic from the existing `run_pipeline.py`. Expose:

- `research-hub run --topic "..." --max-papers N` — main pipeline run
- `research-hub run --dry-run` — existing dry-run behavior
- `research-hub verify` — calls `scripts/verify_setup.py` or its logic

`main()` function must be the entry point referenced by `[project.scripts]`.

## Update references to `python run_pipeline.py`

Grep and replace in:
- `README.md`
- `SKILL.md` (if exists)
- `skills/knowledge-base/SKILL.md` (if exists)
- `scripts/verify_setup.py`
- `RESEARCH_HUB_IMPROVEMENT_PLAN.md` (if exists)

Replace with `research-hub run` or `python -m research_hub run` as appropriate.

## Verification gate (Codex must run before claiming done)

```bash
pip install -e .
pytest -q
research-hub --help
python -m research_hub --help
research-hub run --dry-run
```

All must succeed. If any fail, fix and re-run.

## Rules (do not violate)

- Use `git mv`, NOT `cp` + `rm` — history must be preserved
- No old files at repo root after the move
- Do not add dependencies beyond what's listed
- Do not change pipeline behavior — pure refactor
- Do not commit — leave everything staged for Claude review
- Do not push

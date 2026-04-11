# Contributing

Research Hub is a personal research tool shared publicly. Contributions are welcome, but this is not a production framework — please open an issue before large changes so we can align on scope.

---

## Development setup

```bash
git clone https://github.com/WenyuChiou/research-hub
cd research-hub
pip install -e '.[dev]'
```

The `[dev]` extra pulls in `pytest`, `pytest-mock`, `responses`, `pytest-cov`, and `coverage[toml]`.

---

## Running tests

```bash
pytest -q
```

If you run into import errors, set `PYTHONPATH`:

```bash
PYTHONPATH=src pytest -q
```

42 tests ship in this release; they cover config loading, pipeline entry points, Zotero client credential resolution, fetch helpers, and vault categorization. All tests run without a live Zotero instance — network calls are monkeypatched.

To run with coverage:

```bash
pytest --cov=research_hub --cov-report=term-missing
```

The CI workflow on GitHub Actions runs the suite on Python 3.10, 3.11, and 3.12 against every push.

---

## Branch naming

- `feature/<short-desc>` — new features
- `fix/<short-desc>` — bug fixes
- `docs/<short-desc>` — docs-only changes
- `test/<short-desc>` — test-only changes
- `refactor/<short-desc>` — internal cleanup with no behavior change
- `release/<version>` — release preparation branches

---

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) prefixes:

- `feat:` — new feature
- `fix:` — bug fix
- `test:` — adding or updating tests
- `docs:` — documentation
- `refactor:` — code change that is neither a feature nor a fix
- `chore:` — tooling, config, dependencies

Include a body explaining **why** the change is needed, not just what it does. For non-trivial changes, link to the issue it resolves.

Example:

```
fix(pipeline): raise early if default_collection missing

The pipeline used to swallow the missing-config case and emit a
cryptic KeyError midway through Step 4. Raising RuntimeError at the
top of run_pipeline() gives users an actionable error before any
Zotero writes happen.

Fixes #42
```

---

## Pull requests

- Target `master`
- Ensure CI is green (all three Python versions)
- Ensure tests still pass with `pytest -q`
- One reviewer approval (currently @WenyuChiou)
- Squash-merge unless you have a specific reason to keep individual commits

---

## Code style

- Python: follow PEP 8, 4-space indent
- Use type hints where they add clarity, especially on public function signatures
- No `black` enforcement yet; match the surrounding style
- Avoid adding new dependencies without discussion — keep the runtime deps minimal

---

## Reporting bugs

Open an issue with:

- OS and version (Windows 11, macOS 14, Ubuntu 24.04...)
- Python version (`python --version`)
- Step-by-step reproduction
- Full traceback if the pipeline crashed
- Your `config.json` with API key removed

---

## Requesting features

Open an issue with the `enhancement` label. Describe the use case you're trying to solve, not a proposed implementation. The Phase 2 roadmap (semantic search, incremental build, dedup across Obsidian, classification audit log) is tracked via issues — feel free to pick one up, but say so on the issue first to avoid duplicate work.

---

## Security

This tool reads and writes to your Zotero library. It does not send data anywhere else unless you explicitly enable NotebookLM upload (Step 5). If you find a security issue that should not be discussed publicly, please email the maintainer instead of opening an issue.

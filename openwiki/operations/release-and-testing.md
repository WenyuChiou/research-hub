# Release and testing

How to run the test suite, what the test seams are, and where the release process lives. This page is deliberately a pointer layer — the release runbook is [docs/RELEASING.md](../../docs/RELEASING.md) and dev setup is [CONTRIBUTING.md](../../CONTRIBUTING.md); do not duplicate them here.

## Running the tests

Pytest configuration lives in `pytest.ini` (the `[tool.pytest.ini_options]` block was removed from `pyproject.toml` because pytest prefers `pytest.ini` and the duplicate silently drifted — edit `pytest.ini` only). Defaults: `testpaths = tests`, `--timeout=30` per test, and `-m "not slow and not stress"` plus `--ignore=tests/stress`, so the default run excludes slow and stress tests automatically.

```bash
pip install -e '.[dev]'
pytest -q
```

If imports fail (running from a clone without an editable install), use the dev variant:

```bash
PYTHONPATH=src pytest -q
```

Coverage, per [CONTRIBUTING.md](../../CONTRIBUTING.md):

```bash
pytest --cov=research_hub --cov-report=term-missing
```

## Test seams

The suite is ~350 flat `test_*.py` files under `tests/`, organized by seam rather than by directory — plus two opt-in subdirectories:

- **Default suite** (`tests/test_*.py`) — unit and integration tests over the CLI split, pipeline, connectors, vault maintenance, and dashboard. Includes an e2e smoke (`tests/test_e2e_smoke.py`). Shared fixtures in `tests/conftest.py`.
- **Network fence** — `tests/conftest.py` installs a structural fence via `pytest-socket`: every test is restricted to loopback/unix sockets unless marked `network`, `real_zotero`, or `real_authenticity` (opt-in live-API markers). Unmarked tests cannot silently hit the wire.
- **`tests/evals/`** — accuracy evaluations (search accuracy, fit-check quality, DOI normalization) with a metrics collector that appends results to `tests/evals/_metrics.json`.
- **`tests/stress/`** — stress/load tests, excluded by default; run explicitly with `pytest tests/stress/ -o "addopts=" -m stress`.
- **Markers** (declared in `pytest.ini`): `stress`, `network`, `evals`, `slow` (tests >30 s or blocking at C level; excluded by default).

## Release flow

The release process is **mechanically gated**: `bash scripts/release-check.sh` verifies a clean tree, `__version__`/`pyproject.toml` version sync, and the full pytest suite *including e2e* on a fresh `--basetemp`, then writes a sha-bound marker that a `pre-push` hook (installed by `scripts/install_release_gate.sh`) requires before any `v*` tag push. After pushing, `gh run watch` on real CI is mandatory — local green is not shipped green. The full runbook (version-bump checklist including `server.json`, step ordering rationale, MCP Registry republish, emergency bypass) is [docs/RELEASING.md](../../docs/RELEASING.md).

## CI workflows

- `.github/workflows/ci.yml` — runs on every branch push and on PRs to `master`: full suite (`-m "not slow"`) on Windows/macOS for Python 3.10–3.13 (3.14 experimental, non-gating), a 4-shard `pytest-split` matrix on Ubuntu (RAM limits), a coverage job (`--cov-fail-under=62`, Windows py3.12), a PR-only stress-test job, and a PR-only `skill-version-guard` that blocks skill-content changes lacking a plugin version bump.
- `.github/workflows/publish.yml` — triggered by pushing a `v*` tag: builds the package, validates the wheel installs in a fresh venv with `__version__` matching the tag, smoke-tests the installed wheel (`init --sample` + `describe --json`), then uploads to PyPI with `twine upload --skip-existing`.

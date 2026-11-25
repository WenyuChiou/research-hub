# CI routing and checkout identity

The `CI` workflow runs on pushes to `master` or `verify/**`, and on pull requests targeting **any base branch**. PR events are `opened`, `synchronize`, `reopened`, `ready_for_review`, and `edited`, including draft PRs. `stress-tests` and `skill-version-guard` remain PR-only.

Other feature-branch pushes without a PR do not start CI. Open a PR to run checks, or push a commit to `verify/<unique-name>` for deliberate full-matrix diagnostics (`verify/**` always forces `scope=full`).

## Fail-closed path classification

Every run starts with `classify` (`scripts/classify_ci_changes.py`), which verifies checkout identity and inspects the exact git diff (`merge-base..head` on PRs; `before..after` on `master` pushes). Any unrecognized path, missing/empty diff, git lookup error, or infrastructure file (`pyproject.toml`, `constraints.txt`, `.github/workflows/ci.yml`, CI scripts/tests) **fails closed to `full`**:

| Scope | Triggered paths | Jobs executed |
|---|---|---|
| `docs` | `README*.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `AGENTS.md`, `UPGRADE.md`, `LICENSE`, `SECURITY.md`, `docs/**`, `openwiki/**`, pure docs contract tests | `classify`, `docs-and-skills` (Ubuntu py3.12), `skill-version-guard` (PR) |
| `skills` | `skills/**`, `src/research_hub/skills_data/**`, `.claude-plugin/plugin.json`, skill/reader contract tests (+ optional docs) | `classify`, `docs-and-skills` (Ubuntu py3.12), `docs-and-skills-windows` (Windows py3.12), `skill-version-guard` (PR) |
| `code` | Known `src/**`, `tests/**`, `scripts/**`, `web/**` changes (no infra/dependency files) | `classify`, `test-ubuntu` (3.10–3.13 shards + 3.14 shard 1), `test` (Windows py3.12 w/ 62% coverage + macOS py3.12), `workspace` (only if workspace UI/CLI/web changed), `stress-tests` (PR), `skill-version-guard` (PR) |
| `full` | `verify/**`, dependency/CI infra files, unrecognized paths, or diff errors | Everything in `code` + `workspace` + `test-extended-os` (Windows `3.10, 3.11, 3.13, 3.14*`; macOS `3.10, 3.14*`) + `dependency-audit` |

`*` Python `3.14` rows remain `continue-on-error: true` (experimental, non-blocking). Limiting `macos-latest` to 3 jobs even on `full` prevents exhausting GitHub's hosted macOS concurrency pool. `dependency-audit` runs `pip-audit` once instead of repeating it on every matrix runner, and mocked `defuddle` tests no longer install `defuddle-cli` across every test job.

## Cancellation and dependency downloads

Ordinary runs for the same PR share a workflow-namespaced concurrency group (`CI-pr-<number>`); a newer commit supersedes obsolete running or pending checks for that PR. Different PRs, different workflows, `master`/`verify/**` pushes, and PR `edited` events each get unique non-cancelling run IDs.

`setup-python` caches pip packages keyed on `pyproject.toml`, `constraints.txt`, and `.github/workflows/ci.yml`.

## Checkout identity

Before tests, every job (including `classify` and `docs-and-skills*`) runs `scripts/check_ci_checkout.py` against `GITHUB_EVENT_PATH`, `GITHUB_EVENT_NAME`, `GITHUB_SHA`, and `GITHUB_REF`:

- Pushes must check out `push.after` and the matching branch ref (deletions and all-zero SHAs fail closed).
- PRs must check out the exact two-parent merge commit matching `[base.sha, head.sha]` in order on `refs/pull/<number>/merge`.
- Raw `git cat-file commit` headers preserve parent identities under shallow clones. Missing, malformed, or mismatched identity fails before testing.

## Verification boundary

Run the bounded offline regressions locally:

```text
python -m unittest discover -s tests -p test_ci_routing.py -v
```

These cover YAML routing structure, `classify_ci_changes.py` scope/fail-closed behavior across all 4 scopes, and `CheckoutIdentity` temporary Git regressions. They do not establish hosted GitHub Actions runner scheduling or branch rulesets.

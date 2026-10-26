# CI routing and checkout identity

The `CI` workflow runs the existing full matrix and workspace checks on pushes
to `master` or `verify/**`, and on pull requests targeting **any base branch**. PR events are
`opened`, `synchronize`, `reopened`, `ready_for_review`, and `edited`, including
draft PRs. Stress tests and the skill-version guard remain PR-only.

Other feature-branch pushes without a PR no longer start full CI. Open a PR to
get the full PR checks. For deliberate diagnostics of an exact commit, push it
to a `verify/<unique-name>` branch. This ordinary push route checks that commit
with the matrix, workspace checks, and checkout guard. A green `verify/**` run
is push diagnostics only: PR acceptance also requires the PR's synthetic merge,
stress tests, and skill-version guard. There is no manual dispatcher.

Every PR edit runs real checks, including title/body edits as well as base
changes. This accepts occasional extra runs to avoid replacing valid checks
with same-named skipped jobs or missing a retargeted PR. No path classifier,
Markdown exemption, reduced matrix, or required-check rename is introduced.

## Cancellation and dependency downloads

Ordinary runs for the same PR share a workflow-namespaced concurrency group;
a newer run can supersede obsolete running or pending checks for that PR.
Different PRs and different workflows do not share that group. Every master or
`verify/**` push and every PR `edited` event uses its own run ID, with cancellation off.
This also prevents GitHub's pending-run replacement from discarding integration
or edit checks. Edit runs neither cancel ordinary PR runs nor get cancelled by
them. An old edit run is evidence for its own event, not for a later revision.

`setup-python` caches pip's downloaded packages/wheels, partitioned by its
normal Python/platform key and the hashes of `pyproject.toml`, `constraints.txt`,
and `.github/workflows/ci.yml`. All installation commands still execute normally.
Windows Python 3.12 runs the full suite once with coverage and the existing
62% threshold; its duplicate plain pytest invocation is skipped. Other test
rows, Ubuntu shards, workspace verification, and PR guards keep their checks.

## Checkout identity

Before tests, each job runs `scripts/check_ci_checkout.py` against the runner's
`GITHUB_EVENT_PATH`, `GITHUB_EVENT_NAME`, `GITHUB_SHA`, and `GITHUB_REF`:

- A push must check out exactly the event's `after` SHA and matching branch ref.
  Push deletions and all-zero SHAs fail closed as non-validation events. GitHub
  can associate a branch-deletion run with the default branch SHA, so that
  fallback must not count as proof of the deleted branch's tree. See the
  [official push-event semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#push).
- A PR must check out exactly its event merge SHA and PR merge ref. The raw
  commit must have exactly two parents, in order: the event's base SHA and head
  SHA. Matching only a run's SHA or timestamp cannot establish this.
- Raw `git cat-file commit` headers preserve parent identities even when a
  depth-one checkout hides them from history traversal. Missing, malformed,
  ambiguous, or mismatched identity fails the job before testing.

The guard never fetches or repairs a tree. A stale merge fails rather than
reporting green for the wrong base/head. Re-running an old event retains its
original payload; it does not establish validation against a newer base.

Python 3.14 rows retain their existing experimental `continue-on-error` policy.
An identity failure in such a row can coexist with a green workflow conclusion.
Inspect the actual jobs: overall green alone does not prove experimental
checkout identity or successful validation on every platform.

## Verification boundary

Run the bounded offline regressions without installing anything:

```text
python -m unittest discover -s tests -p test_ci_routing.py -v
```

These check YAML structure, event/concurrency decisions, matrix and coverage
invariants, and the real guard using temporary Git histories, including a
shallow boundary and stale merges. They do not establish hosted event delivery,
cancellation, cache reuse, or repository protection settings. Those need hosted
acceptance after independent patch review. Publication, security, Pages, and
other workflows are outside this change.

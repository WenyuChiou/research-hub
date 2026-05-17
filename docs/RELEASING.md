# Releasing research-hub

The release process is **mechanically gated**. This is not optional
ceremony — it exists because v0.89.1 and v0.91.0 both shipped to
PyPI with a RED CI when the test scope was narrowed under time
pressure (v0.89.1: no pytest; v0.91.0: e2e silently `--ignore`'d).
The gate makes "ship a red release" require a deliberate, logged
`--no-verify`, not a quiet scope cut.

## One-time setup (per clone)

```bash
bash scripts/install_release_gate.sh
```

Installs a `pre-push` hook that refuses to push a `v*` tag unless
`scripts/release-check.sh` passed against that exact commit.
(`--force` backs up + replaces an existing pre-push hook.)

## Release flow

```bash
# 1. Land all changes. Bump version in BOTH:
#      src/research_hub/__init__.py  (__version__)
#      pyproject.toml                ([project] version)
#    Add the CHANGELOG entry. Commit it (release commit).

# 2. Run the gate. It checks: clean tree, version sync, and the
#    FULL pytest suite INCLUDING e2e on a fresh --basetemp.
bash scripts/release-check.sh
#    → on pass it writes .git/RELEASE_GATE_PASSED bound to HEAD.

# 3. Tag + push. The pre-push hook validates the marker's sha
#    against the tag's commit, then consumes it.
git tag -a vX.Y.Z -m "vX.Y.Z ..."
git push origin master vX.Y.Z

# 4. Verify REAL CI, not local:
gh run watch <run-id> --exit-status     # ubuntu+macos+windows green
#    Local green ≠ shipped green (the v0.91.0 lesson).
```

## Why the steps are in this order

- The gate runs **after** the release commit so the marker binds to
  the commit the tag will point at. Re-running after any further
  commit invalidates the old marker (sha mismatch → hook refuses).
- The only allowed pytest exclusion is `test_v065_extras_install`
  (a known Windows venv/ensurepip *environment* issue, not a code
  defect) — hard-coded + justified inside `release-check.sh`, never
  an ad-hoc CLI flag. e2e is **always** included.
- `gh run watch` is mandatory: the gate proves local green; CI
  proves it green on the platforms users actually run.

## Emergency bypass

`git push --no-verify origin master vX.Y.Z` skips the hook. Use
ONLY with explicit operator authorization and record the reason in
the release commit body. Every prior "we'll just skip the gate this
once" in this project's history shipped a broken release.

## Files

- `scripts/release-check.sh` — the gate (clean tree + version sync + full pytest incl e2e)
- `scripts/install_release_gate.sh` — installs the pre-push hook
- `.git/hooks/pre-push` — the installed gate (sha-bound, single-use marker)
- `tests/test_release_gate.py` — meta-tests the gate's own logic

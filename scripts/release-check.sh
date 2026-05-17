#!/usr/bin/env bash
# release-check.sh — the mechanical release gate for research-hub.
#
# WHY THIS EXISTS
# ---------------
# v0.89.1 and v0.91.0 both shipped to PyPI with a RED CI because the
# release pytest scope was narrowed under time pressure (v0.89.1: no
# pytest at all; v0.91.0: the entire e2e suite was `--ignore`'d
# because the dev tree's .pytest-work was icacls-polluted). The
# `code-review` skill catches diff-level defects but does NOT run
# tests. "Claude self-enforces the test gate" demonstrably failed
# twice in one session. This script + the pre-push hook
# (install_release_gate.sh) make the gate MECHANICAL: a v* tag push
# is refused unless this script passed against the exact tagged
# commit.
#
# WHAT IT CHECKS (in order, fail-fast)
#   1. Working tree clean (no uncommitted changes).
#   2. Version sync: src/research_hub/__init__.py __version__
#      == pyproject.toml [project].version.
#   3. FULL pytest suite INCLUDING e2e, on a fresh --basetemp
#      (immune to a locally icacls-polluted .pytest-work).
#      The ONLY excluded test is test_v065_extras_install — a known
#      Windows venv/ensurepip *environment* issue (not a code
#      defect); the exclusion is hard-coded + justified HERE so it
#      is auditable, never an ad-hoc CLI `--ignore` the operator
#      can silently widen.
#
# On full success: writes .git/RELEASE_GATE_PASSED containing
#   "<HEAD-commit-sha> <UTC-timestamp>"
# The pre-push hook validates that sha against the tagged commit,
# so the marker is single-use per release by construction.
#
# Usage:  bash scripts/release-check.sh
# Exit:   0 = gate passed (marker written); non-zero = blocked.

set -euo pipefail

# Resolve repo root from this script's location (works from any cwd).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

GIT_DIR="$(git rev-parse --git-dir)"
MARKER="$GIT_DIR/RELEASE_GATE_PASSED"

fail() { echo "  [release-check] BLOCKED: $1" >&2; rm -f "$MARKER"; exit 1; }

echo "[release-check] 1/3 working tree clean?"
if [[ -n "$(git status --porcelain)" ]]; then
    git status --short >&2
    fail "uncommitted changes — commit or stash before releasing."
fi

echo "[release-check] 2/3 version sync?"
# `|| true` so a grep no-match doesn't trip `set -euo pipefail` and
# abort BEFORE the graceful handler below — keeps fail() (which
# rm's the marker) reachable instead of relying solely on the hook's
# sha-binding as the fail-closed net. (code-review P2)
INIT_V="$(grep -oE '__version__ = "[^"]+"' src/research_hub/__init__.py | grep -oE '[0-9][^"]*' || true)"
PYPROJECT_V="$(grep -oE '^version = "[^"]+"' pyproject.toml | grep -oE '[0-9][^"]*' || true)"
if [[ -z "$INIT_V" || -z "$PYPROJECT_V" ]]; then
    fail "could not extract version (init='$INIT_V' pyproject='$PYPROJECT_V')."
fi
if [[ "$INIT_V" != "$PYPROJECT_V" ]]; then
    fail "version drift: __init__.py=$INIT_V pyproject.toml=$PYPROJECT_V."
fi
echo "  version OK: $INIT_V"

echo "[release-check] 3/3 FULL pytest incl e2e (fresh basetemp)..."
# Hard-coded exclusion list — the ONLY allowed --ignore. e2e is
# DELIBERATELY NOT here: that is the whole point of this gate.
BASETEMP="$(mktemp -d)"
PYTEST_CMD=(python -m pytest tests/ -q --no-header
    --ignore=tests/test_v065_extras_install.py
    --basetemp="$BASETEMP")
echo "  ${PYTEST_CMD[*]}"
if ! "${PYTEST_CMD[@]}"; then
    fail "pytest failed — see output above. DO NOT release."
fi

HEAD_SHA="$(git rev-parse HEAD)"
printf '%s %s\n' "$HEAD_SHA" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$MARKER"
echo "[release-check] PASSED. Marker: $MARKER ($HEAD_SHA)"
echo "  You may now: git tag vX.Y.Z && git push origin master vX.Y.Z"

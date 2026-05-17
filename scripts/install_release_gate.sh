#!/usr/bin/env bash
# install_release_gate.sh — install the pre-push release gate hook.
#
# Mirrors ~/.claude/scripts/install_review_gate.sh (the per-repo
# pre-commit code-review gate) but for RELEASES: it blocks pushing a
# `refs/tags/v*` tag unless scripts/release-check.sh passed against
# the exact commit the tag points to.
#
# Usage:
#   bash scripts/install_release_gate.sh [--force]
#
#   --force : back up an existing pre-push hook to
#             pre-push.bak.YYYYMMDD-HHMMSS before clobbering. Without
#             --force the installer refuses to overwrite a pre-push
#             hook (husky/lefthook users would silently lose theirs).
#
# Uninstall: rm .git/hooks/pre-push  (or restore from .bak).
# Emergency bypass (logged expectation: only with explicit operator
# say-so): git push --no-verify ...

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

GIT_DIR="$(git rev-parse --git-dir)"
GIT_DIR="$(cd "$GIT_DIR" && pwd)"
HOOK_DIR="$GIT_DIR/hooks"
mkdir -p "$HOOK_DIR"
DEST="$HOOK_DIR/pre-push"

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

if [[ -e "$DEST" && $FORCE -eq 0 ]]; then
    echo "Error: $DEST already exists. Re-run with --force to back it up + replace." >&2
    exit 1
fi
if [[ -e "$DEST" && $FORCE -eq 1 ]]; then
    BAK="$DEST.bak.$(date +%Y%m%d-%H%M%S)"
    cp "$DEST" "$BAK"
    echo "Backed up existing pre-push hook → $BAK"
    echo "  (chain it back manually if you need it)"
fi

cat > "$DEST" <<'HOOK'
#!/usr/bin/env bash
# pre-push release gate (installed by scripts/install_release_gate.sh).
#
# Refuses to push a v* tag unless scripts/release-check.sh wrote a
# RELEASE_GATE_PASSED marker bound to the SAME commit the tag points
# to. Non-tag pushes (branches) pass straight through — this gate is
# release-only. The marker is sha-bound so it is single-use per
# release by construction; the hook also consumes it on a validated
# tag push so a re-push must re-verify.
#
# git feeds pre-push these stdin lines:
#   <local-ref> <local-sha> <remote-ref> <remote-sha>
#
# NOTE (code-review P3): if multiple v* tags are pushed in one
# command (e.g. `git push --tags`), this loop keeps only the LAST
# matching tag's commit, so only that one is sha-validated. The
# documented release flow (docs/RELEASING.md) pushes exactly one
# tag at a time (`git push origin master vX.Y.Z`), which this
# handles correctly; the multi-tag path is intentionally not
# supported by the gate.
set -euo pipefail

GIT_DIR="$(git rev-parse --git-dir)"
MARKER="$GIT_DIR/RELEASE_GATE_PASSED"

tag_push=0
tag_commit=""
while read -r local_ref local_sha remote_ref remote_sha; do
    case "$local_ref" in
        refs/tags/v*)
            tag_push=1
            # Resolve the commit the (possibly annotated) tag targets.
            # --verify --quiet => unresolvable ref yields EMPTY (and the
            # sha-compare below then fails closed / refuses), instead of
            # `git rev-parse` echoing the literal "<ref>^{commit}" back
            # (its lenient no--verify behaviour) and silently mismatching.
            tag_commit="$(git rev-parse --verify --quiet "${local_ref}^{commit}" 2>/dev/null || true)"
            ;;
    esac
done

# Not a tag push → nothing to gate.
[[ $tag_push -eq 0 ]] && exit 0

if [[ ! -f "$MARKER" ]]; then
    echo "✗ release gate: no RELEASE_GATE_PASSED marker." >&2
    echo "  Run:  bash scripts/release-check.sh" >&2
    echo "  (it runs the FULL suite incl e2e; only then may you push a v* tag)" >&2
    echo "  Emergency bypass (discouraged): git push --no-verify ..." >&2
    exit 1
fi

marker_sha="$(awk '{print $1}' "$MARKER")"
if [[ "$marker_sha" != "$tag_commit" ]]; then
    echo "✗ release gate: marker is stale." >&2
    echo "  marker commit : $marker_sha" >&2
    echo "  tag commit    : $tag_commit" >&2
    echo "  Re-run:  bash scripts/release-check.sh  (after committing the release)" >&2
    exit 1
fi

# Validated — consume the marker so a re-push must re-verify.
rm -f "$MARKER"
echo "✓ release gate: verified $tag_commit (marker consumed)." >&2
exit 0
HOOK

chmod +x "$DEST"
echo "✓ release gate installed: $DEST"
echo "  Release flow:  bash scripts/release-check.sh  →  git tag vX.Y.Z  →  git push origin master vX.Y.Z"

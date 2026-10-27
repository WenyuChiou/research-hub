"""Fail CI before testing a checkout that does not match its triggering event.

Read raw commit headers: traversal commands hide parents at a shallow boundary.
This guard never fetches, updates refs, or repairs a mismatched checkout.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys


class CheckoutIdentityError(ValueError):
    """The checkout cannot be bound to the event's immutable commit identities."""


def _oid(value: object, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value) or value == "0" * 40:
        raise CheckoutIdentityError(f"{label} must be a full nonzero lowercase SHA-1")
    return value


def _field(event: object, *keys: str) -> object:
    value = event
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            raise CheckoutIdentityError(f"missing event field: {'.'.join(keys)}")
        value = value[key]
    return value


def _git(*args: str, cwd: Path | None) -> str:
    result = subprocess.run(
        ["git", "--no-replace-objects", *args], cwd=cwd,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=True, timeout=10,
    )
    return result.stdout


def verify_checkout(
    event_name: str, event: object, github_sha: str, github_ref: str,
    *, cwd: Path | None = None,
) -> str:
    expected = _oid(github_sha, "GITHUB_SHA")
    if event_name == "push":
        if isinstance(event, dict) and event.get("deleted", False) is not False:
            raise CheckoutIdentityError("push deletion is not a validation event")
        after = _oid(_field(event, "after"), "push.after")
        event_ref = _field(event, "ref")
        if not github_ref.startswith("refs/heads/") or event_ref != github_ref:
            raise CheckoutIdentityError("push ref does not match GITHUB_REF")
        if after != expected:
            raise CheckoutIdentityError("push.after does not match GITHUB_SHA")
    elif event_name == "pull_request":
        number = _field(event, "number")
        if type(number) is not int or number <= 0:
            raise CheckoutIdentityError("PR number must be a positive integer")
        if github_ref != f"refs/pull/{number}/merge":
            raise CheckoutIdentityError("PR checkout must use its merge ref")
        base = _oid(_field(event, "pull_request", "base", "sha"), "PR base SHA")
        head = _oid(_field(event, "pull_request", "head", "sha"), "PR head SHA")
    else:
        raise CheckoutIdentityError(f"unsupported CI event: {event_name!r}")

    actual = _oid(_git("rev-parse", "--verify", "HEAD", cwd=cwd).strip(), "HEAD")
    if actual != expected:
        raise CheckoutIdentityError(f"HEAD {actual} does not match event SHA {expected}")
    if event_name == "pull_request":
        raw = _git("cat-file", "commit", actual, cwd=cwd)
        headers, separator, _ = raw.partition("\n\n")
        parents = [line[7:] for line in headers.splitlines() if line.startswith("parent ")]
        if not separator or len(parents) != 2:
            raise CheckoutIdentityError("PR checkout must be an unambiguous two-parent merge")
        parents = [_oid(parent, "merge parent") for parent in parents]
        if parents != [base, head]:
            raise CheckoutIdentityError(
                f"merge parents {parents} do not match event base/head {[base, head]}"
            )
    return actual


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CheckoutIdentityError(f"duplicate event JSON key: {key}")
        result[key] = value
    return result


def main() -> int:
    try:
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if not event_path:
            raise CheckoutIdentityError("GITHUB_EVENT_PATH is required")
        event = json.loads(Path(event_path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        sha = verify_checkout(
            os.environ.get("GITHUB_EVENT_NAME", ""), event,
            os.environ.get("GITHUB_SHA", ""), os.environ.get("GITHUB_REF", ""),
        )
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"::error::Checkout identity could not be verified: {exc}", file=sys.stderr)
        return 1
    print(f"Checkout identity verified: {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

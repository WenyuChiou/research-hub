#!/usr/bin/env python3
"""Validate `.paper/claims.yml` files against the anti-leakage schema.

Usage:

    python scripts/check_claims_schema.py <path-to-claims.yml> [<more-paths>...]

If no paths are given, prints a usage message and exits with code 2.
The actual schema / validator behavior is exercised by the test suite
at ``tests/test_check_claims_schema.py``.

Enforces the anti-leakage rule from
``skills/paper-memory-builder/SKILL.md`` §"Anti-leakage rule":

    A claim with empty or absent ``evidence_artifacts`` MUST have
    ``status: gap`` plus a one-line ``gap_reason``.

Exits non-zero on the first validation error with a human-readable
location pointer (e.g. ``claims[3].status``). Designed to be called
from CI alongside the rest of the test suite.

Requires: PyYAML + jsonschema (both already declared in the project's
test dependencies).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

import yaml
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    REPO_ROOT
    / "skills"
    / "paper-memory-builder"
    / "references"
    / "claims.schema.json"
)


def _load_schema() -> dict:
    with SCHEMA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _format_path(absolute_path) -> str:
    """Render jsonschema's absolute_path deque as a dotted path with
    bracketed integer indexes, e.g. ``claims[3].status``."""
    parts: list[str] = []
    for p in absolute_path:
        if isinstance(p, int):
            if not parts:
                parts.append(f"[{p}]")
            else:
                parts[-1] = parts[-1] + f"[{p}]"
        else:
            parts.append(str(p))
    return ".".join(parts) if parts else "<root>"


def validate_file(path: Path, validator: Draft202012Validator) -> list[str]:
    """Return a list of human-readable error strings; empty list = clean."""
    if not path.exists():
        return [f"{path}: file not found"]
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        return [f"{path}: YAML parse error: {exc}"]
    if data is None:
        return [f"{path}: file is empty"]
    errors = sorted(
        validator.iter_errors(data), key=lambda e: list(e.absolute_path)
    )
    return [f"{path}: {_format_path(err.absolute_path)}: {err.message}" for err in errors]


def main(argv: Iterable[str]) -> int:
    args = list(argv)
    if not SCHEMA_PATH.exists():
        print(f"error: schema not found at {SCHEMA_PATH}", file=sys.stderr)
        return 2
    schema = _load_schema()
    validator = Draft202012Validator(schema)

    if not args:
        print(
            "usage: python scripts/check_claims_schema.py "
            "<path-to-claims.yml> [<more-paths>...]",
            file=sys.stderr,
        )
        return 2

    all_errors: list[str] = []
    for arg in args:
        all_errors.extend(validate_file(Path(arg), validator))

    if all_errors:
        print(
            f"claims schema check FAILED ({len(all_errors)} "
            f"error{'s' if len(all_errors) != 1 else ''}):",
            file=sys.stderr,
        )
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    n_files = len(args)
    print(
        f"claims schema check OK ({n_files} file{'s' if n_files != 1 else ''})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Keep local project readers independent of provider CLI initialization."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv[:2] not in (["project", "show"], ["project", "list"]):
        from research_hub.cli import main as legacy_main

        return legacy_main(argv)

    from research_hub.workspace.cli import add_workspace_parsers, dispatch_workspace
    from research_hub.audit import audit_command

    parser = argparse.ArgumentParser(prog="research-hub")
    add_workspace_parsers(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(raw_argv)
    # These existing read commands accept no --audit-output. Keep the same
    # no-store audit context instead of importing provider commands to create it.
    with audit_command(None, raw_argv) as audit:
        result = dispatch_workspace(args)
        audit.exit_code = result
        return result

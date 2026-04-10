"""Command line entry points for Research Hub."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from research_hub.pipeline import run_pipeline


def _verify() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "verify_setup.py"
    completed = subprocess.run([sys.executable, str(script_path)], cwd=str(repo_root))
    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-hub")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the research pipeline")
    run_parser.add_argument("--topic", default=None, help="Pipeline topic context")
    run_parser.add_argument("--max-papers", type=int, default=None, help="Maximum papers to process")
    run_parser.add_argument("--dry-run", action="store_true", help="Validate config and inputs only")

    subparsers.add_parser("verify", help="Run repository verification checks")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return run_pipeline(dry_run=args.dry_run)
    if args.command == "verify":
        return _verify()

    parser.error(f"Unknown command: {args.command}")
    return 2

#!/usr/bin/env python3
"""
verify_setup.py — Confirm the Research Hub pipeline is ready to run.

Usage:
    python scripts/verify_setup.py

Runs pytest then a dry-run of the package CLI.
Exits 0 on success, non-zero on any failure.
"""
import subprocess
import sys
import os
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PYTHONPATH = str(REPO_ROOT / "src")


def run(cmd, label):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    env = os.environ.copy()
    env["PYTHONPATH"] = PYTHONPATH if not env.get("PYTHONPATH") else f"{PYTHONPATH}{os.pathsep}{env['PYTHONPATH']}"
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    if result.returncode != 0:
        print(f"\n[FAIL] {label} exited {result.returncode}")
        sys.exit(result.returncode)
    print(f"[OK] {label}")


def check_config():
    config = REPO_ROOT / "config.json"
    example = REPO_ROOT / "config.json.example"
    if not config.exists():
        print(f"\n[WARN] config.json not found.")
        if example.exists():
            print(f"  Copy config.json.example → config.json and edit paths:")
            print(f"    cp config.json.example config.json")
        print("  Or set env vars: RESEARCH_HUB_ROOT, ZOTERO_API_KEY, ZOTERO_LIBRARY_ID")
        print("  Continuing without config (will use HOME defaults)...\n")
    else:
        print(f"[OK] config.json found at {config}")


def main():
    print("Research Hub — Setup Verification")
    print(f"Repo root: {REPO_ROOT}\n")

    check_config()

    run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short"],
        "pytest suite",
    )

    run(
        [sys.executable, "-m", "research_hub", "run", "--dry-run"],
        "python -m research_hub run --dry-run",
    )

    print("\n[ALL CHECKS PASSED] Research Hub is ready.")


if __name__ == "__main__":
    main()

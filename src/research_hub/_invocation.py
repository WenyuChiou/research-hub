"""Helpers for printing runnable research-hub CLI commands."""

from __future__ import annotations

import shutil
import sys


def recommended_cli_invocation() -> str:
    """The command prefix that actually works in this environment:
    the `research-hub` console script if on PATH, else the module form
    `<python> -m research_hub` (works from a source checkout where the
    console script was never installed or is not on PATH).
    """
    exe = shutil.which("research-hub")
    if exe:
        return "research-hub"
    return f"{sys.executable} -m research_hub"

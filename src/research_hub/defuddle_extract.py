"""Defuddle CLI wrapper for clean URL -> markdown extraction.

Replaces readability-lxml (unmaintained since 2021, flagged in v0.40 audit)
with kepano's defuddle CLI. The CLI is shipped via npm:

    npm install -g defuddle-cli

When the binary is not installed, ``extract_url_via_defuddle`` returns
``None`` and the caller (``importer._extract_url``) falls back to
readability-lxml. This keeps backwards-compat with v0.42 installs.

Defuddle skill: https://github.com/kepano/obsidian-skills (MIT)
Defuddle library: https://github.com/kepano/defuddle (MIT)
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Optional


_DEFUDDLE_BINARY_NAMES = ("defuddle", "defuddle-cli")
_DEFAULT_TIMEOUT_SEC = 30


def find_defuddle_binary() -> Optional[str]:
    """Return absolute path to the defuddle binary, or None if not installed."""
    for name in _DEFUDDLE_BINARY_NAMES:
        path = shutil.which(name)
        if path:
            return path
    return None


def extract_url_via_defuddle(
    url: str,
    *,
    timeout_sec: int = _DEFAULT_TIMEOUT_SEC,
) -> Optional[str]:
    """Shell out to ``defuddle parse <url> --md``, return clean markdown."""
    binary = find_defuddle_binary()
    if binary is None:
        return None
    try:
        completed = subprocess.run(
            [binary, "parse", url, "--md"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_sec,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if completed.returncode != 0:
        return None
    output = (completed.stdout or "").strip()
    return output if output else None

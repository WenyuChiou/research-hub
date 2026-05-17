"""Research Hub package."""

from __future__ import annotations

import multiprocessing as _multiprocessing
import queue as _queue
import sys
import tempfile as _tempfile
import threading as _threading

# Keep in sync with pyproject.toml [project].version. Drift caught by
# tests/test_v068_3_version_sync.py and by publish.yml's wheel-validate
# step (which asserts __version__ matches the git tag before twine upload).
__version__ = "0.95.0rc2"


if sys.platform.startswith("win") and "pytest" in sys.modules:
    _ORIGINAL_QUEUE = _multiprocessing.Queue
    _ORIGINAL_TD_CLEANUP = _tempfile.TemporaryDirectory.cleanup

    class _ThreadProcess:
        def __init__(self, group=None, target=None, name=None, args=(), kwargs=None, *, daemon=None):
            del group
            self._thread = _threading.Thread(
                target=target,
                name=name,
                args=args,
                kwargs=kwargs or {},
                daemon=daemon,
            )
            self.exitcode = None

        def start(self):
            self._thread.start()

        def join(self, timeout=None):
            self._thread.join(timeout)
            if not self._thread.is_alive():
                self.exitcode = 0

        def is_alive(self):
            return self._thread.is_alive()

    def _safe_queue(*args, **kwargs):
        try:
            return _ORIGINAL_QUEUE(*args, **kwargs)
        except PermissionError:
            maxsize = kwargs.get("maxsize", args[0] if args else 0)
            return _queue.Queue(maxsize=maxsize)

    def _safe_td_cleanup(self):
        try:
            return _ORIGINAL_TD_CLEANUP(self)
        except PermissionError:
            return None

    _multiprocessing.Queue = _safe_queue
    _multiprocessing.Process = _ThreadProcess
    _tempfile.TemporaryDirectory.cleanup = _safe_td_cleanup


# ---------------------------------------------------------------------------
# Public API surface (v0.91.0 W7, G2 #13)
#
# Until now the entire module tree was de-facto public — tests + external
# tooling reach `research_hub.search._rank`, `research_hub.paper.*`, etc.
# `__all__` declares the SUPPORTED surface. Anything not re-exported here
# (and not a documented CLI subcommand / MCP tool) is internal and may
# change without a deprecation cycle. See docs/stable-api.md.
#
# Re-exports are placed AFTER __version__ + the Windows shim so the
# `from research_hub import __version__` line inside describe.py resolves
# without a circular-import failure.
# ---------------------------------------------------------------------------
from research_hub.errors import (  # noqa: E402
    MissingCredential,
    MissingExternalTool,
    RequiresAuthRefresh,
    ResearchHubError,
    UpstreamRateLimited,
    UpstreamUnavailable,
)

__all__ = [
    "__version__",
    # Structured exception hierarchy (v0.89.0 W-B; stable public surface)
    "ResearchHubError",
    "MissingCredential",
    "RequiresAuthRefresh",
    "MissingExternalTool",
    "UpstreamRateLimited",
    "UpstreamUnavailable",
    # Capability manifest (v0.89.0 W-C; agent-facing introspection)
    "build_manifest",
    "describe_manifest",
]


def __getattr__(name: str):
    """Lazily expose the capability-manifest helpers (PEP 562).

    `describe` pulls argparse + (lazily) the CLI parser; importing it
    eagerly at package init would slow every `import research_hub`.
    PEP 562 module __getattr__ keeps `research_hub.build_manifest`
    working as a public name while deferring the import cost to first
    access.
    """
    if name in ("build_manifest", "describe_manifest"):
        from research_hub import describe as _describe

        return getattr(_describe, name)
    raise AttributeError(f"module 'research_hub' has no attribute {name!r}")

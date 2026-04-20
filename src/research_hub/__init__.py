"""Research Hub package."""

from __future__ import annotations

import multiprocessing as _multiprocessing
import queue as _queue
import sys
import tempfile as _tempfile
import threading as _threading

__version__ = "0.53.1"


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

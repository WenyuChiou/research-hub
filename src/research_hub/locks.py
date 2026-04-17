"""Cross-platform advisory file locks.

Best-effort serialization for state files (clusters.yaml, dedup_index.json)
that may be touched by concurrent research-hub processes — for example,
a long-running dashboard server while the CLI ingests papers in another
terminal. Does not protect against processes that ignore locks.

Usage:
    from research_hub.locks import file_lock
    with file_lock(target_path):
        target_path.write_text(...)

The lock file lives at `<target>.lock` and is created lazily.
"""

from __future__ import annotations

import contextlib
import sys
import time
from pathlib import Path

if sys.platform.startswith("win"):
    import msvcrt

    @contextlib.contextmanager
    def file_lock(path: Path | str, *, timeout: float = 30.0):
        lock_path = Path(str(path) + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.touch(exist_ok=True)
        deadline = time.monotonic() + timeout
        with open(lock_path, "r+b") as fh:
            while True:
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise TimeoutError(
                            f"could not acquire {lock_path} within {timeout}s"
                        )
                    time.sleep(0.1)
            try:
                yield
            finally:
                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
else:
    import fcntl

    @contextlib.contextmanager
    def file_lock(path: Path | str, *, timeout: float = 30.0):
        lock_path = Path(str(path) + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.touch(exist_ok=True)
        deadline = time.monotonic() + timeout
        with open(lock_path, "r+b") as fh:
            while True:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        raise TimeoutError(
                            f"could not acquire {lock_path} within {timeout}s"
                        )
                    time.sleep(0.1)
            try:
                yield
            finally:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass


__all__ = ["file_lock"]

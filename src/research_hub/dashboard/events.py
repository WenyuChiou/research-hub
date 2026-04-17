"""Server-Sent Events broadcaster + mtime-based vault change watcher."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from queue import Empty, Full, Queue


class EventBroadcaster:
    def __init__(self, maxsize: int = 100, *, drop_oldest_on_full: bool = False) -> None:
        self._clients: list[Queue] = []
        self._lock = threading.Lock()
        self.maxsize = maxsize
        self.drop_oldest_on_full = drop_oldest_on_full

    def subscribe(self) -> Queue:
        queue: Queue = Queue(maxsize=self.maxsize)
        with self._lock:
            self._clients.append(queue)
        return queue

    def unsubscribe(self, queue: Queue) -> None:
        with self._lock:
            if queue in self._clients:
                self._clients.remove(queue)

    def broadcast(self, event: dict) -> None:
        dead: list[Queue] = []
        with self._lock:
            clients = list(self._clients)
        for queue in clients:
            try:
                queue.put_nowait(event)
            except Full:
                if not self.drop_oldest_on_full:
                    dead.append(queue)
                    continue
                try:
                    queue.get_nowait()
                except Empty:
                    pass
                try:
                    queue.put_nowait(event)
                except Full:
                    dead.append(queue)
            except Exception:
                dead.append(queue)
        if dead:
            with self._lock:
                for queue in dead:
                    if queue in self._clients:
                        self._clients.remove(queue)


class VaultWatcher(threading.Thread):
    """Poll vault mtimes and broadcast `vault_changed` on drift."""

    def __init__(self, cfg, broadcaster: EventBroadcaster, interval_sec: float = 5.0):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.broadcaster = broadcaster
        self.interval = interval_sec
        self._stop_flag = threading.Event()
        self._last_sig: tuple = ()

    def stop(self) -> None:
        self._stop_flag.set()

    def _compute_signature(self) -> tuple:
        root = Path(self.cfg.root)
        mtimes: list[float] = []
        for rel in (
            ".research_hub/clusters.yaml",
            ".research_hub/dedup_index.json",
            ".research_hub/manifest.jsonl",
        ):
            path = root / rel
            if path.exists():
                try:
                    mtimes.append(path.stat().st_mtime)
                except OSError:
                    continue
        raw = root / "raw"
        if raw.exists():
            try:
                for child in raw.iterdir():
                    if child.is_dir():
                        mtimes.append(child.stat().st_mtime)
            except OSError:
                pass
        return tuple(sorted(mtimes))

    def run(self) -> None:
        self._last_sig = self._compute_signature()
        while not self._stop_flag.wait(self.interval):
            sig = self._compute_signature()
            if sig != self._last_sig:
                self._last_sig = sig
                self.broadcaster.broadcast(
                    {
                        "type": "vault_changed",
                        "timestamp": time.time(),
                    }
                )

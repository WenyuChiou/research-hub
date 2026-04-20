"""Minimal in-memory async job queue for REST API endpoints."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import threading
import traceback
import uuid


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


class JobQueue:
    """Thread-per-job queue with best-effort in-memory retention."""

    def __init__(self, *, ttl_seconds: int = 3600) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def enqueue(self, fn, *args, **kwargs) -> str:
        self._purge_expired()
        job_id = uuid.uuid4().hex
        started_at = _utc_now()
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "status": "running",
                "started_at": _isoformat(started_at),
                "completed_at": None,
                "result": None,
                "error": None,
            }

        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, fn, args, kwargs),
            daemon=True,
        )
        thread.start()
        return job_id

    def get(self, job_id: str) -> dict | None:
        self._purge_expired()
        with self._lock:
            snapshot = self._jobs.get(job_id)
            if snapshot is None:
                return None
            return deepcopy(snapshot)

    def _run_job(self, job_id: str, fn, args: tuple, kwargs: dict) -> None:
        try:
            result = fn(*args, **kwargs)
        except Exception:
            error = {
                "message": "The job failed while processing the request.",
                "code": "internal_error",
                "traceback": traceback.format_exc(),
            }
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job["status"] = "failed"
                job["completed_at"] = _isoformat(_utc_now())
                job["error"] = error["message"]
                job["_traceback"] = error["traceback"]
            return

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job["status"] = "completed"
            job["completed_at"] = _isoformat(_utc_now())
            job["result"] = result

    def _purge_expired(self) -> None:
        cutoff = _utc_now() - self._ttl
        with self._lock:
            expired = []
            for job_id, job in self._jobs.items():
                completed_at = job.get("completed_at")
                if not completed_at:
                    continue
                try:
                    completed_dt = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
                except ValueError:
                    expired.append(job_id)
                    continue
                if completed_dt < cutoff:
                    expired.append(job_id)
            for job_id in expired:
                self._jobs.pop(job_id, None)


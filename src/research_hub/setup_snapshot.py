"""Minimal saved setup observations, never a live readiness authority."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat

from research_hub.workspace.core import WorkspaceError, atomic_json, safe_path

SCHEMA_VERSION = 1
SOURCE = "setup_autonomous"
RELATIVE_PATH = ".research_hub/setup-snapshot.json"
MAX_BYTES = 8192
# UI display policy, NOT a guarantee that credentials/capabilities remain valid.
DISPLAY_MAX_AGE_SECONDS = 86400
COMPONENTS = ("environment", "vault", "zotero", "notebooklm_auth", "llm_cli", "skills")
STATUSES = frozenset({"passed", "failed", "cancelled", "skipped", "unknown"})


def snapshot_root(value: str | Path) -> Path:
    if not str(value).strip() or str(value).startswith(("\\\\", "//")):
        raise WorkspaceError("Snapshot requires an explicit local directory root", "unsafe_path")
    original = Path(value).expanduser().absolute()
    # Check ancestors as well as the root itself before resolving it.
    root = safe_path(Path(original.anchor), original)
    if not root.is_dir():
        raise WorkspaceError("Snapshot requires an existing directory root", "unsafe_path")
    return root


def save_setup_snapshot(root: str | Path, report, *, observed_at: datetime | None = None) -> None:
    root = snapshot_root(root)
    path = safe_path(root, RELATIVE_PATH)
    timestamp = observed_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Snapshot timestamp must include a timezone")
    components = {}
    for name in COMPONENTS:
        status = report.components.get(name, {}).get("status", "unknown")
        components[name] = status if isinstance(status, str) and status in STATUSES else "unknown"
    payload = {"schema_version": SCHEMA_VERSION, "source": SOURCE,
               "observed_at": timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
               "components": components}
    # Existing repository atomic replacement primitive; no destination chosen by report data.
    path.parent.mkdir(parents=True, exist_ok=True)
    path = safe_path(root, RELATIVE_PATH)
    atomic_json(path, payload)


def read_setup_snapshot(root: str | Path, *, observed_now: datetime | None = None) -> dict:
    """Read only an allowlisted, bounded local snapshot. No probes and no writes."""
    result = {"schema_version": SCHEMA_VERSION, "source": "saved_local_setup_snapshot",
              "current_status": "unknown", "freshness": "missing", "observed_at": None,
              "age_seconds": None, "display_max_age_seconds": DISPLAY_MAX_AGE_SECONDS,
              "components": {name: "unknown" for name in COMPONENTS}}
    try:
        path = safe_path(snapshot_root(root), RELATIVE_PATH)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES:
            result["freshness"] = "invalid"
            return result
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                raise ValueError("Snapshot changed during open")
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Oversized snapshot")
        payload = json.loads(raw)
        if (not isinstance(payload, dict) or set(payload) != {"schema_version", "source", "observed_at", "components"}
                or type(payload["schema_version"]) is not int or payload["schema_version"] != SCHEMA_VERSION
                or payload["source"] != SOURCE or not isinstance(payload["observed_at"], str)
                or not isinstance(payload["components"], dict) or set(payload["components"]) != set(COMPONENTS)
                or any(not isinstance(v, str) or v not in STATUSES for v in payload["components"].values())):
            raise ValueError("Invalid snapshot schema")
        timestamp = datetime.fromisoformat(payload["observed_at"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Missing timezone")
        now = observed_now or datetime.now(timezone.utc)
        age = (now - timestamp).total_seconds()
        if age < 0:
            result["freshness"] = "clock_skew"
            return result
        result.update(observed_at=timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                      age_seconds=int(age), freshness="stale" if age > DISPLAY_MAX_AGE_SECONDS else "saved")
        if result["freshness"] == "saved":
            result["components"] = dict(payload["components"])
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        result["freshness"] = "invalid"
    return result

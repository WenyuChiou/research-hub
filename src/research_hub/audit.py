"""Internal audit instrumentation; the documented CLI/files are the public API.

No global HTTP monkeypatching. Contexts are copied explicitly into search
workers, and every attempt is registered before its action starts.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
from pathlib import Path
import re
from threading import RLock
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4
import xml.etree.ElementTree as ET

import requests

VERSION = "1.0.0"
GOOD = {"success", "success_empty"}
_CURRENT: ContextVar[Attempt | None] = ContextVar("research_hub_audit", default=None)
_SECRET = re.compile(
    r"(?:key|token|secret|password|authorization|cookie|mailto|email)", re.I
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _jsonable(value):
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported audit value type: {type(value).__name__}")


def _safe(value):
    if isinstance(value, dict):
        return {
            str(k): "[redacted]" if _SECRET.search(str(k)) else _safe(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        url = urlsplit(value)
        host = url.netloc.rsplit("@", 1)[-1]
        query = [
            (k, "[redacted]" if _SECRET.search(k) else v)
            for k, v in parse_qsl(url.query, keep_blank_values=True)
        ]
        return urlunsplit((url.scheme, host, url.path, urlencode(query), ""))
    return _jsonable(value)


def _error_outcome(error):
    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        return "cancelled"
    if isinstance(error, requests.Timeout):
        return "timeout"
    if isinstance(error, (ValueError, ET.ParseError)):
        return "parse_error"
    if isinstance(error, requests.RequestException):
        return "network_error"
    return "error"


class _Store:
    def __init__(self, directory):
        self.path = Path(directory)
        self.path.mkdir(parents=True, exist_ok=False)
        (self.path / "artifacts").mkdir()
        self.lock = RLock()
        self.sequence = 0
        self.open = {}
        self.closed = False
        self.failed = False
        self.events = self.path / "events.jsonl"
        self.events.touch(exist_ok=False)

    def write(self, event):
        with self.lock:
            if self.closed:
                return
            sequence = self.sequence + 1
            event = {
                "schema_version": VERSION,
                "type": "audit_event",
                "sequence": sequence,
                **event,
            }
            try:
                with self.events.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(
                        json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n"
                    )
                    stream.flush()
            except (OSError, ValueError):
                self.failed = True
                raise
            self.sequence = sequence

    def artifact(self, data, suffix="json"):
        with self.lock:
            if self.closed:
                return None
            name = f"artifacts/{uuid4().hex}.{suffix}"
            try:
                with (self.path / name).open("xb") as stream:
                    stream.write(data)
            except OSError:
                self.failed = True
                raise
            return {
                "path": name,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }


class Attempt:
    def __init__(
        self, operation, backend=None, parameters=None, evidence=None, store=None
    ):
        self.parent = _CURRENT.get()
        self.store = store or (self.parent.store if self.parent else None)
        self.id = uuid4().hex
        self.operation = operation
        self.backend = backend
        self.parameters = _safe(parameters or {})
        self.evidence = evidence
        self.artifacts = []
        self.children = []
        self.count = None
        self.outcome = None
        self.error = None
        self.http_status = None
        self.exit_code = None
        self.transport = False
        self.parsed = False
        self.finished = False

    def __enter__(self):
        self.token = _CURRENT.set(self if self.store else None)
        try:
            if self.store:
                with self.store.lock:
                    if not self.store.closed:
                        self.store.open[self.id] = self
                        self._emit("started")
        except BaseException:
            if self.store:
                with self.store.lock:
                    self.store.open.pop(self.id, None)
            _CURRENT.reset(self.token)
            raise
        return self

    def _emit(self, event):
        self.store.write(
            {
                "event": event,
                "attempt_id": self.id,
                "parent_id": self.parent.id if self.parent else None,
                "operation": self.operation,
                "backend": self.backend,
                "timestamp": _now(),
                "parameters": self.parameters,
                "outcome": self.outcome,
                "error_code": self.error,
                "http_status": self.http_status,
                "record_count": self.count,
                "artifacts": list(self.artifacts),
            }
        )

    def result(self, value):
        if self.store:
            value = _jsonable(value)
            data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode(
                "utf-8"
            )
            ref = self.store.artifact(data)
            if ref:
                self.artifacts.append(ref)
            self.count = (
                len(value) if isinstance(value, list) else (0 if value is None else 1)
            )

    def observed(self, kind):
        node = self
        while node:
            setattr(node, kind, True)
            node = node.parent

    def finish(self, error=None):
        if not self.store or self.finished:
            return
        with self.store.lock:
            if self.store.closed or self.finished:
                return
            if error:
                self.outcome = _error_outcome(error)
                self.error = type(error).__name__
            if self.outcome is None:
                failures = [
                    child for child in self.children if child.outcome not in GOOD
                ]
                if failures:
                    useful = bool(self.count) or any(
                        c.outcome in GOOD and c.operation not in {"http", "parse"}
                        for c in self.children
                    )
                    self.outcome = "partial" if useful else failures[0].outcome
                    self.error = "child_attempt_failed"
                elif self.evidence and (
                    not self.transport
                    or (self.evidence == "parsed" and not self.parsed)
                ):
                    self.outcome = "unknown"
                    self.error = "successful_response_or_parse_not_observed"
                elif self.evidence == "parsed" and self.count == 0:
                    self.outcome = "success_empty"
                else:
                    self.outcome = "success"
            self.finished = True
            self._emit("finished")
            self.store.open.pop(self.id, None)
            if self.parent:
                self.parent.children.append(self)

    def __exit__(self, kind, error, traceback):
        try:
            self.finish(error)
        finally:
            _CURRENT.reset(self.token)


@contextmanager
def audit_command(directory, argv):
    if directory is None:
        yield Attempt("command")
        return
    if _CURRENT.get() is not None:
        raise RuntimeError("Nested audit commands are not supported")
    store = _Store(directory)
    command = Attempt("command", parameters={"argv": argv}, store=store)
    try:
        with command:
            try:
                yield command
            except BaseException as error:
                command.exit_code = 130 if isinstance(error, KeyboardInterrupt) else 1
                raise
            finally:
                # Timed-out worker threads can finish later. Close their recorded
                # attempts now; late completions cannot rewrite this audit.
                with store.lock:
                    for pending in reversed(list(store.open.values())):
                        if pending is not command:
                            pending.outcome = "cancelled"
                            pending.error = "command_ended_before_attempt"
                            pending.finish()
                if store.failed:
                    command.exit_code = 1
                    command.outcome = "error"
                    command.error = "audit_write_failed"
                if command.exit_code not in (None, 0) and command.outcome is None:
                    command.outcome = "error"
                    command.error = "nonzero_exit"
    finally:
        with store.lock:
            if store.failed:
                command.exit_code = 1
                command.outcome = "error"
                command.error = "audit_write_failed"
            store.closed = True
            events = store.events.read_bytes()
            manifest = {
                "schema_version": VERSION,
                "type": "audit_manifest",
                "created_at": _now(),
                "command_id": command.id,
                "complete": not store.failed and command.finished,
                "outcome": command.outcome,
                "exit_code": command.exit_code,
                "event_count": store.sequence,
                "events": {
                    "path": "events.jsonl",
                    "bytes": len(events),
                    "sha256": hashlib.sha256(events).hexdigest(),
                },
            }
            with (store.path / "audit_manifest.json").open(
                "x", encoding="utf-8"
            ) as stream:
                json.dump(
                    manifest, stream, ensure_ascii=False, indent=2, allow_nan=False
                )
            if store.failed:
                raise OSError("Audit output could not be completely persisted")


def audit_call(operation, function, *args, backend=None, evidence=None, **kwargs):
    if _CURRENT.get() is None:
        return function(*args, **kwargs)
    # Sessions/caches are runtime dependencies, never serializable credentials.
    parameters = {
        "args": args,
        "kwargs": {k: v for k, v in kwargs.items() if k not in {"session", "cache"}},
    }
    with Attempt(operation, backend, parameters, evidence) as attempt:
        result = function(*args, **kwargs)
        attempt.result(result)
        return result


def audited(operation, *, backend=None, evidence=None):
    def decorate(function):
        @wraps(function)
        def run(*args, **kwargs):
            return audit_call(
                operation, function, *args, backend=backend, evidence=evidence, **kwargs
            )

        return run

    return decorate


def http_request(method, url, *, client=None, **kwargs):
    request = getattr(client or requests, method.lower())
    if _CURRENT.get() is None:
        return request(url, **kwargs)
    if _CURRENT.get().store.closed:
        raise RuntimeError("Audit session closed; further requests are cancelled")
    # Headers/cookies/auth are deliberately excluded. No credential is persisted.
    params = {
        "method": method.upper(),
        "url": url,
        **{
            k: kwargs[k]
            for k in ("params", "json", "data", "timeout", "allow_redirects")
            if k in kwargs
        },
    }
    with Attempt("http", parameters=params) as attempt:
        response = request(url, **kwargs)
        attempt.http_status = int(response.status_code)
        attempt.parameters["resolved_url"] = _safe(getattr(response, "url", url) or url)
        headers = getattr(response, "headers", {})
        attempt.parameters["response_headers"] = {
            key: headers[key]
            for key in ("Content-Type", "Retry-After")
            if key in headers
        }
        history = getattr(response, "history", [])
        attempt.parameters["redirects"] = (
            [
                {"url": _safe(item.url), "status": item.status_code}
                for item in history
                if isinstance(item, requests.Response)
            ]
            if isinstance(history, list)
            else []
        )
        body = getattr(response, "content", b"")
        if isinstance(body, bytes):
            ref = attempt.store.artifact(body, "bin")
            if ref:
                attempt.artifacts.append(ref)
        status = attempt.http_status
        if 200 <= status < 300:
            attempt.outcome = "success"
            attempt.observed("transport")
        else:
            attempt.outcome = {
                404: "not_found",
                410: "not_found",
                429: "rate_limited",
            }.get(status, "http_error")
            attempt.error = f"http_{status}"
        return response


def read_json(
    response, *, collection=None, collections=None, allow_single=False, empty_count=None
):
    if _CURRENT.get() is None:
        return response.json()
    with Attempt(
        "parse", parameters={"format": "json", "collection": collection}
    ) as attempt:
        payload = response.json()
        paths = [collection] if collection is not None else collections
        if paths:
            found = False
            for path in paths:
                node = payload
                for key in path:
                    if not isinstance(node, dict) or key not in node:
                        break
                    node = node[key]
                else:
                    if not isinstance(node, list) and not (
                        allow_single and isinstance(node, dict)
                    ):
                        raise ValueError("Expected a response list")
                    found = True
                    break
            if not found:
                count = payload
                for part in empty_count or ():
                    count = count.get(part) if isinstance(count, dict) else None
                if not empty_count or count not in (0, "0"):
                    raise ValueError("Missing expected response collection")
        elif not isinstance(payload, (dict, list)):
            raise ValueError("Expected a JSON object or list")
        attempt.observed("parsed")
        return payload


def read_xml(text, *, root_tag=None):
    if _CURRENT.get() is None:
        return ET.fromstring(text)
    with Attempt(
        "parse", parameters={"format": "xml", "root_tag": root_tag}
    ) as attempt:
        root = ET.fromstring(text)
        if root_tag is not None and root.tag != root_tag:
            raise ET.ParseError("Unexpected response root element")
        attempt.observed("parsed")
        return root

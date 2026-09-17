"""Stable audit-file contract and failure semantics (synthetic, offline)."""

import hashlib
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import Event

import pytest
import requests
import responses
from jsonschema import Draft202012Validator, FormatChecker

from research_hub.audit import audit_command, audit_call, http_request, read_json
from research_hub.audit import Attempt


def records(directory):
    return [
        json.loads(line)
        for line in (directory / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]


def lookup():
    response = http_request("get", "https://example.invalid/works")
    if response.status_code != 200:
        return []  # Mirror a legacy backend which swallows HTTP failures.
    return read_json(response, collection=("results",))["results"]


@responses.activate
@pytest.mark.parametrize(
    "status,payload,outcome",
    [
        (200, {"results": []}, "success_empty"),
        (200, {"results": [{"title": "Synthetic record"}]}, "success"),
        (404, {}, "not_found"),
        (429, {}, "rate_limited"),
        (503, {}, "http_error"),
    ],
)
def test_backend_outcomes_and_raw_artifacts(tmp_path, status, payload, outcome):
    directory = tmp_path / "audit"
    responses.get("https://example.invalid/works", json=payload, status=status)
    with audit_command(directory, ["search", "synthetic question"]) as command:
        audit_call("backend-search", lookup, backend="synthetic", evidence="parsed")
        command.exit_code = 0
    events = records(directory)
    backend = next(
        e
        for e in events
        if e["event"] == "finished" and e["operation"] == "backend-search"
    )
    assert backend["outcome"] == outcome
    assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
    started = {e["attempt_id"] for e in events if e["event"] == "started"}
    assert all(e["parent_id"] is None or e["parent_id"] in started for e in events)
    for event in events:
        for artifact in event["artifacts"]:
            data = (directory / artifact["path"]).read_bytes()
            assert len(data) == artifact["bytes"]
            assert hashlib.sha256(data).hexdigest() == artifact["sha256"]
    schema = json.loads(
        (
            Path(__file__).parents[1] / "src/research_hub/schemas/audit-v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for event in events:
        validator.validate(event)
    manifest = json.loads((directory / "audit_manifest.json").read_text())
    validator.validate(manifest)
    assert manifest["exit_code"] == 0
    assert manifest["complete"] is True
    with pytest.raises(Exception):
        validator.validate({**events[0], "schema_version": "99.0.0"})


@responses.activate
def test_parse_failure_survives_legacy_catch(tmp_path):
    responses.get("https://example.invalid/works", json={"wrong": []})

    def swallowed():
        try:
            return lookup()
        except ValueError:
            return []

    with audit_command(tmp_path / "audit", ["search"]) as command:
        audit_call("backend-search", swallowed, backend="synthetic", evidence="parsed")
        command.exit_code = 0
    assert any(
        e.get("outcome") == "parse_error" and e["operation"] == "backend-search"
        for e in records(tmp_path / "audit")
    )


@responses.activate
def test_timeout_cannot_become_success_empty(tmp_path):
    responses.get("https://example.invalid/works", body=requests.Timeout("timeout"))

    def swallowed():
        try:
            return lookup()
        except requests.RequestException:
            return []

    with audit_command(tmp_path / "audit", ["search"]) as command:
        audit_call("backend-search", swallowed, backend="synthetic", evidence="parsed")
        command.exit_code = 0
    assert any(
        e.get("outcome") == "timeout" and e["operation"] == "backend-search"
        for e in records(tmp_path / "audit")
    )


def test_unobserved_empty_is_unknown_and_directory_is_never_reused(tmp_path):
    directory = tmp_path / "audit"
    with audit_command(directory, ["search"]) as command:
        audit_call("backend-search", lambda: [], backend="opaque", evidence="parsed")
        command.exit_code = 0
    before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    assert any(e.get("outcome") == "unknown" for e in records(directory))
    with pytest.raises(FileExistsError):
        with audit_command(directory, ["search"]):
            pass
    assert before == {
        p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()
    }


def test_interruption_is_preserved_and_redaction_does_not_capture_headers(tmp_path):
    directory = tmp_path / "audit"
    with pytest.raises(KeyboardInterrupt):
        with audit_command(directory, ["search", "synthetic"]):
            raise KeyboardInterrupt()
    events = records(directory)
    assert events[-1]["outcome"] == "cancelled"
    manifest = json.loads((directory / "audit_manifest.json").read_text())
    assert manifest["exit_code"] == 130
    assert manifest["outcome"] == "cancelled"


@responses.activate
def test_credentials_not_saved_in_request_parameters(tmp_path):
    responses.get("https://example.invalid/works", json={"results": []})
    directory = tmp_path / "audit"
    with audit_command(directory, ["search", "synthetic"]) as command:
        response = http_request(
            "get",
            "https://example.invalid/works",
            params={"api_key": "synthetic-secret-value", "query": "ordinary query"},
            headers={"Authorization": "secret-header-value"},
        )
        read_json(response, collection=("results",))
        command.exit_code = 0
    text = (directory / "events.jsonl").read_text()
    assert "synthetic-secret-value" not in text
    assert "secret-header-value" not in text
    assert "ordinary query" in text and "[redacted]" in text


def test_late_worker_cannot_rewrite_closed_audit(tmp_path):
    entered, release = Event(), Event()
    directory = tmp_path / "audit"

    def worker():
        with Attempt("backend-search", "synthetic", evidence="parsed") as attempt:
            entered.set()
            assert release.wait(5)
            attempt.result([])

    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            with audit_command(directory, ["search"]) as command:
                future = executor.submit(copy_context().run, worker)
                assert entered.wait(5)
                command.exit_code = 0
            before = (directory / "events.jsonl").read_bytes()
        finally:
            release.set()
        future.result(timeout=5)
    assert (directory / "events.jsonl").read_bytes() == before
    endings = [e for e in records(directory) if e["event"] == "finished"]
    assert endings[0]["operation"] == "backend-search"
    assert endings[0]["outcome"] == "cancelled"
    assert endings[-1]["outcome"] == "cancelled"

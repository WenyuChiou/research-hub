"""Synthetic post-commit preview failure; no network or provider calls."""
import base64
from contextlib import contextmanager
import sqlite3
import uuid

import pytest

from research_hub.workspace.service import WorkspaceService, call_workspace
from research_hub.workspace import text_intake


@pytest.mark.skipif(not text_intake.publication_supported(), reason="Requires native no-follow publication")
@pytest.mark.parametrize("operation", ["save", "lookup", "replay"])
def test_saved_intake_survives_transient_preview_ledger_error(tmp_path, monkeypatch, operation):
    service = WorkspaceService(tmp_path)
    ws = service.workspace
    ws.create_project(id="paper", title="Synthetic preview recovery")
    raw = "Synthetic abstract\r\n研究😀\r\n".encode("utf-8")
    identity = {"version": 1, "workspace_instance_id": ws.preparation_namespace(), "key": str(uuid.uuid4())}
    payload = {"project_id": "paper", "intake_request": identity, "title": "Synthetic source",
               "reading_scope": "unknown", "input_kind": "file", "format": "md",
               "content_base64": base64.b64encode(raw).decode("ascii")}
    if operation != "save":
        assert call_workspace(tmp_path, "project", "source_text", payload, _service=service)["ok"]
    original_reader = text_intake.read_selected_text
    real_db = ws.db

    @contextmanager
    def blocked_db(*, write=False):
        raise sqlite3.OperationalError("synthetic private database detail")
        yield  # pragma: no cover

    def unavailable_preview(*args, **kwargs):
        # Fail the actual reader's DB access only after save/lookup obtained the pair.
        with monkeypatch.context() as scoped:
            scoped.setattr(ws, "db", blocked_db)
            return original_reader(*args, **kwargs)

    monkeypatch.setattr(text_intake, "read_selected_text", unavailable_preview)
    if operation == "lookup":
        result = call_workspace(tmp_path, "project", "source_text_lookup", {
            "project_id": "paper", "workspace_instance_id": identity["workspace_instance_id"], "key": identity["key"]}, _service=service)
    else:
        result = call_workspace(tmp_path, "project", "source_text", payload, _service=service)
    # Even on the faulty baseline, the complete pair and original bytes remain.
    with real_db() as db:
        assert db.execute("SELECT count(*) FROM records").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM artifacts").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0
    copies = list((ws.root / "hub-sources").rglob("*.md"))
    assert len(copies) == 1 and copies[0].read_bytes() == raw
    inode = copies[0].stat().st_ino
    assert result["ok"], result
    assert result["preview"] is None and result["preview_status"] == "unavailable"
    assert result["artifact"]["current"] is False
    assert "private database detail" not in str(result)
    assert result["intake"].get("state", result["intake"].get("disposition")) == {
        "save": "created", "lookup": "found", "replay": "existing"}[operation]
    monkeypatch.setattr(text_intake, "read_selected_text", original_reader)
    recovered = call_workspace(tmp_path, "project", "source_text", payload, _service=service)
    assert recovered["ok"] and recovered["intake"]["disposition"] == "existing"
    assert recovered["preview_status"] == "available" and recovered["artifact"]["current"]
    assert recovered["record"]["id"] == result["record"]["id"]
    assert recovered["artifact"]["id"] == result["artifact"]["id"]
    assert recovered["preview"]["text"].encode("utf-8") == raw
    assert copies[0].stat().st_ino == inode
    assert len(ws.records("paper")) == len(ws.artifacts("paper")) == 1


@pytest.mark.skipif(not text_intake.publication_supported(), reason="Requires native no-follow publication")
@pytest.mark.parametrize("stage", ["before_commit", "lookup"])
def test_ledger_failure_outside_preview_is_not_saved_success(tmp_path, monkeypatch, stage):
    service = WorkspaceService(tmp_path)
    ws = service.workspace
    ws.create_project(id="paper", title="Synthetic ledger failure")
    identity = {"version": 1, "workspace_instance_id": ws.preparation_namespace(), "key": str(uuid.uuid4())}
    payload = {"project_id": "paper", "intake_request": identity, "title": "Synthetic source",
               "reading_scope": "unknown", "input_kind": "paste", "format": "txt",
               "content_base64": base64.b64encode(b"Synthetic abstract").decode("ascii")}
    real_db = ws.db
    if stage == "lookup":
        assert call_workspace(tmp_path, "project", "source_text", payload, _service=service)["ok"]
        monkeypatch.setattr(text_intake.TextIntake, "_lookup",
                            lambda *_a, **_k: (_ for _ in ()).throw(sqlite3.OperationalError("synthetic lookup failure")))
    else:
        @contextmanager
        def fail_commit(*, write=False):
            with real_db(write=write) as db:
                yield db
                if write:
                    assert db.execute("SELECT count(*) FROM records").fetchone()[0] == 1
                    raise sqlite3.OperationalError("synthetic commit failure")
        monkeypatch.setattr(ws, "db", fail_commit)
    result = call_workspace(tmp_path, "project", "source_text", payload, _service=service)
    assert result["ok"] is False and result["code"] == "ledger_unavailable"
    assert "record" not in result and "preview" not in result
    with real_db() as db:
        expected = 1 if stage == "lookup" else 0
        assert db.execute("SELECT count(*) FROM records").fetchone()[0] == expected
        assert db.execute("SELECT count(*) FROM artifacts").fetchone()[0] == expected
    copies = list((ws.root / "hub-sources").rglob("*.txt"))
    assert len(copies) == 1 and copies[0].read_bytes() == b"Synthetic abstract"

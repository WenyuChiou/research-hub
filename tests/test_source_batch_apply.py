"""Actual SQLite native batch save/retry; synthetic project data only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import argparse
import io
import json
import sqlite3
import threading
from contextlib import redirect_stdout
from unittest.mock import patch

import pytest

from research_hub.workspace.core import Workspace, WorkspaceError, encoded
from research_hub.workspace.cli import add_workspace_parsers, dispatch_workspace


def sources(count=20):
    return [{"batch_id": "synthetic-native-batch", "id": f"source-{i}",
             "title": f"Synthetic source {i}", "locator": f"https://example.invalid/{i}",
             "identity_status": "unverified", "human_acceptance": "pending",
             "reading_level": "abstract-snippet" if i == 19 else "abstract",
             "reading_scope": "abstract-snippet" if i == 19 else "abstract",
             "version": None, "prior_batch_matches": []} for i in range(count)]


@pytest.fixture
def ws(tmp_path):
    workspace = Workspace(tmp_path)
    workspace.create_project(id="selected", title="Synthetic native batch")
    return workspace


def apply(ws, data):
    return ws.save_source_batch("selected", kind="source", data=data)


def test_real_save_replay_reuses_all_ids_and_original_timestamps(ws):
    data = sources()
    before = deepcopy(data)
    first = apply(ws, data)
    saved = ws.records("selected")
    with ws.db() as db:
        stored_bytes = [tuple(row) for row in db.execute("SELECT id,body FROM records ORDER BY rowid")]
    second = apply(ws, data)
    assert first["ok"] and second["ok"]
    assert first["batch"]["counts"] == {"created": 20, "reused": 0, "conflicts": 0}
    assert second["batch"]["counts"] == {"created": 0, "reused": 20, "conflicts": 0}
    assert first["batch"]["records"] == second["batch"]["records"] == saved
    assert all(r["data"]["recorded_at"].endswith("Z") for r in saved)
    assert ws.records("selected") == saved and data == before
    with ws.db() as db:
        assert [tuple(row) for row in db.execute("SELECT id,body FROM records ORDER BY rowid")] == stored_bytes


def test_ordinary_save_then_batch_retry_understands_only_core_timestamp(ws):
    data = sources(1)
    saved = ws.add_record("selected", kind="source", data=data[0])
    result = apply(ws, data)
    assert result["ok"] and result["batch"]["records"] == [saved]
    assert result["batch"]["counts"]["reused"] == 1


@pytest.mark.parametrize("field,value", [("summary", "changed generated prose"),
    ("version", "different version"), ("observed_at", "2026-11-01T21:00:00Z"),
    ("reading_scope", "full-text"), ("source_records", [{"evidence_level": "generated-summary"}])])
def test_conflict_preserves_manual_content_and_blocks_other_creates(ws, field, value):
    data = sources(1)
    data[0]["summary"] = "Manual summary"
    ws.add_record("selected", kind="source", data=data[0])
    before = ws.records("selected")
    incoming = deepcopy(data)
    incoming[0][field] = value
    incoming.append(sources(2)[1])
    result = apply(ws, incoming)
    assert not result["ok"] and result["code"] == "conflict"
    assert result["batch"]["counts"]["created"] == 0
    assert ws.records("selected") == before


@pytest.mark.parametrize("stamp", [None, "not-a-timestamp", "2026-11-01",
    "2026-11-01T00:00:00+00:00", "2026-11-01T00:00:00+02:00",
    "2026-11-01 00:00:00Z", "2026-11-01T00:00:00.1Z"])
def test_unknown_legacy_storage_timestamp_conflicts_without_rewrite(ws, stamp):
    data = sources(1)
    saved = ws.add_record("selected", kind="source", data=data[0])
    legacy = saved["data"]
    if stamp is None:
        legacy.pop("recorded_at")
    else:
        legacy["recorded_at"] = stamp
    with ws.db(write=True) as db:
        db.execute("UPDATE records SET body=? WHERE id=?", (encoded(legacy), saved["id"]))
    before = ws.records("selected")
    assert apply(ws, data)["code"] == "conflict"
    assert ws.records("selected") == before


def test_duplicate_input_or_existing_key_never_creates_extra_records(ws):
    data = sources(1)
    assert not apply(ws, data * 2)["ok"]
    assert ws.records("selected") == []
    ws.add_record("selected", kind="source", data=data[0])
    ws.add_record("selected", kind="source", data=data[0])
    before = ws.records("selected")
    assert not apply(ws, data)["ok"]
    assert ws.records("selected") == before


@pytest.mark.parametrize("field,value", [("id", "source-0"), ("summary", "Manual summary")])
def test_duplicate_stored_json_keys_block_mixed_create_and_preserve_sql_bytes(ws, field, value):
    data = sources(1)
    data[0]["summary"] = "Manual summary"
    saved = ws.add_record("selected", kind="source", data=data[0])
    raw = encoded(saved["data"])
    ambiguous = raw[:-1] + "," + json.dumps(field) + ":" + json.dumps(value) + "}"
    with ws.db(write=True) as db:
        db.execute("UPDATE records SET body=? WHERE id=?", (ambiguous, saved["id"]))
    with pytest.raises(WorkspaceError) as rejected:
        apply(ws, data + [sources(2)[1]])
    assert rejected.value.code == "conflict"
    with ws.db() as db:
        assert [tuple(row) for row in db.execute("SELECT id,body FROM records")] == [(saved["id"], ambiguous)]


def test_failure_after_one_insert_rolls_back_entire_batch(ws, monkeypatch):
    original = ws.db
    inserted = []
    class Connection:
        def __init__(self, db): self.db = db
        def execute(self, statement, params=()):
            if statement.startswith("INSERT INTO records"):
                if inserted:
                    raise sqlite3.OperationalError("Synthetic insert failure")
                inserted.append(True)
            return self.db.execute(statement, params)
    @contextmanager
    def observed(*, write=False):
        with original(write=write) as db:
            yield Connection(db)
    monkeypatch.setattr(ws, "db", observed)
    with pytest.raises(sqlite3.OperationalError):
        apply(ws, sources(2))
    assert inserted == [True] and ws.records("selected") == []


def test_two_competing_transactions_create_only_one_batch(ws):
    barrier = threading.Barrier(2)
    def worker():
        own = Workspace(ws.root)
        barrier.wait(timeout=5)
        return apply(own, sources())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert all(r["ok"] for r in results)
    assert sorted(r["batch"]["counts"]["created"] for r in results) == [0, 20]
    assert results[0]["batch"]["records"] == results[1]["batch"]["records"]
    assert len(ws.records("selected")) == 20


@pytest.mark.parametrize("field,value", [("recorded_at", "2026-11-01T00:00:00Z"),
    ("identity_status", "verified"), ("human_acceptance", "accepted")])
def test_caller_cannot_supply_server_clock_or_approval_claims(ws, field, value):
    data = sources(1)
    data[0][field] = value
    before = ws.db_path.read_bytes()
    with pytest.raises(WorkspaceError):
        apply(ws, data)
    assert ws.db_path.read_bytes() == before


def test_other_project_and_legacy_unbatched_sources_are_not_reused(ws):
    ws.create_project(id="other", title="Other synthetic project")
    ws.add_record("other", kind="source", data=sources(1)[0])
    ws.add_record("selected", kind="source", data={"title": "Legacy", "locator": "fixture:legacy"})
    result = apply(ws, sources(1))
    assert result["ok"] and result["batch"]["counts"]["created"] == 1
    assert len(ws.records("selected")) == 2 and len(ws.records("other")) == 1


def test_unknown_project_never_initializes_a_new_root(tmp_path):
    root = tmp_path / "not-created"
    with pytest.raises(WorkspaceError):
        Workspace(root).save_source_batch("selected", kind="source", data=sources(1))
    assert not root.exists()


def test_project_is_rechecked_after_transaction_lock(ws, monkeypatch):
    original = ws.db
    @contextmanager
    def changed(*, write=False):
        with original(write=write) as db:
            if write:
                db.execute("DELETE FROM projects WHERE id='selected'")
            yield db
    monkeypatch.setattr(ws, "db", changed)
    with pytest.raises(WorkspaceError, match="Unknown project"):
        apply(ws, sources(1))
    assert ws.project("selected")["id"] == "selected" and ws.records("selected") == []


def test_explicit_cli_apply_and_service_use_actual_selected_workspace(ws):
    parser = argparse.ArgumentParser()
    add_workspace_parsers(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(["project", "record", "--root", str(ws.root), "--project", "selected",
        "--kind", "source", "--data", json.dumps(sources(2)), "--batch", "--apply"])
    with patch("research_hub.config.get_config", side_effect=AssertionError("No provider config")), redirect_stdout(io.StringIO()) as out:
        assert dispatch_workspace(args) == 0
    assert json.loads(out.getvalue())["batch"]["counts"]["created"] == 2


def test_apply_cannot_accept_snapshot_or_omit_explicit_batch(tmp_path):
    parser = argparse.ArgumentParser()
    add_workspace_parsers(parser.add_subparsers(dest="command", required=True))
    base = ["project", "record", "--root", str(tmp_path / "never"), "--project", "selected",
            "--kind", "source", "--data", json.dumps(sources(1)), "--apply"]
    for extra in ([], ["--batch", "--existing-records", "[]"]):
        args = parser.parse_args(base + extra)
        with patch("research_hub.workspace.cli.call_workspace", side_effect=AssertionError("No access")), redirect_stdout(io.StringIO()):
            assert dispatch_workspace(args) == 1
    with pytest.raises(SystemExit):
        parser.parse_args(base + ["--batch", "--dry-run"])
    assert not (tmp_path / "never").exists()

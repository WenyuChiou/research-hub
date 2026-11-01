"""Oversized ordinary sources must not block another batch's exact keys."""
from contextlib import contextmanager
import sqlite3

import pytest

from research_hub.workspace.core import Workspace, WorkspaceError, encoded
from research_hub.workspace.source_handoff import MAX_SOURCE_RECORD_BYTES


def source(batch="requested", local="one"):
    return {"batch_id": batch, "id": local, "title": "Synthetic source", "locator": "fixture:one"}


def sql_rows(ws):
    with ws.db() as db:
        return [tuple(row) for row in db.execute("SELECT id,body FROM records ORDER BY rowid")]


@pytest.fixture
def ws(tmp_path):
    result = Workspace(tmp_path)
    result.create_project(id="selected", title="Synthetic identity projection")
    return result


def add_large(ws, data, transform=lambda raw: raw):
    data = {**data, "padding": "x" * (MAX_SOURCE_RECORD_BYTES + 1)}
    record = ws.add_record("selected", kind="source", data=data)
    raw = transform(encoded(record["data"]))
    with ws.db(write=True) as db:
        db.execute("UPDATE records SET body=? WHERE id=?", (raw, record["id"]))
    return record


@pytest.mark.parametrize("kind", ["unbatched", "legacy-id", "other-batch", "other-id", "nested", "escaped-keys", "nul-value"])
def test_unrelated_large_source_preserves_exact_retry_and_allows_new_batch_source(ws, kind):
    original = source()
    first = ws.save_source_batch("selected", kind="source", data=[original])
    extra = {"title": "Large unrelated source", "locator": "fixture:unrelated"}
    if kind == "legacy-id":
        extra["id"] = "ordinary-legacy-id"
    elif kind in {"other-batch", "escaped-keys"}:
        extra.update(batch_id="other", id="one")
    elif kind == "other-id":
        extra.update(batch_id="requested", id="other")
    elif kind == "nested":
        extra["nested"] = source()
    elif kind == "nul-value":
        extra.update(batch_id="requested\x00other", id="one")
    transform = lambda raw: raw
    if kind == "escaped-keys":
        transform = lambda raw: raw.replace('"batch_id":', '"\\u0062atch_id":').replace('"id":', '"\\u0069d":')
    add_large(ws, extra, transform)
    before = sql_rows(ws)
    replay = ws.save_source_batch("selected", kind="source", data=[original])
    assert replay["ok"] and replay["batch"]["records"] == first["batch"]["records"]
    assert replay["batch"]["counts"]["reused"] == 1 and sql_rows(ws) == before
    created = ws.save_source_batch("selected", kind="source", data=[source(local="new")])
    assert created["ok"] and created["batch"]["counts"]["created"] == 1
    assert sql_rows(ws)[:2] == before


@pytest.mark.parametrize("fault", ["duplicate-id", "duplicate-id-same", "duplicate-batch", "escaped-duplicate-id", "malformed", "array", "nontext-batch", "matching-batch-missing-id"])
def test_ambiguous_large_identity_rejects_mixed_create_without_changing_SQL(ws, fault):
    data = source(batch="other", local="other")
    if fault == "nontext-batch":
        data["batch_id"] = 7
    if fault == "matching-batch-missing-id":
        data = source(); data.pop("id")
    def transform(raw):
        if fault == "malformed": return raw[:-1]
        if fault == "array": return "[" + raw + "]"
        if fault == "duplicate-id": return raw[:-1] + ',"id":"one"}'
        if fault == "duplicate-id-same": return raw[:-1] + ',"id":"other"}'
        if fault == "duplicate-batch": return raw[:-1] + ',"batch_id":"requested"}'
        if fault == "escaped-duplicate-id": return raw[:-1] + ',"\\u0069d":"one"}'
        return raw
    add_large(ws, data, transform)
    before = sql_rows(ws)
    with pytest.raises(WorkspaceError) as rejected:
        ws.save_source_batch("selected", kind="source", data=[source(), source(local="new")])
    assert rejected.value.code == "conflict" and sql_rows(ws) == before


@pytest.mark.parametrize("identity", ["ordinary", "nul-values", "nul-lookalike-keys"])
def test_requested_oversized_identity_keeps_body_budget_and_never_creates_a_duplicate(ws, identity):
    target = source()
    if identity == "nul-values": target = source(batch="requested\x00suffix", local="one\x00suffix")
    def transform(raw):
        if identity == "nul-lookalike-keys":
            return '{"batch_id\\u0000extra":"other","id\\u0000extra":"other",' + raw[1:]
        return raw
    add_large(ws, target, transform)
    before = sql_rows(ws)
    with pytest.raises(WorkspaceError) as rejected:
        ws.save_source_batch("selected", kind="source", data=[target, source(local="new")])
    assert rejected.value.code == "conflict" and sql_rows(ws) == before


def test_large_legacy_identity_does_not_require_SQLite_JSON_functions(ws, monkeypatch):
    initial = ws.save_source_batch("selected", kind="source", data=[source()])
    add_large(ws, {"title": "Large ordinary source", "locator": "fixture:legacy"})
    original = ws.db
    class NoJSON:
        def __init__(self, connection): self.connection = connection
        def execute(self, statement, parameters=()):
            if "json_" in statement.lower():
                raise sqlite3.OperationalError("Synthetic SQLite build without JSON functions")
            return self.connection.execute(statement, parameters)
    @contextmanager
    def without_JSON(*, write=False):
        with original(write=write) as connection:
            yield NoJSON(connection)
    monkeypatch.setattr(ws, "db", without_JSON)
    before = sql_rows(ws)
    replay = ws.save_source_batch("selected", kind="source", data=[source()])
    assert replay["ok"] and replay["batch"]["records"] == initial["batch"]["records"]
    assert sql_rows(ws) == before

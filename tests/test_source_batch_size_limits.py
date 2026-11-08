"""Synthetic storage-overhead boundaries; no original workspace or providers."""
from copy import deepcopy
import argparse
from contextlib import redirect_stdout
import io
import json
from unittest.mock import patch

import pytest

from research_hub.workspace.core import Workspace, WorkspaceError, encoded
from research_hub.workspace.source_handoff import MAX_PREVIEW_BYTES, preview_source_batch


def size(value):
    return len(encoded(value).encode("utf-8"))


def boundary_batch(count, *, defaults=True):
    rows = [{"batch_id": "synthetic-boundary", "id": f"source-{i}",
             "title": "Synthetic 邊界", "locator": f"fixture:{i}", "padding": ""}
            for i in range(count)]
    if defaults:
        for row in rows:
            row.update(identity_status="unverified", human_acceptance="pending")
    available = MAX_PREVIEW_BYTES - size(rows)
    for index, row in enumerate(rows):
        row["padding"] = "x" * (available // count + (index < available % count))
    assert size(rows) == MAX_PREVIEW_BYTES
    return rows


def sql_rows(ws):
    with ws.db() as db:
        return [tuple(row) for row in db.execute("SELECT id,body FROM records ORDER BY rowid")]


@pytest.mark.parametrize("count", [1, 2])
@pytest.mark.parametrize("defaults", [True, False])
def test_full_input_capacity_first_save_then_exact_retry_keeps_SQL_bytes(tmp_path, count, defaults):
    ws = Workspace(tmp_path)
    ws.create_project(id="selected", title="Synthetic size boundary")
    data = boundary_batch(count, defaults=defaults)
    original = deepcopy(data)
    first = ws.save_source_batch("selected", kind="source", data=data)
    before = sql_rows(ws)
    second = ws.save_source_batch("selected", kind="source", data=data)
    assert first["ok"] and second["ok"]
    assert first["batch"]["counts"] == {"created": count, "reused": 0, "conflicts": 0}
    assert second["batch"]["counts"] == {"created": 0, "reused": count, "conflicts": 0}
    assert first["batch"]["records"] == second["batch"]["records"]
    assert sql_rows(ws) == before and len(before) == count and data == original


@pytest.mark.parametrize("count", [1, 2])
def test_pure_preview_accepts_bounded_outer_wrappers_at_full_input_capacity(count):
    data = boundary_batch(count)
    snapshot = [{"id": f"{i:032x}", "kind": "source", "project_id": "selected", "data": row}
                for i, row in enumerate(data)]
    assert size(snapshot) > MAX_PREVIEW_BYTES
    result = preview_source_batch("selected", kind="source", data=data, existing_records=snapshot)
    assert result["preview"]["counts"] == {"create": 0, "exact-reuse": count, "conflict": 0}


@pytest.mark.parametrize("fault", ["oversized", "nonfinite", "surrogate", "too-many"])
def test_invalid_input_keeps_the_original_input_bound_and_never_opens_storage(tmp_path, fault):
    data = boundary_batch(1)
    if fault == "oversized":
        data[0]["padding"] += "x"
    elif fault == "nonfinite":
        data[0]["padding"] = float("nan")
    elif fault == "surrogate":
        data[0]["padding"] = "\ud800"
    else:
        data = [{}] * 10_001
    root = tmp_path / "must-not-exist"
    with patch.object(Workspace, "db", side_effect=AssertionError("Storage opened")):
        with pytest.raises(WorkspaceError):
            Workspace(root).save_source_batch("selected", kind="source", data=data)
    assert not root.exists()


def test_near_boundary_conflict_blocks_a_mixed_new_record_without_rewriting(tmp_path):
    ws = Workspace(tmp_path)
    ws.create_project(id="selected", title="Synthetic rollback")
    data = boundary_batch(2)
    assert ws.save_source_batch("selected", kind="source", data=data)["ok"]
    before = sql_rows(ws)
    changed = deepcopy(data)
    changed[0]["padding"] = changed[0]["padding"][:-200]
    changed.append({"batch_id": "synthetic-boundary", "id": "new", "title": "New", "locator": "fixture:new"})
    assert size(changed) <= MAX_PREVIEW_BYTES
    result = ws.save_source_batch("selected", kind="source", data=changed)
    assert not result["ok"] and result["code"] == "conflict"
    assert result["batch"]["counts"]["created"] == 0
    assert sql_rows(ws) == before


def test_CLI_snapshot_budget_preserves_full_capacity_preview_without_storage(tmp_path):
    from research_hub.workspace.cli import add_workspace_parsers, dispatch_workspace
    data = boundary_batch(2)
    snapshot = [{"id": f"{i:032x}", "kind": "source", "project_id": "selected", "data": row}
                for i, row in enumerate(data)]
    parser = argparse.ArgumentParser()
    add_workspace_parsers(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(["project", "record", "--root", str(tmp_path / "unused"),
        "--project", "selected", "--kind", "source", "--dry-run", "--batch",
        "--data", encoded(data), "--existing-records", encoded(snapshot)])
    out = io.StringIO()
    with patch("research_hub.workspace.cli.call_workspace", side_effect=AssertionError("Storage opened")), redirect_stdout(out):
        assert dispatch_workspace(args) == 0
    assert json.loads(out.getvalue())["preview"]["counts"]["exact-reuse"] == 2
    assert not (tmp_path / "unused").exists()


@pytest.mark.parametrize("kind", ["stored-row", "snapshot"])
@pytest.mark.parametrize("fault", ["over-budget", "duplicate-keys", "nonfinite", "wrong-shape"])
def test_storage_allowances_remain_finite_and_strict(kind, fault):
    from research_hub.workspace.source_handoff import (parse_stored_source_data, parse_preview_snapshot,
        MAX_SOURCE_RECORD_BYTES, MAX_SOURCE_SNAPSHOT_BYTES)
    parse = parse_stored_source_data if kind == "stored-row" else parse_preview_snapshot
    limit = MAX_SOURCE_RECORD_BYTES if kind == "stored-row" else MAX_SOURCE_SNAPSHOT_BYTES
    if fault == "over-budget":
        raw = encoded({"padding": "x" * limit}) if kind == "stored-row" else encoded(["x" * limit])
    elif fault == "duplicate-keys":
        raw = '{"id":"one","id":"two"}'
        if kind == "snapshot":
            raw = "[" + raw + "]"
    elif fault == "nonfinite":
        raw = '{"x":NaN}' if kind == "stored-row" else "[NaN]"
    else:
        raw = "[]" if kind == "stored-row" else "{}"
    with pytest.raises(WorkspaceError):
        parse(raw)


def test_snapshot_allowance_keeps_the_original_item_count_limit():
    from research_hub.workspace.source_handoff import parse_preview_snapshot, MAX_PREVIEW_ITEMS
    with pytest.raises(WorkspaceError):
        parse_preview_snapshot(encoded([{}] * (MAX_PREVIEW_ITEMS + 1)))


def test_legacy_matching_snapshot_is_bounded_during_collection_before_planning(tmp_path):
    ws = Workspace(tmp_path)
    ws.create_project(id="selected", title="Synthetic legacy snapshot")
    # Ordinary legacy writes have their own contract. Two individually supported
    # rows exceed the bounded aggregate snapshot and must not reach the planner.
    for index in range(2):
        row = boundary_batch(1)[0]
        row["id"] = f"legacy-{index}"
        row["padding"] = row["padding"][:-20]
        ws.add_record("selected", kind="source", data=row)
    before = sql_rows(ws)
    incoming = [{"batch_id": "synthetic-boundary", "id": f"legacy-{i}",
                 "title": "Synthetic 邊界", "locator": "fixture:0"} for i in range(2)]
    with patch("research_hub.workspace.source_handoff.plan_stored_source_batch", side_effect=AssertionError("Oversized snapshot reached planner")):
        with pytest.raises(WorkspaceError) as rejected:
            ws.save_source_batch("selected", kind="source", data=incoming)
    assert rejected.value.code == "conflict"
    assert "snapshot exceeds" in str(rejected.value)
    assert sql_rows(ws) == before

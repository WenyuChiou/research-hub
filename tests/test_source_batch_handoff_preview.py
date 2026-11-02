"""Pure native batch plans through the official CLI, without any write route."""

import argparse
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from unittest.mock import patch

import pytest

from research_hub.workspace.cli import add_workspace_parsers, dispatch_workspace


@pytest.fixture(autouse=True)
def no_preview_access():
    with (
        patch("research_hub.workspace.cli.call_workspace", side_effect=AssertionError("Service forbidden")),
        patch("research_hub.workspace.cli.WorkspaceService", side_effect=AssertionError("Constructor forbidden")),
        patch("research_hub.workspace.core.Workspace", side_effect=AssertionError("Workspace forbidden")),
        patch("research_hub.workspace.core.sqlite3.connect", side_effect=AssertionError("SQLite forbidden")),
        patch("research_hub.config.get_config", side_effect=AssertionError("Config forbidden")),
        patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")),
        patch("socket.create_connection", side_effect=AssertionError("Network forbidden")),
    ):
        yield


def sources():
    return [{"id": f"source-{i}", "batch_id": "synthetic-batch", "title": f"Synthetic {i}",
             "locator": f"https://example.invalid/{i}", "reading_level": "abstract-snippet" if i == 19 else "abstract",
             "reading_scope": "abstract-snippet" if i == 19 else "abstract", "version": None,
             "identity_status": "unverified", "human_acceptance": "pending",
             "relevance": "Relevance is not a summary", "prior_batch_matches": []} for i in range(20)]


def snapshot(data):
    return [{"id": f"hub-{i}", "kind": "source", "project_id": "synthetic-project", "data": deepcopy(row)}
            for i, row in enumerate(data)]


def invoke(root, data, *, existing=None, extra=(), raw=False):
    parser = argparse.ArgumentParser()
    add_workspace_parsers(parser.add_subparsers(dest="command", required=True))
    argv = ["project", "record", "--root", str(root), "--project", "synthetic-project", "--kind", "source",
            "--data", data if raw else json.dumps(data), *extra]
    if existing is not None:
        argv.extend(["--existing-records", json.dumps(existing)])
    args = parser.parse_args(argv)
    out = io.StringIO()
    with redirect_stdout(out):
        rc = dispatch_workspace(args)
    return rc, json.loads(out.getvalue())


def test_twenty_create_then_exact_reuse_has_no_io(tmp_path):
    data = sources()
    before = deepcopy(data)
    root = tmp_path / "never-opened"
    with (
        patch("research_hub.workspace.cli.call_workspace", side_effect=AssertionError("Service forbidden")),
        patch("research_hub.workspace.cli.WorkspaceService", side_effect=AssertionError("Constructor forbidden")),
        patch("research_hub.workspace.core.sqlite3.connect", side_effect=AssertionError("SQLite forbidden")),
        patch("research_hub.config.get_config", side_effect=AssertionError("Config forbidden")),
        patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")),
        patch("socket.create_connection", side_effect=AssertionError("Network forbidden")),
    ):
        rc, result = invoke(root, data, extra=["--dry-run", "--batch"])
        assert rc == 0 and result["ok"]
        assert result["preview"]["counts"] == {"create": 20, "exact-reuse": 0, "conflict": 0}
        assert all(p["record_id"] is None and p["data"] == data[i] for i, p in enumerate(result["preview"]["plans"]))
        rc, reused = invoke(root, data, existing=snapshot(data), extra=["--dry-run", "--batch"])
        assert rc == 0 and reused["preview"]["counts"] == {"create": 0, "exact-reuse": 20, "conflict": 0}
        assert [p["record_id"] for p in reused["preview"]["plans"]] == [f"hub-{i}" for i in range(20)]
        assert reused["preview"]["persisted"] is False and reused["preview"]["execution_authorized"] is False
        assert reused["preview"]["snapshot_verified"] is False and reused["preview"]["project_verified"] is False
    assert data == before and not root.exists()


@pytest.mark.parametrize("field,replacement", [
    ("summary", "Incoming generated prose"), ("version", "another-version"),
    ("source_records", [{"observation_id": "different", "evidence_level": "generated-summary"}]),
])
def test_changed_content_is_conflict_and_preserves_manual_content(tmp_path, field, replacement):
    saved = sources()[:1]
    saved[0]["summary"] = "Human-saved summary must survive"
    existing = snapshot(saved)
    incoming = deepcopy(saved)
    incoming[0][field] = replacement
    before = deepcopy((incoming, existing))
    rc, result = invoke(tmp_path / "unused", incoming, existing=existing, extra=["--dry-run", "--batch"])
    view = result["preview"]
    assert rc == 0 and view["counts"] == {"create": 0, "exact-reuse": 0, "conflict": 1}
    assert view["plans"][0]["data"] == incoming[0] and view["plans"][0]["record_id"] is None
    assert view["existing_records"] == existing and view["existing_records"][0]["data"]["summary"] == saved[0]["summary"]
    assert view["conflicts"][0]["reason"] == "changed-data"
    assert (incoming, existing) == before


def test_generic_batch_preserves_coverage_history_unknowns_and_missing_summary(tmp_path):
    item = sources()[-1]
    # A stored legacy declaration is preserved, not judged by quick-list policy.
    item["reading_scope"] = "abstract"
    item["source_records"] = [
        {"observation_id": "original-snippet", "evidence_level": "metadata", "source_version": None},
        {"observation_id": "later-generated", "evidence_level": "generated-summary", "version_id": None,
         "text_path": "generated/not-opened.md", "text_sha256": None, "reading_ref": None},
    ]
    item["provenance"] = {"capture": None}
    item["prior_batch_matches"] = [{"batch_id": "prior", "id": "prior-item"}]
    item["role_candidate"] = "classic-pending"
    before = deepcopy(item)
    rc, result = invoke(tmp_path / "unused", [item], extra=["--dry-run", "--batch"])
    assert rc == 0 and result["preview"]["plans"][0]["data"] == before == item
    assert "summary" not in result["preview"]["plans"][0]["data"]
    assert set(result["preview"]["destination_writes"].values()) == {"not-performed"}
    assert not result["preview"]["atomic_reservation"]


def test_comparison_is_canonical_and_manual_summary_can_exactly_reuse(tmp_path):
    item = sources()[0]
    item["summary"] = "Manual prose"
    saved = snapshot([dict(reversed(list(item.items())))])
    rc, result = invoke(tmp_path / "unused", [item], existing=saved, extra=["--dry-run", "--batch"])
    assert rc == 0 and result["preview"]["plans"][0]["disposition"] == "exact-reuse"
    assert result["preview"]["plans"][0]["data"]["summary"] == "Manual prose"


def test_only_exact_batch_and_source_keys_match_not_title_or_locator(tmp_path):
    first = sources()[0]
    second = deepcopy(first)
    second["batch_id"] = "another-batch"
    third = deepcopy(first)
    third["id"] = "different-source"
    rc, result = invoke(tmp_path / "unused", [second, third], existing=snapshot([first]), extra=["--dry-run", "--batch"])
    assert rc == 0 and result["preview"]["counts"] == {"create": 2, "exact-reuse": 0, "conflict": 0}


def test_duplicate_incoming_key_never_proposes_duplicate_creates(tmp_path):
    data = sources()[:1] * 2
    rc, result = invoke(tmp_path / "unused", data, extra=["--dry-run", "--batch"])
    assert rc == 0 and result["preview"]["counts"] == {"create": 0, "exact-reuse": 0, "conflict": 2}
    assert len(result["preview"]["conflicts"]) == 1
    assert result["preview"]["conflicts"][0]["incoming_indices"] == [0, 1]


def test_ambiguous_existing_key_keeps_both_records_as_conflict(tmp_path):
    data = sources()[:1]
    existing = snapshot(data * 2)
    rc, result = invoke(tmp_path / "unused", data, existing=existing, extra=["--dry-run", "--batch"])
    assert rc == 0 and result["preview"]["counts"] == {"create": 0, "exact-reuse": 0, "conflict": 1}
    assert result["preview"]["existing_records"] == existing
    assert result["preview"]["conflicts"][0]["existing_record_indices"] == [0, 1]


@pytest.mark.parametrize("field", ["id", "batch_id", "title", "locator"])
def test_missing_source_identity_or_core_field_rejects_entire_batch(tmp_path, field):
    data = sources()[:2]
    del data[1][field]
    rc, result = invoke(tmp_path / "unused", data, extra=["--dry-run", "--batch"])
    assert rc == 1 and not result["ok"] and "preview" not in result


@pytest.mark.parametrize("change", [
    {"project_id": "another-project"}, {"project_id": None}, {"kind": "question"},
    {"id": ""}, {"id": None}, {"data": None}, {"data": {"title": "PRIVATE"}},
])
def test_malformed_or_unbound_snapshot_cannot_silently_create(tmp_path, change):
    data = sources()[:1]
    existing = snapshot(data)
    existing[0].update(change)
    rc, result = invoke(tmp_path / "unused", data, existing=existing, extra=["--dry-run", "--batch"])
    assert rc == 1 and not result["ok"] and "preview" not in result
    assert "PRIVATE" not in json.dumps(result)


def test_repeated_outer_record_identity_rejects_snapshot(tmp_path):
    data = sources()[:2]
    existing = snapshot(data)
    existing[1]["id"] = existing[0]["id"]
    rc, result = invoke(tmp_path / "unused", data, existing=existing, extra=["--dry-run", "--batch"])
    assert rc == 1 and not result["ok"]


@pytest.mark.parametrize("raw", [
    "{}", "null", '[{"PRIVATE":1,"PRIVATE":2}]', '[{"PRIVATE":NaN}]',
    '[{"PRIVATE":Infinity}]', '[{"PRIVATE":1e400}]', '[{"PRIVATE":"\\ud800"}]', "[",
])
def test_malformed_nonfinite_duplicate_or_invalid_unicode_is_safe(tmp_path, raw):
    rc, result = invoke(tmp_path / "unused", raw, raw=True, extra=["--dry-run", "--batch"])
    assert rc == 1 and not result["ok"] and "PRIVATE" not in json.dumps(result)


def test_oversize_and_entry_bounds_are_processing_limits(tmp_path):
    from research_hub.workspace.source_handoff import MAX_PREVIEW_BYTES, MAX_PREVIEW_ITEMS
    for raw in ('["' + "x" * MAX_PREVIEW_BYTES + '"]', json.dumps([{}] * (MAX_PREVIEW_ITEMS + 1))):
        rc, result = invoke(tmp_path / "unused", raw, raw=True, extra=["--dry-run", "--batch"])
        assert rc == 1 and not result["ok"]


@pytest.mark.parametrize("flags,existing", [
    (["--batch"], None), ([], []), (["--dry-run"], []), (["--batch"], []),
    (["--dry-run", "--batch", "--kind", "question"], None),
])
def test_invalid_flag_combinations_never_reach_write_dispatch(tmp_path, flags, existing):
    rc, result = invoke(tmp_path / "unused", sources(), existing=existing, extra=flags)
    assert rc == 1 and not result["ok"] and not (tmp_path / "unused").exists()


def test_main_cli_routes_batch_before_any_configuration_or_service(tmp_path):
    from research_hub import cli
    out = io.StringIO()
    with patch.object(cli, "get_config", side_effect=AssertionError("Config forbidden")), redirect_stdout(out):
        rc = cli.main(["project", "record", "--root", str(tmp_path / "unused"), "--project", "synthetic-project",
                       "--kind", "source", "--data", json.dumps(sources()), "--dry-run", "--batch", "--json"])
    assert rc == 0 and json.loads(out.getvalue())["preview"]["counts"]["create"] == 20


def test_register_retains_source_owner_argument_without_new_flags(tmp_path):
    parser = argparse.ArgumentParser()
    add_workspace_parsers(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(["project", "register", "--root", str(tmp_path), "--project", "synthetic-project",
                              "--path", "synthetic.md", "--role", "evidence", "--source-record-id", "hub-owner"])
    with patch("research_hub.workspace.cli.call_workspace", return_value={"ok": True}) as dispatch:
        assert dispatch_workspace(args) == 0
    dispatch.assert_called_once_with(str(tmp_path), "project", "register",
                                     {"project_id": "synthetic-project", "path": "synthetic.md", "role": "evidence",
                                      "source_record_id": "hub-owner"}, proof=None)
